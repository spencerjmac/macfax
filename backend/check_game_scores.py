"""
Check if Game.home_score and Game.away_score are populated
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import models
from core.models import Team, Game, TeamGameStats

# Get Michigan
michigan = Team.objects.get(name='Michigan')

# Get a few games
games = list(Game.objects.filter(
    season_year=2026
).filter(
    models.Q(home_team=michigan) | models.Q(away_team=michigan)
).order_by('game_date')[:5])

print("First 5 Michigan games:")
print("=" * 100)
for game in games:
    print(f"\nGame ID: {game.id}")
    print(f"  Date: {game.game_date}")
    print(f"  {game.away_team.name} @ {game.home_team.name}")
    print(f"  Game.home_score: {game.home_score}")
    print(f"  Game.away_score: {game.away_score}")
    
    # Check TeamGameStats
    home_stats = TeamGameStats.objects.filter(game=game, team=game.home_team).first()
    away_stats = TeamGameStats.objects.filter(game=game, team=game.away_team).first()
    
    if home_stats and away_stats:
        print(f"  TeamGameStats - Home: {home_stats.pts}, Away: {away_stats.pts}")
    else:
        print(f"  TeamGameStats - Missing!")
