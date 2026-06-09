"""
Backtest: evaluate game-pace adjustment (performing better/worse in faster or slower games).

For each weekly cutoff, trains standard AdjEM ratings on games before the cutoff,
computes per-team pace-sensitivity slopes via OLS residual regression, then scores
both baseline and slope-adjusted predictions on the following test window.

The pace slope captures whether a team systematically over/under-performs vs
expectation as a function of game pace (possessions per 40 min). Positive slope
→ plays better in up-tempo games; negative slope → performs better in slower games.

Both teams in a game face the same pace, so the prediction adjustment is:
    margin_adj = (home_slope - away_slope) × pace_dev

where pace_dev = expected_game_pace - nat_avg_pace.

This is structurally different from opponent-adjust where each team faces a unique
opponent strength. Here the effect is additive on the difference of slopes because
the pace deviation applies symmetrically to both sides.

Note per Evan Miya: pace adjustments are generally less predictive of future success
than opponent-quality adjustments. A small but consistent improvement vs baseline is
sufficient evidence to proceed.

Usage:
    python manage.py backtest_pace_adjust --season 2026
    python manage.py backtest_pace_adjust --season 2026 --slope-k 5 10 20 40
    python manage.py backtest_pace_adjust --season 2026 --k 170 --min-games 6
    python manage.py backtest_pace_adjust --season 2026 --start 2026-01-01
    python manage.py backtest_pace_adjust --season 2026 --seasons 2022 2023 2024 2025 2026
"""

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from scipy import stats as scipy_stats

from django.core.management.base import BaseCommand

from ncaa.models import Game, NationalAverages, Team, TeamGameStats

# Mirror production constants exactly (same as backtest_opponent_adjust.py)
CONVERGENCE = 0.001
MAX_ITERATIONS = 50
RECENCY_LAMBDA = 0.0040
IMP_C = 40.0
IMP_FLOOR = 0.35
CLOSE_M = 12.0
BOOST_MAX = 1.40
FREEZE_ITERATION = 6


# ─── helpers (identical to backtest_opponent_adjust.py) ──────────────────── #

def _time_weights(train_stats, game_dates, ref_date):
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


def _run_ratings(by_team_train, train_stats, stats_lookup, team_ids, nat_avg, gtw, tts, k):
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


def _predict_margin(home_r, away_r, nat_avg, neutral_site):
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


def _game_pace(home_r, away_r, nat_avg):
    """Return expected game pace (harmonic mean of team tempos)."""
    hp, ap = home_r["pace"], away_r["pace"]
    return (2 * hp * ap) / (hp + ap) if hp > 0 and ap > 0 else nat_avg.avg_pace


# ─── pace-sensitivity slope computation ──────────────────────────────────── #

