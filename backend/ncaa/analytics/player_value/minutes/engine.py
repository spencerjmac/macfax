"""
Minutes allocation engine — Phase 2: Roster‑context minutes model.

Converts per‑player demand signals into a realistic rotation that:
  • Sums to 5.00 shares (200 team player‑minutes / 40)
  • Concentrates ~85–90% of minutes in the top 8–9 players naturally
  • Respects a per‑player floor and ceiling
  • Supports manual override (sandbox / scenario) mode
  • Is fully stateless — no DB access; accepts and returns plain dicts

Allocation pipeline (called per roster)
────────────────────────────────────────
  A. Compute per‑player demand scores
       A1. BPR component   — projected_bpr shifted above replacement level
       A2. MPG component   — prior playing‑time signal (normalised mpg/40)
       A3. Trust component — returner stability + experience accumulation
       A4. Uncertainty dampening   (multiplicative reduction)
  B. Roster‑context adjustments
       B1. Positional scarcity bonus
       B2. Crowded‑role penalty (3rd+ player in an overloaded bucket)
  C. Power‑transform for rotation concentration
  D. Water‑fill normalisation to TEAM_TOTAL_SHARES with floor/ceiling
  E. Manual overrides: lock specified players; redistribute remainder

Output per player
─────────────────
  minutes_share   — projected mpg / 40; sums to 5.00 across the roster
  mpg             — minutes_share × 40
  rotation_rank   — 1 = most projected minutes on this roster
  demand_score    — pre‑normalisation internal score (diagnostic use only)
  is_overridden   — True if this player's share was manually locked

Design notes
────────────
  • The power transform (CONCENTRATION_POWER = 2.0) is the primary tool for
    achieving top‑8/9 concentration.  A player with demand score 0.8 vs 0.2
    gets a 16:1 weight advantage post‑transform, naturally compressing bench
    minutes without hard cutoffs.
  • Water‑fill normalisation (rather than simple proportional scaling) ensures
    the floor and ceiling constraints are always satisfied without iterating
    over all players in every loop.
  • Manual overrides are resolved before demand scoring: locked players are
    removed from the normalisation pool; remaining_shares is passed to the
    water‑fill as its target.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from ncaa.analytics.player_value.minutes.constants import (
    TEAM_TOTAL_SHARES,
    MINIMUM_PLAYER_SHARE,
    MAXIMUM_PLAYER_SHARE,
    REPLACEMENT_BPR_FLOOR,
    BPR_WEIGHT,
    MPG_WEIGHT,
    MIN_GP_FOR_MPG_SIGNAL,
    RETURNER_STABILITY_BONUS,
    EXPERIENCE_BONUS_PER_SEASON,
    MAX_EXPERIENCE_SEASONS,
    UNCERTAINTY_DAMPEN,
    CONCENTRATION_POWER,
    MINIMUM_DEMAND_SCORE,
    SCARCITY_BONUS,
    CROWDING_PENALTY_START,
    CROWDING_PENALTY_PER_SLOT,
    MAX_NORMALIZATION_ITERS,
)
from ncaa.analytics.player_value.minutes.role_buckets import (
    classify_role_bucket,
    compute_bucket_contexts,
    bucket_rank_by_bpr,
)

logger = logging.getLogger(__name__)


# ── Data classes — public API ─────────────────────────────────────────────────

@dataclass
class PlayerMinutesInput:
    """
    All per‑player signals consumed by the minutes allocator.

    Every field maps directly to data available in PlayerSeasonProjection
    and PlayerSeasonStats — no external data sources required.

    Fields:
        player_id:              Primary key from the Player / PlayerSeasonProjection.
        projected_bpr:          Phase 1 projected BPR (pts/100 poss above D1 avg).
        projection_uncertainty: Phase 1 uncertainty score [0, 1].
        recruitment_type:       "returner" | "transfer" | "newcomer".
        n_prior_seasons:        Number of prior college seasons in DB before
                                from_season (Phase 1 development proxy).
        prior_mpg:              MPG from the from_season PlayerSeasonStats.
        prior_gp:               GP  from the from_season PlayerSeasonStats.
        prior_poss:             off_poss + def_poss from from_season.
        position:               Player.position string ("G", "F", "C", "ATH", …).
        ast_pg:                 Assists/game (from PlayerSeasonStats.ast).
        blk_pg:                 Blocks/game  (from PlayerSeasonStats.blk).
        reb_pg:                 Rebounds/game (from PlayerSeasonStats.reb).
        fg3a_pg:                3‑point attempts/game (supplementary context).
    """
    player_id:              int
    projected_bpr:          float
    projection_uncertainty: float
    recruitment_type:       str    # "returner" | "transfer" | "newcomer"
    n_prior_seasons:        int
    prior_mpg:              float
    prior_gp:               int
    prior_poss:             float
    position:               str
    ast_pg:                 float = 0.0
    blk_pg:                 float = 0.0
    reb_pg:                 float = 0.0
    fg3a_pg:                float = 0.0


@dataclass
class PlayerMinutesOutput:
    """Per‑player result from allocate_roster_minutes()."""
    player_id:     int
    role_bucket:   str    # "G" | "Wing" | "Big"
    minutes_share: float  # projected mpg / 40; roster sums to 5.00
    mpg:           float  # minutes_share × 40
    rotation_rank: int    # 1 = most projected minutes on this roster
    demand_score:  float  # internal pre‑normalisation score (diagnostics)
    is_overridden: bool   # True if manually pinned via locked_minutes


@dataclass
class RosterAllocationResult:
    """Roster‑level summary returned by allocate_roster_minutes()."""
    players:               list[PlayerMinutesOutput]
    total_shares:          float   # ≈ 5.00
    total_mpg:             float   # ≈ 200.0
    top_5_share:           float   # cumulative share of the top 5 players by minutes
    top_8_share:           float
    top_9_share:           float
    n_above_tenth_share:   int     # players with minutes_share ≥ 0.10 (4 mpg)
    n_above_quarter_share: int     # players with minutes_share ≥ 0.25 (10 mpg)


# ── Step A+B: demand score ────────────────────────────────────────────────────

def _compute_demand_score(
    inp:          PlayerMinutesInput,
    bucket_ctx,               # BucketContext for this player's bucket
    bucket_rank:  int,        # 1‑indexed rank within bucket by projected_bpr
) -> float:
    """
    Compute the raw demand score for one player.

    Formula (all additive before uncertainty dampening):
      base = BPR_WEIGHT × max(0, projected_bpr − REPLACEMENT_BPR_FLOOR)
           + MPG_WEIGHT × (prior_mpg / 40)    [if prior_gp ≥ threshold]
           + RETURNER_STABILITY_BONUS          [if recruitment_type == "returner"]
           + EXPERIENCE_BONUS_PER_SEASON × min(n_prior_seasons, MAX_SEASONS)
      base = base × (1 − UNCERTAINTY_DAMPEN × uncertainty)
      context_adj = +SCARCITY_BONUS if bucket is scarce
                  − CROWDING_PENALTY × (rank − START + 1)  if crowded and deep
      raw_score = max(MINIMUM_DEMAND_SCORE,  base + context_adj)

    The power transform (engine step C) is applied *after* this function,
    so scores here are in a roughly linear additive space.

    Args:
        inp:         The player's input signals.
        bucket_ctx:  BucketContext for this player's role bucket.
        bucket_rank: 1 = best BPR in this bucket; higher = deeper bench.

    Returns:
        Raw demand score > 0.
    """
    # ── A1: BPR component ────────────────────────────────────────────────────
    bpr_shifted   = max(0.0, inp.projected_bpr - REPLACEMENT_BPR_FLOOR)
    bpr_component = BPR_WEIGHT * bpr_shifted

    # ── A2: Prior playing‑time signal ────────────────────────────────────────
    if inp.prior_gp >= MIN_GP_FOR_MPG_SIGNAL and inp.prior_mpg > 0:
        mpg_component = MPG_WEIGHT * (inp.prior_mpg / 40.0)
    else:
        mpg_component = 0.0

    # ── A3: Experience / trust ────────────────────────────────────────────────
    trust = 0.0
    if inp.recruitment_type == "returner":
        trust += RETURNER_STABILITY_BONUS
    trust += EXPERIENCE_BONUS_PER_SEASON * min(inp.n_prior_seasons, MAX_EXPERIENCE_SEASONS)

    # ── A4: Uncertainty dampening ─────────────────────────────────────────────
    unc = max(0.0, min(1.0, inp.projection_uncertainty))
    uncertainty_factor = 1.0 - UNCERTAINTY_DAMPEN * unc

    base_score = (bpr_component + mpg_component + trust) * uncertainty_factor

    # ── B: Roster‑context adjustments ────────────────────────────────────────
    context_adj = 0.0

    if bucket_ctx.is_scarce:
        context_adj += SCARCITY_BONUS

    if bucket_ctx.is_crowded and bucket_rank >= CROWDING_PENALTY_START:
        excess       = bucket_rank - CROWDING_PENALTY_START + 1
        context_adj -= CROWDING_PENALTY_PER_SLOT * excess

    raw_score = base_score + context_adj
    return max(raw_score, MINIMUM_DEMAND_SCORE)


# ── Step D: water‑fill normalisation ─────────────────────────────────────────

def _normalize_with_caps(
    demands:      list[float],
    total_target: float,
    min_share:    float,
    max_share:    float,
    max_iters:    int = MAX_NORMALIZATION_ITERS,
) -> list[float]:
    """
    Scale a list of demand weights so they sum to `total_target`,
    while clamping each element to [min_share, max_share].

    Algorithm (iterative water‑fill):
      1. Compute scale = remaining_target / sum_of_free_demands.
      2. Apply scale to all free (un‑locked) elements.
      3. Lock any element now at or below min_share / at or above max_share.
      4. Repeat until no new locks occur (converged) or max_iters reached.
      5. Final micro‑correction to zero floating‑point residual.

    The algorithm is guaranteed to converge when the constraints are feasible
    (i.e. n × min_share ≤ total_target ≤ n × max_share).

    Args:
        demands:      Raw weights (non‑negative).  Need not sum to anything.
        total_target: Desired sum of output list.
        min_share:    Per‑element floor.
        max_share:    Per‑element ceiling.
        max_iters:    Safety valve — exits early if somehow cycling.

    Returns:
        List of floats summing to total_target (within floating‑point tolerance).
    """
    n = len(demands)
    if n == 0:
        return []

    # Clamp target to feasible range.
    total_target = max(total_target, n * min_share)
    total_target = min(total_target, n * max_share)

    # Initial proportional allocation; fallback to equal split if all demands are 0.
    total_demand = sum(demands)
    if total_demand < 1e-12:
        base = total_target / n
        return [max(min_share, min(max_share, base))] * n

    shares = [d / total_demand * total_target for d in demands]

    for _ in range(max_iters):
        # Apply floor and ceiling clamps.
        for i in range(n):
            shares[i] = max(min_share, min(max_share, shares[i]))

        current_sum = sum(shares)
        residual    = total_target - current_sum
        if abs(residual) < 1e-9:
            break

        # Redistribute residual among players with remaining headroom.
        if residual > 0:
            # Add minutes to players not yet at ceiling.
            eligible = [i for i in range(n) if shares[i] < max_share - 1e-9]
        else:
            # Remove minutes from players not yet at floor.
            eligible = [i for i in range(n) if shares[i] > min_share + 1e-9]

        if not eligible:
            break

        eligible_sum = sum(shares[i] for i in eligible)
        if eligible_sum < 1e-12:
            per_player = residual / len(eligible)
            for i in eligible:
                shares[i] = max(min_share, min(max_share, shares[i] + per_player))
        else:
            for i in eligible:
                shares[i] += residual * shares[i] / eligible_sum

    return shares


# ── Step E: main allocator ────────────────────────────────────────────────────

def allocate_roster_minutes(
    players:        list[PlayerMinutesInput],
    locked_minutes: Optional[dict[int, float]] = None,
    total_shares:   float = TEAM_TOTAL_SHARES,
) -> RosterAllocationResult:
    """
    Allocate projected minutes shares across a roster.

    The allocator is fully stateless (no DB access) and can be called for
    any player list, making it reusable for:
      • Baseline current‑team allocation (called by the service layer)
      • Hypothetical / what‑if rosters
      • Transfer portal scenario mode
      • Manual‑override sandbox mode

    Manual overrides (locked_minutes)
    ──────────────────────────────────
    If `locked_minutes` is provided, those players' shares are fixed at the
    specified values.  The remaining shares (total_shares − locked_total)
    are distributed via the normal demand‑score / concentration algorithm
    among the unlocked players.

    Lock validation rules:
      • Each locked share must be in [0, MAXIMUM_PLAYER_SHARE].
      • The sum of locked shares must not exceed total_shares.
      • A locked share of 0.0 is valid (player is on the roster but not playing).

    Args:
        players:        One PlayerMinutesInput per rostered player.
        locked_minutes: Optional {player_id: minutes_share} override map.
        total_shares:   Team minutes‑share target (default 5.00).

    Returns:
        RosterAllocationResult with per‑player outputs and roster summary.

    Raises:
        ValueError: Locked minutes total exceeds total_shares, or any
                    locked share is out of bounds.
    """
    if not players:
        return _empty_result()

    locked = locked_minutes or {}

    # ── Validate overrides ──────────────────────────────────────────────────
    for pid, share in locked.items():
        if share < 0:
            raise ValueError(
                f"Locked minutes share for player {pid} cannot be negative "
                f"(got {share:.4f})."
            )
        if share > MAXIMUM_PLAYER_SHARE + 1e-6:
            raise ValueError(
                f"Locked share {share:.4f} for player {pid} exceeds the "
                f"per‑player maximum ({MAXIMUM_PLAYER_SHARE})."
            )

    locked_total = sum(locked.values())
    if locked_total > total_shares + 1e-6:
        raise ValueError(
            f"Locked minutes total ({locked_total:.4f}) exceeds the team "
            f"total ({total_shares:.4f}).  Reduce override values."
        )

    # ── Role bucket classification ──────────────────────────────────────────
    player_buckets: dict[int, str] = {
        p.player_id: classify_role_bucket(
            position=p.position,
            blk_pg=p.blk_pg,
            reb_pg=p.reb_pg,
            ast_pg=p.ast_pg,
            fg3a_pg=p.fg3a_pg,
        )
        for p in players
    }
    bucket_contexts = compute_bucket_contexts(player_buckets)

    player_bpr: dict[int, float] = {p.player_id: p.projected_bpr for p in players}
    bucket_ranks: dict[int, int] = {
        p.player_id: bucket_rank_by_bpr(p.player_id, player_buckets, player_bpr)
        for p in players
    }

    # ── Separate locked / free players ─────────────────────────────────────
    free_players   = [p for p in players if p.player_id not in locked]
    locked_players = [p for p in players if p.player_id in locked]
    remaining      = total_shares - locked_total

    # ── Steps A+B: demand scores for free players ───────────────────────────
    demand_scores: dict[int, float] = {}
    for p in free_players:
        demand_scores[p.player_id] = _compute_demand_score(
            inp=p,
            bucket_ctx=bucket_contexts[player_buckets[p.player_id]],
            bucket_rank=bucket_ranks[p.player_id],
        )

    # ── Step C: power transform ─────────────────────────────────────────────
    concentrated: dict[int, float] = {
        pid: score ** CONCENTRATION_POWER
        for pid, score in demand_scores.items()
    }

    # ── Step D: water‑fill normalisation ────────────────────────────────────
    if free_players:
        free_ids  = [p.player_id for p in free_players]
        raw_weights = [concentrated[pid] for pid in free_ids]
        # Scale the per‑player ceiling up when the roster is too small to fill
        # the target under the normal cap (e.g., 1‑player sandbox rosters).
        effective_max = max(MAXIMUM_PLAYER_SHARE, remaining / len(free_players))
        allocated   = _normalize_with_caps(
            demands=raw_weights,
            total_target=remaining,
            min_share=MINIMUM_PLAYER_SHARE,
            max_share=effective_max,
        )
        share_map: dict[int, float] = dict(zip(free_ids, allocated))
    else:
        share_map = {}

    # ── Merge locked + free shares ──────────────────────────────────────────
    all_shares: dict[int, float] = {p.player_id: locked[p.player_id] for p in locked_players}
    all_shares.update(share_map)

    # ── Assign rotation ranks (1 = most minutes) ────────────────────────────
    sorted_by_share = sorted(all_shares.items(), key=lambda kv: kv[1], reverse=True)
    rotation_ranks  = {pid: rank for rank, (pid, _) in enumerate(sorted_by_share, start=1)}

    # ── Build per‑player output ─────────────────────────────────────────────
    outputs: list[PlayerMinutesOutput] = [
        PlayerMinutesOutput(
            player_id=p.player_id,
            role_bucket=player_buckets[p.player_id],
            minutes_share=round(all_shares[p.player_id], 6),
            mpg=round(all_shares[p.player_id] * 40.0, 4),
            rotation_rank=rotation_ranks[p.player_id],
            demand_score=round(demand_scores.get(p.player_id, 0.0), 6),
            is_overridden=(p.player_id in locked),
        )
        for p in players
    ]
    outputs.sort(key=lambda o: o.rotation_rank)

    # ── Roster‑level summary ────────────────────────────────────────────────
    shares_desc     = sorted((o.minutes_share for o in outputs), reverse=True)
    total_allocated = sum(shares_desc)

    return RosterAllocationResult(
        players=outputs,
        total_shares=round(total_allocated, 6),
        total_mpg=round(total_allocated * 40.0, 4),
        top_5_share=round(sum(shares_desc[:5]), 4),
        top_8_share=round(sum(shares_desc[:8]), 4),
        top_9_share=round(sum(shares_desc[:9]), 4),
        n_above_tenth_share=sum(1 for s in shares_desc if s >= 0.10),
        n_above_quarter_share=sum(1 for s in shares_desc if s >= 0.25),
    )


def _empty_result() -> RosterAllocationResult:
    return RosterAllocationResult(
        players=[],
        total_shares=0.0,
        total_mpg=0.0,
        top_5_share=0.0,
        top_8_share=0.0,
        top_9_share=0.0,
        n_above_tenth_share=0,
        n_above_quarter_share=0,
    )
