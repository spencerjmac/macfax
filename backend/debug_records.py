"""
Debug the record calculation issue
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import models
from core.models import Team, TeamSeasonRatings, Game

# Get Michigan
michigan = Team.objects.get(name='Michigan')
season_year = 2026

print("=" * 100)
print("DEBUGGING RECORD CALCULATION FOR MICHIGAN")
print("=" * 100)

# Check TeamSeasonRatings
try:
    ratings = TeamSeasonRatings.objects.get(team=michigan, season__year=season_year)
    print(f"\nTeamSeasonRatings.games_played: {ratings.games_played}")
except TeamSeasonRatings.DoesNotExist:
    print("\nNo TeamSeasonRatings found!")
    ratings = None

# Count home wins
home_wins = michigan.home_games.filter(
    season_year=season_year
).exclude(home_score__isnull=True).filter(
    home_score__gt=models.F('away_score')
).count()

print(f"Home wins: {home_wins}")

# Count away wins  
away_wins = michigan.away_games.filter(
    season_year=season_year
).exclude(away_score__isnull=True).filter(
    away_score__gt=models.F('home_score')
).count()

print(f"Away wins: {away_wins}")

total_wins = home_wins + away_wins
print(f"Total wins: {total_wins}")

if ratings:
    total_losses = ratings.games_played - total_wins
    print(f"Total losses: {total_losses}")
    print(f"Record shown on rankings: {total_wins}-{total_losses}")

# Now let's verify this by checking all games
print("\n" + "=" * 100)
print("MANUAL VERIFICATION - ALL GAMES")
print("=" * 100)

all_home = michigan.home_games.filter(season_year=season_year).exclude(home_score__isnull=True)
all_away = michigan.away_games.filter(season_year=season_year).exclude(away_score__isnull=True)

print(f"\nHome games with scores: {all_home.count()}")
print(f"Away games with scores: {all_away.count()}")
print(f"Total games with scores: {all_home.count() + all_away.count()}")

manual_wins = 0
manual_losses = 0

for game in all_home:
    if game.home_score > game.away_score:
        manual_wins += 1
    else:
        manual_losses += 1

for game in all_away:
    if game.away_score > game.home_score:
        manual_wins += 1
    else:
        manual_losses += 1

print(f"\nManual count - Wins: {manual_wins}, Losses: {manual_losses}")
print(f"Manual record: {manual_wins}-{manual_losses}")
