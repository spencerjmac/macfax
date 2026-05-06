"""
NBA API Views — macfax NBA app

Phase 1: Stub views that return empty/minimal data.
Phase 2: Populated by nba_sync_* management commands + real ingestion.
"""

from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    NBASeason,
    NBATeam,
    NBAGame,
    NBATeamGameStats,
    NBAPlayer,
    NBAPlayerSeasonStats,
    NBATeamSeasonRatings,
    NBAModelCalibration,
)
from .serializers import (
    NBASeasonSerializer,
    NBATeamSerializer,
    NBAGameSerializer,
    NBATeamGameStatsSerializer,
    NBAPlayerSerializer,
    NBAPlayerSeasonStatsSerializer,
    NBATeamSeasonRatingsSerializer,
    NBAModelCalibrationSerializer,
)


class NBASeasonViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/nba/seasons/"""

    queryset = NBASeason.objects.all()
    serializer_class = NBASeasonSerializer
    pagination_class = None


class NBATeamViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/nba/teams/ and /api/nba/teams/<slug>/"""

    serializer_class = NBATeamSerializer
    lookup_field = "slug"

    def get_queryset(self):
        qs = NBATeam.objects.all()
        conf = self.request.query_params.get("conference")
        if conf:
            qs = qs.filter(conference=conf)
        return qs


class NBARankingsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/nba/rankings/?season=2026

    Returns NBATeamSeasonRatings ordered by adj_net.
    Defaults to the current season if no season param is provided.
    """

    serializer_class = NBATeamSeasonRatingsSerializer

    def get_queryset(self):
        qs = NBATeamSeasonRatings.objects.select_related("team", "season")

        season_year = self.request.query_params.get("season")
        if season_year:
            qs = qs.filter(season__year=season_year)
        else:
            try:
                current = NBASeason.objects.get(is_current=True)
                qs = qs.filter(season=current)
            except NBASeason.DoesNotExist:
                return qs.none()

        season_type = self.request.query_params.get("season_type", "regular")
        qs = qs.filter(season_type=season_type)

        return qs.order_by("rank_adj_net", "-adj_net")


class NBAGameViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/nba/games/?season=2026&team=<slug>&season_type=regular
    """

    serializer_class = NBAGameSerializer

    def get_queryset(self):
        qs = NBAGame.objects.select_related("home_team", "away_team", "season")

        season_year = self.request.query_params.get("season")
        if season_year:
            qs = qs.filter(season__year=season_year)

        team_slug = self.request.query_params.get("team")
        if team_slug:
            qs = qs.filter(
                Q(home_team__slug=team_slug) | Q(away_team__slug=team_slug)
            )

        season_type = self.request.query_params.get("season_type", "regular")
        if season_type:
            qs = qs.filter(season_type=season_type)

        return qs.order_by("-date")


class NBATeamDetailView(APIView):
    """
    GET /api/nba/team/<slug>/

    Returns team metadata + current-season ratings in one response.
    """

    def get(self, request, slug):
        try:
            team = NBATeam.objects.get(slug=slug)
        except NBATeam.DoesNotExist:
            return Response({"detail": "Team not found."}, status=status.HTTP_404_NOT_FOUND)

        season_year = request.query_params.get("season")
        if season_year:
            try:
                season = NBASeason.objects.get(year=season_year)
            except NBASeason.DoesNotExist:
                return Response(
                    {"detail": f"Season {season_year} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            try:
                season = NBASeason.objects.get(is_current=True)
            except NBASeason.DoesNotExist:
                season = None

        ratings = None
        if season:
            try:
                r = NBATeamSeasonRatings.objects.get(team=team, season=season)
                ratings = NBATeamSeasonRatingsSerializer(r).data
            except NBATeamSeasonRatings.DoesNotExist:
                pass

        return Response(
            {
                "team": NBATeamSerializer(team).data,
                "season": NBASeasonSerializer(season).data if season else None,
                "ratings": ratings,
            }
        )


class NBAHealthView(APIView):
    """
    GET /api/nba/health/

    Quick status check — how much data is loaded?
    """

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "phase": "Phase 2 — live data",
                "counts": {
                    "seasons": NBASeason.objects.count(),
                    "teams": NBATeam.objects.count(),
                    "games": NBAGame.objects.count(),
                    "games_with_box_scores": NBAGame.objects.filter(
                        box_score_synced=True
                    ).count(),
                    "team_season_ratings": NBATeamSeasonRatings.objects.count(),
                    "players": NBAPlayer.objects.count(),
                },
            }
        )


