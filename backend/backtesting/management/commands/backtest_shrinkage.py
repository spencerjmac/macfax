"""
Backtest: evaluate Bayesian shrinkage k values against out-of-sample prediction accuracy.

For each weekly cutoff date, trains ratings on games strictly before that date,
then scores predictions on completed games in the following window.

Primary metric : spread MAE / RMSE   (D1 vs D1, regulation only — OT excluded)
Secondary metric: win-prob Brier / LogLoss (D1 vs D1, OT included)

Usage:
    python manage.py backtest_shrinkage --season 2026
    python manage.py backtest_shrinkage --season 2026 --k-vals 170 150 100 0
    python manage.py backtest_shrinkage --season 2026 --k-vals 170 150 100 0 --start 2025-12-01
"""

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from scipy import stats as scipy_stats

from django.core.management.base import BaseCommand

from backtesting.rating_replay import predict_margin, run_ratings, time_weights
from ncaa.models import Game, NationalAverages, Team, TeamGameStats


# ─── management command ──────────────────────────────────────────────────── #

class Command(BaseCommand):
    help = "Backtest Bayesian shrinkage k values (spread MAE + win-prob accuracy)"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--k-vals",
            type=float,
            nargs="+",
            default=[170.0, 150.0, 100.0, 0.0],
            help="Direct k (shrinkage) values to test (default: 170 150 100 0)",
        )
        parser.add_argument(
            "--start",
            type=str,
            default=None,
            help="First cutoff date YYYY-MM-DD (default: earliest game date + 14 days)",
        )
        parser.add_argument(
            "--end",
            type=str,
            default=None,
            help="Last cutoff date YYYY-MM-DD (default: latest game date − window days)",
        )
        parser.add_argument(
            "--step",
            type=int,
            default=7,
            help="Days between cutoffs (default: 7)",
        )
        parser.add_argument(
            "--window",
            type=int,
            default=7,
            help="Test window in days after each cutoff (default: 7)",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        k_values = options["k_vals"]
        step = options["step"]
        window = options["window"]

        nat_avg = NationalAverages.objects.get(season__year=season_year)
        sigma = nat_avg.prediction_sigma or 11.08
        EPS = 1e-9  # log-loss clipping

        # ── Load all data once ─────────────────────────────────────────────── #
        self.stdout.write("Loading data...")

        all_stats = list(
            TeamGameStats.objects.filter(
                game__season_year=season_year,
                game__status="final",
                team__is_d1=True,
                opponent__is_d1=True,
            ).select_related("game", "opponent", "team")
        )
        self.stdout.write(f"  {len(all_stats)} team-game stats loaded")

        # Full-season stats lookup for opponent lookups inside the rating loop
        all_game_ids = list({gs.game_id for gs in all_stats})
        stats_lookup = {
            (gs.game_id, gs.team_id): gs
            for gs in TeamGameStats.objects.filter(game_id__in=all_game_ids).select_related("team")
        }

        # Game date per game_id (fast in-Python filter per cutoff)
        game_dates = {gs.game_id: gs.game.game_date for gs in all_stats}

        # Test games: D1 vs D1, final, scores present — loaded as plain dicts (fast)
        all_d1_games = list(
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
        self.stdout.write(f"  {len(all_d1_games)} D1vD1 final games loaded")

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
        self.stdout.write(f"  k values: {[int(k) for k in k_values]}\n")

        # ── Result accumulators ───────────────────────────────────────────── #
        # spread: regulation only (went_to_ot == False)
        # winprob: all games including OT
        acc = {
            k: {
                "spread_ae":  [],   # |pred - actual|
                "spread_se":  [],   # (pred - actual)^2
                "spread_err": [],   # pred - actual  (for bias)
                "brier":      [],
                "logloss":    [],
                "correct":    [],   # 1 if predicted winner was correct
                "per_cutoff": {},   # cutoff -> {"n_s","mae_s","n_w","brier_w"}
            }
            for k in k_values
        }

        # ── Main loop ─────────────────────────────────────────────────────── #
        for ci, cutoff in enumerate(cutoffs):
            wend = cutoff + timedelta(days=window)

            train_stats = [gs for gs in all_stats if game_dates[gs.game_id] < cutoff]
            if len(train_stats) < 20:
                self.stdout.write(f"  [{ci+1:2d}/{len(cutoffs)}] {cutoff}  skip (only {len(train_stats)} train rows)")
                continue

            by_team_train: defaultdict = defaultdict(list)
            for gs in train_stats:
                by_team_train[gs.team_id].append(gs)

            # Recency weights anchored to this cutoff
            gtw, tts = time_weights(train_stats, game_dates, cutoff)

            # Test game slices
            spread_games = [
                g for g in all_d1_games
                if cutoff <= g["game_date"] < wend and not g["went_to_ot"]
            ]
            wp_games = [
                g for g in all_d1_games
                if cutoff <= g["game_date"] < wend
            ]

            n_s_col = len(spread_games)
            n_w_col = len(wp_games)

            self.stdout.write(
                f"  [{ci+1:2d}/{len(cutoffs)}] {cutoff}  "
                f"train={len(train_stats):5d} rows  "
                f"spread_test={n_s_col:3d}  wp_test={n_w_col:3d}",
                ending="",
            )

            for k in k_values:
                ratings = run_ratings(
                    by_team_train, train_stats, stats_lookup,
                    team_ids, nat_avg, gtw, tts, k,
                )

                pc = {"n_s": 0, "ae_sum": 0.0, "se_sum": 0.0,
                      "n_w": 0, "brier_sum": 0.0}

                # — Spread scoring (no OT) —
                for g in spread_games:
                    home_r = ratings.get(g["home_team_id"])
                    away_r = ratings.get(g["away_team_id"])
                    if not home_r or not away_r:
                        continue

                    pred = predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                    actual = g["home_score"] - g["away_score"]
                    err = pred - actual

                    acc[k]["spread_ae"].append(abs(err))
                    acc[k]["spread_se"].append(err ** 2)
                    acc[k]["spread_err"].append(err)
                    pc["n_s"] += 1
                    pc["ae_sum"] += abs(err)
                    pc["se_sum"] += err ** 2

                # — Win-prob scoring (OT included) —
                for g in wp_games:
                    home_r = ratings.get(g["home_team_id"])
                    away_r = ratings.get(g["away_team_id"])
                    if not home_r or not away_r:
                        continue

                    pred_margin = predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                    prob_home = scipy_stats.norm.cdf(pred_margin / sigma)
                    prob_home = max(EPS, min(1.0 - EPS, prob_home))

                    y = 1.0 if g["home_score"] > g["away_score"] else 0.0
                    brier = (prob_home - y) ** 2
                    ll = -(y * math.log(prob_home) + (1 - y) * math.log(1 - prob_home))
                    correct = 1 if (prob_home >= 0.5) == (y >= 0.5) else 0

                    acc[k]["brier"].append(brier)
                    acc[k]["logloss"].append(ll)
                    acc[k]["correct"].append(correct)
                    pc["n_w"] += 1
                    pc["brier_sum"] += brier

                acc[k]["per_cutoff"][cutoff] = pc

            self.stdout.write("")  # newline

        # ── Print summary results ─────────────────────────────────────────── #
        W = 72
        self.stdout.write("\n" + "=" * W)
        self.stdout.write(f"BACKTEST RESULTS — season {season_year}")
        self.stdout.write("=" * W)

        # Spread table
        self.stdout.write("\nSPREAD ACCURACY  (D1vD1, regulation only)")
        hdr = f"  {'k':>6}  {'n':>6}  {'MAE':>8}  {'RMSE':>8}  {'bias':>8}"
        self.stdout.write(hdr)
        self.stdout.write("-" * len(hdr))
        for k in k_values:
            r = acc[k]
            if not r["spread_ae"]:
                continue
            mae  = statistics.fmean(r["spread_ae"])
            rmse = math.sqrt(statistics.fmean(r["spread_se"]))
            bias = statistics.fmean(r["spread_err"])
            self.stdout.write(
                f"  {k:>6.0f}  {len(r['spread_ae']):>6}  "
                f"{mae:>8.3f}  {rmse:>8.3f}  {bias:>+8.3f}"
            )

        # Win-prob table
        self.stdout.write("\nWIN PROBABILITY ACCURACY  (D1vD1, including OT)")
        hdr2 = f"  {'k':>6}  {'n':>6}  {'Brier':>8}  {'LogLoss':>9}  {'Acc%':>6}"
        self.stdout.write(hdr2)
        self.stdout.write("-" * len(hdr2))
        for k in k_values:
            r = acc[k]
            if not r["brier"]:
                continue
            brier   = statistics.fmean(r["brier"])
            logloss = statistics.fmean(r["logloss"])
            accp    = 100 * statistics.fmean(r["correct"])
            self.stdout.write(
                f"  {k:>6.0f}  {len(r['brier']):>6}  "
                f"{brier:>8.4f}  {logloss:>9.4f}  {accp:>6.1f}"
            )

        # Per-cutoff spread MAE detail
        self.stdout.write("\nPER-CUTOFF SPREAD MAE")
        hdr3 = f"  {'cutoff':<12}  {'n_reg':>5}"
        for k in k_values:
            hdr3 += f"  {'k='+str(int(k)):>8}"
        self.stdout.write(hdr3)
        self.stdout.write("-" * (len(hdr3) + 2))
        for cutoff in cutoffs:
            # n is consistent across k; grab from first k that has data
            n_reg = 0
            for k in k_values:
                pc = acc[k]["per_cutoff"].get(cutoff, {})
                if pc.get("n_s", 0) > 0:
                    n_reg = pc["n_s"]
                    break
            row = f"  {str(cutoff):<12}  {n_reg:>5}"
            for k in k_values:
                pc = acc[k]["per_cutoff"].get(cutoff, {})
                n_s = pc.get("n_s", 0)
                row += f"  {(pc['ae_sum']/n_s):>8.3f}" if n_s > 0 else f"  {'—':>8}"
            self.stdout.write(row)

        self.stdout.write("")
