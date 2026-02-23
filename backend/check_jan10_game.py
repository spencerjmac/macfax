"""
Check for Michigan @ Wisconsin game on Jan 10, 2026
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game
from django.db.models import Q
from datetime import date

michigan = Team.objects.get(name='Michigan')
wisconsin = Team.objects.get(name='Wisconsin')

print("=" * 100)
print("CHECKING FOR MICHIGAN @ WISCONSIN (Jan 10, 2026)")
print("=" * 100)

# Check for game on Jan 10
game_date = date(2026, 1, 10)

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
    
    # Check if it shows as a Michigan loss
    if game.home_team == michigan:
        mich_score = game.home_score
        opp_score = game.away_score
    else:
        mich_score = game.away_score
        opp_score = game.home_score
    
    if mich_score and opp_score:
        result = "W" if mich_score > opp_score else "L"
        print(f"\n  Result for Michigan: {result} {mich_score}-{opp_score}")
else:
    print(f"\n✗ Game NOT found in database!")
    print(f"\nExpected: Wisconsin 91, Michigan 88 (Michigan loss)")

# Check all games in early January to see what's there
print(f"\n" + "-" * 100)
print(f"ALL MICHIGAN GAMES IN JANUARY 2026")
print("-" * 100)

jan_games = Game.objects.filter(
    season_year=2026,
    game_date__year=2026,
    game_date__month=1
).filter(
    Q(home_team=michigan) | Q(away_team=michigan)
).order_by('game_date')

if jan_games.exists():
    print(f"\nFound {jan_games.count()} Michigan games in January:\n")
    for g in jan_games:
        opp = g.away_team if g.home_team == michigan else g.home_team
        loc = "vs" if g.home_team == michigan else "@"
        print(f"  {g.game_date}: {loc} {opp.name}")
else:
    print(f"\nNo Michigan games found in January 2026")

print("\n" + "=" * 100)