class NBAModelCalibrationView(APIView):
    """
    GET /api/nba/model-calibration/?season=2026

    Returns the NBAModelCalibration record for the requested season (or the
    current season if no season param is provided).  Returns 404 if
    nba_eval_model has not been run yet for that season.
    """

    def get(self, request):
        season_year = request.query_params.get("season")
        try:
            if season_year:
                calibration = NBAModelCalibration.objects.select_related("season").get(
                    season__year=season_year
                )
            else:
                calibration = (
                    NBAModelCalibration.objects.select_related("season")
                    .filter(season__is_current=True)
                    .first()
                )
                if calibration is None:
                    # Fall back to most recent
                    calibration = (
                        NBAModelCalibration.objects.select_related("season")
                        .order_by("-season__year")
                        .first()
                    )
        except NBAModelCalibration.DoesNotExist:
            calibration = None

        if calibration is None:
            return Response(
                {"detail": "No calibration data found. Run: python manage.py nba_eval_model --season YYYY"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(NBAModelCalibrationSerializer(calibration).data)


class NBATeamRosterView(APIView):
    """
    GET /api/nba/team/<slug>/players/?season=YYYY

    Returns season-averaged stats for all players on a team.
    Ordered by pts descending (scorers first).
    """

    def get(self, request, slug: str):
        try:
            team = NBATeam.objects.get(slug=slug)
        except NBATeam.DoesNotExist:
            return Response({"detail": "Team not found."}, status=status.HTTP_404_NOT_FOUND)

        season_param = request.query_params.get("season")
        if season_param:
            try:
                season = NBASeason.objects.get(year=int(season_param))
            except (NBASeason.DoesNotExist, ValueError):
                return Response({"detail": "Season not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            season = (
                NBASeason.objects.filter(is_current=True).first()
                or NBASeason.objects.order_by("-year").first()
            )
            if season is None:
                return Response({"detail": "No seasons available."}, status=status.HTTP_404_NOT_FOUND)

        players = (
            NBAPlayerSeasonStats.objects
            .filter(team=team, season=season)
            .select_related("player", "team", "season")
            .order_by("-pts")
        )

        if not players.exists():
            return Response(
                {
                    "detail": (
                        f"No player stats for {team.name} in {season.display_name}. "
                        f"Run: python manage.py nba_sync_team_logs --season {season.year}"
                        f" && python manage.py nba_compute_player_stats --season {season.year}"
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(NBAPlayerSeasonStatsSerializer(players, many=True).data)


class NBALeaguePlayersView(APIView):
    """
    GET /api/nba/players/?season=YYYY&ordering=-pts&min_gp=5

    League-wide player season stats, ordered by pts (or any allowed field).
    """

    _ALLOWED_ORDERINGS = {
        # Traditional
        "pts", "-pts", "reb", "-reb", "ast", "-ast",
        "stl", "-stl", "blk", "-blk", "mpg", "-mpg", "gp", "-gp",
        "tov", "-tov", "plus_minus", "-plus_minus",
        "fg_pct", "-fg_pct", "fg3_pct", "-fg3_pct", "ft_pct", "-ft_pct",
        "fga_pg", "-fga_pg", "fg3a_pg", "-fg3a_pg",
        "oreb_pg", "-oreb_pg", "dreb_pg", "-dreb_pg",
        "fta_pg", "-fta_pg",
        # Advanced efficiency
        "efg_pct", "-efg_pct", "ts_pct", "-ts_pct",
        "usg_pct", "-usg_pct", "pie", "-pie",
        "oreb_pct", "-oreb_pct", "dreb_pct", "-dreb_pct",
        "ast_pct", "-ast_pct", "tov_pct", "-tov_pct", "ast_to", "-ast_to",
        # On-court ratings (raw)
        "on_court_ortg", "-on_court_ortg",
        "on_court_drtg", "-on_court_drtg",
        "on_court_net", "-on_court_net",
        # On-court ratings (E_* stabilised)
        "on_court_adj_o", "-on_court_adj_o",
        "on_court_adj_d", "-on_court_adj_d",
        "on_court_adj_em", "-on_court_adj_em",
        # MPIR
        "mpir", "-mpir", "o_mpir", "-o_mpir", "d_mpir", "-d_mpir",
        # Defense
        "stl_pct", "-stl_pct", "blk_pct", "-blk_pct",
    }

    def get(self, request):
        season_param = request.query_params.get("season")
        ordering = request.query_params.get("ordering", "-pts")
        if ordering not in self._ALLOWED_ORDERINGS:
            ordering = "-pts"

        min_gp = max(1, int(request.query_params.get("min_gp", "5")))

        if season_param:
            try:
                season = NBASeason.objects.get(year=int(season_param))
            except (NBASeason.DoesNotExist, ValueError):
                return Response({"detail": "Season not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            season = (
                NBASeason.objects.filter(is_current=True).first()
                or NBASeason.objects.order_by("-year").first()
            )
            if season is None:
                return Response([], status=status.HTTP_200_OK)

        season_type = request.query_params.get("season_type", "regular")

        players = (
            NBAPlayerSeasonStats.objects
            .filter(season=season, gp__gte=min_gp, season_type=season_type)
            .select_related("player", "team", "season")
            .order_by(ordering)
        )

        return Response(NBAPlayerSeasonStatsSerializer(players, many=True).data)

