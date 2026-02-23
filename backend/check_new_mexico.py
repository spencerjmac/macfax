import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game
from django.db.models import Q

# Check New Mexico's actual schedule from NCAA
print("="*70)
print("New Mexico Schedule - Looking for missing game")
print("="*70)

new_mexico = Team.objects.get(name='New Mexico')
games = Game.objects.filter(
    Q(home_team=new_mexico) | Q(away_team=new_mexico),
    game_date__gte='2025-11-01',
    game_date__lte='2026-02-21'
).order_by('game_date')

print(f"\nCurrent games in DB: {games.count()}")
print("\nGames by date:")
print("-"*70)

for game in games:
    if game.home_team == new_mexico:
        opp = game.away_team.name
        location = "vs"
        if game.home_score and game.away_score:
            result = "W" if game.home_score > game.away_score else "L"
            score = f"{game.home_score}-{game.away_score}"
        else:
            result = "?"
            score = "No score"
    else:
        opp = game.home_team.name
        location = "@"
        if game.home_score and game.away_score:
            result = "W" if game.away_score > game.home_score else "L"
            score = f"{game.away_score}-{game.home_score}"
        else:
            result = "?"
            score = "No score"
    
    print(f"{game.game_date} {result} {location} {opp:25s} {score}")

print("\n" + "="*70)
print("According to you, New Mexico should be 20-6 (26 games)")
print("Database shows 19-6 which means they're missing 1 WIN")
print("="*70)
