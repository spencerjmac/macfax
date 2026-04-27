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

from ncaa.models import Game, NationalAverages, Team, TeamGameStats

# Mirror production constants exactly
CONVERGENCE = 0.001
MAX_ITERATIONS = 50        # 50 instead of 75 for speed; almost always converges earlier
RECENCY_LAMBDA = 0.0040
IMP_C = 40.0
IMP_FLOOR = 0.35
CLOSE_M = 12.0
BOOST_MAX = 1.40
FREEZE_ITERATION = 6


# ─── helper: recency weights relative to a given reference date ──────────── #

def _time_weights(train_stats, game_dates, ref_date):
    """
    Compute per-game recency weights and per-team rescale factors,
    both anchored to `ref_date` (the cutoff) rather than today.
    Mirrors the production command's recency prep exactly.
    """
    gtw = {
        gs.game_id: math.exp(-RECENCY_LAMBDA * max(0, (ref_date - game_dates[gs.game_id]).days))
        for gs in train_stats
    }

    sum_p: defaultdict = defaultdict(float)
    sum_pw: defaultdict = defaultdict(float)
    for gs in train_stats:
        p = gs.poss_team
        if not p or p <= 0:
            continue
        sum_p[gs.team_id] += p
        sum_pw[gs.team_id] += p * gtw.get(gs.game_id, 1.0)

    tts = {
        tid: (sum_p[tid] / sum_pw[tid]) if sum_pw[tid] > 0 else 1.0
        for tid in sum_p
    }
    return gtw, tts


# ─── helper: run iterative adjusted ratings in memory ────────────────────── #

def _run_ratings(by_team_train, train_stats, stats_lookup,
                 team_ids, nat_avg, gtw, tts, k):
    """
    Iterative opponent-adjusted rating computation identical to
    compute_adjusted_ratings, but fully in-memory.

    Returns {team_id: {"aor": float, "adr": float, "pace": float}}
    """
    ratings = {
        tid: {"aor": nat_avg.avg_ortg, "adr": nat_avg.avg_ortg, "pace": nat_avg.avg_pace}
        for tid in team_ids
    }
    frozen_imp: dict = {}
    imp_scale: dict = {}

    for iteration in range(1, MAX_ITERATIONS + 1):
        cur_imp: dict = {}
        new_r: dict = {}
        max_change = 0.0

        for tid in team_ids:
            sw_aor = sw_adr = sw_pace = sw = 0.0

            for gs in by_team_train.get(tid, []):
                poss_g = gs.poss_team
                if not poss_g or poss_g <= 0:
                    continue
                opp_id = gs.opponent_id
                if opp_id not in ratings:
                    continue
                opp_st = stats_lookup.get((gs.game_id, opp_id))
                if not opp_st:
                    continue

                minutes = gs.game_minutes or 40
                raw_oe = 100 * gs.pts / poss_g
                raw_de = 100 * opp_st.pts / poss_g
                raw_pace = 40 * poss_g / minutes

                opp_aor = ratings[opp_id]["aor"]
                opp_adr = ratings[opp_id]["adr"]
                opp_pace = ratings[opp_id]["pace"]

                aor_g = raw_oe * (nat_avg.avg_ortg / opp_adr) * gs.site_factor if opp_adr > 0 else raw_oe
                adr_g = raw_de * (nat_avg.avg_ortg / opp_aor) * gs.defensive_site_factor if opp_aor > 0 else raw_de
                blend = (opp_pace + nat_avg.avg_pace) / 2
                pace_g = raw_pace * (nat_avg.avg_pace / blend) if blend > 0 else raw_pace

                w_time = gtw.get(gs.game_id, 1.0) * tts.get(tid, 1.0)

                imp_key = (tid, gs.game_id)
                if iteration <= FREEZE_ITERATION:
                    t_aem = ratings[tid]["aor"] - ratings[tid]["adr"]
                    o_aem = opp_aor - opp_adr
                    gap = abs(t_aem - o_aem)
                    base = max(IMP_FLOOR, 1.0 / (1.0 + (gap / IMP_C) ** 2))
                    closer = max(0.0, abs(t_aem - o_aem) - abs(aor_g - adr_g))
                    cf = 1.0 - math.exp(-closer / CLOSE_M)
                    w_imp = min(1.0, base * (1.0 + (BOOST_MAX - 1.0) * cf))
                    cur_imp[imp_key] = w_imp
                else:
                    w_imp = frozen_imp.get(imp_key, 1.0)

                wt = poss_g * w_time * w_imp * imp_scale.get(tid, 1.0)
                sw_aor += wt * aor_g
                sw_adr += wt * adr_g
                sw_pace += wt * pace_g
                sw += wt

            if sw > 0:
                aor_s = (sw_aor + k * nat_avg.avg_ortg) / (sw + k)
                adr_s = (sw_adr + k * nat_avg.avg_ortg) / (sw + k)
                pace_s = (sw_pace + k * nat_avg.avg_pace) / (sw + k)
            else:
                aor_s = adr_s = nat_avg.avg_ortg
                pace_s = nat_avg.avg_pace

            old_aem = ratings[tid]["aor"] - ratings[tid]["adr"]
            new_aem = aor_s - adr_s
            max_change = max(max_change, abs(new_aem - old_aem))
            new_r[tid] = {"aor": aor_s, "adr": adr_s, "pace": pace_s}

        if iteration == FREEZE_ITERATION:
            frozen_imp = dict(cur_imp)
            sb: defaultdict = defaultdict(float)
            si: defaultdict = defaultdict(float)
            for gs in train_stats:
                p = gs.poss_team
                if not p or p <= 0:
                    continue
                wt = gtw.get(gs.game_id, 1.0) * tts.get(gs.team_id, 1.0)
                wi = frozen_imp.get((gs.team_id, gs.game_id), 1.0)
                sb[gs.team_id] += p * wt
                si[gs.team_id] += p * wt * wi
            imp_scale = {
                t: max(0.85, min(1.30, (sb[t] / si[t]) if si[t] > 0 else 1.0))
                for t in sb
            }

        ratings = new_r
        if max_change < CONVERGENCE:
            break

    return ratings


# ─── helper: predicted margin (home perspective) ─────────────────────────── #

def _predict_margin(home_r, away_r, nat_avg, neutral_site):
    """
    Multiplicative efficiency model — identical to matchup_engine.forecast_game().
    Returns predicted margin from the home team's perspective.
    """
    hp, ap = home_r["pace"], away_r["pace"]
    pace = (2 * hp * ap) / (hp + ap) if hp > 0 and ap > 0 else nat_avg.avg_pace

    exp_oe_home = (home_r["aor"] * away_r["adr"]) / nat_avg.avg_ortg
    exp_oe_away = (away_r["aor"] * home_r["adr"]) / nat_avg.avg_ortg

    pts_home = exp_oe_home * (pace / 100)
    pts_away = exp_oe_away * (pace / 100)

    hca = nat_avg.hca_points or 3.20
    if not neutral_site:
        pts_home += hca / 2
        pts_away -= hca / 2

    return pts_home - pts_away


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
            gtw, tts = _time_weights(train_stats, game_dates, cutoff)

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
                ratings = _run_ratings(
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

                    pred = _predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
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

                    pred_margin = _predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
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
