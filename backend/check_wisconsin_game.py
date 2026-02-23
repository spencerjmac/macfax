"""
Check for the missing Michigan @ Wisconsin game on Feb 13
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game
from django.db.models import Q

michigan = Team.objects.get(name='Michigan')
wisconsin = Team.objects.get(name='Wisconsin')

print("=" * 100)
print("SEARCHING FOR MICHIGAN @ WISCONSIN (Feb 13, 2026)")
print("=" * 100)

# Check for game on Feb 13
from datetime import date
game_date = date(2026, 2, 13)

# Look for this specific game
game = Game.objects.filter(
    season_year=2026,
    game_date=game_date
).filter(
    Q(home_team=wisconsin, away_team=michigan) |
    Q(home_team=michigan, away_team=wisconsin)
).first()

if game:
    print(f"\n✓ Found game:")
    print(f"  Date: {game.game_date}")
    print(f"  Home: {game.home_team.name}")
    print(f"  Away: {game.away_team.name}")
    print(f"  Score: {game.home_score} - {game.away_score}")
    print(f"  Game ID: {game.source_game_id}")
else:
    print(f"\n✗ Game not found in database")
    print(f"\nChecking if Wisconsin exists as a team...")
    
    try:
        wisconsin_check = Team.objects.get(name='Wisconsin')
        print(f"  ✓ Wisconsin found: ID={wisconsin_check.id}")
    except Team.DoesNotExist:
        print(f"  ✗ Wisconsin NOT FOUND in database!")
        print(f"\nSearching for teams with 'Wisc' in name...")
        wisc_teams = Team.objects.filter(name__icontains='wisc')
        if wisc_teams.exists():
            for t in wisc_teams:
                print(f"    - {t.name} (ID: {t.id}, Slug: {t.slug})")
        else:
            print(f"    No teams found with 'Wisc' in name")

# Also check what games Wisconsin has on Feb 13
print(f"\n" + "-" * 100)
print(f"ALL GAMES ON FEB 13, 2026")
print("-" * 100)

all_games_feb13 = Game.objects.filter(
    season_year=2026,
    game_date=game_date
).order_by('source_game_id')

print(f"\nFound {all_games_feb13.count()} games on Feb 13, 2026\n")

# Check if any involve Michigan or Wisconsin
for game in all_games_feb13:
    if michigan in [game.home_team, game.away_team] or (wisconsin and wisconsin in [game.home_team, game.away_team]):
        print(f"  {game.away_team.name} @ {game.home_team.name}")
        print(f"    Score: {game.away_score} - {game.home_score}")
        print(f"    Game ID: {game.source_game_id}")
        print()

print("=" * 100)
