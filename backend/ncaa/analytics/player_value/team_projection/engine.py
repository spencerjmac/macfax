"""
Phase 5: Team Projection Engine — pure, stateless.

Primary entry point: ``project_team(players, roster_fit, d1_context)``.

No Django imports. All DB I/O lives in service.py.
Rank assignment is deferred to service.py (requires all teams computed first).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .constants import (
    COACHING_CONTINUITY_HOOK_ENABLED,
    COACHING_UNCERTAINTY_ADD,
    CONTINUITY_BPR_BLEND_WEIGHT,
    CONTINUITY_BPR_REPLACEMENT_FLOOR,
    CONTINUITY_NEUTRAL_FRACTION,
    FIT_MAX_ADJ_DEF,
    FIT_MAX_ADJ_OFF,
    FIT_TO_RATING_DEF,
    FIT_TO_RATING_OFF,
    MAX_CONTINUITY_ADJ_DEF,
    MAX_CONTINUITY_ADJ_OFF,
    SLOPE_DEF,
    SLOPE_OFF,
    TRANSFER_FIT_RISK_NO_STYLE_DEFAULT,
    TRANSFER_FIT_RISK_WEIGHT,
    UNCERTAINTY_BASE,
    UNCERTAINTY_CONTINUITY_WEIGHT,
    UNCERTAINTY_MAX,
    UNCERTAINTY_MIN,
    UNCERTAINTY_NEWCOMER_WEIGHT,
    UNCERTAINTY_NO_STYLE_DATA,
    UNCERTAINTY_PLAYER_SIGNAL_WEIGHT,
    UNCERTAINTY_SIGMA_MAX,
    UNCERTAINTY_SIGMA_SCALE,
    SIGMA_D_INTERCEPT,
    SIGMA_D_SLOPE,
    SIGMA_EM_INTERCEPT,
    SIGMA_EM_MAX,
    SIGMA_EM_SLOPE,
    SIGMA_O_INTERCEPT,
    SIGMA_O_SLOPE,
)

# ── Input dataclasses ─────────────────────────────────────────────────────────


@dataclass
class PlayerProjectionInput:
    """One player's Phase 1+2 projection data."""

    player_id: int
    projected_obpr: float
    projected_dbpr: float
    projected_bpr: float
    minutes_share_p2: float       # Phase 2 allocated share; team sums ≈5.0
    recruitment_type: str         # 'returner' | 'transfer' | 'newcomer'
    projection_uncertainty: float  # 0-1


@dataclass
class RosterFitInput:
    """Phase 3+4 roster-fit scores for the team (0-100 scale, 50 = D1 avg)."""

    offensive_fit_score: float   # Phase 3 raw
    defensive_fit_score: float   # Phase 3 raw
    adjusted_off_fit: float      # Phase 4 contextually adjusted
    adjusted_def_fit: float      # Phase 4 contextually adjusted
    has_team_style_data: bool    # False → all Phase 4 modifiers are 0


@dataclass
class D1Context:
    """
    Season-level D1 context for centering and calibration.

    league_mean_base_off / league_mean_base_def are computed from all projected
    teams in the same season so that an average-talent team maps exactly to
    D1 average ratings (removes systematic upward bias from player selection).
    """

    avg_adj_o: float             # D1 average adj_o (from NationalAverages)
    avg_adj_d: float             # D1 average adj_d (from TeamSeasonRatings mean)
    league_mean_base_off: float  # mean of team-level base_off across all teams
    league_mean_base_def: float  # mean of team-level base_def across all teams
    n_projected_teams: int       # total teams with projections


# ── Output dataclass ──────────────────────────────────────────────────────────


