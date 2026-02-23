"""
Check for Michigan games on Feb 21 (today)
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

print("=" * 100)
print("CHECKING FOR MICHIGAN GAMES ON FEB 21, 2026 (TODAY)")
print("=" * 100)

# Check for games on Feb 21
game_date = date(2026, 2, 21)

games_today = Game.objects.filter(
    season_year=2026,
    game_date=game_date
).filter(
    Q(home_team=michigan) | Q(away_team=michigan)
)

if games_today.exists():
    print(f"\n✓ Found {games_today.count()} Michigan game(s) on Feb 21:\n")
    for game in games_today:
        opp = game.away_team if game.home_team == michigan else game.home_team
        loc = "vs" if game.home_team == michigan else "@"
        print(f"  {loc} {opp.name}")
        print(f"    Status: {game.status}")
        if game.home_score and game.away_score:
            print(f"    Score: {game.away_score} - {game.home_score}")
        print(f"    Game ID: {game.source_game_id}")
        print()
else:
    print(f"\n✗ No Michigan games found on Feb 21")

# Check total Michigan games
total = Game.objects.filter(season_year=2026).filter(
    Q(home_team=michigan) | Q(away_team=michigan)
).count()

print(f"\nTotal Michigan games in database: {total}")
print("=" * 100)
