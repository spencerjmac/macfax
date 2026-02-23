"""
Quick test to verify margin fields are being returned by the API
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

if teams_data:
    # Show first team's four factors data
    team = teams_data[0]
    print("=" * 80)
    print(f"Testing Four Factors Data for: {team['team_name']}")
    print("=" * 80)
    print("\nOffensive Four Factors:")
    print(f"  eFG%:  {team.get('efg_pct', 'MISSING'):.1f}%")
    print(f"  TOV%:  {team.get('tov_pct', 'MISSING'):.1f}%")
    print(f"  ORB%:  {team.get('orb_pct', 'MISSING'):.1f}%")
    print(f"  FTR:   {team.get('ftr', 'MISSING'):.1f}")
    
    print("\nDefensive Four Factors:")
    print(f"  eFG% D: {team.get('efg_pct_d', 'MISSING'):.1f}%")
    print(f"  TOV% D: {team.get('tov_pct_d', 'MISSING'):.1f}%")
    print(f"  DRB%:   {team.get('drb_pct', 'MISSING'):.1f}%")
    print(f"  FTR D:  {team.get('ftr_d', 'MISSING'):.1f}")
    
    print("\nFour Factor Margins:")
    print(f"  eFG Margin:  {team.get('efg_margin', 'MISSING'):.1f}%")
    print(f"  TOV Edge:    {team.get('tov_edge', 'MISSING'):.1f}%")
    print(f"  REB Edge:    {team.get('reb_edge', 'MISSING'):.1f}%")
    print(f"  FTR Margin:  {team.get('ftr_margin', 'MISSING'):.1f}")
    
    print("\n" + "=" * 80)
    print("✅ All fields present in API response!")
else:
    print("❌ No teams data returned from API")