@dataclass
class TeamProjectionResult:
    """
    Full team projection. Rank fields are None until service.py assigns them
    after all teams are projected (two-pass architecture).
    """

    # ─ Base aggregates ──────────────────────────────────────────────────────
    base_team_offense: float
    base_team_defense: float
    base_team_roster_strength: float

    # ─ Continuity ───────────────────────────────────────────────────────────
    returner_minutes_fraction: float   # 0-1 (minutes-based; backward compat)
    continuity_score: float            # 0-100  (= returner_minutes_fraction × 100)
    continuity_adjustment_off: float
    continuity_adjustment_def: float

    # ─ Fit adjustments ──────────────────────────────────────────────────────
    fit_adjustment_off: float
    fit_adjustment_def: float

    # ─ Coaching (placeholder, always 0.0) ───────────────────────────────────
    coaching_continuity_adjustment: float

    # ─ Projected ratings ────────────────────────────────────────────────────
    projected_adj_o: float
    projected_adj_d: float
    projected_adj_em: float

    # ─ Uncertainty + confidence bands ───────────────────────────────────────
    team_projection_uncertainty: float   # 0-1
    projected_adj_o_low: float
    projected_adj_o_high: float
    projected_adj_d_low: float
    projected_adj_d_high: float
    projected_adj_em_low: float
    projected_adj_em_high: float

    # ─ Ranks (assigned by service.py) ───────────────────────────────────────
    projected_national_rank: Optional[int] = None
    projected_offense_rank: Optional[int] = None
    projected_defense_rank: Optional[int] = None
    national_rank_range_low: Optional[int] = None   # best (lowest) rank estimate
    national_rank_range_high: Optional[int] = None  # worst (highest) rank estimate
    offense_rank_range_low: Optional[int] = None
    offense_rank_range_high: Optional[int] = None
    defense_rank_range_low: Optional[int] = None
    defense_rank_range_high: Optional[int] = None

    # ─ Phase 6: BPR-weighted stability diagnostics ──────────────────────────
    # These are DIAGNOSTIC ONLY — they do not directly shift the projected mean.
    # The continuity adjustment above is driven by continuity_value_score (the
    # BPR-weighted blend), which IS allowed to affect the rating because it
    # captures execution stability (not arbitrary talent bonuses).
    #
    # Default 0.0 so that existing test fixtures (which construct
    # TeamProjectionResult without these fields) remain valid without changes.
    returner_bpr_fraction: float = 0.0       # 0-1, fraction of BPR-weighted output from returners
    transfer_minutes_fraction: float = 0.0   # 0-1, fraction of minutes from transfers
    transfer_bpr_fraction: float = 0.0       # 0-1, fraction of BPR-weighted output from transfers
    transfer_dependence_score: float = 0.0   # 0-100 (= transfer_bpr_fraction × 100)
    continuity_value_score: float = 0.0      # 0-100, BPR-weighted blend (drives continuity adj)

    # ─ Phase 6b: Transfer fit-risk ──────────────────────────────────────────
    # Interaction of transfer dependence × fit shortfall.  Pure uncertainty
    # signal — does NOT shift base_team_offense / defense or mean ratings.
    transfer_fit_risk_score: float = 0.0    # 0-1; feeds TRANSFER_FIT_RISK_WEIGHT into uncertainty

    # ─ Coaching (Sprint 5) ──────────────────────────────────────────────────
    is_first_year_coach: bool = False          # from TeamSeasonStats
    coaching_uncertainty_add: float = 0.0     # COACHING_UNCERTAINTY_ADD when is_first_year_coach

    # ─ Diagnostics ──────────────────────────────────────────────────────────
    projection_summary: dict = field(default_factory=dict)
    driver_breakdown: list[dict] = field(default_factory=list)


# ── Public API ────────────────────────────────────────────────────────────────


