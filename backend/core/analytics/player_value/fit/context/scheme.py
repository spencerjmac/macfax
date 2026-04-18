"""
Phase 4: Scheme Compatibility Engine.

Infers a team's offensive and defensive scheme identity from TeamSeasonRatings
style signals, then evaluates how well the projected roster's archetype mix
matches those scheme demands.

Scheme tags
───────────
Offensive (5 tags):
  spacing_driven     — efficiency-led offense; needs shooters / spacers
  creator_driven     — ball-movement / low-tov identity; needs creators
  pressure_offense   — foul-drawing offense; needs pressure drivers
  glass_emphasis     — offensive rebounding team; needs off rebounders
  halfcourt_control  — deliberate / disciplined; needs disciplined ball handlers

Defensive (3 tags):
  turnover_forcing   — pressure defense creating opponent turnovers; needs disruptors
  rim_anchored       — paint protection + opponent ORB suppression; needs rim protectors
  disciplined_rebounding — above-average defensive glass; needs bigs / rebounders

Switchable defense is intentionally omitted unless we can cleanly identify it
from Phase 3 switchable_wing signal — noted as TODO for a later iteration.

Tag overlap is allowed and intentional: a team can be both creator_driven and
halfcourt_control (disciplined possession identity).  Tags are independent
signals, not mutually exclusive categories.

Alignment scoring
─────────────────
For each fired scheme tag we:
  1. Compute a roster "fit share" — fraction of top-rotation minutes whose
     players meaningfully satisfy that scheme's archetype demands.
  2. Compare against the minimum threshold in constants.py.
  3. Produce a normalized sub-alignment score (0-100).
The overall off/def alignment score is the weighted average of sub-alignments
for all tags that fired.  Tags that didn't fire don't count (they can't
penalize teams that don't run those schemes).

Missing team data → neutral (50, 0).

Public API
──────────
  infer_off_scheme_tags(team_style: dict) -> dict[str, bool]
  infer_def_scheme_tags(team_style: dict) -> dict[str, bool]
  score_off_scheme_compatibility(
      players: list[PlayerFitInput],
      team_style: dict | None,
  ) -> tuple[float, float]
  score_def_scheme_compatibility(
      players: list[PlayerFitInput],
      team_style: dict | None,
  ) -> tuple[float, float]

  team_style dict keys (all optional, None if missing):
      adj_efg_pct, adj_tov_pct, adj_ftr, adj_orb_pct,
      adj_opp_tov_pct, adj_opp_orb_pct, adj_drb_pct, adj_tempo
"""

from __future__ import annotations

from typing import Optional

from core.analytics.player_value.fit.archetypes import PlayerFitInput
from core.analytics.player_value.fit.context.constants import (
    SCORE_MID,
    SCORE_MIN,
    SCORE_MAX,
    MAX_SCHEME_MODIFIER_OFF,
    MAX_SCHEME_MODIFIER_DEF,
    NEUTRAL_ALIGNMENT_SCORE,
    NEUTRAL_MODIFIER,
    TOP_ROTATION_THRESHOLD,
    # Team-level style thresholds
    SPACING_DRIVEN_EFG_THRESHOLD,
    CREATOR_DRIVEN_TOV_MAX,
    PRESSURE_OFFENSE_FTR_THRESHOLD,
    GLASS_EMPHASIS_ORB_THRESHOLD,
    HALFCOURT_CONTROL_TOV_MAX,
    HALFCOURT_CONTROL_TEMPO_MAX,
    TURNOVER_FORCING_OPP_TOV_THRESHOLD,
    RIM_ANCHORED_DRB_THRESHOLD,
    RIM_ANCHORED_OPP_ORB_MAX,
    DISC_REBOUNDING_DRB_THRESHOLD,
    # Roster thresholds
    ROSTER_SPACING_MIN_SHARE,
    ROSTER_CREATOR_MIN_SHARE,
    ROSTER_PRESSURE_MIN_SHARE,
    ROSTER_GLASS_MIN_SHARE,
    ROSTER_HALFCOURT_LOW_TOV_MAX,
    ROSTER_RIM_PROTECTOR_MIN_SHARE,
    ROSTER_DISRUPTOR_MIN_SHARE,
)


