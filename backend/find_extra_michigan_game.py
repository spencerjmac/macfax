"""
Find the extra Michigan game that's making the count 27 instead of 26
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game, TeamGameStats

# Get Michigan team
michigan = Team.objects.get(name='Michigan')

# Get all games
home_games = Game.objects.filter(home_team=michigan, season_year=2026).order_by('game_date')
away_games = Game.objects.filter(away_team=michigan, season_year=2026).order_by('game_date')

all_games = sorted(
    list(home_games) + list(away_games),
    key=lambda g: (g.game_date, g.id)
)

print(f"Total games found: {len(all_games)}\n")
print("=" * 120)
print(f"{'Date':<12} {'ID':<10} {'Home':<25} {'Away':<25} {'Score':<10} {'Has Stats?':<12}")
print("=" * 120)

for game in all_games:
    mich_stats = TeamGameStats.objects.filter(game=game, team=michigan).first()
    if game.home_team == michigan:
        opp = game.away_team
        opp_stats = TeamGameStats.objects.filter(game=game, team=opp).first()
    else:
        opp = game.home_team
        opp_stats = TeamGameStats.objects.filter(game=game, team=opp).first()
    
    if mich_stats and opp_stats:
        score = f"{mich_stats.pts}-{opp_stats.pts}"
        has_stats = "✓ Yes"
        result = "W" if mich_stats.pts > opp_stats.pts else "L"
    else:
        score = "N/A"
        has_stats = "✗ No"
        result = "?"
    
    home_name = game.home_team.name if game.home_team else "None"
    away_name = game.away_team.name if game.away_team else "None"
    
    print(f"{str(game.game_date):<12} {game.id:<10} {home_name:<25} {away_name:<25} {score:<10} {has_stats:<12} {result}")

# Check for duplicates
print("\n" + "=" * 120)
print("CHECKING FOR DUPLICATES")
print("=" * 120)

date_opponent = {}
for game in all_games:
    if game.home_team == michigan:
        opp = game.away_team.name
        location = "vs"
    else:
        opp = game.home_team.name
        location = "@"
    
    key = (str(game.game_date), opp, location)
    if key in date_opponent:
        print(f"⚠ DUPLICATE FOUND: {game.game_date} {location} {opp}")
        print(f"  Game 1: ID={date_opponent[key]}")
        print(f"  Game 2: ID={game.id}")
    else:
        date_opponent[key] = game.id
