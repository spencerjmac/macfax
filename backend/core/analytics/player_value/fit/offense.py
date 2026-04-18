"""
Roster Fit Model — Offensive fit scorer (Phase 3).

Produces 7 normalized offensive subcomponent scores (0-100) and applies
structural composition penalties.

Design
──────
Each subcomponent is built in two layers:

  1. Core trait score — minutes-weighted average of normalized player signals.
     Every raw feature is first converted from its native units to a 0-100
     scale via z-score mapping (50 = D1 average, ±1σ = ±15 pts).

  2. On-court modifier — a sample-dampened nudge using on_court_adj_o
     (the only on-court metric that is clearly offensive in direction).
     Reliability = poss / (poss + 300); max modifier ±6 pts.

Structural penalties live in a separate registry and are applied *after*
the normal subcomponent computation, with a cap (MAX_STRUCTURAL_PENALTY_OFF)
to prevent double-stacking.

Subcomponent ownership of structural penalties
───────────────────────────────────────────────
  creation_fit       → OFF_NO_PRIMARY_CREATOR_PENALTY
                       OFF_NO_SECONDARY_CREATOR_PENALTY
  shooting_fit       → OFF_FEW_SPACERS_PENALTY
                       OFF_SPACER_CONCENTRATION_BONUS  (positive)
  ball_security_fit  → OFF_BALL_STOPPER_POLLUTION_PENALTY
  role_balance_off   → OFF_MANY_NONSHOOTING_BIGS_PENALTY
                       OFF_ROLE_OVERLAP_PENALTY

This ensures each flaw is penalised at most once.

Shooting fit philosophy
────────────────────────
Shooting fit rewards the *distribution* of spacing, not just the weighted
average.  One elite spacer surrounded by five non-shooters does not produce
a good shooting-fit score — the spacer concentration bonus requires multiple
legitimate spacing threats.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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
    OFF_NO_PRIMARY_CREATOR_PENALTY,
    OFF_NO_SECONDARY_CREATOR_PENALTY,
    OFF_FEW_SPACERS_PENALTY,
    OFF_SPACER_CONCENTRATION_BONUS,
    OFF_MANY_NONSHOOTING_BIGS_PENALTY,
    OFF_BALL_STOPPER_POLLUTION_PENALTY,
    OFF_ROLE_OVERLAP_PENALTY,
    MAX_STRUCTURAL_PENALTY_OFF,
)


# ── Output dataclass ──────────────────────────────────────────────────────────

@dataclass
class OffensiveFitResult:
    """
    Per-roster offensive fit output.

    All subcomponent scores are on the 0-100 scale (50 = D1 average).
    `structural_penalties` is a list of (penalty_label, pts_deducted) tuples
    for diagnostics.  The sum is capped at MAX_STRUCTURAL_PENALTY_OFF.
    """
    # Subcomponent scores (pre-penalty)
    creation_fit:         float = 50.0
    shooting_fit:         float = 50.0
    ball_security_fit:    float = 50.0
    finishing_fit:        float = 50.0
    pressure_fit:         float = 50.0
    off_rebounding_fit:   float = 50.0
    role_balance_off_fit: float = 50.0

    # Structural penalties (post-aggregation; capped total)
    structural_penalties: list = None   # list[tuple[str, float]] populated at runtime
    total_penalty:        float = 0.0

    # Final weighted score (after penalty deduction from weighted average)
    offensive_fit_score:  float = 50.0

    def __post_init__(self):
        if self.structural_penalties is None:
            self.structural_penalties = []


# ── Minutes-weighted aggregation helper ───────────────────────────────────────

def _weighted_avg(
    players: list[PlayerFitInput],
    score_fn,
    refs: SeasonRefs,
) -> float:
    """
    Compute a minutes-share-weighted average of a per-player score function.

    Players with zero minutes_share_p2 are skipped.
    Returns SCORE_MID if no minutes weight is available.
    """
    total_weight = sum(p.minutes_share_p2 for p in players)
    if total_weight < 1e-6:
        return SCORE_MID
    return sum(
        p.minutes_share_p2 * score_fn(p, refs)
        for p in players
    ) / total_weight


# ── Per-player component scorers ──────────────────────────────────────────────

def _creation_score(p: PlayerFitInput, refs: SeasonRefs) -> float:
    """
    Per-player creation signal.

    Core = 0.60 × ast_score + 0.40 × off_tov_impact_score
    Secondary modifier: on-court adj_o nudge (limited).

    ast_pg is the clearest creation proxy in the current dataset.
    off_tov_impact captures the RAPM-derived ability to reduce team turnovers
    when on court, which is a secondary creation signal.
    """
    ast_s = normalize(p.ast_pg, *refs.ast_pg)

    if p.off_tov_impact is not None:
        tov_s = normalize(p.off_tov_impact, *refs.off_tov_impact)
    else:
        tov_s = SCORE_MID

    core = 0.60 * ast_s + 0.40 * tov_s

    # On-court modifier: on_court_adj_o reflects team scoring efficiency
    # when this player is on — relevant but noisy.
    core = blend_core_oncourt(
        core,
        on_court_value=p.on_court_adj_o,
        on_court_poss=p.on_court_off_poss,
        ref_mean=refs.on_court_adj_o[0],
        ref_std=refs.on_court_adj_o[1],
        invert=False,
        max_modifier=4.0,   # creation: modest on-court nudge
        shrinkage_k=ON_COURT_SHRINKAGE_K,
    )
    return core


def _shooting_core_score(p: PlayerFitInput, refs: SeasonRefs) -> float:
    """
    Per-player shooting contribution signal.

    Core = 0.50 × fg3a_score        (volume — spacing threat)
         + 0.30 × off_efg_score      (quality — impact on team eFG%)
         + 0.20 × efg_pct_score      (efficiency — individual shooting %)

    fg3a gets the largest weight because spacing is primarily a positioning /
    threat signal, not just whether shots go in.  A player attempting 7
    three-pointers per game forces the defense to respect them even if they
    are an average shooter.
    """
    fg3a_s = normalize(p.fg3a_pg, *refs.fg3a_pg)

    if p.off_efg_impact is not None:
        efg_impact_s = normalize(p.off_efg_impact, *refs.off_efg_impact)
    else:
        efg_impact_s = SCORE_MID

    efg_s = (
        normalize(p.efg_pct, *refs.efg_pct)
        if p.efg_pct is not None else SCORE_MID
    )

    return 0.50 * fg3a_s + 0.30 * efg_impact_s + 0.20 * efg_s


def _ball_security_score(p: PlayerFitInput, refs: SeasonRefs) -> float:
    """
    Per-player ball security signal.

    Core = 0.45 × off_tov_impact_score    (RAPM: reduces team TOV% when on)
         + 0.35 × tov_pg_score (inverted) (lower TOV/game → higher score)
         + 0.20 × ast_to_score            (assist-to-turnover ratio)

    Missing ast_to defaults to SCORE_MID.
    """
    if p.off_tov_impact is not None:
        tov_impact_s = normalize(p.off_tov_impact, *refs.off_tov_impact)
    else:
        tov_impact_s = SCORE_MID

    tov_raw_s = normalize(p.tov_pg, *refs.tov_pg, invert=True)

    ast_to_s = (
        normalize(p.ast_to, *refs.ast_to)
        if p.ast_to is not None else SCORE_MID
    )

    return 0.45 * tov_impact_s + 0.35 * tov_raw_s + 0.20 * ast_to_s


def _finishing_score(p: PlayerFitInput, refs: SeasonRefs) -> float:
    """
    Per-player 2PT finishing / offensive efficiency signal.

    Core = 0.50 × projected_obpr_score  (forward-looking offensive BPR)
         + 0.30 × off_efg_impact_score  (RAPM: team eFG% improvement on court)
         + 0.20 × ts_pct_score          (true shooting — most complete shot efficiency)

    Finishing vs shooting: shooting_fit is about spacing/3PT threat.
    finishing_fit is about interior efficiency, cutting, and overal offensive
    quality — hence the heavy weight on projected_obpr.
    """
    obpr_s = (
        normalize(p.projected_obpr, *refs.proj_obpr)
        if p.projected_obpr is not None else SCORE_MID
    )

    efg_impact_s = (
        normalize(p.off_efg_impact, *refs.off_efg_impact)
        if p.off_efg_impact is not None else SCORE_MID
    )

    ts_s = (
        normalize(p.ts_pct, *refs.ts_pct)
        if p.ts_pct is not None else SCORE_MID
    )

    core = 0.50 * obpr_s + 0.30 * efg_impact_s + 0.20 * ts_s

    # On-court adj_o nudge (offensive finishing is most directly captured here)
    core = blend_core_oncourt(
        core,
        on_court_value=p.on_court_adj_o,
        on_court_poss=p.on_court_off_poss,
        ref_mean=refs.on_court_adj_o[0],
        ref_std=refs.on_court_adj_o[1],
        max_modifier=ON_COURT_MAX_MODIFIER,
        shrinkage_k=ON_COURT_SHRINKAGE_K,
    )
    return core


def _pressure_score(p: PlayerFitInput, refs: SeasonRefs) -> float:
    """
    Per-player free-throw pressure signal.

    Core = 0.60 × fta_pg_score          (drawing fouls — volume of FTA)
         + 0.40 × off_ftr_impact_score  (RAPM: team FTR boost on court)

    FTA/game is the cleanest proxy for "puts pressure on the defense."
    """
    fta_s = normalize(p.fta_pg, *refs.fta_pg)

    ftr_impact_s = (
        normalize(p.off_ftr_impact, *refs.off_ftr_impact)
        if p.off_ftr_impact is not None else SCORE_MID
    )

    return 0.60 * fta_s + 0.40 * ftr_impact_s


def _off_rebounding_score(p: PlayerFitInput, refs: SeasonRefs) -> float:
    """
    Per-player offensive rebounding signal.

    Core = 0.60 × oreb_pg_score         (raw offensive boards)
         + 0.40 × off_orb_impact_score  (RAPM: team ORB% boost on court)
    """
    oreb_s = normalize(p.oreb_pg, *refs.oreb_pg)

    orb_impact_s = (
        normalize(p.off_orb_impact, *refs.off_orb_impact)
        if p.off_orb_impact is not None else SCORE_MID
    )

    return 0.60 * oreb_s + 0.40 * orb_impact_s


# ── Shooting distribution score (roster-level) ────────────────────────────────

def _shooting_distribution_score(
    players: list[PlayerFitInput],
    refs: SeasonRefs,
    rotation_players: list[PlayerFitInput],
) -> float:
    """
    Roster-level shooting fit that rewards distribution, not just average.

    Formula:
        raw = minutes-weighted per-player shooting core score
        distribution_weight = clamp(spacer_count, 0, 3) / 3   [0..1]
        final = raw × (0.6 + 0.4 × distribution_weight)

    The 0.6 floor means even a 0-spacer roster can score up to 60% of its
    weighted average.  A roster with 3+ spacers gets the full raw score.

    This prevents one elite spacer (100-score) surrounded by five non-shooters
    (20-score) from producing an inflated overall shooting score.
    """
    # Minutes-weighted average of per-player shooting core scores
    raw = _weighted_avg(players, _shooting_core_score, refs)

    # Spacer count in main rotation
    spacer_count = sum(
        1 for p in rotation_players if "spacer" in p.archetypes
    )
    distribution_weight = min(spacer_count, 3) / 3.0
    final = raw * (0.6 + 0.4 * distribution_weight)
    return max(SCORE_MIN, min(SCORE_MAX, final))


# ── Role balance subcomponent ─────────────────────────────────────────────────

def _role_balance_off_score(
    rotation_players: list[PlayerFitInput],
    refs: SeasonRefs,
) -> float:
    """
    Pure composition-based offensive role balance score.

    Starts at SCORE_MID and adjusts based on archetype distribution:
      +8  if rotation has both creators (primary or secondary) AND spacers
      +5  if rotation has at least one primary creator
      −5  if rotation has zero creators (primary or secondary)
      −6  if 2+ non-shooting bigs in rotation
      −4  if 3+ ball-stoppers in rotation

    (The large structural penalties for "no creator" and "non-shooting bigs"
     are assessed separately in the penalty registry, not here. This function
     adds the fine-grained balance signal above avg/below avg.)
    """
    score = SCORE_MID

    has_primary  = any("primary_creator" in p.archetypes for p in rotation_players)
    has_secondary = any("secondary_creator" in p.archetypes for p in rotation_players)
    has_spacers  = any("spacer" in p.archetypes for p in rotation_players)
    nsb_count    = sum(1 for p in rotation_players if "non_shooting_big" in p.archetypes)
    stopper_count = sum(1 for p in rotation_players if "ball_stopper" in p.archetypes)

    if (has_primary or has_secondary) and has_spacers:
        score += 8.0
    if has_primary:
        score += 5.0
    if not has_primary and not has_secondary:
        score -= 5.0
    if nsb_count >= 2:
        score -= 6.0
    if stopper_count >= 3:
        score -= 4.0

    return max(SCORE_MIN, min(SCORE_MAX, score))


# ── Structural penalty registry ───────────────────────────────────────────────

def _compute_structural_penalties(
    rotation_players: list[PlayerFitInput],
    top5_players:     list[PlayerFitInput],
) -> list[tuple[str, float]]:
    """
    Evaluate all offensive structural penalties.

    Returns a list of (label, pts_deducted) for triggered penalties, plus
    (label, pts_bonus) for triggered bonuses (negative pts = bonus add).

    Each structural flaw is assigned to exactly ONE primary subcomponent.
    The engine reads this list and applies the penalty to that subcomponent,
    ensuring no double-counting across subcomponents.
    """
    penalties = []

    # ── creation_fit penalties ───────────────────────────────────────────
    has_primary_creator   = any("primary_creator" in p.archetypes for p in rotation_players)
    has_secondary_creator = any("secondary_creator" in p.archetypes for p in rotation_players)

    if not has_primary_creator:
        penalties.append(("no_primary_creator", OFF_NO_PRIMARY_CREATOR_PENALTY))
    if not has_primary_creator and not has_secondary_creator:
        penalties.append(("no_secondary_creator", OFF_NO_SECONDARY_CREATOR_PENALTY))

    # ── shooting_fit penalties ───────────────────────────────────────────
    spacer_count = sum(1 for p in rotation_players if "spacer" in p.archetypes)
    if spacer_count < 2:
        penalties.append(("few_spacers", OFF_FEW_SPACERS_PENALTY))
    elif spacer_count >= 3:
        penalties.append(("spacer_concentration_bonus", -OFF_SPACER_CONCENTRATION_BONUS))

    # ── ball_security_fit penalty ────────────────────────────────────────
    top5_ball_stoppers = sum(1 for p in top5_players if "ball_stopper" in p.archetypes)
    if top5_ball_stoppers >= 1:
        penalties.append(("ball_stopper_in_top5", OFF_BALL_STOPPER_POLLUTION_PENALTY))

    # ── role_balance_off_fit penalties ───────────────────────────────────
    nsb_count = sum(1 for p in rotation_players if "non_shooting_big" in p.archetypes)
    if nsb_count >= 2:
        penalties.append(("many_non_shooting_bigs", OFF_MANY_NONSHOOTING_BIGS_PENALTY))

    if not has_primary_creator and not has_secondary_creator and spacer_count == 0:
        penalties.append(("no_creator_no_spacer_overlap", OFF_ROLE_OVERLAP_PENALTY))

    return penalties


# ── Main scorer ───────────────────────────────────────────────────────────────

# Maps penalty labels to which subcomponent owns them
_PENALTY_OWNER = {
    "no_primary_creator":          "creation_fit",
    "no_secondary_creator":        "creation_fit",
    "few_spacers":                 "shooting_fit",
    "spacer_concentration_bonus":  "shooting_fit",
    "ball_stopper_in_top5":        "ball_security_fit",
    "many_non_shooting_bigs":      "role_balance_off_fit",
    "no_creator_no_spacer_overlap": "role_balance_off_fit",
}


def score_offensive_fit(
    players: list[PlayerFitInput],
    refs: SeasonRefs = DEFAULT_REFS,
) -> OffensiveFitResult:
    """
    Score the offensive fit of a roster.

    Args:
        players: One PlayerFitInput per rostered player (archetypes already tagged).
        refs:    Season-relative reference values (defaults to D1 constants).

    Returns:
        OffensiveFitResult with all subcomponent scores and the weighted
        offensive_fit_score.
    """
    from core.analytics.player_value.fit.constants import OFF_WEIGHTS
    from core.analytics.player_value.fit.archetypes import tag_archetypes

    if not players:
        return OffensiveFitResult()

    # Ensure archetypes are tagged (idempotent if already done by engine).
    for p in players:
        if not p.archetypes:
            p.archetypes = tag_archetypes(p)

    # Split into rotation vs. full roster.
    rotation = [p for p in players if p.minutes_share_p2 >= TOP_ROTATION_THRESHOLD]
    if not rotation:
        rotation = players  # fallback: treat all as rotation

    # Top-5 by minutes for ball-stopper check
    top5 = sorted(players, key=lambda p: p.minutes_share_p2, reverse=True)[:5]

    # ── Compute subcomponent base scores ─────────────────────────────────────
    creation_s        = _weighted_avg(players, _creation_score,        refs)
    shooting_s        = _shooting_distribution_score(players, refs, rotation)
    ball_security_s   = _weighted_avg(players, _ball_security_score,   refs)
    finishing_s       = _weighted_avg(players, _finishing_score,       refs)
    pressure_s        = _weighted_avg(players, _pressure_score,        refs)
    off_rebounding_s  = _weighted_avg(players, _off_rebounding_score,  refs)
    role_balance_s    = _role_balance_off_score(rotation, refs)

    subcomponents = {
        "creation_fit":         creation_s,
        "shooting_fit":         shooting_s,
        "ball_security_fit":    ball_security_s,
        "finishing_fit":        finishing_s,
        "pressure_fit":         pressure_s,
        "off_rebounding_fit":   off_rebounding_s,
        "role_balance_off_fit": role_balance_s,
    }

    # ── Apply structural penalties ────────────────────────────────────────────
    raw_penalties = _compute_structural_penalties(rotation, top5)

    # Three-step penalty application:
    # 1. Cap total penalty at MAX_STRUCTURAL_PENALTY_OFF.
    # 2. Deduct each penalty from its owner subcomponent (floored at SCORE_MIN).
    # 3. Bonus entries (negative pts) are added to their owner subcomponent.
    total_positive = sum(pts for _, pts in raw_penalties if pts > 0)
    cap_scale = min(1.0, MAX_STRUCTURAL_PENALTY_OFF / max(total_positive, 1e-6))

    applied_penalties = []
    for label, pts in raw_penalties:
        if pts > 0:
            effective = pts * cap_scale
            owner = _PENALTY_OWNER.get(label, "role_balance_off_fit")
            subcomponents[owner] = max(SCORE_MIN, subcomponents[owner] - effective)
            applied_penalties.append((label, effective))
        else:
            # Bonus (negative pts value = addition)
            owner = _PENALTY_OWNER.get(label, "shooting_fit")
            bonus = -pts   # positive amount
            subcomponents[owner] = min(SCORE_MAX, subcomponents[owner] + bonus)
            applied_penalties.append((label, pts))   # keep sign for diagnostics

    total_penalty = sum(pts for _, pts in applied_penalties if pts > 0)

    # ── Weighted overall offensive fit score ──────────────────────────────────
    offensive_score = sum(
        OFF_WEIGHTS[k] * subcomponents[k]
        for k in OFF_WEIGHTS
    )
    offensive_score = max(SCORE_MIN, min(SCORE_MAX, offensive_score))

    return OffensiveFitResult(
        creation_fit=round(subcomponents["creation_fit"], 2),
        shooting_fit=round(subcomponents["shooting_fit"], 2),
        ball_security_fit=round(subcomponents["ball_security_fit"], 2),
        finishing_fit=round(subcomponents["finishing_fit"], 2),
        pressure_fit=round(subcomponents["pressure_fit"], 2),
        off_rebounding_fit=round(subcomponents["off_rebounding_fit"], 2),
        role_balance_off_fit=round(subcomponents["role_balance_off_fit"], 2),
        structural_penalties=applied_penalties,
        total_penalty=round(total_penalty, 2),
        offensive_fit_score=round(offensive_score, 2),
    )