def project_team(
    players: list[PlayerProjectionInput],
    roster_fit: Optional[RosterFitInput],
    d1_context: D1Context,
    is_first_year_coach: bool = False,
) -> TeamProjectionResult:
    """
    Project a team's season performance from Phase 1/2/3/4 inputs.

    Backbone formula (dominates all modifiers):
      base_off = Σ(minutes_share × projected_obpr)
      base_def = Σ(minutes_share × projected_dbpr)

      projected_adj_o = D1_avg + SLOPE_OFF × (base_off − league_mean_off)
                       + continuity_adj_off + fit_adj_off
      projected_adj_d = D1_avg − SLOPE_DEF × (base_def − league_mean_def)
                       − continuity_adj_def − fit_adj_def

    Modifier caps (off: ±4.0 total, def: ±4.0 total) are small relative to
    the roster-talent component that can span ±20+ pts.

    Rank fields are left as None — service.py sets them after sorting all teams.
    """
    if not players:
        return _empty_result(d1_context)

    # 1. Base aggregates
    base_off, base_def, base_str = _compute_base_aggregates(players)

    # 2. Continuity (Phase 6: returns _ContinuityProfile with BPR-weighted fields)
    cont = _compute_continuity(players)

    # 3. Fit adjustments from Phase 3+4
    fit_adj_off, fit_adj_def = _compute_fit_adjustments(roster_fit)

    # 4. Coaching continuity (mean: always 0; uncertainty: +COACHING_UNCERTAINTY_ADD for first-year)
    coaching_adj = 0.0   # mean adjustment reserved for future sprint
    coaching_uncertainty_add = (
        COACHING_UNCERTAINTY_ADD
        if COACHING_CONTINUITY_HOOK_ENABLED and is_first_year_coach
        else 0.0
    )

    # 5. Translate base aggregates to projected ratings (centered on D1 avg)
    raw_adj_o = d1_context.avg_adj_o + SLOPE_OFF * (base_off - d1_context.league_mean_base_off)
    raw_adj_d = d1_context.avg_adj_d - SLOPE_DEF * (base_def - d1_context.league_mean_base_def)

    # All adjustments push adj_o up (good) and adj_d down (good)
    projected_adj_o = raw_adj_o + cont.continuity_adjustment_off + fit_adj_off + coaching_adj
    projected_adj_d = raw_adj_d - cont.continuity_adjustment_def - fit_adj_def - coaching_adj
    projected_adj_em = projected_adj_o - projected_adj_d

    # 6. Uncertainty → confidence bands
    newcomer_frac = _compute_newcomer_fraction(players)

    # Minutes-weighted average of per-player projection_uncertainty (the most direct signal)
    total_min_share = sum(p.minutes_share_p2 for p in players)
    weighted_player_unc = (
        sum(p.minutes_share_p2 * p.projection_uncertainty for p in players) / total_min_share
        if total_min_share > 0 else 0.5
    )

    # Phase 6b: transfer fit-risk (interaction of dependence × fit shortfall)
    transfer_fit_risk = _compute_transfer_fit_risk(
        transfer_dependence_score=cont.transfer_dependence_score,
        roster_fit=roster_fit,
    )

    # Phase 6: pass continuity_value_score so uncertainty uses BPR-weighted signal
    uncertainty = _compute_uncertainty(
        cont.returner_minutes_fraction,
        newcomer_frac,
        roster_fit,
        weighted_player_unc,
        continuity_value_score=cont.continuity_value_score,
        transfer_fit_risk=transfer_fit_risk,
        coaching_uncertainty_add=coaching_uncertainty_add,
    )
    sigma_o_pts = sigma_o(uncertainty)
    sigma_d_pts = sigma_d(uncertainty)
    sigma_em_pts = sigma_em(uncertainty)

    result = TeamProjectionResult(
        base_team_offense=base_off,
        base_team_defense=base_def,
        base_team_roster_strength=base_str,
        returner_minutes_fraction=cont.returner_minutes_fraction,
        continuity_score=cont.continuity_score,
        continuity_adjustment_off=cont.continuity_adjustment_off,
        continuity_adjustment_def=cont.continuity_adjustment_def,
        returner_bpr_fraction=cont.returner_bpr_fraction,
        transfer_minutes_fraction=cont.transfer_minutes_fraction,
        transfer_bpr_fraction=cont.transfer_bpr_fraction,
        transfer_dependence_score=cont.transfer_dependence_score,
        continuity_value_score=cont.continuity_value_score,
        transfer_fit_risk_score=transfer_fit_risk,
        fit_adjustment_off=fit_adj_off,
        fit_adjustment_def=fit_adj_def,
        coaching_continuity_adjustment=coaching_adj,
        is_first_year_coach=is_first_year_coach,
        coaching_uncertainty_add=coaching_uncertainty_add,
        projected_adj_o=projected_adj_o,
        projected_adj_d=projected_adj_d,
        projected_adj_em=projected_adj_em,
        team_projection_uncertainty=uncertainty,
        projected_adj_o_low=projected_adj_o - sigma_o_pts,
        projected_adj_o_high=projected_adj_o + sigma_o_pts,
        projected_adj_d_low=projected_adj_d - sigma_d_pts,
        projected_adj_d_high=projected_adj_d + sigma_d_pts,
        projected_adj_em_low=projected_adj_em - sigma_em_pts,
        projected_adj_em_high=projected_adj_em + sigma_em_pts,
    )

    result.driver_breakdown = _build_driver_breakdown(result, d1_context)
    result.projection_summary = _build_summary(result)

    return result


