import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game
from django.db.models import Q

new_mexico = Team.objects.get(name='New Mexico')
games = Game.objects.filter(
    Q(home_team=new_mexico) | Q(away_team=new_mexico),
    game_date__gte='2025-11-01',
    game_date__lte='2026-02-21'
).order_by('game_date')

print("\n" + "="*80)
print("NEW MEXICO 2025-26 SCHEDULE (from database)")
print("="*80)
print(f"Total games: {games.count()}")
print()

wins = 0
losses = 0

for i, game in enumerate(games, 1):
    has_score = game.home_score is not None and game.away_score is not None
    
    if game.home_team == new_mexico:
        opponent = game.away_team.name
        location = "vs"
        if has_score:
            result = "W" if game.home_score > game.away_score else "L"
            score = f"{game.home_score}-{game.away_score}"
            nm_score = game.home_score
            opp_score = game.away_score
            if result == "W":
                wins += 1
            else:
                losses += 1
        else:
            result = "-"
            score = "No score yet"
            nm_score = "-"
            opp_score = "-"
    else:
        opponent = game.home_team.name
        location = "@"
        if has_score:
            result = "W" if game.away_score > game.home_score else "L"
            score = f"{game.away_score}-{game.home_score}"
            nm_score = game.away_score
            opp_score = game.home_score
            if result == "W":
                wins += 1
            else:
                losses += 1
        else:
            result = "-"
            score = "No score yet"
            nm_score = "-"
            opp_score = "-"
    
    # Format the line
    print(f"{i:2d}. {game.game_date}  {result:1s}  {location:2s}  {opponent:30s}  Score: {score:15s}")

print()
print("="*80)
print(f"RECORD (completed games): {wins}-{losses}")
print(f"You said they should be: 20-6")
print(f"Missing: {20-wins} win(s)")
print("="*80)
print()