# ── Team scheme tag inference ─────────────────────────────────────────────────

def infer_off_scheme_tags(team_style: dict) -> dict[str, bool]:
    """
    Infer which offensive scheme tags describe a team based on TeamSeasonRatings.

    Args:
        team_style: dict with keys adj_efg_pct, adj_tov_pct, adj_ftr,
                    adj_orb_pct, adj_tempo.  Values may be None.

    Returns:
        Dict mapping tag name → True if that scheme fires.
    """
    efg     = team_style.get("adj_efg_pct")
    tov     = team_style.get("adj_tov_pct")
    ftr     = team_style.get("adj_ftr")
    orb     = team_style.get("adj_orb_pct")
    tempo   = team_style.get("adj_tempo")

    tags: dict[str, bool] = {}

    # spacing_driven: efficient shooting identity
    tags["spacing_driven"] = (
        efg is not None and efg >= SPACING_DRIVEN_EFG_THRESHOLD
    )

    # creator_driven: disciplined ball-movement offense (low tov)
    tags["creator_driven"] = (
        tov is not None and tov <= CREATOR_DRIVEN_TOV_MAX
    )

    # pressure_offense: high foul-drawing rate
    tags["pressure_offense"] = (
        ftr is not None and ftr >= PRESSURE_OFFENSE_FTR_THRESHOLD
    )

    # glass_emphasis: offensive rebounding team
    tags["glass_emphasis"] = (
        orb is not None and orb >= GLASS_EMPHASIS_ORB_THRESHOLD
    )

    # halfcourt_control: disciplined and deliberate
    # Requires BOTH low tov AND slow-to-mid tempo
    tags["halfcourt_control"] = (
        tov is not None and tov <= HALFCOURT_CONTROL_TOV_MAX
        and tempo is not None and tempo <= HALFCOURT_CONTROL_TEMPO_MAX
    )

    return tags


def infer_def_scheme_tags(team_style: dict) -> dict[str, bool]:
    """
    Infer which defensive scheme tags describe a team based on TeamSeasonRatings.

    Args:
        team_style: dict with keys adj_opp_tov_pct, adj_opp_orb_pct,
                    adj_drb_pct.  Values may be None.

    Returns:
        Dict mapping tag name → True if that scheme fires.
    """
    opp_tov = team_style.get("adj_opp_tov_pct")
    opp_orb = team_style.get("adj_opp_orb_pct")
    drb     = team_style.get("adj_drb_pct")

    tags: dict[str, bool] = {}

    # turnover_forcing: active pressure generating opponent turnovers
    tags["turnover_forcing"] = (
        opp_tov is not None and opp_tov >= TURNOVER_FORCING_OPP_TOV_THRESHOLD
    )

    # rim_anchored: strong defensive glass + opponent ORB suppression
    tags["rim_anchored"] = (
        drb is not None and drb >= RIM_ANCHORED_DRB_THRESHOLD
        and opp_orb is not None and opp_orb <= RIM_ANCHORED_OPP_ORB_MAX
    )

    # disciplined_rebounding: at or above average defensive glass
    tags["disciplined_rebounding"] = (
        drb is not None and drb >= DISC_REBOUNDING_DRB_THRESHOLD
    )

    return tags


# ── Roster archetype share calculators ───────────────────────────────────────

def _top_rotation_players(players: list[PlayerFitInput]) -> list[PlayerFitInput]:
    """Filter to players in the top rotation (minutes_share_p2 >= threshold)."""
    return [p for p in players if (p.minutes_share_p2 or 0.0) >= TOP_ROTATION_THRESHOLD]