# ── Internal helpers ─────────────────────────────────────────────────────────


def _compute_base_aggregates(
    players: list[PlayerProjectionInput],
) -> tuple[float, float, float]:
    """Return (base_off, base_def, base_str) as weighted sums of BPR × min_share."""
    base_off = sum(p.minutes_share_p2 * p.projected_obpr for p in players)
    base_def = sum(p.minutes_share_p2 * p.projected_dbpr for p in players)
    base_str = sum(p.minutes_share_p2 * p.projected_bpr for p in players)
    return base_off, base_def, base_str


def _compute_continuity(
    players: list[PlayerProjectionInput],
) -> "_ContinuityProfile":
    """
    Compute stability profile for the roster.

    Phase 6 refinement: continuity_value_score is a BPR-weighted blend of the
    returner minutes fraction and the returner BPR fraction.  Returning your key
    contributors matters more than returning bench filler.

    BPR values are shifted above CONTINUITY_BPR_REPLACEMENT_FLOOR before
    computing BPR-share fractions so that negative-BPR players do not invert
    the denominator or produce nonsensical shares.

    The continuity adjustment (cont_adj_off / cont_adj_def) uses
    continuity_value_score, making it sensitive to TALENT continuity, not just
    headcount continuity.

    Returner/transfer BPR fractions are DIAGNOSTIC ONLY — they do not add a
    direct mean-talent bonus for returners or a direct penalty for transfers.
    """
    total_share = sum(p.minutes_share_p2 for p in players)
    if total_share <= 0:
        return _ContinuityProfile(
            returner_minutes_fraction=0.5,
            returner_bpr_fraction=0.5,
            transfer_minutes_fraction=0.0,
            transfer_bpr_fraction=0.0,
            transfer_dependence_score=0.0,
            continuity_score=50.0,
            continuity_value_score=50.0,
            continuity_adjustment_off=0.0,
            continuity_adjustment_def=0.0,
        )

    # ── Minutes fractions (Phase 5 baseline) ─────────────────────────────────
    returner_share = sum(
        p.minutes_share_p2 for p in players if p.recruitment_type == "returner"
    )
    transfer_share = sum(
        p.minutes_share_p2 for p in players if p.recruitment_type == "transfer"
    )
    returner_minutes_frac = returner_share / total_share
    transfer_minutes_frac = transfer_share / total_share

    # ── BPR-weighted fractions (Phase 6) ─────────────────────────────────────
    # Shift BPR above floor so all players contribute a non-negative weight.
    # This prevents negative-BPR outliers from making the denominator too small
    # or producing inverted fractions for below-average players.
    def _weight(p: PlayerProjectionInput) -> float:
        return p.minutes_share_p2 * max(
            p.projected_bpr - CONTINUITY_BPR_REPLACEMENT_FLOOR, 0.0
        )

    total_bpr_weight = sum(_weight(p) for p in players)

    if total_bpr_weight > 0:
        returner_bpr_frac = sum(
            _weight(p) for p in players if p.recruitment_type == "returner"
        ) / total_bpr_weight
        transfer_bpr_frac = sum(
            _weight(p) for p in players if p.recruitment_type == "transfer"
        ) / total_bpr_weight
    else:
        # All players below the replacement floor — fall back to minutes fracs
        returner_bpr_frac = returner_minutes_frac
        transfer_bpr_frac = transfer_minutes_frac

    # ── Blended continuity value score ───────────────────────────────────────
    # 60 % minutes fraction + 40 % BPR fraction (CONTINUITY_BPR_BLEND_WEIGHT)
    blended_returner_frac = (
        (1.0 - CONTINUITY_BPR_BLEND_WEIGHT) * returner_minutes_frac
        + CONTINUITY_BPR_BLEND_WEIGHT * returner_bpr_frac
    )
    continuity_value_score = blended_returner_frac * 100.0

    # ── Continuity score (backward compat — minutes-only) ─────────────────
    continuity_score = returner_minutes_frac * 100.0

    # ── Continuity adjustment (linear; driven by BPR-weighted score) ─────────
    raw_off = 2.0 * MAX_CONTINUITY_ADJ_OFF * (blended_returner_frac - CONTINUITY_NEUTRAL_FRACTION)
    raw_def = 2.0 * MAX_CONTINUITY_ADJ_DEF * (blended_returner_frac - CONTINUITY_NEUTRAL_FRACTION)
    cont_adj_off = max(-MAX_CONTINUITY_ADJ_OFF, min(MAX_CONTINUITY_ADJ_OFF, raw_off))
    cont_adj_def = max(-MAX_CONTINUITY_ADJ_DEF, min(MAX_CONTINUITY_ADJ_DEF, raw_def))

    return _ContinuityProfile(
        returner_minutes_fraction=returner_minutes_frac,
        returner_bpr_fraction=returner_bpr_frac,
        transfer_minutes_fraction=transfer_minutes_frac,
        transfer_bpr_fraction=transfer_bpr_frac,
        transfer_dependence_score=transfer_bpr_frac * 100.0,
        continuity_score=continuity_score,
        continuity_value_score=continuity_value_score,
        continuity_adjustment_off=cont_adj_off,
        continuity_adjustment_def=cont_adj_def,
    )


