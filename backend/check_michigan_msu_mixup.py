"""
Check if Michigan and Michigan State games are getting mixed up
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db.models import Q
from core.models import Team, Game, TeamGameStats

print("=" * 100)
print("CHECKING FOR MICHIGAN vs MICHIGAN STATE MIXUP")
print("=" * 100)

michigan = Team.objects.get(name='Michigan')
mich_state = Team.objects.get(name='Michigan State')

print(f"\nMichigan ID: {michigan.id}")
print(f"Michigan State ID: {mich_state.id}")

# Check game count for both teams
mich_games_2026 = Game.objects.filter(
    season_year=2026
).filter(
    Q(home_team=michigan) | Q(away_team=michigan)
).count()

msu_games_2026 = Game.objects.filter(
    season_year=2026
).filter(
    Q(home_team=mich_state) | Q(away_team=mich_state)
).count()

print(f"\nMichigan games in 2026: {mich_games_2026}")
print(f"Michigan State games in 2026: {msu_games_2026}")

# Check a few recent games for each
print("\n" + "-" * 100)
print("RECENT MICHIGAN GAMES (last 5)")
print("-" * 100)

mich_recent = Game.objects.filter(
    season_year=2026
).filter(
    Q(home_team=michigan) | Q(away_team=michigan)
).order_by('-game_date')[:5]

for game in mich_recent:
    home = game.home_team.name
    away = game.away_team.name
    print(f"{game.game_date}: {away} @ {home} (ID: {game.source_game_id})")

print("\n" + "-" * 100)
print("RECENT MICHIGAN STATE GAMES (last 5)")
print("-" * 100)

msu_recent = Game.objects.filter(
    season_year=2026
).filter(
    Q(home_team=mich_state) | Q(away_team=mich_state)
).order_by('-game_date')[:5]

for game in msu_recent:
    home = game.home_team.name
    away = game.away_team.name
    print(f"{game.game_date}: {away} @ {home} (ID: {game.source_game_id})")

# Look for suspicious patterns
print("\n" + "-" * 100)
print("CHECKING FOR KNOWN MISMATCHED GAMES")
print("-" * 100)

# Check the Feb 13 Wisconsin game (should be Michigan State, not Michigan)
game_6505006 = Game.objects.filter(source_game_id='6505006').first()
if game_6505006:
    print(f"\n❌ Game 6505006 (Feb 13, Michigan St @ Wisconsin) IS in database:")
    print(f"   Home: {game_6505006.home_team.name}")
    print(f"   Away: {game_6505006.away_team.name}")
    print(f"   Date: {game_6505006.game_date}")
else:
    print(f"\n✓ Game 6505006 (Michigan St @ Wisconsin) correctly NOT in Michigan's schedule")

# Check if there are any games where the opponent is suspiciously Michigan-like
print("\n" + "-" * 100)
print("GAMES WHERE MICHIGAN PLAYED TEAMS WITH 'MICHIGAN' IN NAME")
print("-" * 100)

for game in Game.objects.filter(season_year=2026).filter(
    Q(home_team=michigan) | Q(away_team=michigan)
):
    opponent = game.away_team if game.home_team == michigan else game.home_team
    if 'michigan' in opponent.name.lower() and opponent != michigan:
        print(f"{game.game_date}: Michigan vs {opponent.name}")

print("\n" + "=" * 100)
