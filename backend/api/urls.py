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
)
from .job_views import DataProcessingJobViewSet
from .trapezoid_views import TrapezoidView
from .landscape_views import EfficiencyLandscapeView
from .crystal_ball_views import CrystalBallView
from .cinderella_views import CinderellaView
from .bracket_views import BracketView
from .viz_builder_views import VizStatsView, VizScatterView
from .auth_views import csrf, login_view, logout_view, me

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
    path("viz/trapezoid/", TrapezoidView.as_view(), name="viz-trapezoid"),
    path("viz/crystal-ball/", CrystalBallView.as_view(), name="viz-crystal-ball"),
    path("viz/cinderella/", CinderellaView.as_view(), name="viz-cinderella"),
    path("viz/bracket/", BracketView.as_view(), name="viz-bracket"),
    path("viz/stats/", VizStatsView.as_view(), name="viz-stats"),
    path("viz/scatter/", VizScatterView.as_view(), name="viz-scatter"),
    path("pipeline-config/", PipelineConfigView.as_view(), name="pipeline-config"),
]
