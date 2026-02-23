"""
Find duplicate or problematic games for specific teams
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import models
from django.db.models import Count
from core.models import Team, Game

# Check Florida for duplicates
print("=" * 100)
print("FLORIDA - Checking for duplicate games")
print("=" * 100)

florida = Team.objects.get(name='Florida')
florida_games = Game.objects.filter(
    models.Q(home_team=florida) | models.Q(away_team=florida),
    season_year=2026
).exclude(
    models.Q(home_score__isnull=True) | models.Q(away_score__isnull=True)
).order_by('game_date')

# Group by date and opponent
from collections import defaultdict
by_date_opp = defaultdict(list)

for game in florida_games:
    if game.home_team == florida:
        opp = game.away_team.id
        key = (game.game_date, opp, 'home')
    else:
        opp = game.home_team.id
        key = (game.game_date, opp, 'away')
    
    by_date_opp[key].append(game)

for key, games in by_date_opp.items():
    if len(games) > 1:
        print(f"\n⚠ DUPLICATE: {games[0].game_date}")
        for g in games:
            print(f"   Game ID {g.id}: {g.away_team.name} @ {g.home_team.name} ({g.away_score}-{g.home_score})")

# Check Houston for duplicates
print("\n" + "=" * 100)
print("HOUSTON - Checking for duplicate games")
print("=" * 100)

houston = Team.objects.get(name='Houston')
houston_games = Game.objects.filter(
    models.Q(home_team=houston) | models.Q(away_team=houston),
    season_year=2026
).exclude(
    models.Q(home_score__isnull=True) | models.Q(away_score__isnull=True)
).order_by('game_date')

by_date_opp = defaultdict(list)

for game in houston_games:
    if game.home_team == houston:
        opp = game.away_team.id
        key = (game.game_date, opp, 'home')
    else:
        opp = game.home_team.id
        key = (game.game_date, opp, 'away')
    
    by_date_opp[key].append(game)

for key, games in by_date_opp.items():
    if len(games) > 1:
        print(f"\n⚠ DUPLICATE: {games[0].game_date}")
        for g in games:
            print(f"   Game ID {g.id}: {g.away_team.name} @ {g.home_team.name} ({g.away_score}-{g.home_score})")

# Check if Houston has the 12/20 games
print("\nHouston games on 2025-12-20:")
dec20_games = houston_games.filter(game_date='2025-12-20')
for g in dec20_games:
    print(f"   Game ID {g.id}: {g.away_team.name} @ {g.home_team.name} ({g.away_score}-{g.home_score})")
