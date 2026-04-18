"""
Roster Fit Model — Defensive fit scorer (Phase 3).

Produces 8 normalized defensive subcomponent scores (0-100) and applies
structural composition penalties.

Design
──────
Same two-layer architecture as the offensive engine:
  1. Core trait score — minutes-weighted average of normalized signals.
  2. On-court modifier — sample-dampened nudge via on_court_adj_d
     (lower is better → invert=True).

Subcomponent ownership of structural penalties
───────────────────────────────────────────────
  rim_protection_fit   → DEF_NO_RIM_PROTECTOR_PENALTY
  def_rebounding_fit   → DEF_POOR_REBOUND_BALANCE_PENALTY
  foul_discipline_fit  → DEF_FOUL_STACK_PENALTY
  size_coverage_fit    → DEF_FEW_BIGS_PENALTY
  role_balance_def_fit → DEF_WEAK_TOP5_PENALTY

perimeter_defense_fit and disruption_fit have no structural penalties because
their structural issues (i.e. "team-wide" perimeter or disruption weakness)
are captured adequately by the minutes-weighted subcomponent scores themselves.

Perimeter defense philosophy
─────────────────────────────
Perimeter defense is NOT just steals.

Steals (disruption_fit) are already a separate subcomponent.
perimeter_defense_fit uses projected_dbpr as the primary signal
(the best available single measure of overall defensive quality), combined
with def_efg_impact (limits opponent shooting) and the on-court defensive
modifier.  Steals have a small secondary contribution here to capture active
guard/wing pressure without dominating.

Size coverage philosophy
─────────────────────────
No height/weight data exist.  The closest proxy is:
  - role_bucket composition (Big fraction in major minutes)
  - defensive rebounding (bigs anchor the defensive glass)
  - block presence (interior deterrence)
This is a roster-level composition check, not a per-player height signal.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.analytics.player_value.fit.archetypes import (
    PlayerFitInput,
    SeasonRefs,
    DEFAULT_REFS,
    normalize,
    blend_core_oncourt,
)
from core.analytics.player_value.fit.constants import (
    SCORE_MID, SCORE_MIN, SCORE_MAX,
    TOP_ROTATION_THRESHOLD,
    ON_COURT_SHRINKAGE_K, ON_COURT_MAX_MODIFIER,
    # Structural penalties
    DEF_NO_RIM_PROTECTOR_PENALTY,
    DEF_WEAK_TOP5_PENALTY,
    DEF_POOR_REBOUND_BALANCE_PENALTY,
    DEF_FOUL_STACK_PENALTY,
    DEF_FEW_BIGS_PENALTY,
    DEF_WEAK_DREB_THRESHOLD,
    MAX_STRUCTURAL_PENALTY_DEF,
)


# ── Output dataclass ──────────────────────────────────────────────────────────

@dataclass
class DefensiveFitResult:
    """
    Per-roster defensive fit output.  All subcomponent scores on 0-100 scale.
    """
    rim_protection_fit:    float = 50.0
    def_rebounding_fit:    float = 50.0
    disruption_fit:        float = 50.0
    foul_discipline_fit:   float = 50.0
    perimeter_defense_fit: float = 50.0
    size_coverage_fit:     float = 50.0
    mobility_fit:          float = 50.0
    role_balance_def_fit:  float = 50.0

    structural_penalties:  list  = None
    total_penalty:         float = 0.0

    defensive_fit_score:   float = 50.0

    def __post_init__(self):
        if self.structural_penalties is None:
            self.structural_penalties = []


# ── Minutes-weighted aggregation helper ───────────────────────────────────────

def _weighted_avg(
    players: list[PlayerFitInput],
    score_fn,
    refs: SeasonRefs,
) -> float:
    total_weight = sum(p.minutes_share_p2 for p in players)
    if total_weight < 1e-6:
        return SCORE_MID
    return sum(
        p.minutes_share_p2 * score_fn(p, refs)
        for p in players
    ) / total_weight


# ── Per-player component scorers ──────────────────────────────────────────────

def _rim_protection_score(p: PlayerFitInput, refs: SeasonRefs) -> float:
    """
    Per-player rim protection signal.

    Core = 0.70 × blk_pg_score          (blocks — most direct rim proxy)
         + 0.30 × def_reb_impact_score   (RAPM: limits opp offensive boards)

    Blocks capture deterrence.  def_reb_impact captures whether the team glass
    improves when this player is on the floor (interior presence secondary sig).
    """
    blk_s = normalize(p.blk_pg, *refs.blk_pg)

    def_reb_s = (
        normalize(p.def_reb_impact, *refs.def_reb_impact)
        if p.def_reb_impact is not None else SCORE_MID
    )

    return 0.70 * blk_s + 0.30 * def_reb_s


def _def_rebounding_score(p: PlayerFitInput, refs: SeasonRefs) -> float:
    """
    Per-player defensive rebounding signal.

    Core = 0.60 × dreb_pg_score          (raw defensive boards)
         + 0.40 × def_reb_impact_score   (RAPM: team DRB% improvement on court)

    On-court defensive modifier applied (lower adj_d = better defense).
    """
    dreb_s = normalize(p.dreb_pg, *refs.dreb_pg)

    def_reb_s = (
        normalize(p.def_reb_impact, *refs.def_reb_impact)
        if p.def_reb_impact is not None else SCORE_MID
    )

    core = 0.60 * dreb_s + 0.40 * def_reb_s

    core = blend_core_oncourt(
        core,
        on_court_value=p.on_court_adj_d,
        on_court_poss=p.on_court_def_poss,
        ref_mean=refs.on_court_adj_d[0],
        ref_std=refs.on_court_adj_d[1],
        invert=True,   # lower opponent efficiency = better
        max_modifier=4.0,
        shrinkage_k=ON_COURT_SHRINKAGE_K,
    )
    return core


def _disruption_score(p: PlayerFitInput, refs: SeasonRefs) -> float:
    """
    Per-player disruption / takeaway signal.

    Core = 0.55 × stl_pg_score           (steals — most direct disruption signal)
         + 0.45 × def_tov_impact_score   (RAPM: forces extra opponent turnovers)

    Steals are noisy but the cleanest box-score disruption proxy.
    def_tov_impact is the RAPM-based counterpart — measures whether the team
    forces more turnovers when this player is on the floor.
    """
    stl_s = normalize(p.stl_pg, *refs.stl_pg)

    def_tov_s = (
        normalize(p.def_tov_impact, *refs.def_tov_impact)
        if p.def_tov_impact is not None else SCORE_MID
    )

    return 0.55 * stl_s + 0.45 * def_tov_s


def _foul_discipline_score(p: PlayerFitInput, refs: SeasonRefs) -> float:
    """
    Per-player foul discipline signal.  Lower fouls = higher score.

    Core = 0.55 × pf_pg_score (inverted)   (fewer fouls → better)
         + 0.45 × def_ftr_impact_score      (RAPM: suppresses opp FTR on court)

    def_ftr_impact is the RAPM-based "don't foul" signal.  Together with raw
    pf/game this captures both the box-score and the on/off reality.
    """
    pf_s = normalize(p.pf_pg, *refs.pf_pg, invert=True)

    def_ftr_s = (
        normalize(p.def_ftr_impact, *refs.def_ftr_impact)
        if p.def_ftr_impact is not None else SCORE_MID
    )

    return 0.55 * pf_s + 0.45 * def_ftr_s


def _perimeter_defense_score(p: PlayerFitInput, refs: SeasonRefs) -> float:
    """
    Per-player perimeter defense signal.

    Core = 0.55 × projected_dbpr_score    (dominant: overall defensive quality)
         + 0.30 × def_efg_impact_score    (limits opponent shooting efficiency)
         + 0.15 × stl_pg_score            (small contribution; active pressure sign)

    projected_dbpr is the dominant signal because the current codebase does
    not have contested-shot data or on-ball defensive metrics.  def_efg_impact
    is the best available "limits opponent shots" signal.

    Steals contribute only 15% — enough to give credit to active guards
    without letting a high-steal player mask poor defensive fundamentals.

    On-court adj_d modifier applied (lower opp efficiency = better defense).
    """
    dbpr_s = (
        normalize(p.projected_dbpr, *refs.proj_dbpr)
        if p.projected_dbpr is not None else SCORE_MID
    )

    def_efg_s = (
        normalize(p.def_efg_impact, *refs.def_efg_impact)
        if p.def_efg_impact is not None else SCORE_MID
    )

    stl_s = normalize(p.stl_pg, *refs.stl_pg)

    core = 0.55 * dbpr_s + 0.30 * def_efg_s + 0.15 * stl_s

    core = blend_core_oncourt(
        core,
        on_court_value=p.on_court_adj_d,
        on_court_poss=p.on_court_def_poss,
        ref_mean=refs.on_court_adj_d[0],
        ref_std=refs.on_court_adj_d[1],
        invert=True,
        max_modifier=ON_COURT_MAX_MODIFIER,
        shrinkage_k=ON_COURT_SHRINKAGE_K,
    )
    return core


def _mobility_score(p: PlayerFitInput, refs: SeasonRefs) -> float:
    """
    Per-player mobility / switchability signal.

    True switchability data does not exist.  The best available proxies are:
      - Wing role bucket (wings are presumed most switchable)
      - Steals (active, movement-oriented defenders tend to be switchable)
      - def_efg_impact (limits both perimeter and interior shots when on)

    Core = 0.50 × wing_bonus (binary: 1.0 if Wing, 0.55 if Guard, 0.30 if Big)
         + 0.30 × stl_pg_score
         + 0.20 × def_efg_impact_score

    The bucket multiplier is applied to SCORE_MID to produce a position-adjusted
    starting point.  Wings get full credit; bigs are penalized as less switchable
    (absent any height/agility data, this is the best available signal).
    """
    bucket_mult = {"Wing": 1.0, "G": 0.90, "Big": 0.55}.get(p.role_bucket, 0.75)
    position_s = SCORE_MID * bucket_mult + SCORE_MID * (1 - bucket_mult) * 0.40

    stl_s = normalize(p.stl_pg, *refs.stl_pg)

    def_efg_s = (
        normalize(p.def_efg_impact, *refs.def_efg_impact)
        if p.def_efg_impact is not None else SCORE_MID
    )

    return max(SCORE_MIN, min(SCORE_MAX,
        0.50 * position_s + 0.30 * stl_s + 0.20 * def_efg_s
    ))


# ── Roster-level size coverage score ─────────────────────────────────────────

def _size_coverage_score(
    players: list[PlayerFitInput],
    refs: SeasonRefs,
) -> float:
    """
    Roster-level size / interior coverage score.

    Because no height data exists, this uses role-bucket composition
    plus defensive interior signals as proxies for size/length.

    Formula:
        weighted_big_fraction = Σ(minutes_share × is_big) / Σ(minutes_share)
        interior_dreb_score   = minutes-weighted avg dreb_pg score (bigs anchor glass)
        blk_anchor_score      = max blk_pg in top-6 players, normalized

        base = 0.40 × map_big_fraction(weighted_big_fraction)
             + 0.35 × interior_dreb_score
             + 0.25 × blk_anchor_score

    map_big_fraction scales 0.08 (good, 1 true big in an 8-man rotation) to 80
    and 0.20 (excellent) to 100, with a floor at 0.

    Unlike other subcomponents, this is computed at the roster level because it
    is fundamentally about team composition, not per-player traits.
    """
    total_weight = sum(p.minutes_share_p2 for p in players)
    if total_weight < 1e-6:
        return SCORE_MID

    # Weighted big fraction
    weighted_bigs = sum(
        p.minutes_share_p2 for p in players if p.role_bucket == "Big"
    )
    big_fraction = weighted_bigs / total_weight

    # Map big fraction to 0-100.  Reference: a team with exactly 1 big
    # at 5 mpg in an 8-man rotation ≈ 0.08 big fraction → score ≈ 60.
    # 0.00 → 5, 0.08 → 60, 0.16 → 90, 0.25+ → 100 (with cap)
    big_fraction_score = max(SCORE_MIN, min(SCORE_MAX,
        5 + big_fraction * 600
    ))

    # Interior rebounding (bigs anchor the glass)
    interior_dreb_s = _weighted_avg(players, lambda p, r: normalize(p.dreb_pg, *r.dreb_pg), refs)

    # Block anchor: normalized score of the best blocker in top-6
    top6 = sorted(players, key=lambda p: p.minutes_share_p2, reverse=True)[:6]
    best_blk = max((p.blk_pg for p in top6), default=0.0)
    blk_anchor_s = normalize(best_blk, *refs.blk_pg)

    return max(SCORE_MIN, min(SCORE_MAX,
        0.40 * big_fraction_score + 0.35 * interior_dreb_s + 0.25 * blk_anchor_s
    ))


# ── Role balance subcomponent ─────────────────────────────────────────────────

def _role_balance_def_score(
    rotation_players: list[PlayerFitInput],
    top5_players: list[PlayerFitInput],
    refs: SeasonRefs,
) -> float:
    """
    Pure composition-based defensive role balance score.

    Starts at SCORE_MID and adjusts based on archetype distribution:
      +8  if rotation has both a rim_protector AND a disruptor
      +5  if rotation has exactly one rim_protector
      −6  if rotation has 4+ weak defenders in rotation (dbpr < -1.0)
      −4  if rotation has 0 disruptors AND 0 rim_protectors (no playmakers)

    (Structural penalties for weak-top-5 defense etc. live in the penalty
     registry, not here.)
    """
    score = SCORE_MID

    has_rim    = any("rim_protector" in p.archetypes for p in rotation_players)
    has_disruptor = any("disruptor" in p.archetypes for p in rotation_players)
    weak_count = sum(1 for p in rotation_players if "weak_defender" in p.archetypes)

    if has_rim and has_disruptor:
        score += 8.0
    if has_rim:
        score += 5.0
    if not has_rim and not has_disruptor:
        score -= 4.0
    if weak_count >= 4:
        score -= 6.0

    return max(SCORE_MIN, min(SCORE_MAX, score))


# ── Structural penalty registry ───────────────────────────────────────────────

def _compute_structural_penalties(
    rotation_players: list[PlayerFitInput],
    top5_players:     list[PlayerFitInput],
    players:          list[PlayerFitInput],
    refs:             SeasonRefs,
) -> list[tuple[str, float]]:
    """
    Evaluate all defensive structural penalties.

    Each flaw is assigned to exactly one primary subcomponent.
    """
    penalties = []

    # ── rim_protection_fit penalty ───────────────────────────────────────────
    has_rim_protector = any("rim_protector" in p.archetypes for p in rotation_players)
    if not has_rim_protector:
        penalties.append(("no_rim_protector", DEF_NO_RIM_PROTECTOR_PENALTY))

    # ── def_rebounding_fit penalty ───────────────────────────────────────────
    total_w = sum(p.minutes_share_p2 for p in players)
    if total_w > 1e-6:
        wtd_dreb = sum(p.minutes_share_p2 * p.dreb_pg for p in players) / total_w
        if wtd_dreb < DEF_WEAK_DREB_THRESHOLD:
            penalties.append(("poor_rebound_balance", DEF_POOR_REBOUND_BALANCE_PENALTY))

    # ── foul_discipline_fit penalty ──────────────────────────────────────────
    top5_foul_prone = sum(1 for p in top5_players if "foul_prone" in p.archetypes)
    if top5_foul_prone >= 2:
        penalties.append(("foul_stack_in_top5", DEF_FOUL_STACK_PENALTY))

    # ── size_coverage_fit penalty ────────────────────────────────────────────
    total_w_rot = sum(p.minutes_share_p2 for p in rotation_players) or 1.0
    wtd_big_fraction = sum(
        p.minutes_share_p2 for p in rotation_players if p.role_bucket == "Big"
    ) / total_w_rot
    if wtd_big_fraction < 0.07:
        penalties.append(("no_meaningful_big_minutes", DEF_FEW_BIGS_PENALTY))

    # ── role_balance_def_fit penalty ─────────────────────────────────────────
    top5_weak_def = sum(1 for p in top5_players if "weak_defender" in p.archetypes)
    if top5_weak_def >= 3:
        penalties.append(("weak_defense_top5", DEF_WEAK_TOP5_PENALTY))

    return penalties


# ── Penalty → subcomponent ownership ─────────────────────────────────────────

_PENALTY_OWNER = {
    "no_rim_protector":         "rim_protection_fit",
    "poor_rebound_balance":     "def_rebounding_fit",
    "foul_stack_in_top5":       "foul_discipline_fit",
    "no_meaningful_big_minutes": "size_coverage_fit",
    "weak_defense_top5":        "role_balance_def_fit",
}


# ── Main scorer ───────────────────────────────────────────────────────────────

def score_defensive_fit(
    players: list[PlayerFitInput],
    refs: SeasonRefs = DEFAULT_REFS,
) -> DefensiveFitResult:
    """
    Score the defensive fit of a roster.

    Args:
        players: One PlayerFitInput per rostered player (archetypes already tagged).
        refs:    Season-relative reference values.

    Returns:
        DefensiveFitResult with all subcomponent scores and defensive_fit_score.
    """
    from core.analytics.player_value.fit.constants import DEF_WEIGHTS
    from core.analytics.player_value.fit.archetypes import tag_archetypes

    if not players:
        return DefensiveFitResult()

    # Ensure archetypes are tagged (idempotent if already done by engine).
    for p in players:
        if not p.archetypes:
            p.archetypes = tag_archetypes(p)

    rotation = [p for p in players if p.minutes_share_p2 >= TOP_ROTATION_THRESHOLD]
    if not rotation:
        rotation = players

    top5 = sorted(players, key=lambda p: p.minutes_share_p2, reverse=True)[:5]

    # ── Subcomponent base scores ──────────────────────────────────────────────
    rim_s        = _weighted_avg(players, _rim_protection_score,   refs)
    dreb_s       = _weighted_avg(players, _def_rebounding_score,   refs)
    disruption_s = _weighted_avg(players, _disruption_score,       refs)
    foul_s       = _weighted_avg(players, _foul_discipline_score,  refs)
    perimeter_s  = _weighted_avg(players, _perimeter_defense_score, refs)
    size_s       = _size_coverage_score(players, refs)
    mobility_s   = _weighted_avg(players, _mobility_score,         refs)
    role_bal_s   = _role_balance_def_score(rotation, top5, refs)

    subcomponents = {
        "rim_protection_fit":    rim_s,
        "def_rebounding_fit":    dreb_s,
        "disruption_fit":        disruption_s,
        "foul_discipline_fit":   foul_s,
        "perimeter_defense_fit": perimeter_s,
        "size_coverage_fit":     size_s,
        "mobility_fit":          mobility_s,
        "role_balance_def_fit":  role_bal_s,
    }

    # ── Structural penalties ──────────────────────────────────────────────────
    raw_penalties = _compute_structural_penalties(rotation, top5, players, refs)

    total_positive = sum(pts for _, pts in raw_penalties if pts > 0)
    cap_scale = min(1.0, MAX_STRUCTURAL_PENALTY_DEF / max(total_positive, 1e-6))

    applied_penalties = []
    for label, pts in raw_penalties:
        effective = pts * cap_scale
        owner = _PENALTY_OWNER.get(label, "role_balance_def_fit")
        subcomponents[owner] = max(SCORE_MIN, subcomponents[owner] - effective)
        applied_penalties.append((label, effective))

    total_penalty = sum(pts for _, pts in applied_penalties)

    # ── Weighted overall defensive fit score ──────────────────────────────────
    defensive_score = sum(
        DEF_WEIGHTS[k] * subcomponents[k]
        for k in DEF_WEIGHTS
    )
    defensive_score = max(SCORE_MIN, min(SCORE_MAX, defensive_score))

    return DefensiveFitResult(
        rim_protection_fit=round(subcomponents["rim_protection_fit"], 2),
        def_rebounding_fit=round(subcomponents["def_rebounding_fit"], 2),
        disruption_fit=round(subcomponents["disruption_fit"], 2),
        foul_discipline_fit=round(subcomponents["foul_discipline_fit"], 2),
        perimeter_defense_fit=round(subcomponents["perimeter_defense_fit"], 2),
        size_coverage_fit=round(subcomponents["size_coverage_fit"], 2),
        mobility_fit=round(subcomponents["mobility_fit"], 2),
        role_balance_def_fit=round(subcomponents["role_balance_def_fit"], 2),
        structural_penalties=applied_penalties,
        total_penalty=round(total_penalty, 2),
        defensive_fit_score=round(defensive_score, 2),
    )
