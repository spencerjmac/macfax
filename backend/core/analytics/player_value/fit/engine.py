"""
Roster Fit Model — Main engine (Phase 3).

Entry point: score_roster_fit()

This module:
  1. Tags per-player archetypes (calls archetypes.tag_archetypes).
  2. Calls the offensive and defensive fit scorers.
  3. Computes the overall fit score.
  4. Builds the structured diagnostics object.

Input / output are fully stateless — no DB access.
The service layer (service.py) handles DB I/O and calls this engine.

Output: RosterFitResult — a dataclass holding all scores and diagnostics,
suitable for serialization to JSON or persistence in TeamRosterFit.

Diagnostics format
──────────────────
  offensive_strengths  / offensive_weaknesses   — top N subcomponent names
  defensive_strengths  / defensive_weaknesses   — top N subcomponent names
  triggered_penalties                           — list of (label, pts) that fired
  fit_summary                                   — compact structured dict for UI use:
    {
      "offensive_fit":   <score>,
      "defensive_fit":   <score>,
      "overall_fit":     <score>,
      "off_subcomponents": { ... },
      "def_subcomponents": { ... },
      "top_off_strengths":  [...],
      "top_off_weaknesses": [...],
      "top_def_strengths":  [...],
      "top_def_weaknesses": [...],
      "penalties": { "offense": [...], "defense": [...] },
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.analytics.player_value.fit.archetypes import (
    PlayerFitInput,
    SeasonRefs,
    DEFAULT_REFS,
    tag_archetypes,
)
from core.analytics.player_value.fit.offense import (
    score_offensive_fit,
    OffensiveFitResult,
)
from core.analytics.player_value.fit.defense import (
    score_defensive_fit,
    DefensiveFitResult,
)
from core.analytics.player_value.fit.constants import (
    SCORE_MIN, SCORE_MAX, SCORE_MID,
    OFF_WEIGHT, DEF_WEIGHT,
    N_DIAGNOSTIC_ITEMS,
)


# ── Output dataclass ──────────────────────────────────────────────────────────

@dataclass
class RosterFitResult:
    """
    Full roster fit output.

    team_id and season_year are metadata; the engine itself is stateless.
    All scores are on 0-100 (50 = D1 average).
    """
    # Metadata (populated by service layer)
    team_id:     Optional[int] = None
    season_year: Optional[int] = None

    # Overall
    overall_fit_score:   float = 50.0
    offensive_fit_score: float = 50.0
    defensive_fit_score: float = 50.0

    # Offensive subcomponents
    creation_fit:         float = 50.0
    shooting_fit:         float = 50.0
    ball_security_fit:    float = 50.0
    finishing_fit:        float = 50.0
    pressure_fit:         float = 50.0
    off_rebounding_fit:   float = 50.0
    role_balance_off_fit: float = 50.0

    # Defensive subcomponents
    rim_protection_fit:    float = 50.0
    def_rebounding_fit:    float = 50.0
    disruption_fit:        float = 50.0
    foul_discipline_fit:   float = 50.0
    perimeter_defense_fit: float = 50.0
    size_coverage_fit:     float = 50.0
    mobility_fit:          float = 50.0
    role_balance_def_fit:  float = 50.0

    # Structural penalties
    off_total_penalty: float = 0.0
    def_total_penalty: float = 0.0
    off_penalties: list = field(default_factory=list)   # list[tuple[str, float]]
    def_penalties: list = field(default_factory=list)

    # Diagnostics
    offensive_strengths:  list = field(default_factory=list)   # list[str]
    offensive_weaknesses: list = field(default_factory=list)
    defensive_strengths:  list = field(default_factory=list)
    defensive_weaknesses: list = field(default_factory=list)

    # Compact summary dict for UI / serialization
    fit_summary: dict = field(default_factory=dict)


# ── Diagnostic helpers ────────────────────────────────────────────────────────

def _rank_subcomponents(subcomponents: dict[str, float]) -> tuple[list[str], list[str]]:
    """
    Return top-N strengths (highest scores) and top-N weaknesses (lowest scores).
    """
    sorted_items = sorted(subcomponents.items(), key=lambda kv: kv[1], reverse=True)
    strengths  = [k for k, _ in sorted_items[:N_DIAGNOSTIC_ITEMS]]
    weaknesses = [k for k, _ in sorted_items[-N_DIAGNOSTIC_ITEMS:][::-1]]
    return strengths, weaknesses


# ── Main entry point ──────────────────────────────────────────────────────────

def score_roster_fit(
    players:    list[PlayerFitInput],
    refs:       SeasonRefs = DEFAULT_REFS,
    team_id:    Optional[int] = None,
    season_year: Optional[int] = None,
) -> RosterFitResult:
    """
    Compute the full roster fit score for a team.

    This function is the single entry point for all roster fit computation.
    It is fully stateless and can be called for:
      - Baseline team allocations
      - Hypothetical / what-if rosters
      - Transfer-portal scenarios

    Steps:
      1. Tag internal archetypes for every player.
      2. Score offensive fit (7 subcomponents + structural penalties).
      3. Score defensive fit (8 subcomponents + structural penalties).
      4. Combine into overall fit score.
      5. Build diagnostics.

    Args:
        players:     One PlayerFitInput per rostered player.
                     minutes_share_p2 must be set (Phase 2 output).
        refs:        Season-relative reference values.
                     Falls back to D1 hard-coded constants if not provided.
        team_id:     Optional team identifier for persistence.
        season_year: Optional projected season year for persistence.

    Returns:
        RosterFitResult with all scores, subcomponents, penalties, and diagnostics.
    """
    if not players:
        return RosterFitResult(team_id=team_id, season_year=season_year)

    # ── Step 1: Tag archetypes ─────────────────────────────────────────────
    for p in players:
        p.archetypes = tag_archetypes(p)

    # ── Step 2: Score offense ──────────────────────────────────────────────
    off: OffensiveFitResult = score_offensive_fit(players, refs)

    # ── Step 3: Score defense ──────────────────────────────────────────────
    def_: DefensiveFitResult = score_defensive_fit(players, refs)

    # ── Step 4: Overall fit score ──────────────────────────────────────────
    overall = max(SCORE_MIN, min(SCORE_MAX,
        OFF_WEIGHT * off.offensive_fit_score + DEF_WEIGHT * def_.defensive_fit_score
    ))

    # ── Step 5: Diagnostics ────────────────────────────────────────────────
    off_subs = {
        "creation_fit":         off.creation_fit,
        "shooting_fit":         off.shooting_fit,
        "ball_security_fit":    off.ball_security_fit,
        "finishing_fit":        off.finishing_fit,
        "pressure_fit":         off.pressure_fit,
        "off_rebounding_fit":   off.off_rebounding_fit,
        "role_balance_off_fit": off.role_balance_off_fit,
    }
    def_subs = {
        "rim_protection_fit":    def_.rim_protection_fit,
        "def_rebounding_fit":    def_.def_rebounding_fit,
        "disruption_fit":        def_.disruption_fit,
        "foul_discipline_fit":   def_.foul_discipline_fit,
        "perimeter_defense_fit": def_.perimeter_defense_fit,
        "size_coverage_fit":     def_.size_coverage_fit,
        "mobility_fit":          def_.mobility_fit,
        "role_balance_def_fit":  def_.role_balance_def_fit,
    }

    off_strengths, off_weaknesses = _rank_subcomponents(off_subs)
    def_strengths, def_weaknesses = _rank_subcomponents(def_subs)

    fit_summary = {
        "offensive_fit":      round(off.offensive_fit_score, 2),
        "defensive_fit":      round(def_.defensive_fit_score, 2),
        "overall_fit":        round(overall, 2),
        "off_subcomponents":  {k: round(v, 2) for k, v in off_subs.items()},
        "def_subcomponents":  {k: round(v, 2) for k, v in def_subs.items()},
        "top_off_strengths":  off_strengths,
        "top_off_weaknesses": off_weaknesses,
        "top_def_strengths":  def_strengths,
        "top_def_weaknesses": def_weaknesses,
        "penalties": {
            "offense": [(l, round(p, 2)) for l, p in off.structural_penalties],
            "defense": [(l, round(p, 2)) for l, p in def_.structural_penalties],
        },
    }

    return RosterFitResult(
        team_id=team_id,
        season_year=season_year,

        overall_fit_score=round(overall, 2),
        offensive_fit_score=round(off.offensive_fit_score, 2),
        defensive_fit_score=round(def_.defensive_fit_score, 2),

        creation_fit=off.creation_fit,
        shooting_fit=off.shooting_fit,
        ball_security_fit=off.ball_security_fit,
        finishing_fit=off.finishing_fit,
        pressure_fit=off.pressure_fit,
        off_rebounding_fit=off.off_rebounding_fit,
        role_balance_off_fit=off.role_balance_off_fit,

        rim_protection_fit=def_.rim_protection_fit,
        def_rebounding_fit=def_.def_rebounding_fit,
        disruption_fit=def_.disruption_fit,
        foul_discipline_fit=def_.foul_discipline_fit,
        perimeter_defense_fit=def_.perimeter_defense_fit,
        size_coverage_fit=def_.size_coverage_fit,
        mobility_fit=def_.mobility_fit,
        role_balance_def_fit=def_.role_balance_def_fit,

        off_total_penalty=off.total_penalty,
        def_total_penalty=def_.total_penalty,
        off_penalties=off.structural_penalties,
        def_penalties=def_.structural_penalties,

        offensive_strengths=off_strengths,
        offensive_weaknesses=off_weaknesses,
        defensive_strengths=def_strengths,
        defensive_weaknesses=def_weaknesses,

        fit_summary=fit_summary,
    )
