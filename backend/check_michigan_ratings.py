import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamSeasonRatings, Season

season = Season.objects.get(year=2026)
michigan = Team.objects.get(name='Michigan')
rating = TeamSeasonRatings.objects.get(team=michigan, season=season)

print("\n" + "="*60)
print("MICHIGAN - TeamSeasonRatings Database Values")
print("="*60)
print(f"Adj O:  {rating.adj_o}")
print(f"Adj D:  {rating.adj_d}")
print(f"AdjEM:  {rating.adj_em}")
print(f"Rank:   {rating.rank_adj_em}")
print("="*60)
