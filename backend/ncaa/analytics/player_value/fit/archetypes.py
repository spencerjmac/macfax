"""
Roster Fit Model — player input, normalization, and internal archetypes.

This module defines:
  1. PlayerFitInput  — one row per player; all signals the fit engine consumes.
  2. SeasonRefs      — season-relative reference means/SDs (replaces hard constants
                       when enough data is available).
  3. normalize()     — z-score → 0-100 mapper with winsorizing.
  4. tag_archetypes() — derives internal role labels from a PlayerFitInput.
                        These labels drive structural composition checks in the
                        offensive and defensive fit engines.  They are never
                        stored directly in the DB as public-facing fields.

Archetype tags (internal only)
───────────────────────────────
  Offensive
    spacer           — high 3PA volume (projects spacing threat)
    shooter          — above-avg eFG% (efficient scorer)
    primary_creator  — high assists (can initiate offense)
    secondary_creator — moderate assists (secondary playmaker)
    off_rebounder    — high offensive rebounds
    pressure_driver  — draws lots of fouls (trips to the line)
    ball_stopper     — high turnovers + low creation (usage without value)
    non_shooting_big — Big bucket + low 3PA (clogs spacing)

  Defensive
    rim_protector    — high blocks per game
    disruptor        — high steals per game
    foul_prone       — high personal fouls
    switchable_wing  — Wing bucket + disruptor-level steals
    weak_defender    — projected_dbpr well below average
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ncaa.analytics.player_value.fit.constants import (
    WINSOR_SIGMA,
    Z_TO_SCORE_SCALE,
    SCORE_MID,
    SCORE_MIN,
    SCORE_MAX,
    # Archetype thresholds
    SPACER_FG3A_THRESHOLD,
    SHOOTER_EFG_THRESHOLD,
    PRIMARY_CREATOR_AST_THRESHOLD,
    SECONDARY_CREATOR_AST_THRESHOLD,
    BALL_STOPPER_TOV_THRESHOLD,
    BALL_STOPPER_AST_MAX,
    OFF_REBOUNDER_THRESHOLD,
    NON_SHOOTING_BIG_FG3A_MAX,
    PRESSURE_DRIVER_FTA_THRESHOLD,
    RIM_PROTECTOR_BLK_THRESHOLD,
    DISRUPTOR_STL_THRESHOLD,
    FOUL_PRONE_THRESHOLD,
    WEAK_DEFENDER_DBPR_MAX,
    SWITCHABLE_WING_ROLE,
    # Bucket-relative thresholds (Sprint 4 — BT-10 validated)
    USE_BUCKET_THRESHOLDS,
    RIM_PROTECTOR_BLK_G, RIM_PROTECTOR_BLK_WING, RIM_PROTECTOR_BLK_BIG,
    DISRUPTOR_STL_G, DISRUPTOR_STL_WING, DISRUPTOR_STL_BIG,
    SPACER_FG3A_G, SPACER_FG3A_WING, SPACER_FG3A_BIG,
    WEAK_DEFENDER_DBPR_POWER, WEAK_DEFENDER_DBPR_HIGH_MID,
    WEAK_DEFENDER_DBPR_MID_MAJOR, WEAK_DEFENDER_DBPR_DEFAULT,
    # Recruit-class tag constants (Sprint 4)
    TAG_RECRUIT_ELITE, TAG_RECRUIT_HIGH, TAG_RECRUIT_MID, TAG_RECRUIT_LOW,
    TAG_RECRUIT_UNRATED, TAG_STARS_HIGH, TAG_STARS_MID, TAG_JUCO,
    RECRUIT_ELITE_RANK_THRESHOLD, RECRUIT_HIGH_RANK_THRESHOLD,
    RECRUIT_MID_RANK_THRESHOLD, RECRUIT_STARS_HIGH_THRESHOLD,
    RECRUIT_STARS_MID_THRESHOLD,
    # D1 reference values
    REF_FG3A_PG, REF_AST_PG, REF_TOV_PG, REF_BLK_PG, REF_STL_PG,
    REF_PF_PG, REF_OREB_PG, REF_DREB_PG, REF_FTA_PG,
    REF_FG_PCT, REF_EFG_PCT, REF_TS_PCT, REF_AST_TO,
    REF_PROJ_OBPR, REF_PROJ_DBPR,
    REF_OFF_EFG_IMPACT, REF_DEF_EFG_IMPACT,
    REF_OFF_TOV_IMPACT, REF_DEF_TOV_IMPACT,
    REF_OFF_ORB_IMPACT, REF_DEF_REB_IMPACT,
    REF_OFF_FTR_IMPACT, REF_DEF_FTR_IMPACT,
    REF_ON_COURT_ADJ_O, REF_ON_COURT_ADJ_D,
)


# ── Input dataclass ───────────────────────────────────────────────────────────

@dataclass
class PlayerFitInput:
    """
    All per-player signals consumed by the fit engine.

    All Optional fields default to None; the engine handles missing values via
    graceful fallback (typically to the D1 reference mean = z-score of 0).

    Sources:
      Phase 1  → projected_obpr, projected_dbpr, projection_uncertainty
      Phase 2  → minutes_share_p2, role_bucket, rotation_rank
      PlayerSeasonStats (from_season) → box-score & four-factor fields
    """

    # Identity
    player_id:         int
    player_name:       str = ""          # for diagnostics only

    # Phase 2 minutes outputs (required for weighting)
    minutes_share_p2:  float = 0.0       # mpg/40; sums to 5.00 per team
    rotation_rank:     int   = 99
    role_bucket:       str   = "Wing"    # "G" | "Wing" | "Big"

    # Phase 1 projected BPR
    projected_obpr:    Optional[float] = None
    projected_dbpr:    Optional[float] = None

    # Box-score rates (per game, from from_season PlayerSeasonStats)
    gp:                int   = 0
    fg3a_pg:           float = 0.0
    ast_pg:            float = 0.0
    tov_pg:            float = 0.0
    blk_pg:            float = 0.0
    stl_pg:            float = 0.0
    pf_pg:             float = 0.0
    oreb_pg:           float = 0.0
    dreb_pg:           float = 0.0
    fta_pg:            float = 0.0
    fg_pct:            Optional[float] = None
    efg_pct:           Optional[float] = None
    ts_pct:            Optional[float] = None
    ast_to:            Optional[float] = None

    # Four-factor impact (RAPM-derived; positive = good)
    off_efg_impact:    Optional[float] = None   # offensive eFG% impact
    def_efg_impact:    Optional[float] = None   # defensive eFG% suppression
    off_tov_impact:    Optional[float] = None   # offensive TOV reduction
    def_tov_impact:    Optional[float] = None   # defensive TOV creation
    off_orb_impact:    Optional[float] = None   # offensive ORB% boost
    def_reb_impact:    Optional[float] = None   # defensive REB% improvement
    off_ftr_impact:    Optional[float] = None   # offensive FTR boost
    def_ftr_impact:    Optional[float] = None   # defensive FTR prevention

    # On-court adjusted metrics (secondary modifier only)
    on_court_adj_o:    Optional[float] = None   # pts/100 poss (adj, while on)
    on_court_adj_d:    Optional[float] = None   # pts/100 poss allowed (adj, while on)
    on_court_off_poss: Optional[float] = None   # sample size for reliability
    on_court_def_poss: Optional[float] = None

    # Derived archetype tags (populated by tag_archetypes)
    archetypes: set = field(default_factory=set)

    # Recruiting profile (Sprint 4 — optional; None = not set).
    # Populated from PlayerRecruitingProfile for DB players, or from ManualPlayerSpec
    # for scenario players. None when data is unavailable.
    national_rank:    Optional[int]  = None
    recruit_stars:    Optional[int]  = None   # named recruit_stars to avoid 'stars' clash
    is_juco_transfer: bool           = False
    # Conference group for bucket-relative weak defender threshold (Sprint 4).
    # Set by fit/service.py from team slug → get_conf_detail(). None in scenario context.
    conf_group:       Optional[str]  = None   # "power" | "high_mid" | "mid_major" | None


# ── Season-relative reference values ─────────────────────────────────────────

@dataclass
class SeasonRefs:
    """
    Season-relative reference means and standard deviations.

    The service layer computes these from actual season data when enough
    qualifying player-seasons exist.  Otherwise the engine falls back to
    hard-coded D1 constants from constants.py.

    All fields are (mean, std_dev) tuples.  std_dev must be > 0.
    """
    fg3a_pg:        tuple = REF_FG3A_PG
    ast_pg:         tuple = REF_AST_PG
    tov_pg:         tuple = REF_TOV_PG
    blk_pg:         tuple = REF_BLK_PG
    stl_pg:         tuple = REF_STL_PG
    pf_pg:          tuple = REF_PF_PG
    oreb_pg:        tuple = REF_OREB_PG
    dreb_pg:        tuple = REF_DREB_PG
    fta_pg:         tuple = REF_FTA_PG
    efg_pct:        tuple = REF_EFG_PCT
    ts_pct:         tuple = REF_TS_PCT
    ast_to:         tuple = REF_AST_TO
    proj_obpr:      tuple = REF_PROJ_OBPR
    proj_dbpr:      tuple = REF_PROJ_DBPR
    off_efg_impact: tuple = REF_OFF_EFG_IMPACT
    def_efg_impact: tuple = REF_DEF_EFG_IMPACT
    off_tov_impact: tuple = REF_OFF_TOV_IMPACT
    def_tov_impact: tuple = REF_DEF_TOV_IMPACT
    off_orb_impact: tuple = REF_OFF_ORB_IMPACT
    def_reb_impact: tuple = REF_DEF_REB_IMPACT
    off_ftr_impact: tuple = REF_OFF_FTR_IMPACT
    def_ftr_impact: tuple = REF_DEF_FTR_IMPACT
    on_court_adj_o: tuple = REF_ON_COURT_ADJ_O
    on_court_adj_d: tuple = REF_ON_COURT_ADJ_D


# Singleton default refs (uses hard-coded constants)
DEFAULT_REFS = SeasonRefs()


# ── Normalization utilities ───────────────────────────────────────────────────

def normalize(
    value:     float,
    ref_mean:  float,
    ref_std:   float,
    invert:    bool = False,
) -> float:
    """
    Convert a raw value to a 0-100 score with 50 = D1 average.

    Formula:
        z     = (value − ref_mean) / ref_std
        z     = clamp(z, −WINSOR_SIGMA, +WINSOR_SIGMA)
        score = 50 + Z_TO_SCORE_SCALE × z          [default]
        score = 50 − Z_TO_SCORE_SCALE × z          [invert=True]

    invert=True is used for "lower is better" metrics (TOV, PF, opp eFG%).

    Args:
        value:    Raw per-player value.
        ref_mean: D1 season reference mean.
        ref_std:  D1 season reference std dev (must be > 0).
        invert:   Set True when a lower value is better (e.g. fouls, TOV).

    Returns:
        Float in [0, 100].
    """
    if ref_std <= 0:
        return SCORE_MID
    z = (value - ref_mean) / ref_std
    z = max(-WINSOR_SIGMA, min(WINSOR_SIGMA, z))
    raw = SCORE_MID + (Z_TO_SCORE_SCALE * (-z if invert else z))
    return max(SCORE_MIN, min(SCORE_MAX, raw))


def normalize_field(
    inp:   PlayerFitInput,
    field: str,
    refs:  SeasonRefs,
    invert: bool = False,
) -> float:
    """
    Normalize a single field from a PlayerFitInput, falling back to SCORE_MID
    when the field is None (i.e., data is missing).

    This ensures missing data degrades gracefully to league-average rather than
    crashing the computation or introducing a deceptive score.
    """
    val = getattr(inp, field, None)
    if val is None:
        return SCORE_MID
    ref_mean, ref_std = getattr(refs, field, (0.0, 1.0))
    return normalize(val, ref_mean, ref_std, invert=invert)


def blend_core_oncourt(
    core_score: float,
    on_court_value: Optional[float],
    on_court_poss: Optional[float],
    ref_mean: float,
    ref_std: float,
    invert: bool = False,
    max_modifier: float = 6.0,
    shrinkage_k: float = 300.0,
) -> float:
    """
    Blend a core trait score with an on-court adjusted signal.

    The on-court signal is treated as a secondary modifier only:
        modifier = on_court_normalized_score − 50    [−50..+50 range, then capped]
        reliability = poss / (poss + shrinkage_k)
        final = core_score + reliability × modifier × (max_modifier / 50)

    This adds at most max_modifier pts at full reliability and high on-court
    signal, so it can meaningfully nudge a score without dominating it.

    Args:
        core_score:      Already-normalized 0-100 score from box/impact data.
        on_court_value:  Raw on-court metric value (e.g. on_court_adj_o).
        on_court_poss:   Possessions used for reliability shrinkage.
        ref_mean / ref_std: D1 reference for the on-court metric.
        invert:          True if lower on-court values are better (e.g. adj_d).
        max_modifier:    Max pts the on-court signal can add/subtract.
        shrinkage_k:     Possessions at which reliability = 50%.

    Returns:
        Modified 0-100 score.
    """
    if on_court_value is None or on_court_poss is None or on_court_poss <= 0:
        return core_score

    poss = max(0.0, on_court_poss)
    reliability = poss / (poss + shrinkage_k)

    raw_z = (on_court_value - ref_mean) / max(ref_std, 1e-6)
    raw_z = max(-WINSOR_SIGMA, min(WINSOR_SIGMA, raw_z))
    normalized_oc = SCORE_MID + Z_TO_SCORE_SCALE * (-raw_z if invert else raw_z)

    modifier_raw = (normalized_oc - SCORE_MID) * reliability * (max_modifier / 50.0)
    return max(SCORE_MIN, min(SCORE_MAX, core_score + modifier_raw))


# ── Archetype tagging ─────────────────────────────────────────────────────────

def tag_archetypes(inp: PlayerFitInput) -> set[str]:
    """
    Derive internal role labels from a PlayerFitInput.

    Returns a set of string tags.  These are used only for structural
    composition checks; they are not persisted or shown in the UI.

    Tag logic is intentionally kept simple and threshold-based.
    Basketball judgment: thresholds are calibrated against D1 season data.
    """
    tags: set[str] = set()
    is_big  = (inp.role_bucket == "Big")
    is_wing = (inp.role_bucket == "Wing")

    # ── Resolve active thresholds (bucket-relative or legacy) ────────────
    if USE_BUCKET_THRESHOLDS:
        _blk_thresh = {"Big": RIM_PROTECTOR_BLK_BIG, "Wing": RIM_PROTECTOR_BLK_WING}.get(
            inp.role_bucket, RIM_PROTECTOR_BLK_G
        )
        _stl_thresh = {"G": DISRUPTOR_STL_G, "Wing": DISRUPTOR_STL_WING}.get(
            inp.role_bucket, DISRUPTOR_STL_BIG
        )
        _spacer_thresh = {"G": SPACER_FG3A_G, "Wing": SPACER_FG3A_WING, "Big": SPACER_FG3A_BIG}.get(
            inp.role_bucket, SPACER_FG3A_G
        )
        _weak_def_thresh = {
            "power": WEAK_DEFENDER_DBPR_POWER,
            "high_mid": WEAK_DEFENDER_DBPR_HIGH_MID,
            "mid_major": WEAK_DEFENDER_DBPR_MID_MAJOR,
        }.get(inp.conf_group or "", WEAK_DEFENDER_DBPR_DEFAULT)
    else:
        _blk_thresh      = RIM_PROTECTOR_BLK_THRESHOLD
        _stl_thresh      = DISRUPTOR_STL_THRESHOLD
        _spacer_thresh   = SPACER_FG3A_THRESHOLD
        _weak_def_thresh = WEAK_DEFENDER_DBPR_MAX

    # ── Offensive archetypes ─────────────────────────────────────────────
    if inp.fg3a_pg >= _spacer_thresh:
        tags.add("spacer")

    if inp.efg_pct is not None and inp.efg_pct >= SHOOTER_EFG_THRESHOLD:
        tags.add("shooter")

    if inp.ast_pg >= PRIMARY_CREATOR_AST_THRESHOLD:
        tags.add("primary_creator")
    elif inp.ast_pg >= SECONDARY_CREATOR_AST_THRESHOLD:
        tags.add("secondary_creator")

    if inp.oreb_pg >= OFF_REBOUNDER_THRESHOLD:
        tags.add("off_rebounder")

    if inp.fta_pg >= PRESSURE_DRIVER_FTA_THRESHOLD:
        tags.add("pressure_driver")

    # Ball stopper: high TOV + low creation (usage without playmaking value)
    if (inp.tov_pg >= BALL_STOPPER_TOV_THRESHOLD
            and inp.ast_pg <= BALL_STOPPER_AST_MAX):
        tags.add("ball_stopper")

    # Non-shooting big: Big bucket + low 3PA (clogs spacing)
    if is_big and inp.fg3a_pg < NON_SHOOTING_BIG_FG3A_MAX:
        tags.add("non_shooting_big")

    # ── Defensive archetypes ─────────────────────────────────────────────
    if inp.blk_pg >= _blk_thresh:
        tags.add("rim_protector")

    if inp.stl_pg >= _stl_thresh:
        tags.add("disruptor")

    if inp.pf_pg >= FOUL_PRONE_THRESHOLD:
        tags.add("foul_prone")

    # Switchable wing: wing position + disruptor-level steals
    if is_wing and inp.stl_pg >= _stl_thresh:
        tags.add("switchable_wing")

    # Weak defender: projected_dbpr well below average (conf-group relative)
    if (inp.projected_dbpr is not None
            and inp.projected_dbpr <= _weak_def_thresh):
        tags.add("weak_defender")

    # ── Recruit-class tags (Sprint 4) ─────────────────────────────────────
    # Additive — do not replace or affect any existing tags above.
    # Only fire when recruiting data is explicitly set on this PlayerFitInput.

    # JUCO fires regardless of rank/stars
    if inp.is_juco_transfer:
        tags.add(TAG_JUCO)

    # Rank takes priority over stars when both are present
    if inp.national_rank is not None:
        if inp.national_rank <= RECRUIT_ELITE_RANK_THRESHOLD:
            tags.add(TAG_RECRUIT_ELITE)
        elif inp.national_rank <= RECRUIT_HIGH_RANK_THRESHOLD:
            tags.add(TAG_RECRUIT_HIGH)
        elif inp.national_rank <= RECRUIT_MID_RANK_THRESHOLD:
            tags.add(TAG_RECRUIT_MID)
        else:
            tags.add(TAG_RECRUIT_LOW)
    elif inp.recruit_stars is not None:
        if inp.recruit_stars >= RECRUIT_STARS_HIGH_THRESHOLD:
            tags.add(TAG_STARS_HIGH)
        elif inp.recruit_stars >= RECRUIT_STARS_MID_THRESHOLD:
            tags.add(TAG_STARS_MID)
        # Stars below 3 with no rank: no tag (insufficient signal to surface in UI)

    # NOTE: TAG_RECRUIT_UNRATED is NOT set here. PlayerFitInput has no recruitment_type
    # field, so we cannot distinguish newcomers from returners/transfers in this function.
    # Set TAG_RECRUIT_UNRATED externally (in the service or scenario layer) when
    # recruitment_type='newcomer' AND national_rank is None AND recruit_stars is None.

    return tags
