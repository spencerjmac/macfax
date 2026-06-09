"""
Backtest: evaluate whether a "clutch factor" — per-team conditional mean residuals
in close games — improves out-of-sample prediction accuracy.

The clutch factor is the conditional mean residual for each team in close games:

    raw_clutch = mean(actual_margin_tid - expected_margin_tid | game was "close")

Applied with Bayesian shrinkage:

    clutch_shrunk = raw_clutch * n_close / (n_close + k)

Applied at prediction time (home-margin convention):

    pred_adj = pred_base + (home_clutch - away_clutch)

Key question: Is "clutch team" a real predictive signal in our data, or mostly noise?

Critical context: The production ratings already use CLOSE_M/BOOST_MAX to upweight
games where the observed margin was closer than expected. That means close-game
information is partially baked into AdjEM. This backtest measures whether there is
RESIDUAL signal beyond what importance weighting already captures.

Configurations swept:
  Threshold sweep (k=5):    margin ≤3, ≤5, ≤8, OT-only
  Shrinkage sweep (mg≤5):   k=3, 5, 8, 10, 15
  Apply mode (mg≤5, k=5):   all games vs predicted-close-only

Each config is evaluated on:
  - ALL test games (does clutch improve general predictions?)
  - CLOSE test games only (does it specifically help close-game predictions?)

Usage:
    python manage.py backtest_clutch --season 2026
    python manage.py backtest_clutch --seasons 2022 2023 2024 2025 2026
    python manage.py backtest_clutch --season 2026 --k 170 --min-close-games 2
"""

import collections
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from scipy import stats as scipy_stats

from django.core.management.base import BaseCommand

from ncaa.models import Game, NationalAverages, Team, TeamGameStats

# ── Production constants (mirror backtest_opponent_adjust.py exactly) ────────
CONVERGENCE      = 0.001
MAX_ITERATIONS   = 50
RECENCY_LAMBDA   = 0.0040
IMP_C            = 40.0
IMP_FLOOR        = 0.35
CLOSE_M          = 12.0
BOOST_MAX        = 1.40
FREEZE_ITERATION = 6

# Fixed threshold used when reporting the close-game-only accuracy section
CLOSE_REPORT_THRESHOLD = 5


# ── Config descriptor ─────────────────────────────────────────────────────────

@dataclass
class ClutchConfig:
    label: str
    margin_threshold: float  # abs(final_margin) <= this = "close"  (0 = OT-only)
    include_ot: bool          # OT games always qualify as close
    shrinkage_k: float
    close_only_apply: bool    # if True, only apply adjustment when pred_base is also close


CONFIGS = [
    # ── Threshold sweep (k=5, apply=all) ──
    ClutchConfig("mg3_k5",    3.0, True,  5.0, False),
    ClutchConfig("mg5_k5",    5.0, True,  5.0, False),
    ClutchConfig("mg8_k5",    8.0, True,  5.0, False),
    ClutchConfig("ot_k5",     0.0, True,  5.0, False),   # OT games only
    # ── Shrinkage sweep (threshold=5, apply=all) ──
    ClutchConfig("mg5_k3",    5.0, True,  3.0, False),
    ClutchConfig("mg5_k8",    5.0, True,  8.0, False),
    ClutchConfig("mg5_k10",   5.0, True, 10.0, False),
    ClutchConfig("mg5_k15",   5.0, True, 15.0, False),
    # ── Apply mode (threshold=5, k=5, close-predicted-only) ──
    ClutchConfig("mg5_k5_co", 5.0, True,  5.0, True),
]

CONFIG_MAP = {cfg.label: cfg for cfg in CONFIGS}
LABELS = ["base"] + [cfg.label for cfg in CONFIGS]


# ── Helpers (identical to backtest_opponent_adjust.py) ───────────────────────

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


# ── Clutch factor computation ─────────────────────────────────────────────────

