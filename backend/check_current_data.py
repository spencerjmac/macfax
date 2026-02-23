import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamSeasonRatings, Game
from django.db.models import Q

print("=== Current Database Status ===\n")

# Check total games
total_games = Game.objects.filter(
    game_date__gte='2025-11-01',
    game_date__lte='2026-02-21'
).count()
print(f"Total games in database: {total_games}\n")

# Check key teams
teams_to_check = ['Michigan', 'Houston', 'Florida', 'Utah St.', 'Saint Louis']

print("Team Records (from TeamSeasonRatings):")
print("-" * 60)

for team_name in teams_to_check:
    try:
        team = Team.objects.get(name=team_name)
        ratings = TeamSeasonRatings.objects.filter(team=team, season__year=2026).first()
        
        if ratings:
            print(f"{team_name:15s}: {ratings.games_played:2d} games, Adj EM: {ratings.adj_em:+6.2f}, Adj O: {ratings.adj_o:.2f}, Adj D: {ratings.adj_d:.2f}")
        else:
            print(f"{team_name:15s}: No ratings found")
    except Team.DoesNotExist:
        print(f"{team_name:15s}: Team not found")

print("\n" + "=" * 60)
print("\nWebsite Status:")
print("  Backend:  http://localhost:8000")
print("  Frontend: http://localhost:3001")
print("\nData is ready to view on the website!")
