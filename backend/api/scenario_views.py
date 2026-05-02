"""
Scenario API views — Sprint 3.

Endpoints:
  POST /api/scenarios/compute/   — stateless scenario computation (no DB write)
  POST /api/scenarios/save/      — persist a ScenarioSnapshot
  GET  /api/scenarios/<pk>/      — retrieve a saved snapshot
  GET  /api/scenarios/           — list saved snapshots (filter by ?team_id=X)
"""

from __future__ import annotations

import dataclasses
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

log = logging.getLogger(__name__)


def _result_to_dict(result) -> dict:
    """Recursively convert a ScenarioResult dataclass tree to a plain dict."""
    import dataclasses
    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        return {
            k: _result_to_dict(v)
            for k, v in dataclasses.asdict(result).items()
        }
    if isinstance(result, list):
        return [_result_to_dict(item) for item in result]
    return result


class ScenarioComputeView(APIView):
    """
    POST /api/scenarios/compute/

    Compute a scenario in memory and return a ScenarioResult JSON.
    No DB write.  At least 1 slot required; at most 20.

    Returns 200 on success, 400 on validation or data error.
    """

    def post(self, request):
        from api.scenario_serializers import ScenarioRosterRequestSerializer
        from ncaa.analytics.player_value.scenario.service import (
            compute_scenario,
            ScenarioRosterRequest,
            ScenarioSlot,
        )
        from ncaa.analytics.player_value.scenario.manual_player import ManualPlayerSpec
        from ncaa.models import Season, Team

        serializer = ScenarioRosterRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        vd = serializer.validated_data

        # Validate team and season exist
        try:
            team = Team.objects.get(id=vd["team_id"])
        except Team.DoesNotExist:
            return Response(
                {"error": f"Team {vd['team_id']} not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            Season.objects.get(year=vd["season_year"])
        except Season.DoesNotExist:
            return Response(
                {"error": f"Season {vd['season_year']} not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build ScenarioRosterRequest
        slots: list[ScenarioSlot] = []
        for slot_data in vd["slots"]:
            if slot_data["slot_type"] == "manual_player":
                spec_data = slot_data["manual_spec"]
                manual_spec = ManualPlayerSpec(
                    display_name=spec_data["display_name"],
                    position=spec_data["position"],
                    recruitment_type=spec_data["recruitment_type"],
                    projected_obpr=spec_data.get("projected_obpr"),
                    projected_dbpr=spec_data.get("projected_dbpr"),
                    national_rank=spec_data.get("national_rank"),
                    stars=spec_data.get("stars"),
                    composite_score=spec_data.get("composite_score"),
                    placeholder_key=spec_data.get("placeholder_key"),
                    conf_group=spec_data.get("conf_group", "power"),
                    quality_tier=spec_data.get("quality_tier", "starter"),
                    intended_mpg=spec_data.get("intended_mpg"),
                    is_juco=spec_data.get("is_juco", False),
                    slot_id=spec_data.get("slot_id", ""),
                )
                slots.append(ScenarioSlot(slot_type="manual_player", manual_spec=manual_spec))
            else:
                slots.append(ScenarioSlot(
                    slot_type="db_player",
                    projection_id=slot_data.get("projection_id"),
                ))

        scenario_request = ScenarioRosterRequest(
            team_id=vd["team_id"],
            season_year=vd["season_year"],
            slots=slots,
            compare_to_baseline=vd.get("compare_to_baseline", False),
        )

        try:
            result = compute_scenario(scenario_request)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            log.exception("[ScenarioComputeView] Unexpected error for team=%s season=%s",
                          vd["team_id"], vd["season_year"])
            return Response(
                {"error": f"Scenario computation failed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Staleness check on the baseline data this scenario is built from
        from django.db.models import Max
        from ncaa.models import PlayerSeasonProjection, TeamRosterFit, TeamSeasonProjection, Season as SeasonModel
        from ncaa.analytics.staleness import check_staleness

        try:
            season_obj = SeasonModel.objects.get(year=vd["season_year"])
            psp_agg = PlayerSeasonProjection.objects.filter(
                team_id=vd["team_id"], from_season=season_obj
            ).aggregate(latest=Max("computed_at"))
            psp_computed_at = psp_agg["latest"]

            trf_computed_at = None
            try:
                trf_obj = TeamRosterFit.objects.get(team_id=vd["team_id"], from_season=season_obj)
                trf_computed_at = trf_obj.computed_at
            except TeamRosterFit.DoesNotExist:
                pass

            data_staleness_warnings = [
                {
                    "severity": w.severity,
                    "upstream_phase": w.upstream_phase,
                    "downstream_phase": w.downstream_phase,
                    "delta_seconds": w.delta_seconds,
                    "message": w.message,
                }
                for w in check_staleness(vd["season_year"], vd["team_id"], psp_computed_at, trf_computed_at, None)
            ]
        except Exception:
            data_staleness_warnings = []

        response_data = _result_to_dict(result)
        response_data["data_staleness_warnings"] = data_staleness_warnings
        return Response(response_data, status=status.HTTP_200_OK)


class ScenarioSaveView(APIView):
    """
    POST /api/scenarios/save/

    Persist a previously computed scenario.  The client sends both the
    original request and the computed result.  Returns the snapshot id
    and created_at timestamp.
    """

    def post(self, request):
        from api.scenario_serializers import ScenarioSaveSerializer
        from ncaa.models import ScenarioSnapshot, Season, Team

        serializer = ScenarioSaveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        vd = serializer.validated_data
        req_data = vd["scenario_request"]
        res_data = vd["scenario_result"]

        team_id    = req_data.get("team_id")
        season_year = req_data.get("season_year")

        try:
            team   = Team.objects.get(id=team_id)
            season = Season.objects.get(year=season_year)
        except (Team.DoesNotExist, Season.DoesNotExist) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        snapshot = ScenarioSnapshot.objects.create(
            team=team,
            from_season=season,
            projected_season_year=season_year + 1,
            name=vd.get("name", ""),
            scenario_input=req_data,
            scenario_result=res_data,
            projected_adj_em=res_data.get("projected_adj_em"),
            projected_national_rank=res_data.get("projected_national_rank"),
            n_manual_players=int(res_data.get("n_manual_players") or 0),
        )

        return Response(
            {"id": snapshot.id, "created_at": snapshot.created_at.isoformat()},
            status=status.HTTP_201_CREATED,
        )


class ScenarioDetailView(APIView):
    """GET /api/scenarios/<pk>/ — retrieve a saved snapshot with full result."""

    def get(self, request, pk: int):
        from ncaa.models import ScenarioSnapshot
        from api.scenario_serializers import ScenarioSnapshotDetailSerializer

        try:
            snap = ScenarioSnapshot.objects.select_related("team", "from_season").get(pk=pk)
        except ScenarioSnapshot.DoesNotExist:
            return Response({"error": "Snapshot not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ScenarioSnapshotDetailSerializer(snap)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ScenarioListView(APIView):
    """
    GET /api/scenarios/?team_id=X

    List saved ScenarioSnapshot records for a team.
    Returns summary fields only (no full scenario_result).
    """

    def get(self, request):
        from ncaa.models import ScenarioSnapshot
        from api.scenario_serializers import ScenarioSnapshotListSerializer

        qs = ScenarioSnapshot.objects.select_related("team", "from_season").order_by("-updated_at")

        team_id = request.query_params.get("team_id")
        if team_id:
            try:
                qs = qs.filter(team_id=int(team_id))
            except ValueError:
                return Response(
                    {"error": "team_id must be an integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = ScenarioSnapshotListSerializer(qs[:50], many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
