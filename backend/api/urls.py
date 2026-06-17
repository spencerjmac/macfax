"""
URL configuration for API
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SeasonViewSet,
    ConferenceViewSet,
    RankingsViewSet,
    TeamViewSet,
    MatchupViewSet,
    GameViewSet,
    PipelineConfigView,
    TeamRosterView,
    LeaguePlayersView,
)
from .job_views import DataProcessingJobViewSet
from .trapezoid_views import TrapezoidView
from .landscape_views import EfficiencyLandscapeView
from .nba_landscape_views import NBAEfficiencyLandscapeView
from .crystal_ball_views import CrystalBallView
from .nba_crystal_ball_views import NBACrystalBallView
from .nba_luck_chart_views import NBALuckChartView
from .cinderella_views import CinderellaView
from .bracket_views import BracketView
from .viz_builder_views import VizStatsView, VizScatterView
from .auth_views import csrf, login_view, logout_view, me
from .outlook_views import RosterOutlookView, ScenarioProjectionView, PlayerSearchView, PlaceholderListView
from .scenario_views import ScenarioComputeView, ScenarioSaveView, ScenarioDetailView, ScenarioListView
from .validation_views import ValidationSummaryView, ValidationWeeklyView, ValidationRecentGamesView
from .game_detail_views import ncaa_game_detail
from .analyze_view import AnalyzeCriteriaView

router = DefaultRouter()
router.register(r"seasons", SeasonViewSet, basename="season")
router.register(r"conferences", ConferenceViewSet, basename="conference")
router.register(r"rankings", RankingsViewSet, basename="rankings")
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"matchup", MatchupViewSet, basename="matchup")
router.register(r"games", GameViewSet, basename="game")
router.register(r"jobs", DataProcessingJobViewSet, basename="job")
urlpatterns = [
    path("", include(router.urls)),
    path("auth/csrf/", csrf, name="auth-csrf"),
    path("auth/login/", login_view, name="auth-login"),
    path("auth/logout/", logout_view, name="auth-logout"),
    path("auth/me/", me, name="auth-me"),
    path("viz/landscape/", EfficiencyLandscapeView.as_view(), name="viz-landscape"),
    path("viz/nba-landscape/", NBAEfficiencyLandscapeView.as_view(), name="viz-nba-landscape"),
    path("viz/trapezoid/", TrapezoidView.as_view(), name="viz-trapezoid"),
    path("viz/crystal-ball/", CrystalBallView.as_view(), name="viz-crystal-ball"),
    path("viz/nba-crystal-ball/", NBACrystalBallView.as_view(), name="viz-nba-crystal-ball"),
    path("viz/nba-luck-chart/", NBALuckChartView.as_view(), name="viz-nba-luck-chart"),
    path("viz/cinderella/", CinderellaView.as_view(), name="viz-cinderella"),
    path("viz/bracket/", BracketView.as_view(), name="viz-bracket"),
    path("viz/stats/", VizStatsView.as_view(), name="viz-stats"),
    path("viz/scatter/", VizScatterView.as_view(), name="viz-scatter"),
    path("pipeline-config/", PipelineConfigView.as_view(), name="pipeline-config"),
    path("team/<slug:slug>/players/", TeamRosterView.as_view(), name="team-roster"),
    path("players/", LeaguePlayersView.as_view(), name="league-players"),
    # Phase 7: Roster Outlook (specific paths must precede the slug catch-all)
    path("outlook/scenario/", ScenarioProjectionView.as_view(), name="roster-outlook-scenario"),
    path("outlook/player-search/", PlayerSearchView.as_view(), name="roster-outlook-player-search"),
    path("outlook/placeholders/", PlaceholderListView.as_view(), name="roster-outlook-placeholders"),
    path("outlook/<slug:slug>/", RosterOutlookView.as_view(), name="roster-outlook"),
    # Sprint 3: Scenario layer (richer than /outlook/scenario/)
    path("scenarios/compute/",    ScenarioComputeView.as_view(),  name="scenario-compute"),
    path("scenarios/save/",       ScenarioSaveView.as_view(),     name="scenario-save"),
    path("scenarios/<int:pk>/",   ScenarioDetailView.as_view(),   name="scenario-detail"),
    path("scenarios/",            ScenarioListView.as_view(),     name="scenario-list"),
    # Validation
    path("validation/summary/",       ValidationSummaryView.as_view(),      name="validation-summary"),
    path("validation/weekly/",        ValidationWeeklyView.as_view(),       name="validation-weekly"),
    path("validation/recent-games/",  ValidationRecentGamesView.as_view(),  name="validation-recent-games"),
    # Game detail
    path("games/<int:game_id>/detail/", ncaa_game_detail, name="ncaa-game-detail"),
    path("analyze/", AnalyzeCriteriaView.as_view(), name="analyze-criteria"),
]
