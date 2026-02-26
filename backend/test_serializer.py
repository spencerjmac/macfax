"""
Test the RankingsSerializer shooting splits methods
"""
import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Season, TeamSeasonRatings
from api.serializers import RankingsSerializer

# Get a few teams
season = Season.objects.filter(year=2026).first()
teams = TeamSeasonRatings.objects.filter(season=season).order_by('rank_adj_em')[:5]

print("Testing RankingsSerializer shooting splits...")
print("=" * 80)

for team in teams:
    serializer = RankingsSerializer(team)
    data = serializer.data
    
    print(f"\n{data.get('team_name')}:")
    print(f"  FG3%: {data.get('fg3_pct')}")
    print(f"  FG2%: {data.get('fg2_pct')}")
    print(f"  FT%: {data.get('ft_pct')}")
    print(f"  FG3 Rate: {data.get('fg3_rate')}")

print("\n" + "=" * 80)
print("Test complete!")