def _compute_clutch_factors(train_stats, stats_lookup, ratings, nat_avg, cfg, min_close_games=1):
    """
    Per-team conditional mean residual in close games with Bayesian shrinkage.

    A game qualifies as "close" if:
        abs(final_score_diff) <= cfg.margin_threshold   (when threshold > 0)
        OR  went_to_ot                                   (when cfg.include_ot is True)

    For each qualifying game, from team tid's perspective:
        residual_tid = actual_margin_tid - predicted_margin_tid

    Team-level aggregation:
        raw_clutch = mean(residuals over close games)
        shrunk = raw_clutch * n / (n + shrinkage_k)

    Sign convention: positive = team over-performs model expectations in close games.

    Applied at prediction time as:
        pred_adj = pred_base + (home_clutch - away_clutch)

    Returns:
        factors      {team_id -> shrunk clutch factor}
        diagnostics  {team_id -> per-team close-game breakdown dict}
    """
    team_residuals: defaultdict = defaultdict(list)
    team_margins: defaultdict = defaultdict(list)
    team_exp_margins: defaultdict = defaultdict(list)
    team_wins: defaultdict = defaultdict(int)
    team_losses: defaultdict = defaultdict(int)
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

        # Was this game close?
        abs_score_diff = abs(gs.pts - opp_st.pts)
        is_ot = gs.game.went_to_ot
        is_close = (
            (cfg.margin_threshold > 0 and abs_score_diff <= cfg.margin_threshold)
            or (cfg.include_ot and is_ot)
        )
        if not is_close:
            continue

        is_home = (gs.game.home_team_id == tid)
        home_id = tid if is_home else opp_id
        away_id = opp_id if is_home else tid

        pred_home = _predict_margin(ratings[home_id], ratings[away_id], nat_avg, gs.game.neutral_site)
        actual_home = gs.pts - opp_st.pts if is_home else opp_st.pts - gs.pts
        residual_home = actual_home - pred_home

        # From tid's perspective (flip sign for away team)
        residual_tid = residual_home  if is_home else -residual_home
        actual_tid   = actual_home    if is_home else -actual_home
        exp_tid      = pred_home      if is_home else -pred_home

        team_residuals[tid].append(residual_tid)
        team_margins[tid].append(actual_tid)
        team_exp_margins[tid].append(exp_tid)
        if actual_tid > 0:
            team_wins[tid] += 1
        elif actual_tid < 0:
            team_losses[tid] += 1

    factors = {}
    diagnostics = {}

    for tid in set(team_residuals.keys()):
        residuals = team_residuals[tid]
        n = len(residuals)
        raw = sum(residuals) / n if n > 0 else 0.0
        shrunk = raw * n / (n + cfg.shrinkage_k) if n >= min_close_games else 0.0
        factors[tid] = shrunk

        margins     = team_margins.get(tid, [])
        exp_margins = team_exp_margins.get(tid, [])
        diagnostics[tid] = {
            "n": n,
            "wins":         team_wins.get(tid, 0),
            "losses":       team_losses.get(tid, 0),
            "mean_margin":  sum(margins) / len(margins)     if margins     else 0.0,
            "mean_exp":     sum(exp_margins) / len(exp_margins) if exp_margins else 0.0,
            "raw_clutch":   raw,
            "shrunk":       shrunk,
        }

    return factors, diagnostics


