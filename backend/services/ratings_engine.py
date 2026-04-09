"""
Shared ratings engine — sport-agnostic iterative opponent-adjustment.

Used by:
  - NBA: nba/management/commands/nba_compute_ratings.py (Phase 2)
  - NCAA: can migrate compute_adjusted_ratings.py to this in a future phase

The algorithm:
  For each game, compute a context-adjusted raw rating for each team.
  Iteratively solve: adj_off(team) = f(raw_off, opp adj_def)
                     adj_def(team) = f(raw_def, opp adj_off)
  Shrinkage toward the league prior is controlled by prior_games.

References:
  - Possession estimate: FGA - OREB + TO + 0.44*FTA  (standard NCAA/NBA formula)
  - Per-possession efficiency: 100 * PTS / poss
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GameRecord:
    """Normalized game record for a single team's appearance in one game."""

    team_id: int
    opp_id: int
    raw_ortg: float        # pts / poss * 100
    raw_drtg: float        # opp_pts / opp_poss * 100
    poss: float            # estimated possessions for this team

    # Context flags — set to None if not known / not applicable
    is_home: Optional[bool] = None
    rest_days: Optional[int] = None    # days since last game (None = first game of season)
    is_b2b: bool = False

    # Set False for preseason, NBA Cup final, play-in, etc.
    counts_toward_ratings: bool = True


@dataclass
class RatingsConfig:
    """Configuration for the iterative opponent-adjustment."""

    iterations: int = 8
    convergence_threshold: float = 0.001

    # Bayesian shrinkage — how many "prior games" to blend toward league average.
    # NCAA: ~15 (fewer games, more uncertainty)
    # NBA:  ~5  (82-game schedule gives much more signal)
    prior_games: float = 5.0

    # League-average priors for the current season.
    prior_ortg: float = 110.0
    prior_drtg: float = 110.0

    # Context adjustments — set to 0.0 to disable.
    # Positive home_court_adj boosts home team offense, penalizes home team defense.
    home_court_adj: float = 0.0
    rest_adj_per_day: float = 0.0  # bonus per day of rest beyond 1 day (capped at 3)
    b2b_penalty: float = 0.0       # shared penalty on both ends for back-to-back nights


def compute_possessions(fga: int, oreb: int, tov: int, fta: int) -> float:
    """
    Standard possession estimate used in both NCAA and NBA.
    Formula: FGA - OREB + TO + 0.44 * FTA
    """
    return fga - oreb + tov + 0.44 * fta