@dataclass
class _ContinuityProfile:
    """Internal: full stability profile returned by _compute_continuity()."""

    returner_minutes_fraction: float   # 0-1, minutes-based
    returner_bpr_fraction: float       # 0-1, BPR-weighted
    transfer_minutes_fraction: float   # 0-1, minutes-based
    transfer_bpr_fraction: float       # 0-1, BPR-weighted
    transfer_dependence_score: float   # 0-100 (= transfer_bpr_frac × 100)
    continuity_score: float            # 0-100 (minutes-only; backward compat)
    continuity_value_score: float      # 0-100 (BPR-weighted blend; drives adj)
    continuity_adjustment_off: float   # pts/100 poss added to projected_adj_o
    continuity_adjustment_def: float   # pts/100 poss added to projected_adj_d (subtracted)


def _compute_newcomer_fraction(players: list[PlayerProjectionInput]) -> float:
    """Fraction of total minutes going to newcomers (for uncertainty calc)."""
    total_share = sum(p.minutes_share_p2 for p in players)
    if total_share <= 0:
        return 0.0
    newcomer_share = sum(
        p.minutes_share_p2
        for p in players
        if p.recruitment_type == "newcomer"
    )
    return newcomer_share / total_share


def _compute_fit_adjustments(
    roster_fit: Optional[RosterFitInput],
) -> tuple[float, float]:
    """
    Return (fit_adj_off, fit_adj_def) in pts/100 poss.

    Positive = improvement over D1 average fit.
    Uses Phase 4 adjusted_off_fit / adjusted_def_fit (0-100 scale, 50 = neutral).
    If no fit data, returns (0.0, 0.0) — neutral, no adjustment.
    """
    if roster_fit is None:
        return 0.0, 0.0

    raw_off = FIT_TO_RATING_OFF * (roster_fit.adjusted_off_fit - 50.0) / 50.0
    raw_def = FIT_TO_RATING_DEF * (roster_fit.adjusted_def_fit - 50.0) / 50.0

    fit_adj_off = max(-FIT_MAX_ADJ_OFF, min(FIT_MAX_ADJ_OFF, raw_off))
    fit_adj_def = max(-FIT_MAX_ADJ_DEF, min(FIT_MAX_ADJ_DEF, raw_def))

    return fit_adj_off, fit_adj_def


