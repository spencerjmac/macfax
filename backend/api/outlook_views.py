"""
Phase 7: Roster Outlook API views.

Endpoints
---------
GET  /api/outlook/<slug>/         – Baseline team roster outlook (projection + players + fit)
POST /api/outlook/scenario/       – Stateless scenario re-projection (edited roster)
GET  /api/outlook/player-search/  – Search projected players for scenario add flow
"""

from __future__ import annotations

import logging

from django.db.models import Max
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ncaa.models import (
    NationalAverages,
    PlayerSeasonProjection,
    PlaceholderArchetype,
    Season,
    Team,
    TeamRosterFit,
    TeamSeasonProjection,
)
from ncaa.analytics.staleness import check_staleness
from ncaa.analytics.player_value.team_projection.engine import (
    D1Context,
    PlayerProjectionInput,
    RosterFitInput,
    compute_team_base_aggregates,
    project_team,
    sigma_em,
)
from ncaa.analytics.player_value.team_projection.constants import (
    REPLACEMENT_FILL_DBPR,
    REPLACEMENT_FILL_OBPR,
)
from ncaa.analytics.player_value.team_projection.service import get_stored_d1_context

log = logging.getLogger(__name__)

# ── helpers ────────────────────────────────────────────────────────────────────

_FIT_GRADE_THRESHOLDS = [
    (82, "A+", "Elite"),
    (74, "A", "Elite"),
    (66, "B+", "Strong"),
    (58, "B", "Strong"),
    (50, "C+", "Solid"),
    (42, "C", "Solid"),
    (34, "D", "Weak"),
    (0,  "F", "Poor"),
]


def _fit_grade(score: float | None) -> dict:
    if score is None:
        return {"letter": "?", "label": "N/A", "score": None}
    for threshold, letter, label in _FIT_GRADE_THRESHOLDS:
        if score >= threshold:
            return {"letter": letter, "label": label, "score": round(score, 1)}
    return {"letter": "F", "label": "Poor", "score": round(score, 1)}


def _resolve_season(season_param: str | None) -> Season | None:
    """
    Return the Season for an optional ?season=YYYY query param.

    Explicit param: that season or None if it doesn't exist.
    No param: the most recent season that actually HAS team projections —
    never a silent fallback to a projection-less season (Phase 3 P3 fix;
    the old `A and B or C` chain could return a season with no projections,
    producing downstream 404s).
    """
    if season_param:
        try:
            return Season.objects.get(year=int(season_param))
        except (Season.DoesNotExist, ValueError):
            return None
    return (
        Season.objects.filter(team_projections__isnull=False)
        .order_by("-year")
        .first()
    )


def _get_d1_context(season: Season) -> D1Context:
    """
    Build a D1Context for scenario re-projection.

    Phase 3 P4: delegates to the pipeline's shared builder so the scenario
    path and the baseline pipeline can never disagree on context construction.
    """
    return get_stored_d1_context(season)


def _approx_rank_in_distribution(
    season: Season,
    scenario_em: float,
    uncertainty: float = 0.0,
    team: Team | None = None,
) -> dict:
    """
    Approximate national rank for a scenario projection by counting existing
    TeamSeasonProjection rows better than the scenario value.

    D1-only pool (Phase 3 D4) — matches the stored pipeline's rank universe
    (service.py._assign_ranks), not the full 562-team projected-teams set.

    The scenario team's own baseline row is excluded from the pool (Phase 3
    P2 — a team must not be ranked against its own ghost), so the worst
    possible rank is naturally len(pool) + 1.

    Returns rank, plus a ±1σ ("likely range", ~68%) rank range using the
    empirically-fit EM sigma (Phase 3 Stage 2, engine.sigma_em — the same
    sigma that drives the displayed AdjEM band, so the rank range and the
    EM band always agree):
    rank_low  = rank if the scenario team performed at scenario_em + 1σ_em
    rank_high = rank if the scenario team performed at scenario_em − 1σ_em
    """
    pool = TeamSeasonProjection.objects.filter(from_season=season, team__is_d1=True)
    if team is not None:
        pool = pool.exclude(team=team)
    existing_ems = list(pool.values_list("projected_adj_em", flat=True))
    n = len(existing_ems)
    rank = sum(1 for em in existing_ems if em > scenario_em) + 1
    sigma_pts = sigma_em(uncertainty)
    rank_low  = max(1, sum(1 for em in existing_ems if em > scenario_em + sigma_pts) + 1)
    rank_high = sum(1 for em in existing_ems if em > scenario_em - sigma_pts) + 1
    return {
        "approx_national_rank": rank,
        "n_teams_in_pool": n,
        "national_rank_range_low": rank_low,
        "national_rank_range_high": rank_high,
    }


