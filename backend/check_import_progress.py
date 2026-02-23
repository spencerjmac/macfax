"""
Quick script to check import progress
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Game, TeamExternalId, Team

# Count games
games_count = Game.objects.filter(season_year=2026).count()
external_ids_count = TeamExternalId.objects.filter(source='ncaa').count()
teams_with_games = Team.objects.filter(home_games__season_year=2026).distinct().count()

print("=" * 60)
print("2026 SEASON IMPORT PROGRESS")
print("=" * 60)
print(f"Total games imported: {games_count}")
print(f"Teams mapped (NCAA external IDs): {external_ids_count}")
print(f"Teams with games: {teams_with_games}")
print("=" * 60)

# Show some recent games
print("\nRecent games imported:")
recent_games = Game.objects.filter(season_year=2026).order_by('-game_date')[:5]
for game in recent_games:
    print(f"  {game.game_date}: {game.home_team.name} vs {game.away_team.name}")