def _compute_transfer_fit_risk(
    transfer_dependence_score: float,
    roster_fit: Optional[RosterFitInput],
) -> float:
    """
    Phase 6b: Compute transfer fit-risk ∈ [0, 1].

    Interaction of transfer dependence × fit shortfall:
      dep_frac      = transfer_dependence_score / 100
      fit_shortfall = max(0, (50 - avg_fit) / 50)  → 0 at neutral/good fit, 1 at score=0
      risk          = dep_frac × fit_shortfall

    Properties:
      - No transfer dependence → risk = 0 (no effect)
      - High dependence + good fit (≥ 50) → shortfall = 0 → risk = 0
      - High dependence + poor fit → risk peaks toward 1.0
      - Missing fit data → TRANSFER_FIT_RISK_NO_STYLE_DEFAULT (neutral, not penalised)

    Does NOT affect mean projection (base_team_offense/defense unchanged).
    """
    if roster_fit is None:
        return TRANSFER_FIT_RISK_NO_STYLE_DEFAULT

    dep_frac = transfer_dependence_score / 100.0
    avg_fit = (roster_fit.adjusted_off_fit + roster_fit.adjusted_def_fit) / 2.0
    fit_shortfall = max(0.0, (50.0 - avg_fit) / 50.0)
    return dep_frac * fit_shortfall


def _compute_uncertainty(
    returner_frac: float,
    newcomer_frac: float,
    roster_fit: Optional[RosterFitInput],
    weighted_player_uncertainty: float = 0.5,
    continuity_value_score: Optional[float] = None,
    transfer_fit_risk: float = 0.0,
    coaching_uncertainty_add: float = 0.0,
) -> float:
    """
    Compute team_projection_uncertainty ∈ [UNCERTAINTY_MIN, UNCERTAINTY_MAX].

    Higher = less confident. Driven by:
      - Base: all teams have inherent uncertainty
      - Player projections: minutes-weighted avg of per-player projection_uncertainty
        (the primary signal — captures how hard each player individually was to project)
      - Newcomer share: categorical penalty for untested players beyond the player signal
      - Low-continuity: roster churn makes systemic prediction harder
      - Transfer fit-risk: transfer-heavy roster in a poor-fit system (Phase 6b)
      - Missing style data: Phase 4 modifiers were placeholders

    Phase 6: the continuity term now uses ``continuity_value_score`` (the
    BPR-weighted blend, 0-100) rather than raw ``returner_frac`` when provided.
    This avoids giving outsized stability credit to returners who hold bench roles.
    When ``continuity_value_score`` is None (e.g., legacy test calls), the function
    falls back to ``returner_frac`` for backward compatibility.

    Phase 6b: ``transfer_fit_risk`` ∈ [0, 1] is the interaction of transfer
    dependence score × fit shortfall.  Defaults to 0.0 so legacy test calls
    that do not supply this parameter are unaffected.

    ``weighted_player_uncertainty`` defaults to 0.5 (neutral) when called from
    tests that do not supply player-level data.
    """
    uncertainty = UNCERTAINTY_BASE

    # Primary signal: how hard were the individual player projections?
    uncertainty += UNCERTAINTY_PLAYER_SIGNAL_WEIGHT * weighted_player_uncertainty

    # Categorical penalty for newcomers (on top of their typically high player uncertainty)
    uncertainty += UNCERTAINTY_NEWCOMER_WEIGHT * newcomer_frac

    # Low-continuity adds prediction difficulty.
    # Phase 6: use BPR-weighted continuity_value_score when available so that
    # uncertainty correctly reflects talent-level churn (not just headcount churn).
    cont_input = (continuity_value_score / 100.0) if continuity_value_score is not None else returner_frac
    uncertainty += UNCERTAINTY_CONTINUITY_WEIGHT * (1.0 - cont_input)

    # Phase 6b: transfer fit-risk — wider range when transfers land in a poor-fit
    # system.  Zero when transfer_fit_risk=0 (no dependence OR good fit).
    uncertainty += TRANSFER_FIT_RISK_WEIGHT * transfer_fit_risk

    # Missing team-style data
    if roster_fit is None or not roster_fit.has_team_style_data:
        uncertainty += UNCERTAINTY_NO_STYLE_DATA

    # Coaching: first-year coach adds outcome variance (Sprint 5)
    uncertainty += coaching_uncertainty_add

    return max(UNCERTAINTY_MIN, min(UNCERTAINTY_MAX, uncertainty))


