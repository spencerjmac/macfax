"""
Phase 4: Contextual Fit Engine — main entry point.

Combines pace compatibility and scheme compatibility into a small, controlled
contextual modifier that adjusts Phase 3 offensive and defensive fit scores.

This is the single entry point for Phase 4.  Everything below is stateless.
The service layer (service.py) handles DB I/O and calls this engine.

Design
──────
Phase 4 is a secondary layer on top of Phase 3 fit scores.  The overall
adjustment budget is ±5 pts per side (off or def), composed of:

  off_contextual_modifier = pace_modifier (100% weight) + off_scheme_modifier
  def_contextual_modifier = pace_modifier (50% weight)  + def_scheme_modifier

Caps are enforced in order:
  1. Raw pace_modifier clamped to ±MAX_PACE_MODIFIER_OFF (±2.0)
  2. off/def scheme modifiers clamped to ±MAX_SCHEME_MODIFIER (±3.0)
  3. Combined contextual totals clamped to ±MAX_CONTEXTUAL_TOTAL (±5.0)

Input
─────
  ContextualFitInput:
    players:        list[PlayerFitInput]   — archetypes must already be populated
    phase3_off:     float                  — Phase 3 offensive_fit_score (0-100)
    phase3_def:     float                  — Phase 3 defensive_fit_score (0-100)
    phase3_overall: float                  — Phase 3 overall_fit_score (0-100)
    team_style:     dict | None            — loaded from TeamSeasonRatings (see below)

  team_style keys (all optional, None = missing):
    adj_tempo, adj_efg_pct, adj_tov_pct, adj_ftr, adj_orb_pct,
    adj_opp_tov_pct, adj_opp_orb_pct, adj_drb_pct

Output
──────
  ContextualFitResult:
    Alignment scores     (0-100, 50=neutral)
    Raw modifiers        (signed float)
    Combined contextual  (clamped ±5)
    Adjusted fit scores  (Phase 3 + contextual, clipped 0-100)
    has_team_style_data  (bool flagging data availability)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ncaa.analytics.player_value.fit.archetypes import PlayerFitInput
from ncaa.analytics.player_value.fit.context.constants import (
    SCORE_MIN,
    SCORE_MAX,
    SCORE_MID,
    MAX_PACE_MODIFIER_OFF,
    MAX_PACE_MODIFIER_DEF,
    MAX_SCHEME_MODIFIER_OFF,
    MAX_SCHEME_MODIFIER_DEF,
    MAX_CONTEXTUAL_TOTAL,
    NEUTRAL_ALIGNMENT_SCORE,
    NEUTRAL_MODIFIER,
)
from ncaa.analytics.player_value.fit.context.pace import (
    roster_pace_profile,
    normalize_team_pace,
    score_pace_compatibility,
)
from ncaa.analytics.player_value.fit.context.scheme import (
    score_off_scheme_compatibility,
    score_def_scheme_compatibility,
)


# ── Output dataclass ──────────────────────────────────────────────────────────

@dataclass
class ContextualFitResult:
    """
    Full Phase 4 contextual fit output.

    All alignment scores: 0-100 (50 = neutral, no mismatch or bonus).
    All raw modifiers: signed float (pos = bonus, neg = penalty).
    Adjusted scores: Phase 3 score + contextual modifier, clipped to 0-100.
    """

    # ── Pace ─────────────────────────────────────────────────────────────────
    pace_alignment_score: float = SCORE_MID    # 0-100
    pace_modifier:        float = 0.0          # -2.0 to +2.0 (raw; engine splits off/def)

    # ── Offensive scheme ─────────────────────────────────────────────────────
    off_scheme_alignment_score: float = SCORE_MID
    off_scheme_modifier:        float = 0.0    # -3.0 to +3.0

    # ── Defensive scheme ─────────────────────────────────────────────────────
    def_scheme_alignment_score: float = SCORE_MID
    def_scheme_modifier:        float = 0.0    # -3.0 to +3.0

    # ── Combined contextual modifiers (clamped ±MAX_CONTEXTUAL_TOTAL) ────────
    off_contextual_modifier: float = 0.0       # pace(100%) + off_scheme, clamped ±5
    def_contextual_modifier: float = 0.0       # pace(50%)  + def_scheme, clamped ±5

    # ── Adjusted fit scores (Phase 3 + contextual, clipped 0-100) ────────────
    adjusted_off_fit:     float = SCORE_MID
    adjusted_def_fit:     float = SCORE_MID
    adjusted_overall_fit: float = SCORE_MID

    # ── Data quality flag ─────────────────────────────────────────────────────
    has_team_style_data: bool = False


# ── Helper: clamp ─────────────────────────────────────────────────────────────

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ── Main entry point ──────────────────────────────────────────────────────────

def score_contextual_fit(
    players:        list[PlayerFitInput],
    phase3_off:     float,
    phase3_def:     float,
    phase3_overall: float,
    team_style:     Optional[dict],
) -> ContextualFitResult:
    """
    Compute Phase 4 contextual fit for a team roster.

    Fully stateless.  Archetypes on each PlayerFitInput must be populated
    before calling (the Phase 3 engine does this; call tag_archetypes()
    beforehand if running Phase 4 standalone).

    Args:
        players:        One PlayerFitInput per rostered player.
                        minutes_share_p2 and archetypes must be set.
        phase3_off:     Offensive fit score from Phase 3 (0-100).
        phase3_def:     Defensive fit score from Phase 3 (0-100).
        phase3_overall: Overall fit score from Phase 3 (0-100).
        team_style:     Dict of TeamSeasonRatings fields (see module doc).
                        Pass None if no style data is available for this team.

    Returns:
        ContextualFitResult with all scores, modifiers, and adjusted fits.
    """
    result = ContextualFitResult(
        adjusted_off_fit=phase3_off,
        adjusted_def_fit=phase3_def,
        adjusted_overall_fit=phase3_overall,
    )

    if not players:
        return result

    has_data = bool(team_style)
    result.has_team_style_data = has_data

    # ── Step 1: Pace compatibility ─────────────────────────────────────────
    roster_pace = roster_pace_profile(players)

    if has_data and team_style.get("adj_tempo") is not None:
        team_pace = normalize_team_pace(float(team_style["adj_tempo"]))
    else:
        team_pace = None  # triggers neutral output

    pace_alignment, pace_mod_raw = score_pace_compatibility(roster_pace, team_pace)
    pace_mod_raw = _clamp(pace_mod_raw, -MAX_PACE_MODIFIER_OFF, MAX_PACE_MODIFIER_OFF)

    result.pace_alignment_score = pace_alignment
    result.pace_modifier         = pace_mod_raw

    # ── Step 2: Offensive scheme compatibility ─────────────────────────────
    off_align, off_scheme_mod = score_off_scheme_compatibility(players, team_style)
    off_scheme_mod = _clamp(off_scheme_mod, -MAX_SCHEME_MODIFIER_OFF, MAX_SCHEME_MODIFIER_OFF)

    result.off_scheme_alignment_score = off_align
    result.off_scheme_modifier         = off_scheme_mod

    # ── Step 3: Defensive scheme compatibility ─────────────────────────────
    def_align, def_scheme_mod = score_def_scheme_compatibility(players, team_style)
    def_scheme_mod = _clamp(def_scheme_mod, -MAX_SCHEME_MODIFIER_DEF, MAX_SCHEME_MODIFIER_DEF)

    result.def_scheme_alignment_score = def_align
    result.def_scheme_modifier         = def_scheme_mod

    # ── Step 4: Assemble contextual modifiers ─────────────────────────────
    # Pace biased toward offense: 100% to off, 50% to def
    pace_contribution_off = pace_mod_raw                          # full pace modifier
    pace_contribution_def = pace_mod_raw * MAX_PACE_MODIFIER_DEF / MAX_PACE_MODIFIER_OFF
    # MAX_PACE_MODIFIER_DEF=1.0, MAX_PACE_MODIFIER_OFF=2.0 → 50% weight for def

    off_contextual = pace_contribution_off + off_scheme_mod
    def_contextual = pace_contribution_def + def_scheme_mod

    # Apply outer cap ±5
    result.off_contextual_modifier = _clamp(off_contextual, -MAX_CONTEXTUAL_TOTAL, MAX_CONTEXTUAL_TOTAL)
    result.def_contextual_modifier = _clamp(def_contextual, -MAX_CONTEXTUAL_TOTAL, MAX_CONTEXTUAL_TOTAL)

    # ── Step 5: Adjusted fit scores ────────────────────────────────────────
    result.adjusted_off_fit = _clamp(
        phase3_off + result.off_contextual_modifier, SCORE_MIN, SCORE_MAX
    )
    result.adjusted_def_fit = _clamp(
        phase3_def + result.def_contextual_modifier, SCORE_MIN, SCORE_MAX
    )

    # Overall: recompute from adjusted off/def using Phase 3 weights
    from ncaa.analytics.player_value.fit.constants import OFF_WEIGHT, DEF_WEIGHT
    result.adjusted_overall_fit = _clamp(
        OFF_WEIGHT * result.adjusted_off_fit + DEF_WEIGHT * result.adjusted_def_fit,
        SCORE_MIN, SCORE_MAX,
    )

    return result
