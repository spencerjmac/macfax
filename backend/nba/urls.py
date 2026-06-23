"""
NBA URL configuration — macfax NBA app

Mounted at /api/nba/ by config/urls.py
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    NBASeasonViewSet,
    NBATeamViewSet,
    NBARankingsViewSet,
    NBAGameViewSet,
    NBATeamDetailView,
    NBATeamRosterView,
    NBALeaguePlayersView,
    NBAHealthView,
    NBAMatchupView,
    NBAModelCalibrationView,
    NBAPlayerCompareView,
    NBATeamRosterValueView,
    TeamOutlookListView,
    TeamOutlookDetailView,
)
from .game_detail_views import nba_game_detail

router = DefaultRouter()
router.register(r"seasons", NBASeasonViewSet, basename="nba-season")
router.register(r"teams", NBATeamViewSet, basename="nba-team")
router.register(r"rankings", NBARankingsViewSet, basename="nba-rankings")
router.register(r"games", NBAGameViewSet, basename="nba-game")

urlpatterns = [
    path("", include(router.urls)),
    path("team/<slug:slug>/", NBATeamDetailView.as_view(), name="nba-team-detail"),
    path("team/<slug:slug>/players/", NBATeamRosterView.as_view(), name="nba-team-roster"),
    path("players/", NBALeaguePlayersView.as_view(), name="nba-players"),
    path("players/compare/", NBAPlayerCompareView.as_view(), name="nba-player-compare"),
    path("teams/<slug:slug>/roster-value/", NBATeamRosterValueView.as_view(), name="nba-team-roster-value"),
    path("health/", NBAHealthView.as_view(), name="nba-health"),
    path("model-calibration/", NBAModelCalibrationView.as_view(), name="nba-model-calibration"),
    path("matchup/", NBAMatchupView.as_view(), name="nba-matchup"),
    path("games/<str:game_id>/detail/", nba_game_detail, name="nba-game-detail"),
    path("outlook/", TeamOutlookListView.as_view(), name="nba-team-outlook-list"),
    path("outlook/<slug:slug>/", TeamOutlookDetailView.as_view(), name="nba-team-outlook-detail"),
]
