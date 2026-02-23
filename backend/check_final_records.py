#!/usr/bin/env python
"""
Check final records for key teams in the database
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamSeasonRatings, Season, TeamExternalId

# Get 2025-26 season
season = Season.objects.get(year=2026)

# Teams to check
team_names = ['Michigan', 'New Mexico', 'Saint Louis', 'Houston', 'Duke', 'Arizona']

print("=" * 80)
print("FINAL TEAM RECORDS - 2025-26 SEASON")
print("=" * 80)
print()

for team_name in team_names:
    try:
        # Look up by NCAA external ID
        ext_id = TeamExternalId.objects.get(source='ncaa', external_name=team_name)
        team = ext_id.team
        
        if not team.is_d1:
            print(f"{team_name:25} | NON-D1 TEAM")
            continue
            
        ratings = TeamSeasonRatings.objects.get(team=team, season=season)
        
        print(f"{team_name:25} | Record: {ratings.wins}-{ratings.losses} | Games: {ratings.games_played} (D1: {ratings.d1_games_played}) | Adj EM: {ratings.adj_em:+.2f}")
    except TeamExternalId.DoesNotExist:
        print(f"{team_name:25} | NOT FOUND")
    except TeamSeasonRatings.DoesNotExist:
        print(f"{team_name:25} | NO RATINGS DATA")

print()
print("=" * 80)
print("DATABASE SUMMARY")
print("=" * 80)

total_d1_teams = Team.objects.filter(is_d1=True).count()
total_non_d1_teams = Team.objects.filter(is_d1=False).count()
teams_with_ratings = TeamSeasonRatings.objects.filter(season=season).count()

print(f"D1 Teams: {total_d1_teams}")
print(f"Non-D1 Teams (opponents only): {total_non_d1_teams}")
print(f"Teams with Ratings: {teams_with_ratings}")
print()