def _uncertainty_to_sigma(uncertainty: float) -> float:
    """
    LEGACY flat sigma model — no longer used for engine band construction
    (superseded by sigma_o / sigma_d / sigma_em below, Phase 3 Stage 2).

    Retained because still referenced by bt6_coverage_calibration.py /
    run_bt6.py (an independent backtest tool) and the Sprint-3 scenario
    endpoint (scenario/service.py, /api/scenarios/compute/), which was out
    of scope for the Phase 3 band-convention unification.

    Convert 0-1 uncertainty to pts/100 poss confidence band half-width.
    sigma grows linearly from SIGMA_SCALE at uncertainty=0 to SIGMA_MAX at 1.
    """
    sigma = UNCERTAINTY_SIGMA_SCALE + (UNCERTAINTY_SIGMA_MAX - UNCERTAINTY_SIGMA_SCALE) * uncertainty
    return min(UNCERTAINTY_SIGMA_MAX, sigma)


def sigma_o(uncertainty: float) -> float:
    """
    AdjO band half-width (pts/100 poss), empirically fit on DEMEANED O
    residuals (Phase 3 Stage 2, operator decision D1 — the band answers
    "team strength relative to the field," so league-wide scoring-
    environment drift is removed before fitting). See constants.py for the
    full derivation.

    projected_adj_o ± sigma_o(u) is the ±1σ ("likely range", ~68%) band.
    """
    u = max(UNCERTAINTY_MIN, min(UNCERTAINTY_MAX, uncertainty))
    return SIGMA_O_INTERCEPT + SIGMA_O_SLOPE * u


def sigma_d(uncertainty: float) -> float:
    """
    AdjD band half-width (pts/100 poss), empirically fit on DEMEANED D
    residuals (Phase 3 Stage 2, operator decision D1). See sigma_o() and
    constants.py for the derivation rationale.

    projected_adj_d ± sigma_d(u) is the ±1σ ("likely range", ~68%) band.
    """
    u = max(UNCERTAINTY_MIN, min(UNCERTAINTY_MAX, uncertainty))
    return SIGMA_D_INTERCEPT + SIGMA_D_SLOPE * u


def sigma_em(uncertainty: float) -> float:
    """
    AdjEM band half-width (pts/100 poss), empirically fit on RAW EM
    residuals (Phase 3 Stage 2, operator decision D2 — league-wide
    scoring-environment drift cancels in the O−D margin by construction,
    so EM is not demeaned). Also drives national/offense/defense rank
    ranges (api/outlook_views.py, team_projection/service.py).

    projected_adj_em ± sigma_em(u) is the ±1σ ("likely range", ~68%) band —
    the old ±2σ_rating convention is retired; this fit already absorbs what
    that 2x multiplier was informally approximating.
    """
    u = max(UNCERTAINTY_MIN, min(UNCERTAINTY_MAX, uncertainty))
    return min(SIGMA_EM_MAX, SIGMA_EM_INTERCEPT + SIGMA_EM_SLOPE * u)


def _build_driver_breakdown(
    result: TeamProjectionResult,
    d1_context: D1Context,
) -> list[dict]:
    """
    Return a list of adjustment driver dicts for the projection_summary UI.
    Each entry: {driver, value_off, value_def, note}.
    Ordered from largest to smallest absolute impact.
    """
    base_gain_off = SLOPE_OFF * (result.base_team_offense - d1_context.league_mean_base_off)
    base_gain_def = SLOPE_DEF * (result.base_team_defense - d1_context.league_mean_base_def)

    drivers = [
        {
            "driver": "Base Roster Offense",
            "value_off": round(base_gain_off, 3),
            "value_def": None,
            "unit": "pts/100",
        },
        {
            "driver": "Base Roster Defense",
            "value_off": None,
            "value_def": round(base_gain_def, 3),
            "unit": "pts/100",
        },
        {
            "driver": "Continuity",
            "value_off": round(result.continuity_adjustment_off, 3),
            "value_def": round(result.continuity_adjustment_def, 3),
            "unit": "pts/100",
        },
        {
            "driver": "Roster Fit",
            "value_off": round(result.fit_adjustment_off, 3),
            "value_def": round(result.fit_adjustment_def, 3),
            "unit": "pts/100",
        },
        {
            "driver": "Coaching Continuity",
            "value_off": 0.0,
            "value_def": 0.0,
            "unit": "pts/100",
            "note": "Placeholder — no coach data available",
        },
        {
            "driver": "Transfer Fit Risk",
            "value_off": None,
            "value_def": None,
            "unit": "uncertainty",
            "note": (
                f"transfer_dependence={result.transfer_dependence_score:.1f}, "
                f"risk={result.transfer_fit_risk_score:.3f}"
            ),
        },
    ]
    return drivers


