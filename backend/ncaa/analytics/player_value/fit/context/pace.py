"""
Phase 4: Pace Compatibility Engine.

This module computes how well a projected roster's collective pace tendency
aligns with the team's actual pace identity (from TeamSeasonRatings).

Key design decisions
─────────────────────
1. UNIT CONSISTENCY
   Both the player-derived roster_pace_score and the team-derived
   team_pace_score live on the same 0-100 scale (50 = D1 average pace).
   They are directly comparable.

   Player tendency:
       z_composite = weighted z-score sum over (fg3a_pg, ast_pg, stl_pg,
                                                -fta_pg, -oreb_pg)
       player_pace_score = clamp(50 + z_composite * Z_TO_SCORE_SCALE, 0, 100)

   Team pace score (when available):
       z_tempo = (adj_tempo - TEMPO_MEAN) / TEMPO_STD
       team_pace_score = clamp(50 + z_tempo * Z_TO_SCORE_SCALE, 0, 100)

2. MISSING DATA → NEUTRAL
   If no team adj_tempo data exists, all outputs are neutral:
       pace_alignment_score = 50  (NEUTRAL_ALIGNMENT_SCORE)
       pace_modifier        = 0   (NEUTRAL_MODIFIER)
   No national-average substitution.  has_team_style_data=False will be set
   by the caller to make this explicit.

3. PACE BIASED TOWARD OFFENSE
   The raw pace_modifier is used 100% for offense and 50% for defense.
   This split happens in engine.py, not here.  This module returns one
   unsigned modifier; the engine applies the asymmetric weights.

4. LINEAR ALIGNMENT CURVE
   alignment_score = 50 at perfect match, descends toward 0 or ascends
   toward 100 symmetrically.  The alignment→modifier mapping is linear:
       pace_modifier = (alignment_score - 50) / 50 * MAX_PACE_MODIFIER_OFF

Public API
──────────
   player_pace_score(p: PlayerFitInput) -> float
   roster_pace_profile(players: list[PlayerFitInput]) -> float
   normalize_team_pace(adj_tempo: float) -> float
   score_pace_compatibility(
       roster_pace_score: float,
       team_pace_score: float | None,
   ) -> tuple[float, float]   # (alignment_score 0-100, modifier -2 to +2)
"""

from __future__ import annotations

import math
from typing import Optional

from ncaa.analytics.player_value.fit.archetypes import PlayerFitInput
from ncaa.analytics.player_value.fit.context.constants import (
    SCORE_MID,
    SCORE_MIN,
    SCORE_MAX,
    Z_TO_SCORE_SCALE,
    WINSOR_SIGMA,
    MAX_PACE_MODIFIER_OFF,
    NEUTRAL_ALIGNMENT_SCORE,
    NEUTRAL_MODIFIER,
    PACE_WEIGHT_FG3A,
    PACE_WEIGHT_AST,
    PACE_WEIGHT_STL,
    PACE_WEIGHT_FTA,
    PACE_WEIGHT_OREB,
    REF_PACE_FG3A_PG,
    REF_PACE_AST_PG,
    REF_PACE_STL_PG,
    REF_PACE_FTA_PG,
    REF_PACE_OREB_PG,
    REF_ADJ_TEMPO,
    TOP_ROTATION_THRESHOLD,
)


def _winsorize(z: float) -> float:
    return max(-WINSOR_SIGMA, min(WINSOR_SIGMA, z))


def _z(value: float, mean: float, std: float) -> float:
    """Safe z-score.  Returns 0 if std ≤ 0."""
    if std <= 0:
        return 0.0
    return (value - mean) / std


def _z_winsorized(value: float, ref: tuple[float, float]) -> float:
    return _winsorize(_z(value, ref[0], ref[1]))


# ── Player pace tendency ──────────────────────────────────────────────────────