# ── Management command ────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Backtest clutch factor (close-game conditional residuals) vs. baseline"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, default=None)
        parser.add_argument(
            "--seasons", type=int, nargs="+", default=None,
            help="Run multiple seasons (e.g. --seasons 2022 2023 2024 2025 2026)",
        )
        parser.add_argument("--k", type=float, default=170.0, help="Ratings shrinkage k (default: 170)")
        parser.add_argument(
            "--min-close-games", type=int, default=1,
            help="Min close games required to use a team's clutch factor (default: 1)",
        )
        parser.add_argument("--start", type=str, default=None, help="First cutoff YYYY-MM-DD")
        parser.add_argument("--end",   type=str, default=None, help="Last cutoff YYYY-MM-DD")
        parser.add_argument("--step",  type=int, default=7,    help="Days between cutoffs (default: 7)")
        parser.add_argument("--window", type=int, default=7,   help="Test window in days (default: 7)")

    def handle(self, *args, **options):
        seasons = options["seasons"] or ([options["season"]] if options["season"] else None)
        if not seasons:
            self.stderr.write("Provide --season YEAR or --seasons YEAR [YEAR ...]")
            return
        for season_year in seasons:
            self._run_season(season_year, options)

    def _run_season(self, season_year, options):
        ratings_k       = options["k"]
        min_close_games = options["min_close_games"]
        step            = options["step"]
        window          = options["window"]

        W = 90
        self.stdout.write("\n" + "=" * W)
        self.stdout.write(f"CLUTCH FACTOR BACKTEST — season {season_year}  (ratings k={ratings_k:.0f})")
        self.stdout.write("=" * W)
        self.stdout.write("Configs:")
        self.stdout.write(f"  {'base':<12} no clutch adjustment")
        for cfg in CONFIGS:
            thresh_str = "OT only" if cfg.margin_threshold == 0 else f"margin ≤{int(cfg.margin_threshold)}"
            apply_str  = "close-predicted-only" if cfg.close_only_apply else "all games"
            self.stdout.write(
                f"  {cfg.label:<12} {thresh_str} + OT, k={cfg.shrinkage_k:.0f}, apply={apply_str}"
            )

        nat_avg = NationalAverages.objects.get(season__year=season_year)
        sigma   = nat_avg.prediction_sigma or 11.08
        EPS     = 1e-9

        # ── Load data ──────────────────────────────────────────────────────── #
        self.stdout.write("\nLoading data...")

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

        total = len(all_d1_games) or 1
        n_close3 = sum(1 for g in all_d1_games if abs(g["home_score"] - g["away_score"]) <= 3 or g["went_to_ot"])
        n_close5 = sum(1 for g in all_d1_games if abs(g["home_score"] - g["away_score"]) <= 5 or g["went_to_ot"])
        n_ot     = sum(1 for g in all_d1_games if g["went_to_ot"])
        self.stdout.write(
            f"  Close-game distribution: ≤3+OT={n_close3} ({100*n_close3/total:.1f}%)  "
            f"≤5+OT={n_close5} ({100*n_close5/total:.1f}%)  "
            f"OT-only={n_ot} ({100*n_ot/total:.1f}%)"
        )

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
            f"  ratings k={ratings_k:.0f}  min_close_games={min_close_games}  "
            f"close-report-threshold=≤{CLOSE_REPORT_THRESHOLD}\n"
        )

        # ── Accumulators ──────────────────────────────────────────────────── #
        def _make_acc():
            return {
                "spread_ae": [], "spread_se": [], "spread_err": [],
                "brier": [], "logloss": [], "correct": [],
            }

        acc_all   = {lbl: _make_acc() for lbl in LABELS}
        acc_close = {lbl: _make_acc() for lbl in LABELS}

        last_diag: dict = {}

        # ── Main walk-forward loop ─────────────────────────────────────────── #
        for ci, cutoff in enumerate(cutoffs):
            wend = cutoff + timedelta(days=window)

            train_stats = [gs for gs in all_stats if game_dates[gs.game_id] < cutoff]
            if len(train_stats) < 20:
                self.stdout.write(
                    f"  [{ci+1:2d}/{len(cutoffs)}] {cutoff}  skip ({len(train_stats)} rows)"
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
                f"train={len(train_stats):5d}  "
                f"spread_test={len(spread_games):3d}  "
                f"wp_test={len(wp_games):3d}",
                ending="",
            )

            # Compute ratings once per cutoff
            ratings = _run_ratings(
                by_team_train, train_stats, stats_lookup,
                team_ids, nat_avg, gtw, tts, ratings_k,
            )

            # Compute clutch factors for all configs (fast: just residual aggregation)
            factors_by_cfg: dict = {}
            diag_by_cfg: dict = {}
            for cfg in CONFIGS:
                f, d = _compute_clutch_factors(
                    train_stats, stats_lookup, ratings, nat_avg, cfg, min_close_games
                )
                factors_by_cfg[cfg.label] = f
                diag_by_cfg[cfg.label] = d

            if ci == len(cutoffs) - 1:
                last_diag = diag_by_cfg.get("mg5_k5", {})

            # ── Score spread test games ──────────────────────────────────── #
            for g in spread_games:
                home_r = ratings.get(g["home_team_id"])
                away_r = ratings.get(g["away_team_id"])
                if not home_r or not away_r:
                    continue

                pred_base = _predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                actual    = g["home_score"] - g["away_score"]
                is_close_actual = abs(actual) <= CLOSE_REPORT_THRESHOLD  # OT excluded from spread_games

                for lbl in LABELS:
                    if lbl == "base":
                        pred = pred_base
                    else:
                        cfg = CONFIG_MAP[lbl]
                        hc  = factors_by_cfg[lbl].get(g["home_team_id"], 0.0)
                        ac  = factors_by_cfg[lbl].get(g["away_team_id"], 0.0)
                        if cfg.close_only_apply and abs(pred_base) > cfg.margin_threshold:
                            pred = pred_base
                        else:
                            pred = pred_base + hc - ac

                    err = pred - actual
                    ae, se = abs(err), err ** 2
                    acc_all[lbl]["spread_ae"].append(ae)
                    acc_all[lbl]["spread_se"].append(se)
                    acc_all[lbl]["spread_err"].append(err)

                    if is_close_actual:
                        acc_close[lbl]["spread_ae"].append(ae)
                        acc_close[lbl]["spread_se"].append(se)
                        acc_close[lbl]["spread_err"].append(err)

            # ── Score win-probability test games ─────────────────────────── #
            for g in wp_games:
                home_r = ratings.get(g["home_team_id"])
                away_r = ratings.get(g["away_team_id"])
                if not home_r or not away_r:
                    continue

                pred_base    = _predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                is_close_actual = (
                    abs(g["home_score"] - g["away_score"]) <= CLOSE_REPORT_THRESHOLD
                    or g["went_to_ot"]
                )

                for lbl in LABELS:
                    if lbl == "base":
                        pred = pred_base
                    else:
                        cfg = CONFIG_MAP[lbl]
                        hc  = factors_by_cfg[lbl].get(g["home_team_id"], 0.0)
                        ac  = factors_by_cfg[lbl].get(g["away_team_id"], 0.0)
                        if cfg.close_only_apply and abs(pred_base) > cfg.margin_threshold:
                            pred = pred_base
                        else:
                            pred = pred_base + hc - ac

                    prob_home = scipy_stats.norm.cdf(pred / sigma)
                    prob_home = max(EPS, min(1.0 - EPS, prob_home))
                    y       = 1.0 if g["home_score"] > g["away_score"] else 0.0
                    brier   = (prob_home - y) ** 2
                    ll      = -(y * math.log(prob_home) + (1 - y) * math.log(1 - prob_home))
                    correct = 1 if (prob_home >= 0.5) == (y >= 0.5) else 0

                    acc_all[lbl]["brier"].append(brier)
                    acc_all[lbl]["logloss"].append(ll)
                    acc_all[lbl]["correct"].append(correct)

                    if is_close_actual:
                        acc_close[lbl]["brier"].append(brier)
                        acc_close[lbl]["logloss"].append(ll)
                        acc_close[lbl]["correct"].append(correct)

            self.stdout.write("")  # newline after per-cutoff progress

        # ── Print summary results ──────────────────────────────────────────── #
        self.stdout.write("\n" + "=" * W)
        self.stdout.write(f"RESULTS — season {season_year}  (ratings k={ratings_k:.0f})")
        self.stdout.write("=" * W)

        def _print_spread(title, acc):
            self.stdout.write(f"\n{title}")
            hdr = f"  {'config':<12}  {'n':>6}  {'MAE':>8}  {'RMSE':>8}  {'bias':>8}  {'Δ MAE':>8}"
            self.stdout.write(hdr)
            self.stdout.write("-" * len(hdr))
            base_mae = None
            for lbl in LABELS:
                r = acc[lbl]
                if not r["spread_ae"]:
                    continue
                mae  = statistics.fmean(r["spread_ae"])
                rmse = math.sqrt(statistics.fmean(r["spread_se"]))
                bias = statistics.fmean(r["spread_err"])
                if base_mae is None:
                    base_mae = mae
                delta     = mae - base_mae
                delta_str = f"{delta:>+8.3f}" if lbl != "base" else f"{'—':>8}"
                self.stdout.write(
                    f"  {lbl:<12}  {len(r['spread_ae']):>6}  "
                    f"{mae:>8.3f}  {rmse:>8.3f}  {bias:>+8.3f}  {delta_str}"
                )

        def _print_brier(title, acc):
            self.stdout.write(f"\n{title}")
            hdr2 = f"  {'config':<12}  {'n':>6}  {'Brier':>8}  {'LogLoss':>9}  {'Acc%':>6}  {'Δ Brier':>9}"
            self.stdout.write(hdr2)
            self.stdout.write("-" * len(hdr2))
            base_brier = None
            for lbl in LABELS:
                r = acc[lbl]
                if not r["brier"]:
                    continue
                brier   = statistics.fmean(r["brier"])
                logloss = statistics.fmean(r["logloss"])
                accp    = 100 * statistics.fmean(r["correct"])
                if base_brier is None:
                    base_brier = brier
                delta     = brier - base_brier
                delta_str = f"{delta:>+9.4f}" if lbl != "base" else f"{'—':>9}"
                self.stdout.write(
                    f"  {lbl:<12}  {len(r['brier']):>6}  "
                    f"{brier:>8.4f}  {logloss:>9.4f}  {accp:>6.1f}  {delta_str}"
                )

        _print_spread("SPREAD ACCURACY  (D1vD1, regulation only — ALL test games)", acc_all)
        _print_brier ("WIN PROBABILITY ACCURACY  (D1vD1 — ALL test games)", acc_all)
        _print_spread(
            f"SPREAD ACCURACY  (D1vD1, regulation close games ≤{CLOSE_REPORT_THRESHOLD}pts)",
            acc_close,
        )
        _print_brier(
            f"WIN PROBABILITY ACCURACY  (close games ≤{CLOSE_REPORT_THRESHOLD}pts or OT)",
            acc_close,
        )

        # ── Clutch diagnostics (mg5_k5, end-of-season) ──────────────────── #
        if last_diag and team_names:
            self.stdout.write(
                f"\nCLUTCH DIAGNOSTICS  (mg5_k5, end-of-season, "
                f"min_close_games={min_close_games})"
            )
            self.stdout.write(f"  Close game = margin ≤5 + OT  |  shrinkage k=5")
            self.stdout.write(f"  Positive shrunk → over-performs expectations in close games\n")

            eligible = [(tid, d) for tid, d in last_diag.items() if d["n"] >= max(min_close_games, 2)]
            ranked   = sorted(eligible, key=lambda x: x[1]["shrunk"])
            top10    = ranked[-10:][::-1]
            bot10    = ranked[:10]

            hdr_d = (
                f"  {'rk':<4}  {'n':>4}  {'rec':>7}  "
                f"{'avg_mg':>7}  {'exp_mg':>7}  {'raw':>7}  {'shrunk':>7}  team"
            )

            self.stdout.write("  Top 10 — most clutch (over-performs in close games):")
            self.stdout.write(hdr_d)
            for rank, (tid, d) in enumerate(top10, 1):
                rec = f"{d['wins']}-{d['losses']}"
                self.stdout.write(
                    f"  {rank:<4}  {d['n']:>4}  {rec:>7}  "
                    f"{d['mean_margin']:>+7.2f}  {d['mean_exp']:>+7.2f}  "
                    f"{d['raw_clutch']:>+7.3f}  {d['shrunk']:>+7.3f}  "
                    f"{team_names.get(tid, str(tid))}"
                )

            self.stdout.write("\n  Bottom 10 — least clutch (under-performs in close games):")
            self.stdout.write(hdr_d)
            for rank, (tid, d) in enumerate(bot10, 1):
                rec = f"{d['wins']}-{d['losses']}"
                self.stdout.write(
                    f"  {rank:<4}  {d['n']:>4}  {rec:>7}  "
                    f"{d['mean_margin']:>+7.2f}  {d['mean_exp']:>+7.2f}  "
                    f"{d['raw_clutch']:>+7.3f}  {d['shrunk']:>+7.3f}  "
                    f"{team_names.get(tid, str(tid))}"
                )

            # Sample size distribution
            n_counts = sorted(d["n"] for d in last_diag.values())
            if n_counts:
                self.stdout.write(f"\n  Close-game sample distribution (all teams with ≥1 close game):")
                self.stdout.write(
                    f"  n={len(n_counts)}  mean={sum(n_counts)/len(n_counts):.1f}  "
                    f"median={n_counts[len(n_counts)//2]}  "
                    f"min={n_counts[0]}  max={n_counts[-1]}"
                )
                buckets = [(1, 1), (2, 3), (4, 6), (7, 10), (11, 15), (16, 99)]
                for lo, hi in buckets:
                    cnt   = sum(1 for n in n_counts if lo <= n <= hi)
                    label = f"={lo}" if lo == hi else f"{lo}–{hi}" if hi < 99 else f"≥{lo}"
                    self.stdout.write(f"    n{label}: {cnt} teams")

        self.stdout.write("")
