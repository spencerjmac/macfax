from django.urls import path
from .views import WorldCupRankingsView

urlpatterns = [
    path("rankings/", WorldCupRankingsView.as_view(), name="wc-rankings"),
]
