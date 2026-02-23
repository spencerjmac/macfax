"""
Check date range of imported games
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Game
from django.db.models import Max, Min, Count

stats = Game.objects.filter(season_year=2026).aggregate(
    min_date=Min('game_date'),
    max_date=Max('game_date'),
    total=Count('id')
)

print(f"Date range imported: {stats['min_date']} to {stats['max_date']}")
print(f"Total games: {stats['total']}")

# Check games by date
from collections import defaultdict
games_by_date = defaultdict(int)
for game in Game.objects.filter(season_year=2026).values('game_date'):
    games_by_date[game['game_date']] += 1

print(f"\nLast 10 dates with games:")
for date in sorted(games_by_date.keys(), reverse=True)[:10]:
    print(f"  {date}: {games_by_date[date]} games")