def _build_summary(result: TeamProjectionResult) -> dict:
    """Compact projection summary dict for UI / API serialization."""
    rank = result.projected_national_rank
    rank_low = result.national_rank_range_low
    rank_high = result.national_rank_range_high
    rank_range_str = (
        f"{rank_low}–{rank_high}" if rank_low is not None and rank_high is not None else None
    )

    return {
        "projected_adj_o": round(result.projected_adj_o, 2),
        "projected_adj_d": round(result.projected_adj_d, 2),
        "projected_adj_em": round(result.projected_adj_em, 2),
        "projected_adj_em_range": [
            round(result.projected_adj_em_low, 2),
            round(result.projected_adj_em_high, 2),
        ],
        "national_rank": rank,
        "national_rank_range": rank_range_str,
        "offense_rank": result.projected_offense_rank,
        "defense_rank": result.projected_defense_rank,
        "continuity_score": round(result.continuity_score, 1),
        "continuity_value_score": round(result.continuity_value_score, 1),
        "transfer_dependence_score": round(result.transfer_dependence_score, 1),
        "transfer_fit_risk_score": round(result.transfer_fit_risk_score, 3),
        "uncertainty": round(result.team_projection_uncertainty, 3),
    }


def compute_team_base_aggregates(
    players: list[PlayerProjectionInput],
) -> tuple[float, float]:
    """
    Lightweight helper used by service.py in the first pass (centering step).
    Returns (base_off, base_def) without running the full projection.
    """
    return _compute_base_aggregates(players)[:2]


# ── Utility: empty result for teams with no player projections ────────────────


def _empty_result(d1_context: D1Context) -> TeamProjectionResult:
    """Return a neutral/average projection for teams with zero projected players."""
    max_sigma_o = sigma_o(UNCERTAINTY_MAX)
    max_sigma_d = sigma_d(UNCERTAINTY_MAX)
    max_sigma_em = sigma_em(UNCERTAINTY_MAX)
    return TeamProjectionResult(
        base_team_offense=0.0,
        base_team_defense=0.0,
        base_team_roster_strength=0.0,
        returner_minutes_fraction=0.0,
        continuity_score=0.0,
        continuity_adjustment_off=0.0,
        continuity_adjustment_def=0.0,
        returner_bpr_fraction=0.0,
        transfer_minutes_fraction=0.0,
        transfer_bpr_fraction=0.0,
        transfer_dependence_score=0.0,
        continuity_value_score=0.0,
        transfer_fit_risk_score=0.0,
        fit_adjustment_off=0.0,
        fit_adjustment_def=0.0,
        coaching_continuity_adjustment=0.0,
        projected_adj_o=d1_context.avg_adj_o,
        projected_adj_d=d1_context.avg_adj_d,
        projected_adj_em=d1_context.avg_adj_o - d1_context.avg_adj_d,
        team_projection_uncertainty=UNCERTAINTY_MAX,
        projected_adj_o_low=d1_context.avg_adj_o - max_sigma_o,
        projected_adj_o_high=d1_context.avg_adj_o + max_sigma_o,
        projected_adj_d_low=d1_context.avg_adj_d - max_sigma_d,
        projected_adj_d_high=d1_context.avg_adj_d + max_sigma_d,
        projected_adj_em_low=(d1_context.avg_adj_o - d1_context.avg_adj_d) - max_sigma_em,
        projected_adj_em_high=(d1_context.avg_adj_o - d1_context.avg_adj_d) + max_sigma_em,
    )
