"""
Backtest: evaluate opponent strength adjustment (playing up/down to competition).

For each weekly cutoff, trains standard AdjEM ratings on games before the cutoff,
computes per-team sensitivity slopes via OLS residual regression, then scores
both baseline and slope-adjusted predictions on the following test window.

The slope captures whether a team systematically over/under-performs vs expectation
as a function of opponent quality.  Positive → plays up to tough competition;
negative → pads stats vs weak opponents.  The key fix over the previous NBA attempt:
residuals are computed against the converged *prediction* (not against a circular
re-use of opponent-adjusted net), and the prediction adjustment is a clean additive
formula derived from the slope interpretation.

Usage:
    python manage.py backtest_opponent_adjust --season 2026
    python manage.py backtest_opponent_adjust --season 2026 --slope-k 5 10 20 40
    python manage.py backtest_opponent_adjust --season 2026 --k 170 --min-games 6
    python manage.py backtest_opponent_adjust --season 2026 --start 2026-01-01
"""

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from scipy import stats as scipy_stats

from django.core.management.base import BaseCommand

from backtesting.rating_replay import predict_margin, run_ratings, time_weights
from ncaa.models import Game, NationalAverages, Team, TeamGameStats


# ─── new: opponent-sensitivity slope computation ─────────────────────────── #

def _compute_slopes(train_stats, stats_lookup, ratings, nat_avg, slope_k, min_games):
    """
    Per-team OLS slope of residuals on mean-centered opponent AEM.

    residual_i = actual_team_margin_i - predicted_team_margin_i

    The predicted margin uses the fully converged ratings, so residuals are
    genuinely out-of-model — no circular dependency on opponent-adjusted values.

    Prediction formula (applied to test games):
        pred_adj = pred_base
                 + home_slope * away_aem
                 - away_slope * home_aem

    Interpretation: home_slope * away_aem > 0 when the home team plays up to
    a strong opponent (positive slope, positive away_aem).

    Returns {team_id: shrunk_slope}
    """
    team_data: defaultdict = defaultdict(list)  # tid -> [(opp_aem, residual)]
    seen: set = set()

    for gs in train_stats:
        key = (gs.game_id, gs.team_id)
        if key in seen:
            continue
        seen.add(key)

        tid = gs.team_id
        opp_id = gs.opponent_id
        if tid not in ratings or opp_id not in ratings:
            continue
        opp_st = stats_lookup.get((gs.game_id, opp_id))
        if not opp_st:
            continue

        is_home = (gs.game.home_team_id == tid)
        home_id = tid if is_home else opp_id
        away_id = opp_id if is_home else tid

        pred_home = predict_margin(
            ratings[home_id], ratings[away_id], nat_avg, gs.game.neutral_site
        )

        # gs.pts - opp_st.pts = team_pts - opp_pts regardless of home/away
        actual_team = gs.pts - opp_st.pts
        pred_team = pred_home if is_home else -pred_home

        residual = actual_team - pred_team
        opp_aem = ratings[opp_id]["aor"] - ratings[opp_id]["adr"]
        team_data[tid].append((opp_aem, residual))

    slopes = {}
    for tid, pairs in team_data.items():
        n = len(pairs)
        if n < min_games:
            slopes[tid] = 0.0
            continue

        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        x_bar = sum(xs) / n
        xc = [x - x_bar for x in xs]

        denom = sum(v * v for v in xc)
        if denom < 1e-9:
            slopes[tid] = 0.0
            continue

        raw_slope = sum(xc[i] * ys[i] for i in range(n)) / denom
        slopes[tid] = raw_slope * n / (n + slope_k)

    return slopes


# ─── management command ──────────────────────────────────────────────────── #

