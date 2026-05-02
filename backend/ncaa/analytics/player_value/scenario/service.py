"""
scenario/service.py — Scenario orchestration service (Sprint 3).

Main entry point: compute_scenario(request) → ScenarioResult

Pipeline (all in-memory, no DB writes):
  Step 1  Load D1Context + placeholder lookup
  Step 2  Resolve each slot → ScenarioPlayerResolved
  Step 3  Phase 2: allocate_roster_minutes() + apply_mpg_overrides()
  Step 4  Phase 3: score_roster_fit()
  Step 5  Phase 5: project_team()
  Step 6  Build ScenarioResult (archetypes, ranks, comparison)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ncaa.analytics.player_value.scenario.manual_player import (
    ManualPlayerSpec,
    ScenarioPlayerResolved,
    SOURCE_TIER_DB,
    resolve_manual_player,
    resolve_db_player,
)
from ncaa.analytics.player_value.minutes.engine import (
    PlayerMinutesInput,
    PlayerMinutesOutput,
    RosterAllocationResult,
    allocate_roster_minutes,
)
from ncaa.analytics.player_value.minutes.constants import (
    TEAM_TOTAL_SHARES,
    MINIMUM_PLAYER_SHARE,
    MAXIMUM_PLAYER_SHARE,
)
from ncaa.analytics.player_value.team_projection.engine import (
    D1Context,
    PlayerProjectionInput,
    RosterFitInput,
    project_team,
    _uncertainty_to_sigma,
)
from ncaa.analytics.player_value.team_projection.constants import (
    FALLBACK_D1_ADJ_O,
    FALLBACK_D1_ADJ_D,
)
from ncaa.analytics.player_value.fit.archetypes import (
    PlayerFitInput,
    DEFAULT_REFS,
    tag_archetypes,
)
from ncaa.analytics.player_value.fit.engine import score_roster_fit

logger = logging.getLogger(__name__)


# ── Request/response dataclasses ──────────────────────────────────────────────

@dataclass
class ScenarioSlot:
    """One player slot in a scenario roster."""
    slot_type: str              # 'db_player' | 'manual_player'
    projection_id: Optional[int] = None
    manual_spec: Optional[ManualPlayerSpec] = None


@dataclass
class ScenarioRosterRequest:
    """Validated scenario computation request."""
    team_id: int
    season_year: int
    slots: list[ScenarioSlot]
    compare_to_baseline: bool = False
    overrides: dict = field(default_factory=dict)


@dataclass
class ScenarioPlayerResult:
    """Per-player output within a ScenarioResult."""
    player_id: int
    display_name: str
    slot_id: str
    is_manual: bool
    source_tier: str
    display_label: str
    role_bucket: str
    rotation_rank: int
    minutes_share: float
    mpg: float
    is_overridden: bool
    projected_obpr: float
    projected_dbpr: float
    projected_bpr: float
    projection_uncertainty: float
    recruitment_type: str
    resolution_method: str
    national_rank: Optional[int]
    stars: Optional[int]
    is_juco: bool
    archetypes: list[str]
    competition_warning: Optional[str] = None


@dataclass
class ScenarioResult:
    """Full scenario computation result."""
    # Input echo
    team_id: int
    season_year: int
    projected_season_year: int

    # Per-player
    players: list[ScenarioPlayerResult]

    # Phase 5 team projection
    projected_adj_o: float
    projected_adj_d: float
    projected_adj_em: float
    projected_adj_em_low: float
    projected_adj_em_high: float
    projected_national_rank: Optional[int]
    national_rank_range_low: Optional[int]
    national_rank_range_high: Optional[int]
    rank_display: str
    projected_offense_rank: Optional[int]
    offense_rank_range_low: Optional[int]
    offense_rank_range_high: Optional[int]
    off_rank_display: str
    projected_defense_rank: Optional[int]
    defense_rank_range_low: Optional[int]
    defense_rank_range_high: Optional[int]
    def_rank_display: str
    team_projection_uncertainty: float
    continuity_score: float
    transfer_dependence_score: float

    # Phase 3 fit
    offensive_fit_score: float
    defensive_fit_score: float
    overall_fit_score: float
    off_subcomponents: dict
    def_subcomponents: dict
    top_off_strengths: list[str]
    top_off_weaknesses: list[str]
    top_def_strengths: list[str]
    top_def_weaknesses: list[str]
    structural_penalties: dict

    # Metadata
    n_manual_players: int
    n_db_players: int
    has_mpg_overrides: bool
    computed_at: str

    # Coaching flag (Sprint 5)
    is_first_year_coach: bool = False

    # Baseline comparison (optional)
    baseline_adj_em: Optional[float] = None
    adj_em_delta: Optional[float] = None


# ── DB helpers ────────────────────────────────────────────────────────────────

def load_placeholder_lookup(season_year: Optional[int] = None) -> dict[str, dict]:
    """
    Load all PlaceholderArchetype rows for resolve_manual_player().

    If season_year is provided but no rows match, retries with no year filter
    to always return a non-empty lookup when archetypes exist.

    Returns:
        {key: archetype_data_dict} keyed by PlaceholderArchetype.key.
    """
    from ncaa.models import PlaceholderArchetype

    def _build(qs) -> dict:
        return {
            arch["key"]: arch
            for arch in qs.values(
                "key", "display_name", "conf_group", "role_bucket", "quality_tier",
                "projected_obpr", "projected_dbpr", "projected_bpr",
                "minutes_share", "mpg", "uncertainty",
                "efg_pct", "fg3_pct", "ts_pct", "ast_to",
                "oreb_pg", "dreb_pg", "tov", "fg3a_pg",
                "sample_n", "source_season_year",
            )
        }

    qs = PlaceholderArchetype.objects.all()
    if season_year:
        filtered = _build(qs.filter(source_season_year=season_year))
        if filtered:
            return filtered
    return _build(qs)


def _get_d1_context_for_scenario(season) -> D1Context:
    """
    Build D1Context for scenario projection.

    Primary: reads stored aggregates from TeamSeasonProjection (fast, O(1)).
    Fallback when empty: computes league means from PlayerSeasonProjection rows
    (same approach as the production pipeline's first pass).
    """
    from django.db.models import Avg
    from ncaa.models import TeamSeasonRatings, TeamSeasonProjection, PlayerSeasonProjection

    agg_ratings = TeamSeasonRatings.objects.filter(season=season).aggregate(
        mean_o=Avg("adj_o"), mean_d=Avg("adj_d"),
    )
    avg_adj_o = float(agg_ratings["mean_o"] or FALLBACK_D1_ADJ_O)
    avg_adj_d = float(agg_ratings["mean_d"] or FALLBACK_D1_ADJ_D)

    agg_proj = TeamSeasonProjection.objects.filter(from_season=season).aggregate(
        mean_off=Avg("base_team_offense"),
        mean_def=Avg("base_team_defense"),
    )
    n_teams = TeamSeasonProjection.objects.filter(from_season=season).count()

    if agg_proj["mean_off"] is not None:
        league_mean_base_off = float(agg_proj["mean_off"])
        league_mean_base_def = float(agg_proj["mean_def"] or avg_adj_d)
    else:
        # Fallback: compute from PlayerSeasonProjection (before Phase 5 has run)
        psp_rows = PlayerSeasonProjection.objects.filter(
            from_season=season,
            minutes_share_p2__isnull=False,
            projected_obpr__isnull=False,
        ).values("team_id", "projected_obpr", "projected_dbpr", "minutes_share_p2")

        team_base_offs: dict[int, float] = defaultdict(float)
        team_base_defs: dict[int, float] = defaultdict(float)
        for row in psp_rows:
            tid = row["team_id"]
            team_base_offs[tid] += float(row["projected_obpr"] or 0.0) * float(row["minutes_share_p2"] or 0.0)
            team_base_defs[tid] += float(row["projected_dbpr"] or 0.0) * float(row["minutes_share_p2"] or 0.0)

        if team_base_offs:
            league_mean_base_off = sum(team_base_offs.values()) / len(team_base_offs)
            league_mean_base_def = sum(team_base_defs.values()) / len(team_base_defs)
            n_teams = len(team_base_offs)
        else:
            league_mean_base_off = avg_adj_o
            league_mean_base_def = avg_adj_d
            n_teams = 1

    return D1Context(
        avg_adj_o=avg_adj_o,
        avg_adj_d=avg_adj_d,
        league_mean_base_off=league_mean_base_off,
        league_mean_base_def=league_mean_base_def,
        n_projected_teams=max(n_teams, 1),
    )


def _fmt_rank_display(rank, rank_low, rank_high) -> str:
    """Format rank as '15 (5–35)', 'Unranked', or '15' when range is a single point."""
    if rank is None:
        return "Unranked"
    if rank_low is None or rank_high is None or rank_low == rank_high:
        return str(rank)
    return f"{rank} ({rank_low}–{rank_high})"


def _approx_rank(season, scenario_em: float, uncertainty: float = 0.0) -> dict:
    """Approximate national rank by counting teams projected better than scenario_em.

    rank_range uses uncertainty-based sigma bands (±2σ on adj_em) rather than a fixed ±15.
    """
    from ncaa.models import TeamSeasonProjection

    existing = list(
        TeamSeasonProjection.objects.filter(from_season=season)
        .values_list("projected_adj_em", flat=True)
    )
    n = len(existing)
    rank = sum(1 for em in existing if em > scenario_em) + 1
    sigma_pts = _uncertainty_to_sigma(uncertainty)
    rank_low  = max(1, sum(1 for em in existing if em > scenario_em + 2 * sigma_pts) + 1)
    rank_high = min(n + 1, sum(1 for em in existing if em > scenario_em - 2 * sigma_pts) + 1)
    return {
        "approx_rank": rank,
        "n_teams": n,
        "rank_range_low": rank_low,
        "rank_range_high": rank_high,
    }


def _approx_offense_defense_ranks(
    season,
    adj_o: float,
    adj_d: float,
    uncertainty: float = 0.0,
) -> dict:
    """Approximate offense and defense ranks against the stored distribution.

    Offense: higher adj_o = better (lower rank number).
    Defense: lower adj_d = better (lower rank number).
    Returns: off_rank, off_rank_low, off_rank_high, def_rank, def_rank_low, def_rank_high
    """
    from ncaa.models import TeamSeasonProjection

    rows = list(
        TeamSeasonProjection.objects.filter(from_season=season)
        .values_list("projected_adj_o", "projected_adj_d")
    )
    if not rows:
        return {
            "off_rank": None, "off_rank_low": None, "off_rank_high": None,
            "def_rank": None, "def_rank_low": None, "def_rank_high": None,
        }

    existing_os = [r[0] for r in rows]
    existing_ds = [r[1] for r in rows]
    n = len(rows)
    sigma_pts = _uncertainty_to_sigma(uncertainty)

    # Offense: higher is better
    off_rank      = sum(1 for o in existing_os if o > adj_o) + 1
    off_rank_low  = max(1, sum(1 for o in existing_os if o > adj_o + sigma_pts) + 1)
    off_rank_high = min(n + 1, sum(1 for o in existing_os if o > adj_o - sigma_pts) + 1)

    # Defense: lower is better (fewer pts allowed)
    def_rank      = sum(1 for d in existing_ds if d < adj_d) + 1
    def_rank_low  = max(1, sum(1 for d in existing_ds if d < adj_d - sigma_pts) + 1)
    def_rank_high = min(n + 1, sum(1 for d in existing_ds if d < adj_d + sigma_pts) + 1)

    return {
        "off_rank": off_rank,
        "off_rank_low": off_rank_low,
        "off_rank_high": off_rank_high,
        "def_rank": def_rank,
        "def_rank_low": def_rank_low,
        "def_rank_high": def_rank_high,
    }


# ── apply_mpg_overrides ───────────────────────────────────────────────────────

def apply_mpg_overrides(
    allocation_result: RosterAllocationResult,
    overrides: dict[int, float],
    team_total: float = TEAM_TOTAL_SHARES,
    min_share: float = MINIMUM_PLAYER_SHARE,
    max_share: float = MAXIMUM_PLAYER_SHARE,
) -> RosterAllocationResult:
    """
    Apply intended-MPG overrides to a RosterAllocationResult.

    Pins overridden players' shares, then re-scales non-pinned players
    proportionally to maintain team_total. Preserves relative rank order
    of non-overridden players.

    Args:
        allocation_result: Phase 2 output from allocate_roster_minutes().
        overrides:         {player_id: intended_minutes_share} for pinned players.
        team_total:        Target total shares (default 5.0).
        min_share:         Per-player floor.
        max_share:         Per-player ceiling.

    Returns:
        New RosterAllocationResult with updated shares, mpg, rotation_rank,
        and is_overridden flags.
    """
    if not overrides:
        return allocation_result

    import dataclasses

    # Step 1: pin overridden players, build separate lists
    pinned: list[PlayerMinutesOutput] = []
    non_pinned: list[PlayerMinutesOutput] = []
    pinned_total = 0.0

    for p in allocation_result.players:
        if p.player_id in overrides:
            pinned_share = max(min_share, min(max_share, overrides[p.player_id]))
            pinned.append(dataclasses.replace(p, minutes_share=pinned_share, is_overridden=True))
            pinned_total += pinned_share
        else:
            non_pinned.append(dataclasses.replace(p))

    remaining_budget = team_total - pinned_total

    # Step 2: scale non-pinned proportionally
    if non_pinned:
        raw_total = sum(p.minutes_share for p in non_pinned)
        if raw_total > 0.0 and remaining_budget > 0.0:
            scale = remaining_budget / raw_total
            non_pinned = [
                dataclasses.replace(p, minutes_share=max(min_share, min(max_share, p.minutes_share * scale)))
                for p in non_pinned
            ]
        elif remaining_budget > 0.0:
            share_each = remaining_budget / len(non_pinned)
            non_pinned = [
                dataclasses.replace(p, minutes_share=max(min_share, min(max_share, share_each)))
                for p in non_pinned
            ]

        # Step 3: iterative water-fill for rounding drift and cap violations
        # Some players may be capped at max_share; distribute their excess to others.
        for _ in range(20):
            current_total = pinned_total + sum(p.minutes_share for p in non_pinned)
            diff = team_total - current_total
            if abs(diff) < 1e-6:
                break
            uncapped = [p for p in non_pinned if p.minutes_share < max_share - 1e-9]
            if not uncapped:
                break
            share_add = diff / len(uncapped)
            non_pinned_new = []
            for p in non_pinned:
                if p.minutes_share < max_share - 1e-9:
                    non_pinned_new.append(
                        dataclasses.replace(p, minutes_share=max(min_share, min(max_share, p.minutes_share + share_add)))
                    )
                else:
                    non_pinned_new.append(p)
            non_pinned = non_pinned_new

    # Step 4: recompute mpg and rotation_rank
    all_players = pinned + non_pinned
    all_players.sort(key=lambda p: p.minutes_share, reverse=True)
    final_players = [
        dataclasses.replace(p, mpg=round(p.minutes_share * 40.0, 3), rotation_rank=rank + 1)
        for rank, p in enumerate(all_players)
    ]

    total = sum(p.minutes_share for p in final_players)
    return RosterAllocationResult(
        players=final_players,
        total_shares=round(total, 4),
        total_mpg=round(total * 40.0, 2),
        top_5_share=sum(p.minutes_share for p in final_players[:5]),
        top_8_share=sum(p.minutes_share for p in final_players[:8]),
        top_9_share=sum(p.minutes_share for p in final_players[:9]),
        n_above_tenth_share=sum(1 for p in final_players if p.minutes_share >= 0.10),
        n_above_quarter_share=sum(1 for p in final_players if p.minutes_share >= 0.25),
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def compute_scenario(request: ScenarioRosterRequest) -> ScenarioResult:
    """
    Run the full in-memory scenario pipeline (Phases 2–5) and return a result.

    No DB writes. Negative synthetic player_ids are used for manual players.
    Phase 4 contextual modifiers are neutral for scenarios (has_team_style_data=False).

    Args:
        request: Validated ScenarioRosterRequest.

    Returns:
        ScenarioResult with per-player data, team projection, fit scores,
        archetypes, and optional baseline comparison.

    Raises:
        ValueError: If fewer than 3 players resolve successfully.
        Season.DoesNotExist: If season_year is not in the DB.
        Team.DoesNotExist: If team_id is not in the DB.
    """
    from ncaa.models import (
        Season, Team, PlayerSeasonProjection, PlayerSeasonStats,
        Player, TeamSeasonProjection,
    )

    # ── Step 1: Load context ──────────────────────────────────────────────────
    from ncaa.conf_utils import get_conf_detail
    from ncaa.models import TeamSeasonStats as _TeamSeasonStats
    season = Season.objects.get(year=request.season_year)
    team   = Team.objects.get(id=request.team_id)
    target_conf_group = get_conf_detail(team.slug)
    d1_context = _get_d1_context_for_scenario(season)
    placeholder_lookup = load_placeholder_lookup(request.season_year)

    # Load first-year coach flag for this team/season
    first_year_coach = _TeamSeasonStats.objects.filter(
        team_id=request.team_id,
        season__year=request.season_year,
        is_first_year_coach=True,
    ).exists()

    # ── Step 2: Resolve slots ─────────────────────────────────────────────────
    resolved: list[ScenarioPlayerResolved] = []
    synthetic_counter = -1

    for slot in request.slots:
        if slot.slot_type == "db_player" and slot.projection_id is not None:
            psp = (
                PlayerSeasonProjection.objects
                .filter(id=slot.projection_id)
                .select_related("player")
                .values(
                    "id", "player_id", "from_season_id",
                    "projected_obpr", "projected_dbpr", "projected_bpr",
                    "projection_uncertainty", "recruitment_type", "n_prior_seasons",
                    "player__display_name", "player__position",
                )
                .first()
            )
            if psp is None:
                raise ValueError(f"PlayerSeasonProjection {slot.projection_id} not found.")

            pss = (
                PlayerSeasonStats.objects
                .filter(player_id=psp["player_id"], season_id=psp["from_season_id"])
                .values("mpg", "gp", "off_poss", "def_poss", "ast", "blk", "reb", "fg3a_pg")
                .first()
            ) or {}

            proj_dict = dict(psp)
            proj_dict["player_name"] = psp.get("player__display_name", "")
            r = resolve_db_player(
                projection=proj_dict,
                stats=pss,
                position=psp.get("player__position") or "",
            )
            resolved.append(r)

        elif slot.slot_type == "manual_player" and slot.manual_spec is not None:
            slot.manual_spec.conf_group = target_conf_group
            r = resolve_manual_player(slot.manual_spec, placeholder_lookup, synthetic_counter)
            synthetic_counter -= 1
            resolved.append(r)

    if len(resolved) < 3:
        raise ValueError(f"Scenario requires at least 3 players; got {len(resolved)}.")

    # Warn on unrealistic total intended MPG
    total_intended = sum(
        r.intended_mpg for r in resolved if r.intended_mpg is not None
    )
    if total_intended > 40.0:
        logger.warning(
            "[Scenario] Total intended_mpg %s > 40 for team_id=%s — re-normalization will balance.",
            total_intended, request.team_id,
        )

    # ── Step 3: Phase 2 — minutes allocation ─────────────────────────────────
    minutes_inputs = [
        PlayerMinutesInput(
            player_id=r.player_id,
            projected_bpr=r.projected_bpr,
            projection_uncertainty=r.projection_uncertainty,
            recruitment_type=r.recruitment_type,
            n_prior_seasons=r.n_prior_seasons,
            prior_mpg=r.prior_mpg,
            prior_gp=r.prior_gp,
            prior_poss=r.prior_poss,
            position=r.position,
            ast_pg=r.ast_pg,
            blk_pg=r.blk_pg,
            reb_pg=r.reb_pg,
            fg3a_pg=r.fg3a_pg,
        )
        for r in resolved
    ]
    alloc_result = allocate_roster_minutes(minutes_inputs)

    # Apply intended_mpg overrides
    mpg_overrides = {
        r.player_id: r.intended_mpg / 40.0
        for r in resolved
        if r.intended_mpg is not None
    }
    has_mpg_overrides = bool(mpg_overrides)
    if mpg_overrides:
        alloc_result = apply_mpg_overrides(alloc_result, mpg_overrides)

    alloc_by_id: dict[int, PlayerMinutesOutput] = {
        p.player_id: p for p in alloc_result.players
    }

    # ── Step 4: Phase 3 — roster fit ─────────────────────────────────────────
    fit_inputs: list[PlayerFitInput] = []
    for r in resolved:
        alloc = alloc_by_id[r.player_id]
        fit_inputs.append(PlayerFitInput(
            player_id=r.player_id,
            player_name=r.display_name,
            minutes_share_p2=alloc.minutes_share,
            rotation_rank=alloc.rotation_rank,
            role_bucket=alloc.role_bucket,   # Phase 2 result — not raw position
            projected_obpr=r.projected_obpr,
            projected_dbpr=r.projected_dbpr,
            gp=r.prior_gp,
            fg3a_pg=r.fg3a_pg,
            ast_pg=r.ast_pg,
            blk_pg=r.blk_pg,
            reb_pg=r.reb_pg,
            # Four-factor impacts left as None for manual players (no RAPM)
            # Recruiting profile (Sprint 4)
            national_rank=r.national_rank if r.is_manual else None,
            recruit_stars=r.stars if r.is_manual else None,
            is_juco_transfer=r.is_juco if r.is_manual else False,
            conf_group=None,  # scenario: no conf_group — team-agnostic by default
        ))

    fit_result = score_roster_fit(
        fit_inputs,
        refs=DEFAULT_REFS,
        team_id=request.team_id,
        season_year=request.season_year + 1,
    )

    # ── Step 5: Phase 5 — team projection ────────────────────────────────────
    engine_inputs = [
        PlayerProjectionInput(
            player_id=r.player_id,
            projected_obpr=r.projected_obpr,
            projected_dbpr=r.projected_dbpr,
            projected_bpr=r.projected_bpr,
            minutes_share_p2=alloc_by_id[r.player_id].minutes_share,
            recruitment_type=r.recruitment_type,
            projection_uncertainty=r.projection_uncertainty,
        )
        for r in resolved
    ]

    roster_fit_input = RosterFitInput(
        offensive_fit_score=fit_result.offensive_fit_score,
        defensive_fit_score=fit_result.defensive_fit_score,
        adjusted_off_fit=50.0,   # neutral — no Phase 4 for scenarios
        adjusted_def_fit=50.0,
        has_team_style_data=False,
    )

    team_result = project_team(engine_inputs, roster_fit_input, d1_context,
                               is_first_year_coach=first_year_coach)

    # ── Step 6: Build per-player results with archetypes ─────────────────────
    fit_by_pid = {fi.player_id: fi for fi in fit_inputs}
    player_results: list[ScenarioPlayerResult] = []

    for r in resolved:
        alloc = alloc_by_id[r.player_id]
        fi = fit_by_pid.get(r.player_id)
        archetypes_list: list[str] = []
        if fi is not None:
            archetypes_list = sorted(tag_archetypes(fi))

        player_results.append(ScenarioPlayerResult(
            player_id=r.player_id,
            display_name=r.display_name,
            slot_id=r.slot_id,
            is_manual=r.is_manual,
            source_tier=r.source_tier,
            display_label=r.display_label,
            role_bucket=alloc.role_bucket,
            rotation_rank=alloc.rotation_rank,
            minutes_share=round(alloc.minutes_share, 4),
            mpg=round(alloc.mpg, 2),
            is_overridden=alloc.is_overridden,
            projected_obpr=r.projected_obpr,
            projected_dbpr=r.projected_dbpr,
            projected_bpr=r.projected_bpr,
            projection_uncertainty=r.projection_uncertainty,
            recruitment_type=r.recruitment_type,
            resolution_method=r.resolution_method,
            national_rank=r.national_rank,
            stars=r.stars,
            is_juco=r.is_juco,
            archetypes=archetypes_list,
            competition_warning=r.competition_warning,
        ))

    # Sort by rotation_rank
    player_results.sort(key=lambda p: p.rotation_rank)

    # ── Step 7: Approximate rank (national + offense + defense) ──────────────
    uncertainty = team_result.team_projection_uncertainty
    rank_info = _approx_rank(season, team_result.projected_adj_em, uncertainty)
    od_ranks  = _approx_offense_defense_ranks(
        season, team_result.projected_adj_o, team_result.projected_adj_d, uncertainty
    )

    # ── Step 8: Baseline comparison (optional) ────────────────────────────────
    baseline_adj_em: Optional[float] = None
    adj_em_delta: Optional[float] = None
    if request.compare_to_baseline:
        try:
            bl = TeamSeasonProjection.objects.get(team=team, from_season=season)
            baseline_adj_em = bl.projected_adj_em
            adj_em_delta = round(team_result.projected_adj_em - baseline_adj_em, 3)
        except TeamSeasonProjection.DoesNotExist:
            pass

    # ── Step 9: Assemble and return ───────────────────────────────────────────
    summary = fit_result.fit_summary
    n_manual = sum(1 for r in resolved if r.is_manual)
    n_db     = len(resolved) - n_manual

    return ScenarioResult(
        team_id=request.team_id,
        season_year=request.season_year,
        projected_season_year=request.season_year + 1,
        players=player_results,
        projected_adj_o=round(team_result.projected_adj_o, 3),
        projected_adj_d=round(team_result.projected_adj_d, 3),
        projected_adj_em=round(team_result.projected_adj_em, 3),
        projected_adj_em_low=round(team_result.projected_adj_em_low, 3),
        projected_adj_em_high=round(team_result.projected_adj_em_high, 3),
        projected_national_rank=rank_info["approx_rank"],
        national_rank_range_low=rank_info["rank_range_low"],
        national_rank_range_high=rank_info["rank_range_high"],
        rank_display=_fmt_rank_display(
            rank_info["approx_rank"],
            rank_info["rank_range_low"],
            rank_info["rank_range_high"],
        ),
        projected_offense_rank=od_ranks["off_rank"],
        offense_rank_range_low=od_ranks["off_rank_low"],
        offense_rank_range_high=od_ranks["off_rank_high"],
        off_rank_display=_fmt_rank_display(
            od_ranks["off_rank"],
            od_ranks["off_rank_low"],
            od_ranks["off_rank_high"],
        ),
        projected_defense_rank=od_ranks["def_rank"],
        defense_rank_range_low=od_ranks["def_rank_low"],
        defense_rank_range_high=od_ranks["def_rank_high"],
        def_rank_display=_fmt_rank_display(
            od_ranks["def_rank"],
            od_ranks["def_rank_low"],
            od_ranks["def_rank_high"],
        ),
        team_projection_uncertainty=round(team_result.team_projection_uncertainty, 4),
        continuity_score=round(team_result.continuity_score, 2),
        transfer_dependence_score=round(team_result.transfer_dependence_score, 2),
        offensive_fit_score=round(fit_result.offensive_fit_score, 2),
        defensive_fit_score=round(fit_result.defensive_fit_score, 2),
        overall_fit_score=round(fit_result.overall_fit_score, 2),
        off_subcomponents=summary.get("off_subcomponents", {}),
        def_subcomponents=summary.get("def_subcomponents", {}),
        top_off_strengths=fit_result.offensive_strengths,
        top_off_weaknesses=fit_result.offensive_weaknesses,
        top_def_strengths=fit_result.defensive_strengths,
        top_def_weaknesses=fit_result.defensive_weaknesses,
        structural_penalties={
            "offense": [p[0] for p in (fit_result.off_penalties or [])],
            "defense": [p[0] for p in (fit_result.def_penalties or [])],
        },
        n_manual_players=n_manual,
        n_db_players=n_db,
        has_mpg_overrides=has_mpg_overrides,
        computed_at=datetime.now(tz=timezone.utc).isoformat(),
        baseline_adj_em=baseline_adj_em,
        adj_em_delta=adj_em_delta,
        is_first_year_coach=team_result.is_first_year_coach,
    )
