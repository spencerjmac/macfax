import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game
from django.db.models import Q
import requests
from datetime import datetime, timedelta

# Check New Mexico's schedule on NCAA API to find missing game
print("="*70)
print("Finding New Mexico's missing win")
print("="*70)

# Get all New Mexico games from NCAA scoreboard for the entire season
new_mexico = Team.objects.get(name='New Mexico')

# Get games from database
db_games = Game.objects.filter(
    Q(home_team=new_mexico) | Q(away_team=new_mexico),
    game_date__gte='2025-11-01',
    game_date__lte='2026-02-21'
).exclude(home_score__isnull=True).order_by('game_date')

print(f"\nNew Mexico has {db_games.count()} games with scores in database")
print("\nLet me check for gaps in the schedule...\n")

# Check for date gaps
prev_date = None
for game in db_games:
    if prev_date:
        gap = (game.game_date - prev_date).days
        if gap > 7:  # More than a week gap
            print(f"⚠️  Large gap: {prev_date} -> {game.game_date} ({gap} days)")
    prev_date = game.game_date

# Also check if there are any games in that date range without scores
missing_score_games = Game.objects.filter(
    Q(home_team=new_mexico) | Q(away_team=new_mexico),
    game_date__gte='2025-11-01',
    game_date__lte='2026-02-21',
    home_score__isnull=True
).order_by('game_date')

if missing_score_games.exists():
    print(f"\n⚠️  Found {missing_score_games.count()} games without scores:")
    for game in missing_score_games:
        print(f"  {game.game_date}: {game.home_team.name} vs {game.away_team.name} (ID: {game.id})")