def _total_minutes(players: list[PlayerFitInput]) -> float:
    return sum(p.minutes_share_p2 or 0.0 for p in players)


def _minutes_share_with_tag(players: list[PlayerFitInput], archetype: str) -> float:
    """
    Fraction of total minutes from players who have a given archetype tag.
    """
    total = _total_minutes(players)
    if total <= 0:
        return 0.0
    tagged = sum(
        p.minutes_share_p2 or 0.0
        for p in players
        if archetype in (p.archetypes or set())
    )
    return tagged / total


def _minutes_share_low_tov(players: list[PlayerFitInput]) -> float:
    """
    Fraction of top-rotation minutes from disciplined ball handlers
    (tov_pg <= ROSTER_HALFCOURT_LOW_TOV_MAX).
    """
    top = _top_rotation_players(players)
    total = _total_minutes(top)
    if total <= 0:
        return 0.0
    disciplined = sum(
        p.minutes_share_p2 or 0.0
        for p in top
        if (p.tov_pg or 0.0) <= ROSTER_HALFCOURT_LOW_TOV_MAX
    )
    return disciplined / total


# ── Sub-alignment scorer (0-100) ──────────────────────────────────────────────

def _sub_alignment_score(roster_share: float, min_share: float) -> float:
    """
    Convert a roster share measurement into a 0-100 alignment score.

    At or above min_share: scores map toward 100 (strong alignment).
    Below min_share: scores map toward 0 (mismatch penalty).

    Formula (linear):
        ratio = roster_share / min_share
        score = clamp(50 + (ratio - 1.0) * 50, 0, 100)

    At ratio=1 (exactly meeting threshold): score=50 (neutral).
    At ratio=2 (double the threshold):      score=100 (great fit).
    At ratio=0 (zero match):                score=0   (poor fit).
    """
    if min_share <= 0:
        return SCORE_MID
    ratio = roster_share / min_share
    score = SCORE_MID + (ratio - 1.0) * SCORE_MID
    return max(SCORE_MIN, min(SCORE_MAX, score))


# ── Scheme compatibility scorers ──────────────────────────────────────────────

def score_off_scheme_compatibility(
    players: list[PlayerFitInput],
    team_style: Optional[dict],
) -> tuple[float, float]:
    """
    Score how well the roster's archetype mix aligns with the team's
    offensive scheme identity.

    Args:
        players:    List of PlayerFitInput (archetypes must be populated).
        team_style: Dict of team style signals from TeamSeasonRatings.
                    Pass None if no style data available.

    Returns:
        (alignment_score 0-100, off_scheme_modifier -3 to +3)

        alignment_score=50 and modifier=0 when no style data exists (neutral).
    """
    if not team_style or not players:
        return NEUTRAL_ALIGNMENT_SCORE, NEUTRAL_MODIFIER

    tags = infer_off_scheme_tags(team_style)
    active_tags = [tag for tag, fired in tags.items() if fired]

    if not active_tags:
        # Team has style data but no scheme fires — neutral outcome
        return NEUTRAL_ALIGNMENT_SCORE, NEUTRAL_MODIFIER

    top = _top_rotation_players(players)
    if not top:
        return NEUTRAL_ALIGNMENT_SCORE, NEUTRAL_MODIFIER

    sub_scores: list[float] = []

    for tag in active_tags:
        if tag == "spacing_driven":
            share = _minutes_share_with_tag(top, "spacer")
            sub_scores.append(_sub_alignment_score(share, ROSTER_SPACING_MIN_SHARE))

        elif tag == "creator_driven":
            # Count both primary and secondary creators
            total = _total_minutes(top)
            if total > 0:
                creator_mins = sum(
                    p.minutes_share_p2 or 0.0
                    for p in top
                    if ("primary_creator" in (p.archetypes or set()))
                    or ("secondary_creator" in (p.archetypes or set()))
                )
                share = creator_mins / total
            else:
                share = 0.0
            sub_scores.append(_sub_alignment_score(share, ROSTER_CREATOR_MIN_SHARE))

        elif tag == "pressure_offense":
            share = _minutes_share_with_tag(top, "pressure_driver")
            sub_scores.append(_sub_alignment_score(share, ROSTER_PRESSURE_MIN_SHARE))

        elif tag == "glass_emphasis":
            share = _minutes_share_with_tag(top, "off_rebounder")
            sub_scores.append(_sub_alignment_score(share, ROSTER_GLASS_MIN_SHARE))

        elif tag == "halfcourt_control":
            share = _minutes_share_low_tov(top)
            sub_scores.append(_sub_alignment_score(share, 0.40))
            # 40% threshold for halfcourt_control: most of rotation should be disciplined

    # Average of fired-tag sub-scores
    alignment_score = sum(sub_scores) / len(sub_scores) if sub_scores else SCORE_MID
    alignment_score = max(SCORE_MIN, min(SCORE_MAX, alignment_score))

    # Linear modifier map: 50 → 0, 100 → +MAX, 0 → -MAX
    modifier = (alignment_score - SCORE_MID) / SCORE_MID * MAX_SCHEME_MODIFIER_OFF
    modifier = max(-MAX_SCHEME_MODIFIER_OFF, min(MAX_SCHEME_MODIFIER_OFF, modifier))

    return alignment_score, modifier


