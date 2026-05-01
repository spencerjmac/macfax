"""
manual_player.py — ManualPlayerSpec resolver (Sprint 3, Phase 1.3).

Pure Python — no Django imports, no DB access.  All DB lookups happen in
service.py; this module only contains dataclasses and resolver logic.

Resolution priority for a ManualPlayerSpec:
  1. Direct BPR override  (projected_obpr + projected_dbpr both set)
  2. Recruit rank lookup  (national_rank or stars; newcomers and JUCOs only)
  3. PlaceholderArchetype lookup  (placeholder_key found in placeholder_lookup)
  4. Default fallback  (auto-match by conf_group + role_bucket + quality_tier,
                        or flat type defaults when no placeholder matches)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ncaa.analytics.player_value.projection.engine import get_recruiting_prior
from ncaa.analytics.player_value.projection.constants import (
    UNCERTAINTY_BASE,
    JUCO_BPR_BOOST,
    JUCO_UNCERTAINTY_FACTOR,
)
from ncaa.analytics.player_value.minutes.role_buckets import classify_role_bucket


# ── Source-tier constants ─────────────────────────────────────────────────────

SOURCE_TIER_BPR_OVERRIDE = "bpr_override"
SOURCE_TIER_RANK_ELITE   = "rank_elite"      # national_rank <= 30
SOURCE_TIER_RANK_HIGH    = "rank_high"       # 31–100
SOURCE_TIER_RANK_MID     = "rank_mid"        # 101–200
SOURCE_TIER_RANK_LOW     = "rank_low"        # > 200
SOURCE_TIER_STARS        = "stars_fallback"  # rank=None but stars set
SOURCE_TIER_PLACEHOLDER  = "placeholder"
SOURCE_TIER_DEFAULT      = "default"
SOURCE_TIER_JUCO         = "juco"
SOURCE_TIER_DB           = "db"              # existing DB player (no badge)

# ── Competition warnings (Sprint 4) ──────────────────────────────────────────
WARN_MID_MAJOR_IN_POWER = (
    "Mid-major BPR — performance measured in weaker competition. "
    "May be inflated vs. power conference opponents."
)
WARN_HIGH_MID_IN_POWER  = "High mid-major BPR — slight competition gap vs. power conference."
WARN_JUCO               = (
    "JUCO transfer — college production adjusted for competition level. "
    "Higher uncertainty than D1 transfers."
)
WARN_CUSTOM_BPR         = "Manually entered BPR — this is a user estimate, not a model projection."
WARN_UNRATED_NEWCOMER   = (
    "Unrated newcomer — no recruiting data available. "
    "Projection is based on position defaults only."
)

_DISPLAY_LABELS: dict[str, str] = {
    SOURCE_TIER_BPR_OVERRIDE: "Custom BPR",
    SOURCE_TIER_RANK_ELITE:   "5★ / Top-30",
    SOURCE_TIER_RANK_HIGH:    "Top-100",
    SOURCE_TIER_RANK_MID:     "Top-200",
    SOURCE_TIER_RANK_LOW:     "Unranked",
    SOURCE_TIER_STARS:        "★ Recruit",    # formatted at runtime with star count
    SOURCE_TIER_PLACEHOLDER:  "",             # overridden by archetype display_name
    SOURCE_TIER_DEFAULT:      "Type Default",
    SOURCE_TIER_JUCO:         "JUCO Transfer",
    SOURCE_TIER_DB:           "",
}

# ── Default box stats by position ─────────────────────────────────────────────
# Used for manual players who have no observed stats.
# Based on D1 reference means stratified by position group.

DEFAULT_BOX_STATS_BY_POSITION: dict[str, dict] = {
    "G":   {"ast_pg": 2.5, "blk_pg": 0.1, "reb_pg": 2.5, "fg3a_pg": 3.0},
    "PG":  {"ast_pg": 2.5, "blk_pg": 0.1, "reb_pg": 2.5, "fg3a_pg": 3.0},
    "SG":  {"ast_pg": 2.5, "blk_pg": 0.1, "reb_pg": 2.5, "fg3a_pg": 3.0},
    "F":   {"ast_pg": 1.5, "blk_pg": 0.3, "reb_pg": 4.5, "fg3a_pg": 2.0},
    "SF":  {"ast_pg": 1.5, "blk_pg": 0.3, "reb_pg": 4.5, "fg3a_pg": 2.0},
    "PF":  {"ast_pg": 0.8, "blk_pg": 1.0, "reb_pg": 6.0, "fg3a_pg": 0.8},
    "C":   {"ast_pg": 0.8, "blk_pg": 1.0, "reb_pg": 6.0, "fg3a_pg": 0.8},
    "ATH": {"ast_pg": 1.5, "blk_pg": 0.4, "reb_pg": 4.0, "fg3a_pg": 2.0},
    "":    {"ast_pg": 1.5, "blk_pg": 0.4, "reb_pg": 4.0, "fg3a_pg": 2.0},
}


# ── Input dataclass ───────────────────────────────────────────────────────────

@dataclass
class ManualPlayerSpec:
    """
    Specification for a player not in the Macfax database.

    Resolution priority (highest to lowest):
      1. Direct BPR override (projected_obpr + projected_dbpr explicitly set)
      2. Recruit rank lookup → NEWCOMER_RANK_PRIORS (newcomers and JUCOs only)
      3. PlaceholderArchetype key lookup
      4. Position + recruitment_type defaults (league average for that type)

    Fields marked Optional are nullable — the resolver handles missing values
    gracefully at each priority level before falling back to the next.
    """
    # Identity (required)
    display_name: str
    position: str         # ESPN abbreviation: 'G', 'F', 'C', 'PG', 'SG', 'SF', 'PF'
    recruitment_type: str  # 'returner' | 'transfer' | 'newcomer'

    # Resolution Option 1: Direct BPR override
    projected_obpr: Optional[float] = None
    projected_dbpr: Optional[float] = None

    # Resolution Option 2: Recruit rank
    national_rank: Optional[int]   = None
    stars:         Optional[int]   = None
    composite_score: Optional[float] = None

    # Resolution Option 3: PlaceholderArchetype key
    placeholder_key: Optional[str] = None   # e.g. 'power_starter_g'

    # Resolution Option 4: Context hints for auto-placeholder selection
    conf_group:   str = "power"     # 'power' | 'high_mid' | 'mid_major' | 'national'
    quality_tier: str = "starter"   # 'elite' | 'all_conference' | 'starter' | 'rotation' | 'bench'

    # Minutes intent (soft constraint passed to Phase 2)
    intended_mpg: Optional[float] = None

    # JUCO flag (lower uncertainty, slight BPR boost at same rank)
    is_juco: bool = False

    # Unique identifier for this slot in the scenario (client-generated)
    slot_id: str = ""


# ── Output dataclass ──────────────────────────────────────────────────────────

@dataclass
class ScenarioPlayerResolved:
    """
    Fully resolved player representation for scenario computation.

    Both DB players and manual players resolve to this type, making the
    scenario engine uniform downstream.  Manual players carry is_manual=True
    and a display_label; DB players carry is_manual=False and empty label.
    """
    # Identity
    player_id:    int     # DB pk (positive) OR negative synthetic id for manual
    display_name: str
    slot_id:      str

    # Source provenance
    is_manual:         bool
    source_tier:       str   # SOURCE_TIER_* constant
    display_label:     str   # UI badge text
    resolution_method: str   # 'bpr_override'|'rank_lookup'|'placeholder'|'default'|'db'

    # Core projection
    projected_obpr:       float
    projected_dbpr:       float
    projected_bpr:        float
    projection_uncertainty: float
    recruitment_type:     str
    n_prior_seasons:      int

    # Phase 2 inputs
    position:   str
    prior_mpg:  float
    prior_gp:   int
    prior_poss: float
    ast_pg:     float
    blk_pg:     float
    reb_pg:     float
    fg3a_pg:    float

    # Phase 2 soft override
    intended_mpg: Optional[float]

    # Provenance metadata
    placeholder_key: Optional[str]
    national_rank:   Optional[int]
    stars:           Optional[int]
    is_juco:         bool

    # Competition context warning surfaced to the UI (Sprint 4)
    competition_warning: Optional[str] = None


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _get_default_box_stats(position: str) -> dict:
    """Return default box stats for a given ESPN position string."""
    key = (position or "").strip().upper()
    return DEFAULT_BOX_STATS_BY_POSITION.get(key, DEFAULT_BOX_STATS_BY_POSITION[""])


def _source_tier_from_rank(national_rank: Optional[int], stars: Optional[int]) -> str:
    """Derive source tier from national_rank, falling back to stars."""
    if national_rank is not None:
        if national_rank <= 30:  return SOURCE_TIER_RANK_ELITE
        if national_rank <= 100: return SOURCE_TIER_RANK_HIGH
        if national_rank <= 200: return SOURCE_TIER_RANK_MID
        return SOURCE_TIER_RANK_LOW
    if stars is not None:
        return SOURCE_TIER_STARS
    return SOURCE_TIER_DEFAULT


def _make_resolved(
    spec: ManualPlayerSpec,
    synthetic_id: int,
    projected_obpr: float,
    projected_dbpr: float,
    projection_uncertainty: float,
    source_tier: str,
    display_label: str,
    resolution_method: str,
    placeholder_key: Optional[str] = None,
    competition_warning: Optional[str] = None,
) -> ScenarioPlayerResolved:
    """Construct ScenarioPlayerResolved from a ManualPlayerSpec and resolved values."""
    box = _get_default_box_stats(spec.position)
    return ScenarioPlayerResolved(
        player_id=synthetic_id,
        display_name=spec.display_name,
        slot_id=spec.slot_id,
        is_manual=True,
        source_tier=source_tier,
        display_label=display_label,
        resolution_method=resolution_method,
        projected_obpr=projected_obpr,
        projected_dbpr=projected_dbpr,
        projected_bpr=round(projected_obpr + projected_dbpr, 4),
        projection_uncertainty=min(1.0, max(0.0, projection_uncertainty)),
        recruitment_type=spec.recruitment_type,
        n_prior_seasons=0,
        position=spec.position,
        prior_mpg=0.0,
        prior_gp=0,
        prior_poss=0.0,
        ast_pg=box["ast_pg"],
        blk_pg=box["blk_pg"],
        reb_pg=box["reb_pg"],
        fg3a_pg=box["fg3a_pg"],
        intended_mpg=spec.intended_mpg,
        placeholder_key=placeholder_key,
        national_rank=spec.national_rank,
        stars=spec.stars,
        is_juco=spec.is_juco,
        competition_warning=competition_warning,
    )


# ── Main resolver ─────────────────────────────────────────────────────────────

def _competition_warning_for_arch(arch_conf_group: str, target_conf_group: str) -> Optional[str]:
    """Return competition warning when a mid/high-mid archetype is placed on a power team."""
    if arch_conf_group == "mid_major" and target_conf_group in ("power", "national"):
        return WARN_MID_MAJOR_IN_POWER
    if arch_conf_group == "high_mid" and target_conf_group == "power":
        return WARN_HIGH_MID_IN_POWER
    return None


def resolve_manual_player(
    spec: ManualPlayerSpec,
    placeholder_lookup: dict[str, dict],
    synthetic_id_counter: int,
) -> ScenarioPlayerResolved:
    """
    Resolve a ManualPlayerSpec into a ScenarioPlayerResolved.

    This function is pure: no DB access, no side effects.
    The placeholder_lookup dict is pre-loaded by the service layer.

    Args:
        spec:                 The manual player specification.
        placeholder_lookup:   {key: archetype_data_dict} pre-loaded from DB.
        synthetic_id_counter: Negative integer as synthetic player_id.
                              Caller decrements per manual player.

    Returns:
        ScenarioPlayerResolved with all fields populated.
    """
    # ── Priority 1: Direct BPR override ──────────────────────────────────────
    if spec.projected_obpr is not None and spec.projected_dbpr is not None:
        unc = UNCERTAINTY_BASE.get(spec.recruitment_type, 0.80)
        return _make_resolved(
            spec, synthetic_id_counter,
            projected_obpr=spec.projected_obpr,
            projected_dbpr=spec.projected_dbpr,
            projection_uncertainty=unc,
            source_tier=SOURCE_TIER_BPR_OVERRIDE,
            display_label=_DISPLAY_LABELS[SOURCE_TIER_BPR_OVERRIDE],
            resolution_method="bpr_override",
            competition_warning=WARN_CUSTOM_BPR,
        )

    # ── Priority 2: Rank lookup (newcomers and JUCOs only) ───────────────────
    if (spec.national_rank is not None or spec.stars is not None) and \
            (spec.recruitment_type == "newcomer" or spec.is_juco):
        prior = get_recruiting_prior(spec.national_rank, spec.stars)
        obpr = prior["obpr_prior"]
        dbpr = prior["dbpr_prior"]
        unc  = prior["uncertainty_override"]
        if spec.is_juco:
            obpr += JUCO_BPR_BOOST
            unc  *= JUCO_UNCERTAINTY_FACTOR
            tier  = SOURCE_TIER_JUCO
            label = _DISPLAY_LABELS[SOURCE_TIER_JUCO]
        else:
            tier  = _source_tier_from_rank(spec.national_rank, spec.stars)
            if tier == SOURCE_TIER_STARS:
                label = f"{spec.stars}★ Recruit"
            else:
                label = _DISPLAY_LABELS[tier]
        return _make_resolved(
            spec, synthetic_id_counter,
            projected_obpr=obpr,
            projected_dbpr=dbpr,
            projection_uncertainty=unc,
            source_tier=tier,
            display_label=label,
            resolution_method="rank_lookup",
            competition_warning=WARN_JUCO if spec.is_juco else None,
        )

    # ── Priority 3: Explicit placeholder key ─────────────────────────────────
    if spec.placeholder_key and spec.placeholder_key in placeholder_lookup:
        arch = placeholder_lookup[spec.placeholder_key]
        box  = _get_default_box_stats(spec.position)
        comp_warn = _competition_warning_for_arch(
            str(arch.get("conf_group") or ""), spec.conf_group
        )
        return ScenarioPlayerResolved(
            player_id=synthetic_id_counter,
            display_name=spec.display_name,
            slot_id=spec.slot_id,
            is_manual=True,
            source_tier=SOURCE_TIER_PLACEHOLDER,
            display_label=str(arch.get("display_name", spec.placeholder_key)),
            resolution_method="placeholder",
            projected_obpr=float(arch.get("projected_obpr") or 0.0),
            projected_dbpr=float(arch.get("projected_dbpr") or 0.0),
            projected_bpr=float(arch.get("projected_bpr") or 0.0),
            projection_uncertainty=float(arch.get("uncertainty") or 0.5),
            recruitment_type=spec.recruitment_type,
            n_prior_seasons=0,
            position=spec.position,
            prior_mpg=0.0,
            prior_gp=0,
            prior_poss=0.0,
            ast_pg=box["ast_pg"],
            blk_pg=box["blk_pg"],
            reb_pg=box["reb_pg"],
            fg3a_pg=float(arch.get("fg3a_pg") or box["fg3a_pg"]),
            intended_mpg=spec.intended_mpg,
            placeholder_key=spec.placeholder_key,
            national_rank=spec.national_rank,
            stars=spec.stars,
            is_juco=spec.is_juco,
            competition_warning=comp_warn,
        )

    # ── Priority 4: Default fallback ─────────────────────────────────────────
    # Try auto-matching by conf_group + role_bucket + quality_tier.
    role_bucket = classify_role_bucket(
        position=spec.position,
        blk_pg=0.0, reb_pg=0.0, ast_pg=0.0, fg3a_pg=0.0,
    )
    best_key: Optional[str] = None
    for k, v in placeholder_lookup.items():
        if (v.get("conf_group") == spec.conf_group
                and v.get("role_bucket") == role_bucket
                and v.get("quality_tier") == spec.quality_tier):
            best_key = k
            break

    if best_key:
        arch = placeholder_lookup[best_key]
        box  = _get_default_box_stats(spec.position)
        comp_warn = _competition_warning_for_arch(
            str(arch.get("conf_group") or ""), spec.conf_group
        )
        return ScenarioPlayerResolved(
            player_id=synthetic_id_counter,
            display_name=spec.display_name,
            slot_id=spec.slot_id,
            is_manual=True,
            source_tier=SOURCE_TIER_DEFAULT,
            display_label=str(arch.get("display_name", "Type Default")),
            resolution_method="default",
            projected_obpr=float(arch.get("projected_obpr") or 0.0),
            projected_dbpr=float(arch.get("projected_dbpr") or 0.0),
            projected_bpr=float(arch.get("projected_bpr") or 0.0),
            projection_uncertainty=float(arch.get("uncertainty") or
                                         UNCERTAINTY_BASE.get(spec.recruitment_type, 0.80)),
            recruitment_type=spec.recruitment_type,
            n_prior_seasons=0,
            position=spec.position,
            prior_mpg=0.0,
            prior_gp=0,
            prior_poss=0.0,
            ast_pg=box["ast_pg"],
            blk_pg=box["blk_pg"],
            reb_pg=box["reb_pg"],
            fg3a_pg=float(arch.get("fg3a_pg") or box["fg3a_pg"]),
            intended_mpg=spec.intended_mpg,
            placeholder_key=best_key,
            national_rank=spec.national_rank,
            stars=spec.stars,
            is_juco=spec.is_juco,
            competition_warning=comp_warn,
        )

    # Flat defaults — no matching placeholder
    unc = UNCERTAINTY_BASE.get(spec.recruitment_type, 0.80)
    flat_warn = (
        WARN_UNRATED_NEWCOMER
        if (spec.recruitment_type == "newcomer"
            and spec.national_rank is None
            and spec.stars is None)
        else None
    )
    return _make_resolved(
        spec, synthetic_id_counter,
        projected_obpr=0.0,
        projected_dbpr=0.0,
        projection_uncertainty=unc,
        source_tier=SOURCE_TIER_DEFAULT,
        display_label=_DISPLAY_LABELS[SOURCE_TIER_DEFAULT],
        resolution_method="default",
        competition_warning=flat_warn,
    )


def resolve_db_player(
    projection: dict,
    stats: dict,
    position: str,
) -> ScenarioPlayerResolved:
    """
    Convert an existing DB PlayerSeasonProjection into ScenarioPlayerResolved.

    Args:
        projection: PlayerSeasonProjection .values() dict.
        stats:      PlayerSeasonStats .values() dict for the same player/season.
        position:   Player.position string.

    Returns:
        ScenarioPlayerResolved with is_manual=False.
    """
    prior_poss = (
        float(stats.get("off_poss") or 0.0)
        + float(stats.get("def_poss") or 0.0)
    )
    return ScenarioPlayerResolved(
        player_id=projection["player_id"],
        display_name=projection.get("player_name", ""),
        slot_id=str(projection.get("id", "")),
        is_manual=False,
        source_tier=SOURCE_TIER_DB,
        display_label="",
        resolution_method="db",
        projected_obpr=float(projection.get("projected_obpr") or 0.0),
        projected_dbpr=float(projection.get("projected_dbpr") or 0.0),
        projected_bpr=float(projection.get("projected_bpr") or 0.0),
        projection_uncertainty=float(projection.get("projection_uncertainty") or 0.5),
        recruitment_type=str(projection.get("recruitment_type") or "returner"),
        n_prior_seasons=int(projection.get("n_prior_seasons") or 0),
        position=position or "",
        prior_mpg=float(stats.get("mpg") or 0.0),
        prior_gp=int(stats.get("gp") or 0),
        prior_poss=prior_poss,
        ast_pg=float(stats.get("ast") or 0.0),
        blk_pg=float(stats.get("blk") or 0.0),
        reb_pg=float(stats.get("reb") or 0.0),
        fg3a_pg=float(stats.get("fg3a_pg") or 0.0),
        intended_mpg=None,
        placeholder_key=None,
        national_rank=None,
        stars=None,
        is_juco=False,
        competition_warning=None,
    )