def iterative_adjust(
    games: list[GameRecord],
    config: RatingsConfig,
) -> dict[int, dict]:
    """
    Iteratively compute opponent-adjusted offensive and defensive ratings.

    Returns:
        dict mapping team_id -> {
            'adj_off': float,
            'adj_def': float,
            'adj_net': float,    # adj_off - adj_def
            'raw_off': float,    # simple average of context-adjusted raw ratings
            'raw_def': float,
            'game_count': int,
        }

    Only games with counts_toward_ratings=True are used in the calculation.
    """
    from collections import defaultdict

    active_games = [g for g in games if g.counts_toward_ratings]
    if not active_games:
        return {}

    # Collect all team IDs (including opponents who may not have their own rows yet)
    team_ids: set[int] = set()
    for g in active_games:
        team_ids.add(g.team_id)
        team_ids.add(g.opp_id)

    # Initialize at league prior
    adj_off: dict[int, float] = {tid: config.prior_ortg for tid in team_ids}
    adj_def: dict[int, float] = {tid: config.prior_drtg for tid in team_ids}

    # Pre-compute context-adjusted raw values per team.
    # Positive context_adj helps the advantaged team's offense.
    team_ctx_ortg: dict[int, list[float]] = defaultdict(list)
    team_ctx_drtg: dict[int, list[float]] = defaultdict(list)
    team_poss: dict[int, list[float]] = defaultdict(list)
    team_opps: dict[int, list[int]] = defaultdict(list)

    for g in active_games:
        ctx = 0.0
        if g.is_home is not None and config.home_court_adj:
            ctx += config.home_court_adj if g.is_home else -config.home_court_adj
        if g.is_b2b and config.b2b_penalty:
            ctx -= config.b2b_penalty
        elif g.rest_days is not None and config.rest_adj_per_day:
            extra_rest = min(max(g.rest_days - 1, 0), 3)
            ctx += extra_rest * config.rest_adj_per_day

        # Remove context advantage to get "true" underlying performance
        team_ctx_ortg[g.team_id].append(g.raw_ortg - ctx)
        team_ctx_drtg[g.team_id].append(g.raw_drtg + ctx)
        team_poss[g.team_id].append(g.poss)
        team_opps[g.team_id].append(g.opp_id)

    # League average for prior (computed from context-adjusted values)
    all_ctx_ortg = [v for vals in team_ctx_ortg.values() for v in vals]
    all_ctx_drtg = [v for vals in team_ctx_drtg.values() for v in vals]
    lg_avg_off = sum(all_ctx_ortg) / len(all_ctx_ortg) if all_ctx_ortg else config.prior_ortg
    lg_avg_def = sum(all_ctx_drtg) / len(all_ctx_drtg) if all_ctx_drtg else config.prior_drtg

    # ── Iterative solver ────────────────────────────────────────────────────
    for _ in range(config.iterations):
        new_adj_off: dict[int, float] = {}
        new_adj_def: dict[int, float] = {}
        max_delta = 0.0

        for tid in team_ids:
            ortg_vals = team_ctx_ortg.get(tid, [])
            drtg_vals = team_ctx_drtg.get(tid, [])
            opp_ids = team_opps.get(tid, [])
            poss_vals = team_poss.get(tid, [])

            # Bayesian prior contribution (shrinkage toward league average)
            off_weighted_sum = lg_avg_off * config.prior_games
            def_weighted_sum = lg_avg_def * config.prior_games
            total_weight = config.prior_games

            for ortg, drtg, opp_id, poss in zip(ortg_vals, drtg_vals, opp_ids, poss_vals):
                # Possession-weight each game — higher-poss games get slightly more weight
                w = max(poss / 100.0, 0.5)
                opp_adj_def = adj_def.get(opp_id, config.prior_drtg)
                opp_adj_off = adj_off.get(opp_id, config.prior_ortg)
                # Opponent-adjusted contribution:
                # raw_off + (lg_avg - opp_adj_def) measures offense above/below expectation
                off_weighted_sum += (ortg + (lg_avg_off - opp_adj_def)) * w
                def_weighted_sum += (drtg + (lg_avg_def - opp_adj_off)) * w
                total_weight += w

            new_off = off_weighted_sum / total_weight
            new_def = def_weighted_sum / total_weight

            max_delta = max(
                max_delta,
                abs(new_off - adj_off.get(tid, config.prior_ortg)),
                abs(new_def - adj_def.get(tid, config.prior_drtg)),
            )
            new_adj_off[tid] = new_off
            new_adj_def[tid] = new_def

        adj_off = new_adj_off
        adj_def = new_adj_def

        if max_delta < config.convergence_threshold:
            break

    # ── Build output dict ────────────────────────────────────────────────────
    results: dict[int, dict] = {}
    for tid in team_ids:
        ctx_ortg_vals = team_ctx_ortg.get(tid, [])
        ctx_drtg_vals = team_ctx_drtg.get(tid, [])
        n = len(ctx_ortg_vals)
        raw_off = sum(ctx_ortg_vals) / n if n else config.prior_ortg
        raw_def = sum(ctx_drtg_vals) / n if n else config.prior_drtg

        results[tid] = {
            "adj_off": adj_off[tid],
            "adj_def": adj_def[tid],
            "adj_net": adj_off[tid] - adj_def[tid],
            "raw_off": raw_off,
            "raw_def": raw_def,
            "game_count": n,
        }

    return results
