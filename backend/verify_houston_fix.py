import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game
from django.db.models import Q

houston = Team.objects.get(name='Houston')
games = Game.objects.filter(
    Q(home_team=houston) | Q(away_team=houston),
    game_date__gte='2025-11-01',
    game_date__lte='2026-02-21'
).order_by('game_date')

wins = 0
losses = 0

print(f"Houston games ({games.count()} total):")
print()

for game in games:
    if game.home_team == houston:
        result = "W" if game.home_score > game.away_score else "L"
        opponent = game.away_team.name
        score = f"{game.home_score}-{game.away_score}"
        location = "vs"
    else:
        result = "W" if game.away_score > game.home_score else "L"
        opponent = game.home_team.name
        score = f"{game.away_score}-{game.home_score}"
        location = "@"
    
    if result == "W":
        wins += 1
    else:
        losses += 1
    
    print(f"{game.game_date} {result} {location} {opponent:20s} {score}")

print()
print(f"Final Record: {wins}-{losses}")
