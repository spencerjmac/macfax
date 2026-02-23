"""
Check which teams don't have games in 2026
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game

# Find teams without games
teams_with_games = set(Team.objects.filter(home_games__season_year=2026).values_list('id', flat=True))
teams_with_games.update(Team.objects.filter(away_games__season_year=2026).values_list('id', flat=True))

all_teams = Team.objects.all()
teams_without_games = [team for team in all_teams if team.id not in teams_with_games]

print("=" * 60)
print(f"TEAMS WITHOUT 2026 GAMES: {len(teams_without_games)}")
print("=" * 60)

for team in teams_without_games:
    print(f"  - {team.name}")
