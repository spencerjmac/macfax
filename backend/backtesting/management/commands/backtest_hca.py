"""
Backtest: evaluate prediction-layer HCA values against out-of-sample accuracy.

Holds all other parameters fixed (k=150, same recency/importance constants as
backtest_shrinkage) and sweeps a grid of hca_points values.

Primary metric   : absolute bias as close to 0.000 as possible
Secondary metric : spread MAE
Tertiary metrics : win-prob log-loss / Brier score

Usage:
    python manage.py backtest_hca --season 2026
    python manage.py backtest_hca --season 2026 --hca-vals 1.7 2.2 2.7 3.2 3.45
    python manage.py backtest_hca --season 2026 --k 150
"""

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from scipy import stats as scipy_stats

from django.core.management.base import BaseCommand

from backtesting.rating_replay import predict_margin, run_ratings, time_weights
from ncaa.models import Game, NationalAverages, Team, TeamGameStats


# ── management command ─────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Backtest prediction-layer HCA values (spread bias + MAE + win-prob)"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--hca-vals",
            type=float,
            nargs="+",
            default=None,
            help=(
                "HCA point values to test. "
                "Default: current − 0.5, current, +0.25, +0.50, +0.75, +1.00, +1.25"
            ),
        )
        parser.add_argument(
            "--k",
            type=float,
            default=150.0,
            help="Fixed shrinkage k to use throughout (default: 150)",
        )
        parser.add_argument("--start", type=str, default=None,
                            help="First cutoff date YYYY-MM-DD")
        parser.add_argument("--end", type=str, default=None,
                            help="Last cutoff date YYYY-MM-DD")
        parser.add_argument("--step", type=int, default=7,
                            help="Days between cutoffs (default: 7)")
        parser.add_argument("--window", type=int, default=7,
                            help="Test window in days after each cutoff (default: 7)")

    def handle(self, *args, **options):
        season_year = options["season"]
        k = options["k"]
        step = options["step"]
        window = options["window"]

        nat_avg = NationalAverages.objects.get(season__year=season_year)
        sigma = nat_avg.prediction_sigma or 11.08
        cur_hca = nat_avg.hca_points or 3.20
        EPS = 1e-9

        # Build default HCA grid around the stored value
        if options["hca_vals"] is None:
            hca_values = [
                round(cur_hca - 0.50, 4),
                round(cur_hca,        4),
                round(cur_hca + 0.25, 4),
                round(cur_hca + 0.50, 4),
                round(cur_hca + 0.75, 4),
                round(cur_hca + 1.00, 4),
                round(cur_hca + 1.25, 4),
            ]
        else:
            hca_values = options["hca_vals"]

        # ── Load all data once ───────────────────────────────────────────── #
        self.stdout.write(f"Loading data...  (k={k:.0f}, σ={sigma:.3f}, cur_hca={cur_hca:.4f})")

        all_stats = list(
            TeamGameStats.objects.filter(
                game__season_year=season_year,
                game__status="final",
                team__is_d1=True,
                opponent__is_d1=True,
            ).select_related("game", "opponent", "team")
        )
        self.stdout.write(f"  {len(all_stats)} team-game stats loaded")

        all_game_ids = list({gs.game_id for gs in all_stats})
        stats_lookup = {
            (gs.game_id, gs.team_id): gs
            for gs in TeamGameStats.objects.filter(
                game_id__in=all_game_ids
            ).select_related("team")
        }

        game_dates = {gs.game_id: gs.game.game_date for gs in all_stats}

        all_d1_games = list(
            Game.objects.filter(
                season_year=season_year,
                status="final",
                home_team__is_d1=True,
                away_team__is_d1=True,
                home_score__isnull=False,
                away_score__isnull=False,
                neutral_site=False,      # neutral games excluded from HCA test
            ).values(
                "id", "game_date", "home_team_id", "away_team_id",
                "home_score", "away_score", "neutral_site", "went_to_ot",
            )
        )
        # Also load neutral-site games for the win-prob table (neutral still
        # uses HCA=0 regardless of what we're testing, so they don't affect
        # the bias comparison but are fair game for probability accuracy)
        all_d1_games_wp = list(
            Game.objects.filter(
                season_year=season_year,
                status="final",
                home_team__is_d1=True,
                away_team__is_d1=True,
                home_score__isnull=False,
                away_score__isnull=False,
            ).values(
                "id", "game_date", "home_team_id", "away_team_id",
                "home_score", "away_score", "neutral_site", "went_to_ot",
            )
        )

        self.stdout.write(
            f"  {len(all_d1_games)} non-neutral D1vD1 games (spread/bias)  |  "
            f"{len(all_d1_games_wp)} total D1vD1 games (win-prob)"
        )

        team_ids = [t.id for t in Team.objects.filter(is_d1=True)]

        # ── Build cutoff schedule ─────────────────────────────────────────── #
        all_dates = sorted(game_dates.values())
        if not all_dates:
            self.stderr.write("No games found.")
            return

        start_cutoff = (
            date.fromisoformat(options["start"])
            if options["start"]
            else all_dates[0] + timedelta(days=14)
        )
        end_cutoff = (
            date.fromisoformat(options["end"])
            if options["end"]
            else all_dates[-1] - timedelta(days=window)
        )

        cutoffs = []
        c = start_cutoff
        while c <= end_cutoff:
            cutoffs.append(c)
            c += timedelta(days=step)

        self.stdout.write(
            f"  {len(cutoffs)} cutoffs: {cutoffs[0]} → {cutoffs[-1]}  "
            f"(step={step}d, window={window}d)"
        )
        self.stdout.write(f"  HCA values tested: {[round(h, 4) for h in hca_values]}\n")

        # ── Result accumulators ───────────────────────────────────────────── #
        acc = {
            h: {
                "spread_ae":  [],
                "spread_se":  [],
                "spread_err": [],   # signed error → bias
                "brier":      [],
                "logloss":    [],
                "correct":    [],
                "per_cutoff": {},
            }
            for h in hca_values
        }

        # ── Main loop ─────────────────────────────────────────────────────── #
        for ci, cutoff in enumerate(cutoffs):
            wend = cutoff + timedelta(days=window)

            train_stats = [gs for gs in all_stats if game_dates[gs.game_id] < cutoff]
            if len(train_stats) < 20:
                self.stdout.write(
                    f"  [{ci+1:2d}/{len(cutoffs)}] {cutoff}  "
                    f"skip (only {len(train_stats)} train rows)"
                )
                continue

            by_team_train: defaultdict = defaultdict(list)
            for gs in train_stats:
                by_team_train[gs.team_id].append(gs)

            gtw, tts = time_weights(train_stats, game_dates, cutoff)

            spread_games = [
                g for g in all_d1_games
                if cutoff <= g["game_date"] < wend and not g["went_to_ot"]
            ]
            wp_games = [
                g for g in all_d1_games_wp
                if cutoff <= g["game_date"] < wend
            ]

            self.stdout.write(
                f"  [{ci+1:2d}/{len(cutoffs)}] {cutoff}  "
                f"train={len(train_stats):5d}  "
                f"spread_test={len(spread_games):3d}  wp_test={len(wp_games):3d}",
                ending="",
            )

            # Ratings are independent of HCA — compute once per cutoff
            ratings = run_ratings(
                by_team_train, train_stats, stats_lookup,
                team_ids, nat_avg, gtw, tts, k,
            )

            for h in hca_values:
                pc = {"n_s": 0, "ae_sum": 0.0, "se_sum": 0.0, "err_sum": 0.0,
                      "n_w": 0, "brier_sum": 0.0}

                for g in spread_games:
                    home_r = ratings.get(g["home_team_id"])
                    away_r = ratings.get(g["away_team_id"])
                    if not home_r or not away_r:
                        continue

                    pred = predict_margin(home_r, away_r, nat_avg, g["neutral_site"], h)
                    actual = g["home_score"] - g["away_score"]
                    err = pred - actual

                    acc[h]["spread_ae"].append(abs(err))
                    acc[h]["spread_se"].append(err ** 2)
                    acc[h]["spread_err"].append(err)
                    pc["n_s"] += 1
                    pc["ae_sum"] += abs(err)
                    pc["se_sum"] += err ** 2
                    pc["err_sum"] += err

                for g in wp_games:
                    home_r = ratings.get(g["home_team_id"])
                    away_r = ratings.get(g["away_team_id"])
                    if not home_r or not away_r:
                        continue

                    pred_margin = predict_margin(
                        home_r, away_r, nat_avg, g["neutral_site"], h
                    )
                    prob_home = scipy_stats.norm.cdf(pred_margin / sigma)
                    prob_home = max(EPS, min(1.0 - EPS, prob_home))

                    y = 1.0 if g["home_score"] > g["away_score"] else 0.0
                    acc[h]["brier"].append((prob_home - y) ** 2)
                    acc[h]["logloss"].append(
                        -(y * math.log(prob_home) + (1 - y) * math.log(1 - prob_home))
                    )
                    acc[h]["correct"].append(1 if (prob_home >= 0.5) == (y >= 0.5) else 0)
                    pc["n_w"] += 1
                    pc["brier_sum"] += (prob_home - y) ** 2

                acc[h]["per_cutoff"][cutoff] = pc

            self.stdout.write("")  # newline

        # ── Summary tables ─────────────────────────────────────────────────── #
        W = 76
        self.stdout.write("\n" + "=" * W)
        self.stdout.write(f"BACKTEST RESULTS — season {season_year}  (k={k:.0f}, non-neutral spread games)")
        self.stdout.write("=" * W)

        # Spread / bias table — sorted by |bias| ascending (primary goal)
        rows = []
        for h in hca_values:
            r = acc[h]
            if not r["spread_ae"]:
                continue
            mae  = statistics.fmean(r["spread_ae"])
            rmse = math.sqrt(statistics.fmean(r["spread_se"]))
            bias = statistics.fmean(r["spread_err"])
            rows.append((h, len(r["spread_ae"]), mae, rmse, bias))

        rows_by_bias = sorted(rows, key=lambda x: abs(x[4]))

        self.stdout.write("\nSPREAD ACCURACY  (non-neutral, regulation only) — sorted by |bias|")
        hdr = f"  {'HCA':>6}  {'n':>6}  {'MAE':>8}  {'RMSE':>8}  {'bias':>8}  {'|bias|':>7}"
        self.stdout.write(hdr)
        self.stdout.write("-" * len(hdr))
        baseline_mae = rows[0][2] if rows else 0.0
        for h, n, mae, rmse, bias in rows_by_bias:
            marker = " ◄" if abs(bias) == min(abs(r[4]) for r in rows_by_bias) else ""
            delta_mae = mae - baseline_mae
            self.stdout.write(
                f"  {h:>6.4f}  {n:>6}  {mae:>8.3f}  {rmse:>8.3f}  "
                f"{bias:>+8.3f}  {abs(bias):>7.3f}"
                f"  Δmae={delta_mae:+.3f}{marker}"
            )

        # Win-prob table
        self.stdout.write("\nWIN PROBABILITY ACCURACY  (all D1vD1 incl. OT)")
        hdr2 = f"  {'HCA':>6}  {'n':>6}  {'Brier':>8}  {'LogLoss':>9}  {'Acc%':>6}"
        self.stdout.write(hdr2)
        self.stdout.write("-" * len(hdr2))
        for h in hca_values:
            r = acc[h]
            if not r["brier"]:
                continue
            brier   = statistics.fmean(r["brier"])
            logloss = statistics.fmean(r["logloss"])
            accp    = 100 * statistics.fmean(r["correct"])
            self.stdout.write(
                f"  {h:>6.4f}  {len(r['brier']):>6}  "
                f"{brier:>8.4f}  {logloss:>9.4f}  {accp:>6.1f}"
            )

        # Per-cutoff bias breakdown
        self.stdout.write("\nPER-CUTOFF BIAS  (signed: positive = over-predicting home)")
        hdr3 = f"  {'cutoff':<12}  {'n_reg':>5}"
        for h in hca_values:
            hdr3 += f"  {'hca='+f'{h:.2f}':>9}"
        self.stdout.write(hdr3)
        self.stdout.write("-" * (len(hdr3) + 2))
        for cutoff in cutoffs:
            n_reg = 0
            for h in hca_values:
                pc = acc[h]["per_cutoff"].get(cutoff, {})
                if pc.get("n_s", 0) > 0:
                    n_reg = pc["n_s"]
                    break
            row = f"  {str(cutoff):<12}  {n_reg:>5}"
            for h in hca_values:
                pc = acc[h]["per_cutoff"].get(cutoff, {})
                n_s = pc.get("n_s", 0)
                if n_s > 0:
                    bias_c = pc["err_sum"] / n_s
                    row += f"  {bias_c:>+9.3f}"
                else:
                    row += f"  {'—':>9}"
            self.stdout.write(row)

        # Summary recommendation
        if rows_by_bias:
            best_h, _, best_mae, _, best_bias = rows_by_bias[0]
            self.stdout.write(f"\n{'─'*W}")
            self.stdout.write(
                f"RECOMMENDATION: HCA={best_h:.4f}  "
                f"(bias={best_bias:+.3f}, MAE={best_mae:.3f})"
            )
            self.stdout.write(
                "Stored hca_points is {:.4f}.  "
                "Change: {:+.4f}".format(cur_hca, best_h - cur_hca)
            )
        self.stdout.write("")