class Command(BaseCommand):
    help = "Backtest opponent strength adjustment (playing up/down to competition)"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--k", type=float, default=170.0,
            help="Ratings shrinkage k (default: 170)",
        )
        parser.add_argument(
            "--slope-k", type=float, nargs="+", default=[5.0, 10.0, 20.0, 40.0],
            help="Slope shrinkage k values to sweep (default: 5 10 20 40)",
        )
        parser.add_argument(
            "--min-games", type=int, default=8,
            help="Min training games required to use a team's slope (default: 8)",
        )
        parser.add_argument("--start", type=str, default=None,
                            help="First cutoff YYYY-MM-DD")
        parser.add_argument("--end", type=str, default=None,
                            help="Last cutoff YYYY-MM-DD")
        parser.add_argument("--step", type=int, default=7,
                            help="Days between cutoffs (default: 7)")
        parser.add_argument("--window", type=int, default=7,
                            help="Test window in days after each cutoff (default: 7)")

    def handle(self, *args, **options):
        season_year = options["season"]
        ratings_k = options["k"]
        slope_ks = options["slope_k"]
        min_games = options["min_games"]
        step = options["step"]
        window = options["window"]

        nat_avg = NationalAverages.objects.get(season__year=season_year)
        sigma = nat_avg.prediction_sigma or 11.08
        EPS = 1e-9

        # ── Load all data once ──────────────────────────────────────────────── #
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

        all_game_ids = list({gs.game_id for gs in all_stats})
        stats_lookup = {
            (gs.game_id, gs.team_id): gs
            for gs in TeamGameStats.objects.filter(game_id__in=all_game_ids).select_related("team")
        }

        game_dates = {gs.game_id: gs.game.game_date for gs in all_stats}
        team_names = {gs.team_id: gs.team.name for gs in all_stats}

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

        # ── Build cutoff schedule ──────────────────────────────────────────── #
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
        self.stdout.write(
            f"  ratings k={ratings_k:.0f}  slope k sweep: {[int(k) for k in slope_ks]}  "
            f"min_games={min_games}\n"
        )

        # ── Result accumulators ────────────────────────────────────────────── #
        label_to_sk = {f"sk={int(sk)}": sk for sk in slope_ks}
        labels = ["base"] + list(label_to_sk.keys())

        acc = {
            lbl: {
                "spread_ae":  [],
                "spread_se":  [],
                "spread_err": [],
                "brier":      [],
                "logloss":    [],
                "correct":    [],
                "per_cutoff": {},
            }
            for lbl in labels
        }

        last_slopes: dict = {}  # tid -> slope at final cutoff (for diagnostic)

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
                g for g in all_d1_games
                if cutoff <= g["game_date"] < wend
            ]

            self.stdout.write(
                f"  [{ci+1:2d}/{len(cutoffs)}] {cutoff}  "
                f"train={len(train_stats):5d} rows  "
                f"spread_test={len(spread_games):3d}  wp_test={len(wp_games):3d}",
                ending="",
            )

            # Compute ratings once per cutoff (shared across all slope_k values)
            ratings = run_ratings(
                by_team_train, train_stats, stats_lookup,
                team_ids, nat_avg, gtw, tts, ratings_k,
            )

            # Compute slopes for each slope_k
            slopes_by_sk = {
                sk: _compute_slopes(train_stats, stats_lookup, ratings, nat_avg, sk, min_games)
                for sk in slope_ks
            }

            # Save last-cutoff slopes for end-of-run diagnostic
            if ci == len(cutoffs) - 1 and slope_ks:
                last_slopes = slopes_by_sk[slope_ks[0]]

            # ── Score test games ───────────────────────────────────────────── #
            for lbl in labels:
                slopes = {} if lbl == "base" else slopes_by_sk[label_to_sk[lbl]]
                pc = {"n_s": 0, "ae_sum": 0.0, "se_sum": 0.0, "n_w": 0, "brier_sum": 0.0}

                for g in spread_games:
                    home_r = ratings.get(g["home_team_id"])
                    away_r = ratings.get(g["away_team_id"])
                    if not home_r or not away_r:
                        continue

                    pred = predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                    if slopes:
                        home_aem = home_r["aor"] - home_r["adr"]
                        away_aem = away_r["aor"] - away_r["adr"]
                        pred += (
                            slopes.get(g["home_team_id"], 0.0) * away_aem
                            - slopes.get(g["away_team_id"], 0.0) * home_aem
                        )

                    actual = g["home_score"] - g["away_score"]
                    err = pred - actual
                    acc[lbl]["spread_ae"].append(abs(err))
                    acc[lbl]["spread_se"].append(err ** 2)
                    acc[lbl]["spread_err"].append(err)
                    pc["n_s"] += 1
                    pc["ae_sum"] += abs(err)
                    pc["se_sum"] += err ** 2

                for g in wp_games:
                    home_r = ratings.get(g["home_team_id"])
                    away_r = ratings.get(g["away_team_id"])
                    if not home_r or not away_r:
                        continue

                    pred = predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                    if slopes:
                        home_aem = home_r["aor"] - home_r["adr"]
                        away_aem = away_r["aor"] - away_r["adr"]
                        pred += (
                            slopes.get(g["home_team_id"], 0.0) * away_aem
                            - slopes.get(g["away_team_id"], 0.0) * home_aem
                        )

                    prob_home = scipy_stats.norm.cdf(pred / sigma)
                    prob_home = max(EPS, min(1.0 - EPS, prob_home))
                    y = 1.0 if g["home_score"] > g["away_score"] else 0.0
                    brier = (prob_home - y) ** 2
                    ll = -(y * math.log(prob_home) + (1 - y) * math.log(1 - prob_home))
                    correct = 1 if (prob_home >= 0.5) == (y >= 0.5) else 0

                    acc[lbl]["brier"].append(brier)
                    acc[lbl]["logloss"].append(ll)
                    acc[lbl]["correct"].append(correct)
                    pc["n_w"] += 1
                    pc["brier_sum"] += brier

                acc[lbl]["per_cutoff"][cutoff] = pc

            self.stdout.write("")  # newline after per-cutoff progress

        # ── Print summary results ──────────────────────────────────────────── #
        W = 80
        self.stdout.write("\n" + "=" * W)
        self.stdout.write(f"BACKTEST RESULTS — season {season_year}  (ratings k={ratings_k:.0f})")
        self.stdout.write("=" * W)

        # Spread accuracy
        self.stdout.write("\nSPREAD ACCURACY  (D1vD1, regulation only)")
        hdr = f"  {'config':<10}  {'n':>6}  {'MAE':>8}  {'RMSE':>8}  {'bias':>8}  {'Δ MAE':>8}"
        self.stdout.write(hdr)
        self.stdout.write("-" * len(hdr))
        base_mae = None
        for lbl in labels:
            r = acc[lbl]
            if not r["spread_ae"]:
                continue
            mae  = statistics.fmean(r["spread_ae"])
            rmse = math.sqrt(statistics.fmean(r["spread_se"]))
            bias = statistics.fmean(r["spread_err"])
            if base_mae is None:
                base_mae = mae
            delta = mae - base_mae
            delta_str = f"{delta:>+8.3f}" if lbl != "base" else f"{'—':>8}"
            self.stdout.write(
                f"  {lbl:<10}  {len(r['spread_ae']):>6}  "
                f"{mae:>8.3f}  {rmse:>8.3f}  {bias:>+8.3f}  {delta_str}"
            )

        # Win-prob accuracy
        self.stdout.write("\nWIN PROBABILITY ACCURACY  (D1vD1, including OT)")
        hdr2 = f"  {'config':<10}  {'n':>6}  {'Brier':>8}  {'LogLoss':>9}  {'Acc%':>6}  {'Δ Brier':>9}"
        self.stdout.write(hdr2)
        self.stdout.write("-" * len(hdr2))
        base_brier = None
        for lbl in labels:
            r = acc[lbl]
            if not r["brier"]:
                continue
            brier   = statistics.fmean(r["brier"])
            logloss = statistics.fmean(r["logloss"])
            accp    = 100 * statistics.fmean(r["correct"])
            if base_brier is None:
                base_brier = brier
            delta = brier - base_brier
            delta_str = f"{delta:>+9.4f}" if lbl != "base" else f"{'—':>9}"
            self.stdout.write(
                f"  {lbl:<10}  {len(r['brier']):>6}  "
                f"{brier:>8.4f}  {logloss:>9.4f}  {accp:>6.1f}  {delta_str}"
            )

        # Per-cutoff spread MAE detail
        self.stdout.write("\nPER-CUTOFF SPREAD MAE")
        hdr3 = f"  {'cutoff':<12}  {'n_reg':>5}"
        for lbl in labels:
            hdr3 += f"  {lbl:>10}"
        self.stdout.write(hdr3)
        self.stdout.write("-" * (len(hdr3) + 2))
        for cutoff in cutoffs:
            n_reg = 0
            for lbl in labels:
                pc = acc[lbl]["per_cutoff"].get(cutoff, {})
                if pc.get("n_s", 0) > 0:
                    n_reg = pc["n_s"]
                    break
            row = f"  {str(cutoff):<12}  {n_reg:>5}"
            for lbl in labels:
                pc = acc[lbl]["per_cutoff"].get(cutoff, {})
                n_s = pc.get("n_s", 0)
                row += f"  {(pc['ae_sum']/n_s):>10.3f}" if n_s > 0 else f"  {'—':>10}"
            self.stdout.write(row)

        # Slope diagnostic (end-of-season slopes, first slope_k)
        if last_slopes and team_names:
            sk0 = slope_ks[0] if slope_ks else None
            self.stdout.write(f"\nOPPONENT ADJUST SLOPES  (slope_k={int(sk0)}, end-of-season)")
            ranked = sorted(
                [(tid, sl) for tid, sl in last_slopes.items() if sl != 0.0],
                key=lambda x: x[1],
            )
            top10 = ranked[-10:][::-1]
            bot10 = ranked[:10]

            self.stdout.write("\n  Top 10 — plays UP to strong competition (positive slope):")
            self.stdout.write(f"  {'rank':<5}  {'slope':>7}  team")
            for rank, (tid, sl) in enumerate(top10, 1):
                self.stdout.write(f"  {rank:<5}  {sl:>+7.3f}  {team_names.get(tid, str(tid))}")

            self.stdout.write("\n  Bottom 10 — pads stats vs weak competition (negative slope):")
            self.stdout.write(f"  {'rank':<5}  {'slope':>7}  team")
            for rank, (tid, sl) in enumerate(bot10, 1):
                self.stdout.write(f"  {rank:<5}  {sl:>+7.3f}  {team_names.get(tid, str(tid))}")

        self.stdout.write("")
