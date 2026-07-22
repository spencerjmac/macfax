"""
Phase 6 Stage 2: Macfax Player Market Value API.

Serve, don't render — these endpoints are functional but nothing in the
frontend links to them. Display wiring is Phase 7, gated on the operator
removing the methodology sign-off banner.

GET /api/market-value/players/?season=&ordering=&min_gp=&limit=
GET /api/market-value/teams/<slug>/?season=
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ncaa.models import PlayerMarketValue, PlayerSeasonStats, Season, Team
from ncaa.analytics.market_value.constants import METHODOLOGY_VERSION


def _resolve_season(param: str | None) -> Season | None:
    if param:
        try:
            return Season.objects.get(year=int(param))
        except (Season.DoesNotExist, ValueError):
            return None
    return (
        Season.objects.filter(player_market_values__isnull=False)
        .order_by("-year")
        .first()
    )


def _serialize(mv: PlayerMarketValue, team_name=None, team_slug=None) -> dict:
    return {
        "player_id": mv.player_id,
        "player_name": mv.player.display_name,
        "team_name": team_name,
        "team_slug": team_slug,
        "bpr": round(mv.bpr, 2),
        "minutes_share": round(mv.minutes_share, 4),
        "marginal_em": round(mv.marginal_em, 3),
        "marginal_wins": round(mv.marginal_wins, 3),
        "value_low": round(mv.value_low),
        "value_high": round(mv.value_high),
        "constants_hash": mv.constants_hash,
    }


class MarketValuePlayerListView(APIView):
    """League-wide market value list, descending by marginal wins by default."""

    def get(self, request):
        season = _resolve_season(request.query_params.get("season"))
        if season is None:
            return Response({"error": "No market value data"}, status=status.HTTP_404_NOT_FOUND)

        ordering = request.query_params.get("ordering", "-marginal_wins")
        if ordering.lstrip("-") not in {"marginal_wins", "value_high", "bpr", "minutes_share"}:
            ordering = "-marginal_wins"
        try:
            limit = min(int(request.query_params.get("limit", 100)), 500)
        except ValueError:
            limit = 100
        try:
            min_gp = int(request.query_params.get("min_gp", 0))
        except ValueError:
            min_gp = 0

        qs = (
            PlayerMarketValue.objects.filter(season=season)
            .select_related("player")
            .order_by(ordering)
        )
        # team context (and optional gp filter) via the player's primary PSS row
        pss = {
            r["player_id"]: r
            for r in PlayerSeasonStats.objects.filter(
                season=season, team__isnull=False
            ).values("player_id", "team__name", "team__slug", "gp")
        }
        results = []
        for mv in qs:
            info = pss.get(mv.player_id, {})
            if min_gp and (info.get("gp") or 0) < min_gp:
                continue
            results.append(_serialize(mv, info.get("team__name"), info.get("team__slug")))
            if len(results) >= limit:
                break
        return Response({
            "season": season.year,
            "methodology_version": METHODOLOGY_VERSION,
            "count": len(results),
            "results": results,
        })


class MarketValueTeamView(APIView):
    """Roster rollup for one team: player rows + team total range."""

    def get(self, request, slug: str):
        season = _resolve_season(request.query_params.get("season"))
        if season is None:
            return Response({"error": "No market value data"}, status=status.HTTP_404_NOT_FOUND)
        team = Team.objects.filter(slug=slug).first()
        if team is None:
            return Response({"error": f"Team '{slug}' not found"}, status=status.HTTP_404_NOT_FOUND)

        player_ids = list(
            PlayerSeasonStats.objects.filter(season=season, team=team)
            .values_list("player_id", flat=True)
        )
        rows = list(
            PlayerMarketValue.objects.filter(season=season, player_id__in=player_ids)
            .select_related("player")
            .order_by("-marginal_wins")
        )
        total_low = sum(max(mv.value_low, 0.0) for mv in rows)
        total_high = sum(max(mv.value_high, 0.0) for mv in rows)
        return Response({
            "season": season.year,
            "methodology_version": METHODOLOGY_VERSION,
            "team": {"name": team.name, "slug": team.slug},
            "team_total_value_low": round(total_low),
            "team_total_value_high": round(total_high),
            "players": [_serialize(mv, team.name, team.slug) for mv in rows],
        })
