"""
Check records for Florida, Houston, Utah St., and Saint Louis
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import models
from core.models import Team, Game, TeamGameStats, TeamSeasonRatings

teams_to_check = ['Florida', 'Houston', 'Utah St.', 'Saint Louis']

for team_name in teams_to_check:
    print("=" * 100)
    print(f"CHECKING: {team_name}")
    print("=" * 100)
    
    try:
        team = Team.objects.get(name=team_name)
    except Team.DoesNotExist:
        print(f"Team '{team_name}' not found!")
        continue
    
    # Get TeamSeasonRatings
    try:
        ratings = TeamSeasonRatings.objects.get(team=team, season__year=2026)
        print(f"TeamSeasonRatings.games_played: {ratings.games_played}")
    except TeamSeasonRatings.DoesNotExist:
        print("No TeamSeasonRatings found!")
        ratings = None
    
    # Count actual games with scores
    home_games = team.home_games.filter(season_year=2026).exclude(home_score__isnull=True)
    away_games = team.away_games.filter(season_year=2026).exclude(away_score__isnull=True)
    
    total_games = home_games.count() + away_games.count()
    print(f"Actual games with scores: {total_games}")
    
    # Count wins
    home_wins = home_games.filter(home_score__gt=models.F('away_score')).count()
    away_wins = away_games.filter(away_score__gt=models.F('home_score')).count()
    total_wins = home_wins + away_wins
    total_losses = total_games - total_wins
    
    print(f"Actual record: {total_wins}-{total_losses}")
    
    if ratings:
        calc_losses = ratings.games_played - total_wins
        print(f"Record shown on website: {total_wins}-{calc_losses}")
        
        if calc_losses != total_losses:
            print(f"❌ MISMATCH! games_played={ratings.games_played} but actual games={total_games}")
    
    print()