def _rank_display(rank, rank_low, rank_high) -> str:
    """Format rank as '15 (5–35)' or 'Unranked' or just '15' when range is a single value."""
    if rank is None:
        return "Unranked"
    if rank_low is None or rank_high is None or rank_low == rank_high:
        return str(rank)
    return f"{rank} ({rank_low}–{rank_high})"


def _serialize_player_projection(row: PlayerSeasonProjection) -> dict:
    return {
        "player_id": row.player_id,
        "player_name": row.player.display_name,
        "player_short_name": row.player.short_name,
        "position": row.player.position,
        "headshot_url": row.player.headshot_url or None,
        "projected_obpr": row.projected_obpr,
        "projected_dbpr": row.projected_dbpr,
        "projected_bpr": row.projected_bpr,
        "minutes_share_p2": row.minutes_share_p2,
        "mpg_p2": row.mpg_p2,
        "role_bucket": row.role_bucket,
        "recruitment_type": row.recruitment_type,
        "projection_uncertainty": row.projection_uncertainty,
        "rotation_rank": row.rotation_rank,
        "n_prior_seasons": row.n_prior_seasons,
    }


def _serialize_projection(proj: TeamSeasonProjection) -> dict:
    return {
        "projected_adj_o": proj.projected_adj_o,
        "projected_adj_d": proj.projected_adj_d,
        "projected_adj_em": proj.projected_adj_em,
        "projected_adj_o_low": proj.projected_adj_o_low,
        "projected_adj_o_high": proj.projected_adj_o_high,
        "projected_adj_d_low": proj.projected_adj_d_low,
        "projected_adj_d_high": proj.projected_adj_d_high,
        "projected_adj_em_low": proj.projected_adj_em_low,
        "projected_adj_em_high": proj.projected_adj_em_high,
        "projected_national_rank": proj.projected_national_rank,
        "national_rank_range_low": proj.national_rank_range_low,
        "national_rank_range_high": proj.national_rank_range_high,
        "rank_display": _rank_display(
            proj.projected_national_rank,
            proj.national_rank_range_low,
            proj.national_rank_range_high,
        ),
        "projected_offense_rank": proj.projected_offense_rank,
        "offense_rank_range_low": proj.offense_rank_range_low,
        "offense_rank_range_high": proj.offense_rank_range_high,
        "off_rank_display": _rank_display(
            proj.projected_offense_rank,
            proj.offense_rank_range_low,
            proj.offense_rank_range_high,
        ),
        "projected_defense_rank": proj.projected_defense_rank,
        "defense_rank_range_low": proj.defense_rank_range_low,
        "defense_rank_range_high": proj.defense_rank_range_high,
        "def_rank_display": _rank_display(
            proj.projected_defense_rank,
            proj.defense_rank_range_low,
            proj.defense_rank_range_high,
        ),
        "team_projection_uncertainty": proj.team_projection_uncertainty,
        "returner_minutes_fraction": proj.returner_minutes_fraction,
        "continuity_score": proj.continuity_score,
        "continuity_value_score": proj.continuity_value_score,
        "transfer_dependence_score": proj.transfer_dependence_score,
        "transfer_fit_risk_score": proj.transfer_fit_risk_score,
    }


def _serialize_fit(fit: TeamRosterFit) -> dict:
    return {
        "offensive_fit_score": fit.offensive_fit_score,
        "defensive_fit_score": fit.defensive_fit_score,
        "overall_fit_score": fit.overall_fit_score,
        "adjusted_off_fit": fit.adjusted_off_fit,
        "adjusted_def_fit": fit.adjusted_def_fit,
        "adjusted_overall_fit": fit.adjusted_overall_fit,
        "has_team_style_data": fit.has_team_style_data,
        "off_grade": _fit_grade(fit.adjusted_off_fit),
        "def_grade": _fit_grade(fit.adjusted_def_fit),
        "offensive_strengths": fit.offensive_strengths or [],
        "offensive_weaknesses": fit.offensive_weaknesses or [],
        "defensive_strengths": fit.defensive_strengths or [],
        "defensive_weaknesses": fit.defensive_weaknesses or [],
    }


