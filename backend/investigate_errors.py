import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Game

# Check Saint Louis losses
print("="*70)
print("SAINT LOUIS LOSSES (should have 2 losses, showing 3)")
print("="*70)

loss_ids = [10671, 11113, 13830]  # Stanford, Florida Atlantic, Rhode Island

for game_id in loss_ids:
    game = Game.objects.get(id=game_id)
    print(f"\nGame ID {game_id}:")
    print(f"  {game.game_date}: {game.away_team.name} @ {game.home_team.name}")
    print(f"  Score: {game.away_score}-{game.home_score}")
    
    # Determine which team is Saint Louis
    if game.home_team.name == "Saint Louis":
        print(f"  Saint Louis scored {game.home_score}, opponent scored {game.away_score}")
        result = "W" if game.home_score > game.away_score else "L"
    else:
        print(f"  Saint Louis scored {game.away_score}, opponent scored {game.home_score}")
        result = "W" if game.away_score > game.home_score else "L"
    print(f"  Result in DB: {result}")

print("\n" + "="*70)
print("NEW MEXICO - Checking all results")
print("="*70)

# Check New Mexico games
from core.models import Team
from django.db.models import Q

new_mexico = Team.objects.get(name="New Mexico")
games = Game.objects.filter(
    Q(home_team=new_mexico) | Q(away_team=new_mexico),
    game_date__gte='2025-11-01',
    game_date__lte='2026-02-21'
).exclude(home_score__isnull=True).order_by('game_date')

for game in games:
    if game.home_team == new_mexico:
        opp = game.away_team.name
        nm_score = game.home_score
        opp_score = game.away_score
        location = "vs"
    else:
        opp = game.home_team.name
        nm_score = game.away_score
        opp_score = game.home_score
        location = "@"
    
    result = "W" if nm_score > opp_score else "L"
    print(f"{game.game_date} {result} {location} {opp:25s} {nm_score}-{opp_score} (Game ID: {game.id})")
