"""
engine.py — Player projection computation engine (Phase 1).

Produces next-season BPR projections from current-season player data.
All projection logic lives here; the pipeline module handles DB I/O.

This produces a BASELINE projection anchored on the player's known
current-season context — it is NOT a final destination-team-adjusted
roster-scenario result.  Roster simulator adjustments belong in Phase 2.

10-step projection pipeline:
  1.  Classify recruitment_type (returner / transfer / newcomer)
  2.  Extract current-season talent signals
  3.  Select talent signal (RAPM primary; Box BPR as fallback only)
  4.  Get possession counts (fall back to MPG estimate)
  5.  Year-to-year shrinkage toward D1 average
  6.  Multi-year trend (if prior RAPM available)
  7.  Development / aging adjustment
  8.  Arrival-context competition adjustment (transfers, based on prior → current team)
  9.  Projection uncertainty
  10. Baseline minutes share

Known Phase 1 limitations (track before Phase 2):
  - newcomer bucket cannot distinguish freshman vs grad-transfer vs JUCO;
    labelled explicitly as an umbrella bucket in this file.
  - Transfer competition adjustment (step 8) reflects how the player
    ARRIVED at the current team, not where they may go next season.
  - Minutes model is a rough baseline; a roster-context model belongs in Phase 2.
  - Talent signal priority (RAPM > Box) is a Phase 1 provisional design;
    backtest on historical seasons before refining for Phase 2.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.analytics.player_value.projection.constants import (
    YTY_SHRINK_POSS_OFF,
    YTY_SHRINK_POSS_DEF,
    TREND_WEIGHT_OFF,
    TREND_WEIGHT_DEF,
    DEV_OFF_NEWCOMER,
    DEV_DEF_NEWCOMER,
    DEV_OFF_SECOND_YEAR,
    DEV_DEF_SECOND_YEAR,
    DEV_OFF_SENIOR,
    DEV_DEF_SENIOR,
    SENIOR_SEASON_THRESHOLD,
    TRANSFER_COMP_WEIGHT_OFF,
    TRANSFER_COMP_WEIGHT_DEF,
    UNCERTAINTY_BASE,
    UNCERTAINTY_POSS_MAX_ADD,
    UNCERTAINTY_STABLE_POSS,
    MINUTES_SHARE_BASE_BY_TYPE,
    MINUTES_BPR_WEIGHT,
    MINUTES_SHARE_MIN,
    MINUTES_SHARE_MAX,
    POSS_PER_MINUTE,
    PROJECTION_VERSION,
)

logger = logging.getLogger(__name__)

# Canonical recruitment type strings
RETURNER = "returner"
TRANSFER = "transfer"
NEWCOMER = "newcomer"
# NOTE: NEWCOMER is a Phase 1 umbrella bucket.  Without external roster/
# recruiting data we cannot reliably distinguish true freshmen from grad
# transfers, JUCOs, or international players making their first D1 appearance.
# The constant and all downstream logic are structured so that
# freshman / other_newcomer sub-buckets can be inserted later without
# touching the core projection math.  See classify_recruitment_type() below.


# ── Step 1: Recruitment type classification ────────────────────────────────────

def classify_recruitment_type(
    player_id: int,
    current_team_id: Optional[int],
    prior_season_row: Optional[dict],
) -> str:
    """
    Classify how this player arrived at their current (from_season) team.

    returner  — appeared in the prior season at the same team
    transfer  — appeared in the prior season at a different team
    newcomer  — no prior season data in DB (first college season found)

    NOTE: Without external recruiting or roster data we cannot distinguish
    true freshmen from graduate transfers or JUCOs. "newcomer" covers all.
    """
    if prior_season_row is None:
        return NEWCOMER

    prior_team_id = prior_season_row.get("team_id")

    if prior_team_id is not None and current_team_id is not None:
        return RETURNER if prior_team_id == current_team_id else TRANSFER

    # Prior season data exists but team is unknown — conservative default.
    return RETURNER


# ── Step 3: Talent signal selection ──────────────────────────────────────────

def _select_talent_signal(
    obpr: Optional[float],
    dbpr: Optional[float],
    box_obpr: Optional[float],
    box_dbpr: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """
    Select the best available talent signal for projection.

    RAPM BPR (obpr/dbpr) is the primary signal when available.
    Box BPR (box_obpr/box_dbpr) is used ONLY as a fallback for players
    who lack on-court RAPM data.

    We do NOT blend RAPM and Box BPR.  The final BPR values (obpr/dbpr) are
    produced by a Bayesian RAPM fitting chain in which box_obpr/box_dbpr
    acts as the player prior:
        baseline RAPM → Box BPR prior → final prior-informed RAPM (obpr)
    Blending obpr with box_obpr again would give the box signal two bites at
    the apple — double-counting that inflates the box component's influence
    beyond its intended prior weight.

    Selection priority (Phase 1 provisional; backtest before Phase 2):
      1. RAPM available (obpr + dbpr)  → use as-is (box prior already baked in)
      2. Only Box available             → use box as standalone signal
      3. Neither                        → return None (signal=0, max uncertainty)
    """
    if obpr is not None and dbpr is not None:
        return obpr, dbpr
    if box_obpr is not None and box_dbpr is not None:
        return box_obpr, box_dbpr
    return None, None


# ── Step 5: Year-to-year shrinkage ────────────────────────────────────────────

def _year_to_year_shrinkage(
    signal_off: float,
    signal_def: float,
    poss_off: float,
    poss_def: float,
) -> tuple[float, float]:
    """
    Regress the blended talent signal toward the D1 average (0.0).

    λ = SHRINK_POSS / (SHRINK_POSS + poss)
    projected = (1 − λ) × signal
    """
    lambda_off = YTY_SHRINK_POSS_OFF / (YTY_SHRINK_POSS_OFF + max(poss_off, 0.0))
    lambda_def = YTY_SHRINK_POSS_DEF / (YTY_SHRINK_POSS_DEF + max(poss_def, 0.0))
    return (1.0 - lambda_off) * signal_off, (1.0 - lambda_def) * signal_def


# ── Step 6: Multi-year trend ──────────────────────────────────────────────────

def _trend_adjustment(
    current_obpr: Optional[float],
    current_dbpr: Optional[float],
    prior_obpr:   Optional[float],
    prior_dbpr:   Optional[float],
) -> tuple[float, float]:
    """
    Apply a fraction of the prior→current trend to the projection.
    Returns (off_adj, def_adj) in pts/100 poss.
    """
    off_adj = def_adj = 0.0

    if current_obpr is not None and prior_obpr is not None:
        off_adj = TREND_WEIGHT_OFF * (current_obpr - prior_obpr)
    if current_dbpr is not None and prior_dbpr is not None:
        def_adj = TREND_WEIGHT_DEF * (current_dbpr - prior_dbpr)

    return off_adj, def_adj


# ── Step 7: Development / aging ───────────────────────────────────────────────

def _development_adjustment(
    n_prior_seasons: int,
    recruitment_type: str,
) -> tuple[float, float]:
    """
    Return (off_adj, def_adj) for expected development or aging.

    n_prior_seasons: prior college seasons in DB before from_season.
      newcomer OR 0 prior → freshman developing into sophomore
      1 prior             → sophomore → junior (moderate growth)
      2 prior             → junior → senior (stabilizing, no adjustment)
      ≥ SENIOR_THRESHOLD  → senior+ → slight expected decline
    """
    if recruitment_type == NEWCOMER or n_prior_seasons == 0:
        return DEV_OFF_NEWCOMER, DEV_DEF_NEWCOMER
    if n_prior_seasons == 1:
        return DEV_OFF_SECOND_YEAR, DEV_DEF_SECOND_YEAR
    if n_prior_seasons >= SENIOR_SEASON_THRESHOLD:
        return DEV_OFF_SENIOR, DEV_DEF_SENIOR
    return 0.0, 0.0


# ── Step 8: Transfer competition adjustment ───────────────────────────────────

def _transfer_competition_adjustment(
    prior_team_adj_em:   Optional[float],
    current_team_adj_em: Optional[float],
) -> tuple[float, float]:
    """
    Apply a small retrospective arrival-context adjustment for transfers.

    This corrects for a known competition-level translation gap: a player who
    transferred FROM a stronger program to a weaker one had their BPR measured
    against tougher competition, so their stats may be slightly deflated vs
    their true talent in the new context, and vice versa.

    adj_delta = prior_team_adj_em − current_team_adj_em
    positive  → arrived from stronger program → slight positive correction
    negative  → arrived from weaker program   → slight negative correction

    NOTE (Phase 1 scope): This adjustment is RETROSPECTIVE — it describes how
    the player arrived at their CURRENT (from_season) team.  It does NOT model
    any future roster movement.  For roster-scenario projections where the player
    may move to a new destination next season, this step must be re-evaluated
    dynamically in Phase 2 using the destination team's adj_em.

    Returns (off_adj, def_adj).
    """
    if prior_team_adj_em is None or current_team_adj_em is None:
        return 0.0, 0.0
    adj_delta = prior_team_adj_em - current_team_adj_em
    return TRANSFER_COMP_WEIGHT_OFF * adj_delta, TRANSFER_COMP_WEIGHT_DEF * adj_delta


# ── Step 9: Projection uncertainty ───────────────────────────────────────────

def _compute_uncertainty(
    recruitment_type: str,
    poss_off: float,
    poss_def: float,
    has_rapm: bool,
) -> float:
    """
    Compute projection uncertainty in [0, 1].

    Base: by recruitment_type (returner < transfer < newcomer).
    +Add: for small RAPM samples; decays to 0 at UNCERTAINTY_STABLE_POSS.
    +Max: if no RAPM data at all (has_rapm=False).
    """
    base = UNCERTAINTY_BASE.get(recruitment_type, 0.80)

    poss = max(poss_off, poss_def, 0.0)
    if not has_rapm:
        poss_add = UNCERTAINTY_POSS_MAX_ADD
    else:
        poss_fraction = min(poss, UNCERTAINTY_STABLE_POSS) / UNCERTAINTY_STABLE_POSS
        poss_add = UNCERTAINTY_POSS_MAX_ADD * (1.0 - poss_fraction)

    return min(1.0, max(0.0, base + poss_add))


# ── Step 10: Baseline minutes share ───────────────────────────────────────────

def _compute_minutes_share(
    recruitment_type: str,
    mpg: Optional[float],
    gp: int,
    projected_bpr: float,
) -> float:
    """
    Phase 1 baseline minutes share estimate.

    For players with meaningful observed MPG (≥5 GP): mpg / 40.
    Otherwise: type-based default.
    Apply a small BPR-based upward adjustment.
    """
    if mpg is not None and mpg > 0.0 and gp >= 5:
        base = min(mpg / 40.0, 1.0)
    else:
        base = MINUTES_SHARE_BASE_BY_TYPE.get(recruitment_type, 0.30)

    return max(MINUTES_SHARE_MIN, min(MINUTES_SHARE_MAX, base + MINUTES_BPR_WEIGHT * projected_bpr))


# ── Main entry point ──────────────────────────────────────────────────────────

def project_player(
    current:  dict,
    prior:    Optional[dict],
    current_team_adj_em: Optional[float],
    prior_team_adj_em:   Optional[float],
    n_prior_seasons:     int,
) -> dict:
    """
    Compute a baseline next-season projection for a single player.

    All inputs are anchored on the player's known from_season context.
    This is NOT a future-destination projection — transfer movement and
    destination-team context for the NEXT season belong in Phase 2.

    Args:
        current:             Canonical PlayerSeasonStats field dict for from_season
                             (one row per player, chosen by most possessions).
        prior:               Canonical PlayerSeasonStats dict for the immediately
                             prior season, or None if none in DB.
        current_team_adj_em: TeamSeasonRatings.adj_em for the player's canonical
                             team in from_season.
        prior_team_adj_em:   TeamSeasonRatings.adj_em for the player's canonical
                             prior team in the prior season (used only for transfers
                             to correct the retrospective competition-level gap).
        n_prior_seasons:     Distinct college seasons before from_season in DB.

    Returns:
        dict with keys: projected_obpr, projected_dbpr, projected_bpr,
        projected_minutes_share, projection_uncertainty, recruitment_type,
        n_prior_seasons, prior_rapm_used, projection_version.
    """
    current_team_id = current.get("team_id")

    # ── Step 1 ──────────────────────────────────────────────────────────────
    recruitment_type = classify_recruitment_type(
        player_id=current.get("player_id"),
        current_team_id=current_team_id,
        prior_season_row=prior,
    )

    # ── Step 2 ──────────────────────────────────────────────────────────────
    obpr     = current.get("obpr")
    dbpr     = current.get("dbpr")
    box_obpr = current.get("box_obpr")
    box_dbpr = current.get("box_dbpr")
    has_rapm = obpr is not None and dbpr is not None

    # ── Step 3 ──────────────────────────────────────────────────────────────
    signal_off, signal_def = _select_talent_signal(obpr, dbpr, box_obpr, box_dbpr)
    signal_off = signal_off or 0.0
    signal_def = signal_def or 0.0

    # ── Step 4 ──────────────────────────────────────────────────────────────
    poss_off = current.get("off_poss") or 0.0
    poss_def = current.get("def_poss") or 0.0
    mpg = current.get("mpg") or 0.0
    gp  = current.get("gp") or 0

    if poss_off < 1.0 and mpg > 0.0 and gp > 0:
        # Estimate: half of all possessions are offensive
        estimated = mpg * gp * POSS_PER_MINUTE * 0.5
        poss_off = estimated
        poss_def = estimated

    # ── Step 5 ──────────────────────────────────────────────────────────────
    proj_off, proj_def = _year_to_year_shrinkage(signal_off, signal_def, poss_off, poss_def)

    # ── Step 6 ──────────────────────────────────────────────────────────────
    prior_obpr = prior.get("obpr") if prior else None
    prior_dbpr = prior.get("dbpr") if prior else None
    prior_rapm_used = prior_obpr is not None or prior_dbpr is not None

    trend_off, trend_def = _trend_adjustment(obpr, dbpr, prior_obpr, prior_dbpr)
    proj_off += trend_off
    proj_def += trend_def

    # ── Step 7 ──────────────────────────────────────────────────────────────
    dev_off, dev_def = _development_adjustment(n_prior_seasons, recruitment_type)
    proj_off += dev_off
    proj_def += dev_def

    # ── Step 8 ──────────────────────────────────────────────────────────────
    if recruitment_type == TRANSFER:
        comp_off, comp_def = _transfer_competition_adjustment(
            prior_team_adj_em, current_team_adj_em
        )
        proj_off += comp_off
        proj_def += comp_def

    proj_bpr = proj_off + proj_def

    # ── Step 9 ──────────────────────────────────────────────────────────────
    uncertainty = _compute_uncertainty(recruitment_type, poss_off, poss_def, has_rapm)

    # ── Step 10 ─────────────────────────────────────────────────────────────
    minutes_share = _compute_minutes_share(recruitment_type, mpg, gp, proj_bpr)

    return {
        "projected_obpr":          round(proj_off, 4),
        "projected_dbpr":          round(proj_def, 4),
        "projected_bpr":           round(proj_bpr, 4),
        "projected_minutes_share": round(minutes_share, 4),
        "projection_uncertainty":  round(uncertainty, 4),
        "recruitment_type":        recruitment_type,
        "n_prior_seasons":         n_prior_seasons,
        "prior_rapm_used":         prior_rapm_used,
        "projection_version":      PROJECTION_VERSION,
    }
