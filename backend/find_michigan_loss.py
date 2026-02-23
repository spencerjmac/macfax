"""
Check for Michigan losses in detail
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db.models import Q
from core.models import Team, Game, TeamGameStats

michigan = Team.objects.get(name='Michigan')

print("=" * 100)
print("CHECKING FOR MICHIGAN LOSSES")
print("=" * 100)

# Get all 2026 games
games = Game.objects.filter(
    season_year=2026
).filter(
    Q(home_team=michigan) | Q(away_team=michigan)
).order_by('game_date')

print(f"\nTotal games: {games.count()}\n")

wins = 0
losses = 0
no_stats = 0

for game in games:
    mich_stats = TeamGameStats.objects.filter(game=game, team=michigan).first()
    
    if game.home_team == michigan:
        opp = game.away_team
        opp_stats = TeamGameStats.objects.filter(game=game, team=opp).first()
    else:
        opp = game.home_team
        opp_stats = TeamGameStats.objects.filter(game=game, team=opp).first()
    
    if mich_stats and opp_stats:
        result = 'W' if mich_stats.pts > opp_stats.pts else 'L'
        if result == 'L':
            print(f"❌ LOSS: {game.game_date} - Michigan {mich_stats.pts}, {opp.name} {opp_stats.pts}")
            print(f"   Game ID: {game.source_game_id}")
            print(f"   Location: {'Home' if game.home_team == michigan else 'Away'}")
            print()
            losses += 1
        else:
            wins += 1
    else:
        print(f"⚠ No stats: {game.game_date} vs {opp.name} (Game ID: {game.source_game_id})")
        no_stats += 1

print("\n" + "=" * 100)
print(f"RECORD: {wins}-{losses} ({wins + losses} games with stats, {no_stats} without stats)")
print("=" * 100)