def player_pace_score(p: PlayerFitInput) -> float:
    """
    Compute a single player's pace tendency on a 0-100 scale.

    50 = D1 average pace tendency (neither a speed-up nor a slow-down player).
    Above 50 = player profile enables / fits a faster pace.
    Below 50 = player profile contributes to a slower, more deliberate game.

    Formula (weighted z-score composite):
        z = Σ weight_i × z_i
        pace_score = clamp(50 + z × Z_TO_SCORE_SCALE, 0, 100)

    Signals:
      + fg3a_pg  (spacers open the floor → pace-friendly)
      + ast_pg   (playmakers → transition capability)
      + stl_pg   (steals → defensive transition; small weight)
      - fta_pg   (foul-drawing trips the clock)
      - oreb_pg  (glass crashing → halfcourt reset possession use)

    tov_pg is intentionally excluded: turnovers represent chaos, not a
    deliberate pace preference, and correlate weakly with actual team tempo.
    """
    # Weighted z-score sum (weights are already normalized to sum to ~1.0
    # in absolute value, so the composite is already in z-score units)
    total_weight = (
        abs(PACE_WEIGHT_FG3A) + abs(PACE_WEIGHT_AST)
        + abs(PACE_WEIGHT_STL) + abs(PACE_WEIGHT_FTA) + abs(PACE_WEIGHT_OREB)
    )

    z_fg3a  = _z_winsorized(p.fg3a_pg, REF_PACE_FG3A_PG)
    z_ast   = _z_winsorized(p.ast_pg,  REF_PACE_AST_PG)
    z_stl   = _z_winsorized(p.stl_pg,  REF_PACE_STL_PG)
    z_fta   = _z_winsorized(p.fta_pg,  REF_PACE_FTA_PG)
    z_oreb  = _z_winsorized(p.oreb_pg, REF_PACE_OREB_PG)

    # weighted composite (signals already have +/- polarity applied)
    z_composite = (
        PACE_WEIGHT_FG3A * z_fg3a
        + PACE_WEIGHT_AST  * z_ast
        + PACE_WEIGHT_STL  * z_stl
        + PACE_WEIGHT_FTA  * z_fta   # negative weight, fta is naturally positive z when high
        + PACE_WEIGHT_OREB * z_oreb  # negative weight
    )

    # Normalize so the composite behaves like a single z-score
    # (divide by sum of absolute weights to stay in ~[-1, +1] z range)
    z_normalized = z_composite / total_weight if total_weight > 0 else 0.0

    score = SCORE_MID + z_normalized * Z_TO_SCORE_SCALE
    return max(SCORE_MIN, min(SCORE_MAX, score))


# ── Roster pace profile ───────────────────────────────────────────────────────

def roster_pace_profile(players: list[PlayerFitInput]) -> float:
    """
    Compute the minutes-weighted average pace tendency for a roster.

    Only players with minutes_share_p2 > 0 are included.
    Returns SCORE_MID (50) if no qualifying players found.
    """
    total_weight = 0.0
    weighted_sum = 0.0

    for p in players:
        w = p.minutes_share_p2 or 0.0
        if w <= 0:
            continue
        weighted_sum += w * player_pace_score(p)
        total_weight += w

    if total_weight <= 0:
        return SCORE_MID

    return weighted_sum / total_weight


# ── Team pace normalizer ──────────────────────────────────────────────────────

def normalize_team_pace(adj_tempo: float) -> float:
    """
    Normalize a team's adj_tempo (poss/game) to 0-100, same scale as
    player_pace_score().

    50 = D1 average (adj_tempo ≈ 69.24).
    Above 50 = faster than D1 average.
    Below 50 = slower than D1 average.
    """
    z = _winsorize(_z(adj_tempo, REF_ADJ_TEMPO[0], REF_ADJ_TEMPO[1]))
    score = SCORE_MID + z * Z_TO_SCORE_SCALE
    return max(SCORE_MIN, min(SCORE_MAX, score))


# ── Pace compatibility ────────────────────────────────────────────────────────

def score_pace_compatibility(
    roster_pace: float,
    team_pace: Optional[float],
) -> tuple[float, float]:
    """
    Score how well the roster's collective pace tendency aligns with the
    team's actual pace identity.

    Args:
        roster_pace:  Output of roster_pace_profile() — 0-100 roster pace score.
        team_pace:    Output of normalize_team_pace() — 0-100 team pace score.
                      Pass None if no TeamSeasonRatings data is available.

    Returns:
        (alignment_score, pace_modifier)

        alignment_score (0-100):
            50 = neutral / no data.
            100 = perfect pace alignment.
            0 = extreme pace mismatch.

        pace_modifier (-MAX_PACE_MODIFIER_OFF to +MAX_PACE_MODIFIER_OFF):
            Positive = good alignment (small bonus).
            Negative = poor alignment (small penalty).
            0 = neutral (no data or perfect 50/50).

    Notes:
        - Modifier is capped to ±MAX_PACE_MODIFIER_OFF (±2.0 pts).
        - This module returns one raw modifier; engine.py applies the
          offense/defense asymmetry (100% to off, 50% to def).
        - Missing team data produces (50, 0) — truly neutral, no signal.
    """
    if team_pace is None:
        return NEUTRAL_ALIGNMENT_SCORE, NEUTRAL_MODIFIER

    # Distance between roster tendency and team pace identity.
    # Both are on 0-100; max possible distance = 100.
    distance = abs(roster_pace - team_pace)

    # Convert distance to alignment score:
    #   distance=0  → alignment=100 (perfect)
    #   distance=50 → alignment=50  (neutral)
    #   distance=100 → alignment=0  (maximum mismatch)
    alignment_score = max(SCORE_MIN, min(SCORE_MAX, 100.0 - distance))

    # Linear map: alignment=100 → +MAX, alignment=50 → 0, alignment=0 → -MAX
    modifier = (alignment_score - SCORE_MID) / SCORE_MID * MAX_PACE_MODIFIER_OFF

    # Clamp (defensive, should already be within range given the formula)
    modifier = max(-MAX_PACE_MODIFIER_OFF, min(MAX_PACE_MODIFIER_OFF, modifier))

    return alignment_score, modifier