def _compute_pace_slopes(train_stats, stats_lookup, ratings, nat_avg, slope_k, min_games):
    """
    Per-team OLS slope of residuals on pace deviation from the national average.

        residual_i = actual_team_margin_i - predicted_team_margin_i
        pace_dev_i = game_pace_i - nat_avg_pace

    where game_pace_i is the harmonic mean of the two teams' adj_tempo at the
    current cutoff (the same formula used in forecast_game / _predict_margin).

    Positive slope → team performs above expectation in faster games (up-tempo).
    Negative slope → team performs above expectation in slower games.

    Prediction adjustment (applied at prediction time):
        margin_adj = (home_slope - away_slope) × pace_dev_pred

    This differs from opponent-adjust where each team faces a unique opponent
    strength. Here both teams see the same game pace, so the net effect on the
    home margin is (home_team_benefit - away_team_benefit) × shared_pace_dev.

    Returns {team_id: shrunk_slope}
    """
    team_data: defaultdict = defaultdict(list)  # tid -> [(pace_dev, residual)]
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

        home_r = ratings[home_id]
        away_r = ratings[away_id]

        pred_home = _predict_margin(home_r, away_r, nat_avg, gs.game.neutral_site)

        # Actual margin from home team's perspective
        if is_home:
            actual_home = gs.pts - opp_st.pts
        else:
            actual_home = opp_st.pts - gs.pts

        residual_home = actual_home - pred_home

        # From tid's perspective: flip sign if team was away
        residual_tid = residual_home if is_home else -residual_home

        # Pace deviation: how much faster/slower than average was this game?
        game_pace = _game_pace(home_r, away_r, nat_avg)
        pace_dev = game_pace - nat_avg.avg_pace

        team_data[tid].append((pace_dev, residual_tid))

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
    help = "Backtest game-pace adjustment (performing better/worse in faster or slower games)"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, default=None)
        parser.add_argument(
            "--seasons", type=int, nargs="+", default=None,
            help="Run multiple seasons in sequence (e.g. --seasons 2022 2023 2024 2025 2026)",
        )
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
        seasons = options["seasons"] or ([options["season"]] if options["season"] else None)
        if not seasons:
            self.stderr.write("Provide --season YEAR or --seasons YEAR [YEAR ...]")
            return

        for season_year in seasons:
            self._run_season(season_year, options)

    def _run_season(self, season_year, options):
        ratings_k = options["k"]
        slope_ks = options["slope_k"]
        min_games = options["min_games"]
        step = options["step"]
        window = options["window"]

        W = 82
        self.stdout.write("\n" + "=" * W)
        self.stdout.write(f"PACE ADJUST BACKTEST — season {season_year}  (ratings k={ratings_k:.0f})")
        self.stdout.write("=" * W)

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
            self.stderr.write(f"No games found for {season_year}.")
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
            f"min_games={min_games}  nat_avg_pace={nat_avg.avg_pace:.1f}\n"
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

            gtw, tts = _time_weights(train_stats, game_dates, cutoff)

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
            ratings = _run_ratings(
                by_team_train, train_stats, stats_lookup,
                team_ids, nat_avg, gtw, tts, ratings_k,
            )

            # Compute pace slopes for each slope_k
            slopes_by_sk = {
                sk: _compute_pace_slopes(
                    train_stats, stats_lookup, ratings, nat_avg, sk, min_games
                )
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

                    pred = _predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                    if slopes:
                        pace_dev = _game_pace(home_r, away_r, nat_avg) - nat_avg.avg_pace
                        pred += (
                            slopes.get(g["home_team_id"], 0.0)
                            - slopes.get(g["away_team_id"], 0.0)
                        ) * pace_dev

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

                    pred = _predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                    if slopes:
                        pace_dev = _game_pace(home_r, away_r, nat_avg) - nat_avg.avg_pace
                        pred += (
                            slopes.get(g["home_team_id"], 0.0)
                            - slopes.get(g["away_team_id"], 0.0)
                        ) * pace_dev

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
        self.stdout.write("\n" + "=" * W)
        self.stdout.write(f"RESULTS — season {season_year}  (ratings k={ratings_k:.0f})")
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
            self.stdout.write(f"\nPACE SLOPES  (slope_k={int(sk0)}, end-of-season)")
            self.stdout.write(
                f"  nat_avg_pace={nat_avg.avg_pace:.1f} poss/40min  "
                f"(positive = better in faster games, negative = better in slower games)"
            )
            ranked = sorted(
                [(tid, sl) for tid, sl in last_slopes.items() if sl != 0.0],
                key=lambda x: x[1],
            )
            top10 = ranked[-10:][::-1]
            bot10 = ranked[:10]

            self.stdout.write("\n  Top 10 — plays BETTER in faster games (positive slope):")
            self.stdout.write(f"  {'rank':<5}  {'slope':>7}  team")
            for rank, (tid, sl) in enumerate(top10, 1):
                self.stdout.write(f"  {rank:<5}  {sl:>+7.3f}  {team_names.get(tid, str(tid))}")

            self.stdout.write("\n  Bottom 10 — plays BETTER in slower games (negative slope):")
            self.stdout.write(f"  {'rank':<5}  {'slope':>7}  team")
            for rank, (tid, sl) in enumerate(bot10, 1):
                self.stdout.write(f"  {rank:<5}  {sl:>+7.3f}  {team_names.get(tid, str(tid))}")

        # Pace deviation distribution diagnostic
        self.stdout.write(f"\nPACE DEVIATION DISTRIBUTION  (training games, season {season_year})")
        all_devs = []
        for gs in all_stats:
            tid = gs.team_id
            opp_id = gs.opponent_id
            if tid not in {gs2.team_id for gs2 in all_stats} or opp_id not in {gs2.team_id for gs2 in all_stats}:
                continue
            # We don't have final ratings here (end-of-season), just use raw pace as proxy
            minutes = gs.game_minutes or 40
            if gs.poss_team and gs.poss_team > 0:
                raw_pace = 40 * gs.poss_team / minutes
                all_devs.append(raw_pace - nat_avg.avg_pace)
        if all_devs:
            all_devs.sort()
            n = len(all_devs)
            p10 = all_devs[int(0.10 * n)]
            p25 = all_devs[int(0.25 * n)]
            p75 = all_devs[int(0.75 * n)]
            p90 = all_devs[int(0.90 * n)]
            mean_dev = sum(all_devs) / n
            self.stdout.write(
                f"  n={n:,}  mean_dev={mean_dev:+.2f}  "
                f"p10={p10:+.2f}  p25={p25:+.2f}  p75={p75:+.2f}  p90={p90:+.2f}"
            )

        self.stdout.write("")
