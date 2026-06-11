from django.urls import path
from .views import WorldCupGroupView, WorldCupMatchupView, WorldCupRankingsView

urlpatterns = [
    path("rankings/", WorldCupRankingsView.as_view(), name="wc-rankings"),
    path("matchup/", WorldCupMatchupView.as_view(), name="wc-matchup"),
    path("group/<str:group>/", WorldCupGroupView.as_view(), name="wc-group"),
]
