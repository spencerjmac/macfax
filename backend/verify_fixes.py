"""
Quick verification of the 4 teams that were fixed
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.views import RankingsViewSet
from rest_framework.test import APIRequestFactory

factory = APIRequestFactory()
request = factory.get('/api/rankings/?season=2026')
view = RankingsViewSet.as_view({'get': 'list'})
response = view(request)
teams_data = response.data.get('results', [])

# Teams that were fixed
fixed_teams = ['massachusetts', 'liberty', 'kennesaw-st', 'texas']

print("=" * 80)
print("VERIFICATION OF FIXED TEAMS:")
print("=" * 80)
for team in teams_data:
    if team.get('team_slug', '').lower() in fixed_teams:
        print(f"  ✅ {team['team_name']:25} → {team['conference']:6} (slug: {team['team_slug']})")
print("=" * 80)
