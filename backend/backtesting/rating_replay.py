"""
In-memory replay of the production AdjEM rating loop, shared by the tuning
backtests (backtest_shrinkage, _hca, _recency, _importance, _opponent_adjust,
_pace_adjust, _clutch).

Each backtest trains ratings on games before a cutoff date, then scores the
games after it. They all need the same three pieces, so those live here once:

    time_weights(...)   recency weights anchored to the cutoff date
    run_ratings(...)    the iterative opponent-adjusted rating loop, no DB writes
    predict_margin(...) predicted home margin from two teams' ratings

This is a *replay*, not the production code. It follows the loop in
ncaa/management/commands/compute_adjusted_ratings.py, but only as of the
defaults below. Known differences from production (kept on purpose, because
changing them would change every backtest result):

  * MAX_ITERATIONS is 50 here (production: PipelineConfig.adj_ratings_iterations,
    default 75). Ratings almost always converge sooner; 50 keeps sweeps fast.
  * The importance-weight freeze iteration is fixed at 6 here. Production's
    default (--freeze-iter 0) is adaptive: max(4, min(20, avg_games_played / 2)).
    Pass freeze_iteration= to run_ratings() to test the adaptive value.
  * No BPR prior and no dynamic shrinkage floor: k is passed in by the caller.
  * Recency lambda and the importance constants are fixed (see below).

tests/test_rating_replay.py checks the constants below against production so a
change there is noticed.
"""

import math
from collections import defaultdict
from dataclasses import dataclass

# Production constants (see the module docstring for the ones that differ).
CONVERGENCE = 0.001
MAX_ITERATIONS = 50        # production default is 75; 50 is enough and faster
RECENCY_LAMBDA = 0.0040
IMP_C = 40.0
IMP_FLOOR = 0.35
CLOSE_M = 12.0
BOOST_MAX = 1.40
FREEZE_ITERATION = 6       # production default is adaptive, see module docstring


@dataclass(frozen=True)
class ImportanceParams:
    """Settings for importance weighting (down-weighting mismatch games)."""
    enabled: bool = True
    c: float = IMP_C
    floor: float = IMP_FLOOR
    close_m: float = CLOSE_M
    boost_max: float = BOOST_MAX


PRODUCTION_IMPORTANCE = ImportanceParams()
NO_IMPORTANCE = ImportanceParams(enabled=False)


def time_weights(train_stats, game_dates, ref_date, lam=RECENCY_LAMBDA):
    """
    Compute per-game recency weights and per-team rescale factors,
    both anchored to `ref_date` (the cutoff) rather than today.
    With lam=0 every weight is 1.0.

    Returns (game_weights, team_rescale): {game_id: w}, {team_id: factor}.
    """
    if lam == 0.0:
        gtw = {gs.game_id: 1.0 for gs in train_stats}
        tts = {gs.team_id: 1.0 for gs in train_stats}
        return gtw, tts

    gtw = {
        gs.game_id: math.exp(-lam * max(0, (ref_date - game_dates[gs.game_id]).days))
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


def _iterate_ratings(by_team_train, train_stats, stats_lookup, team_ids,
                     nat_avg, gtw, tts, k, importance, freeze_iteration):
    """The rating loop. Returns (ratings, frozen_importance_weights)."""
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
                if not importance.enabled:
                    w_imp = 1.0
                elif iteration <= freeze_iteration:
                    t_aem = ratings[tid]["aor"] - ratings[tid]["adr"]
                    o_aem = opp_aor - opp_adr
                    gap = abs(t_aem - o_aem)
                    base = max(importance.floor, 1.0 / (1.0 + (gap / importance.c) ** 2))
                    closer = max(0.0, abs(t_aem - o_aem) - abs(aor_g - adr_g))
                    cf = 1.0 - math.exp(-closer / importance.close_m)
                    w_imp = min(1.0, base * (1.0 + (importance.boost_max - 1.0) * cf))
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

        if importance.enabled and iteration == freeze_iteration:
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

    return ratings, frozen_imp


def run_ratings(by_team_train, train_stats, stats_lookup, team_ids,
                nat_avg, gtw, tts, k,
                importance=PRODUCTION_IMPORTANCE, freeze_iteration=FREEZE_ITERATION):
    """
    Iterative opponent-adjusted ratings, fully in memory (no DB writes).

    importance: ImportanceParams; use NO_IMPORTANCE to switch it off.
    Returns {team_id: {"aor": float, "adr": float, "pace": float}}.
    """
    ratings, _ = _iterate_ratings(
        by_team_train, train_stats, stats_lookup, team_ids,
        nat_avg, gtw, tts, k, importance, freeze_iteration,
    )
    return ratings


def run_ratings_with_importance_weights(by_team_train, train_stats, stats_lookup, team_ids,
                                        nat_avg, gtw, tts, k,
                                        importance=PRODUCTION_IMPORTANCE,
                                        freeze_iteration=FREEZE_ITERATION):
    """
    Same as run_ratings(), but also returns every importance weight computed
    at the freeze iteration (for mean / median / floor-hit diagnostics).
    The list is empty when importance is off or the loop converged first.

    Returns (ratings, importance_weights).
    """
    ratings, frozen_imp = _iterate_ratings(
        by_team_train, train_stats, stats_lookup, team_ids,
        nat_avg, gtw, tts, k, importance, freeze_iteration,
    )
    return ratings, list(frozen_imp.values())


def predict_margin(home_r, away_r, nat_avg, neutral_site, hca=None):
    """
    Multiplicative efficiency model, same as api.matchup_engine.forecast_game().
    Returns the predicted margin from the home team's perspective.

    hca: home-court advantage in points. None means use the season's stored
    value (nat_avg.hca_points, or 3.20 if unset); an explicit 0.0 is honoured.
    """
    hp, ap = home_r["pace"], away_r["pace"]
    pace = (2 * hp * ap) / (hp + ap) if hp > 0 and ap > 0 else nat_avg.avg_pace

    exp_oe_home = (home_r["aor"] * away_r["adr"]) / nat_avg.avg_ortg
    exp_oe_away = (away_r["aor"] * home_r["adr"]) / nat_avg.avg_ortg

    pts_home = exp_oe_home * (pace / 100)
    pts_away = exp_oe_away * (pace / 100)

    if hca is None:
        hca = nat_avg.hca_points or 3.20
    if not neutral_site:
        pts_home += hca / 2
        pts_away -= hca / 2

    return pts_home - pts_away