# ── Views ───────────────────────────────────────────────────────────────────────


class RosterOutlookView(APIView):
    """
    GET /api/outlook/<slug>/?season=<year>

    Returns baseline roster outlook for a team:
      - team metadata
      - team-level projection (TeamSeasonProjection)
      - player projections (PlayerSeasonProjection), sorted by rotation_rank
      - fit scores and grades (TeamRosterFit)
    """

    def get(self, request, slug: str):
        team = get_object_or_404(Team, slug=slug)
        season_param = request.query_params.get("season")
        season = _resolve_season(season_param)
        if season is None:
            return Response({"error": "No season data available"}, status=status.HTTP_404_NOT_FOUND)

        # --- Team projection ---
        try:
            proj = TeamSeasonProjection.objects.get(team=team, from_season=season)
        except TeamSeasonProjection.DoesNotExist:
            return Response(
                {"error": f"No projection found for {team.name} in season {season.year}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # --- Player projections ---
        players_qs = (
            PlayerSeasonProjection.objects
            .filter(team=team, from_season=season)
            .select_related("player")
            .order_by("rotation_rank", "-projected_bpr")
        )
        players = [_serialize_player_projection(row) for row in players_qs]

        # --- Fit ---
        try:
            fit = TeamRosterFit.objects.get(team=team, from_season=season)
            fit_data = _serialize_fit(fit)
        except TeamRosterFit.DoesNotExist:
            fit = None
            fit_data = None

        # --- Staleness check (3 targeted queries) ---
        psp_agg = PlayerSeasonProjection.objects.filter(
            team=team, from_season=season
        ).aggregate(latest=Max("computed_at"))
        psp_computed_at = psp_agg["latest"]

        trf_computed_at = fit.computed_at if fit is not None else None

        tsp_computed_at = proj.computed_at

        staleness_warnings = [
            {
                "severity": w.severity,
                "upstream_phase": w.upstream_phase,
                "downstream_phase": w.downstream_phase,
                "delta_seconds": w.delta_seconds,
                "message": w.message,
            }
            for w in check_staleness(season.year, team.id, psp_computed_at, trf_computed_at, tsp_computed_at)
        ]

        return Response({
            "team": {
                "id": team.id,
                "name": team.name,
                "slug": team.slug,
                "logo_url": team.logo_url if hasattr(team, "logo_url") else None,
            },
            "season": {
                "year": season.year,
                "display_name": getattr(season, "display_name", str(season.year)),
                "projected_season_year": proj.projected_season_year,
            },
            "projection": _serialize_projection(proj),
            "players": players,
            "fit": fit_data,
            "staleness_warnings": staleness_warnings,
        })


class ScenarioProjectionView(APIView):
    """
    POST /api/outlook/scenario/

    Accept an edited roster and return a stateless re-projection.
    The projection math (engine) runs on the backend; no DB writes.

    Request body:
    {
        "from_season_year": 2025,
        "team_slug": "connecticut",
        "players": [
            {
                "player_id": 123,           // null-ok (for added non-DB players)
                "player_name": "...",
                "projected_obpr": 4.18,
                "projected_dbpr": 2.19,
                "projected_bpr": 6.37,
                "minutes_share": 0.32,      // fraction of 5.0 pool (not raw MPG)
                "recruitment_type": "returner",
                "projection_uncertainty": 0.25
            }
        ]
    }

    Response:
    {
        "projected_adj_o": ...,
        "projected_adj_d": ...,
        "projected_adj_em": ...,
        "projected_adj_em_low": ...,
        "projected_adj_em_high": ...,
        "approx_national_rank": ...,
        "national_rank_range_low": ...,
        "national_rank_range_high": ...,
        "team_projection_uncertainty": ...,
        "returner_minutes_fraction": ...,
        "continuity_value_score": ...,
        "transfer_dependence_score": ...,
        "transfer_fit_risk_score": ...
    }
    """

    def post(self, request):
        data = request.data
        season_year = data.get("from_season_year")
        team_slug = data.get("team_slug")
        player_inputs = data.get("players", [])

        if not season_year or not team_slug:
            return Response(
                {"error": "from_season_year and team_slug are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not player_inputs:
            return Response(
                {"error": "players list cannot be empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            season = Season.objects.get(year=int(season_year))
        except (Season.DoesNotExist, ValueError):
            return Response(
                {"error": f"Season {season_year} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        team = get_object_or_404(Team, slug=team_slug)

        # --- Build player inputs ---
        engine_inputs: list[PlayerProjectionInput] = []
        for idx, p in enumerate(player_inputs):
            try:
                pi = PlayerProjectionInput(
                    player_id=int(p.get("player_id") or 0) or (idx + 90000),
                    projected_obpr=float(p.get("projected_obpr") or 0.0),
                    projected_dbpr=float(p.get("projected_dbpr") or 0.0),
                    projected_bpr=float(p.get("projected_bpr") or 0.0),
                    minutes_share_p2=float(p.get("minutes_share") or 0.0),
                    recruitment_type=str(p.get("recruitment_type") or "newcomer"),
                    projection_uncertainty=float(p.get("projection_uncertainty") or 0.5),
                )
            except (TypeError, ValueError) as exc:
                return Response(
                    {"error": f"Invalid player data at index {idx}: {exc}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            engine_inputs.append(pi)

        # --- Normalize the minutes pool to 5.0 (200 team-minutes) ---
        # Over-filled rosters are scaled down proportionally (legitimate).
        # Under-filled rosters are padded with one synthetic replacement-level
        # newcomer so partial rosters are not projected as if the submitted
        # players play every minute. The fill player exists only inside the
        # engine call — it is never returned to the frontend.
        total_share = sum(p.minutes_share_p2 for p in engine_inputs)
        POOL_EPSILON = 0.05
        replacement_fill_share = 0.0
        if total_share > 5.0 + POOL_EPSILON:
            scale = 5.0 / total_share
            for p in engine_inputs:
                p.minutes_share_p2 *= scale
        elif total_share < 5.0 - POOL_EPSILON:
            replacement_fill_share = 5.0 - total_share
            engine_inputs.append(
                PlayerProjectionInput(
                    player_id=-1,  # reserved sentinel: replacement-level fill
                    projected_obpr=REPLACEMENT_FILL_OBPR,
                    projected_dbpr=REPLACEMENT_FILL_DBPR,
                    projected_bpr=REPLACEMENT_FILL_OBPR + REPLACEMENT_FILL_DBPR,
                    minutes_share_p2=replacement_fill_share,
                    recruitment_type="newcomer",
                    projection_uncertainty=0.80,
                )
            )

        # --- Build D1 context (from stored distributions) ---
        d1_context = _get_d1_context(season)

        # --- Build roster fit input ---
        try:
            db_fit = TeamRosterFit.objects.get(team=team, from_season=season)
            roster_fit: RosterFitInput | None = RosterFitInput(
                offensive_fit_score=db_fit.offensive_fit_score or 50.0,
                defensive_fit_score=db_fit.defensive_fit_score or 50.0,
                adjusted_off_fit=db_fit.adjusted_off_fit if db_fit.adjusted_off_fit is not None else 50.0,
                adjusted_def_fit=db_fit.adjusted_def_fit if db_fit.adjusted_def_fit is not None else 50.0,
                has_team_style_data=db_fit.has_team_style_data,
            )
        except TeamRosterFit.DoesNotExist:
            roster_fit = None

        # --- Run engine ---
        result = project_team(engine_inputs, roster_fit, d1_context)

        # --- Approximate rank (uncertainty-aware range; own baseline excluded) ---
        rank_info = _approx_rank_in_distribution(
            season, result.projected_adj_em, result.team_projection_uncertainty,
            team=team,
        )
        approx_rank = rank_info["approx_national_rank"]
        rank_low    = rank_info["national_rank_range_low"]
        rank_high   = rank_info["national_rank_range_high"]

        if rank_low == rank_high:
            rank_display = str(approx_rank)
        else:
            rank_display = f"{approx_rank} ({rank_low}–{rank_high})"

        return Response({
            "projected_adj_o": round(result.projected_adj_o, 3),
            "projected_adj_d": round(result.projected_adj_d, 3),
            "projected_adj_em": round(result.projected_adj_em, 3),
            "projected_adj_o_low": round(result.projected_adj_o_low, 3),
            "projected_adj_o_high": round(result.projected_adj_o_high, 3),
            "projected_adj_d_low": round(result.projected_adj_d_low, 3),
            "projected_adj_d_high": round(result.projected_adj_d_high, 3),
            "projected_adj_em_low": round(result.projected_adj_em_low, 3),
            "projected_adj_em_high": round(result.projected_adj_em_high, 3),
            "approx_national_rank": approx_rank,
            "n_teams_in_pool": rank_info["n_teams_in_pool"],
            "national_rank_range_low": rank_low,
            "national_rank_range_high": rank_high,
            "rank_display": rank_display,
            "team_projection_uncertainty": round(result.team_projection_uncertainty, 4),
            "returner_minutes_fraction": round(result.returner_minutes_fraction, 4),
            "continuity_score": round(result.continuity_score, 2),
            "continuity_value_score": round(result.continuity_value_score, 2),
            "transfer_dependence_score": round(result.transfer_dependence_score, 2),
            "transfer_fit_risk_score": round(result.transfer_fit_risk_score, 4),
            "pool_fill_fraction": round(total_share / 5.0, 4),
            "replacement_fill_share": round(max(0.0, replacement_fill_share), 4),
        })


class PlayerSearchView(APIView):
    """
    GET /api/outlook/player-search/?q=<name>&season=<year>

    Search PlayerSeasonProjection by player name to support the
    scenario add-player flow.  Returns up to 25 results.
    """

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        season_param = request.query_params.get("season")

        if len(q) < 2:
            return Response([], status=status.HTTP_200_OK)

        season = _resolve_season(season_param)
        if season is None:
            return Response([], status=status.HTTP_200_OK)

        qs = (
            PlayerSeasonProjection.objects
            .filter(
                from_season=season,
                player__display_name__icontains=q,
                minutes_share_p2__isnull=False,
                projected_bpr__isnull=False,
            )
            .select_related("player", "team")
            .order_by("-projected_bpr")
            [:25]
        )

        results = []
        for row in qs:
            results.append({
                "player_id": row.player_id,
                "player_name": row.player.display_name,
                "player_short_name": row.player.short_name,
                "position": row.player.position,
                "headshot_url": row.player.headshot_url or None,
                "team_name": row.team.name if row.team else "Unknown",
                "team_slug": row.team.slug if row.team else None,
                "projected_obpr": row.projected_obpr,
                "projected_dbpr": row.projected_dbpr,
                "projected_bpr": row.projected_bpr,
                "minutes_share_p2": row.minutes_share_p2,
                "mpg_p2": row.mpg_p2,
                "role_bucket": row.role_bucket,
                "recruitment_type": row.recruitment_type,
                "projection_uncertainty": row.projection_uncertainty,
                "rotation_rank": row.rotation_rank,
                "n_prior_seasons": row.n_prior_seasons,
            })

        return Response(results)


class PlaceholderListView(APIView):
    """
    GET /api/outlook/placeholders/

    Returns pre-built archetype players for the scenario editor.
    Each archetype is derived from the median of a real cohort of D1 players
    (see: python manage.py build_placeholder_archetypes).

    Optional query params:
      ?role=G|Wing|Big
      ?tier=elite|starter|rotation
      ?conf_group=national|power|mid_major
    """

    def get(self, request):
        from api.serializers import PlaceholderArchetypeSerializer

        qs = PlaceholderArchetype.objects.all()

        role = request.query_params.get("role")
        tier = request.query_params.get("tier")
        conf_group = request.query_params.get("conf_group")

        if role:
            qs = qs.filter(role_bucket=role)
        if tier:
            qs = qs.filter(quality_tier=tier)
        if conf_group:
            qs = qs.filter(conf_group=conf_group)

        serializer = PlaceholderArchetypeSerializer(qs, many=True)
        return Response({"archetypes": serializer.data})