def score_def_scheme_compatibility(
    players: list[PlayerFitInput],
    team_style: Optional[dict],
) -> tuple[float, float]:
    """
    Score how well the roster's archetype mix aligns with the team's
    defensive scheme identity.

    Args:
        players:    List of PlayerFitInput (archetypes must be populated).
        team_style: Dict of team style signals from TeamSeasonRatings.
                    Pass None if no style data available.

    Returns:
        (alignment_score 0-100, def_scheme_modifier -3 to +3)
    """
    if not team_style or not players:
        return NEUTRAL_ALIGNMENT_SCORE, NEUTRAL_MODIFIER

    tags = infer_def_scheme_tags(team_style)
    active_tags = [tag for tag, fired in tags.items() if fired]

    if not active_tags:
        return NEUTRAL_ALIGNMENT_SCORE, NEUTRAL_MODIFIER

    top = _top_rotation_players(players)
    if not top:
        return NEUTRAL_ALIGNMENT_SCORE, NEUTRAL_MODIFIER

    sub_scores: list[float] = []

    for tag in active_tags:
        if tag == "turnover_forcing":
            share = _minutes_share_with_tag(top, "disruptor")
            sub_scores.append(_sub_alignment_score(share, ROSTER_DISRUPTOR_MIN_SHARE))

        elif tag == "rim_anchored":
            share = _minutes_share_with_tag(top, "rim_protector")
            sub_scores.append(_sub_alignment_score(share, ROSTER_RIM_PROTECTOR_MIN_SHARE))

        elif tag == "disciplined_rebounding":
            # Any role benefits defensive rebounding — use bigs (role_bucket=Big)
            # as the primary signal (they own the glass)
            total = _total_minutes(top)
            if total > 0:
                big_mins = sum(
                    p.minutes_share_p2 or 0.0
                    for p in top
                    if (p.role_bucket or "Wing") == "Big"
                )
                share = big_mins / total
            else:
                share = 0.0
            # Threshold: ≥20% of minutes from bigs for "disciplined rebounding"
            sub_scores.append(_sub_alignment_score(share, 0.20))

    alignment_score = sum(sub_scores) / len(sub_scores) if sub_scores else SCORE_MID
    alignment_score = max(SCORE_MIN, min(SCORE_MAX, alignment_score))

    modifier = (alignment_score - SCORE_MID) / SCORE_MID * MAX_SCHEME_MODIFIER_DEF
    modifier = max(-MAX_SCHEME_MODIFIER_DEF, min(MAX_SCHEME_MODIFIER_DEF, modifier))

    return alignment_score, modifier
