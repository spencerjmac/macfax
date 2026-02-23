"""
Comprehensive diagnostic to identify unmapped NCAA teams
Checks multiple weeks and identifies which teams need mappings
"""
import os
import sys
import django
from datetime import date, timedelta

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamExternalId
from core.utils.ncaa_api import NCAAAPIClient
from core.utils.team_mapping import TeamMapper

def main():
    api = NCAAAPIClient()
    mapper = TeamMapper('ncaa')  # Pass source parameter
    
    # Check 8 different dates across the season
    dates = [
        date(2025, 11, 4),   # Opening week
        date(2025, 11, 15),  # Week 2
        date(2025, 12, 1),   # Week 4
        date(2025, 12, 15),  # Mid-December
        date(2026, 1, 5),    # New Year
        date(2026, 1, 20),   # Mid-January
        date(2026, 2, 1),    # Early February
        date(2026, 2, 15),   # Mid-February
    ]
    
    unmapped_teams = {}  # {ncaa_name: count}
    mapped_count = 0
    total_count = 0
    
    print("Scanning NCAA API for unmapped teams...")
    print("=" * 60)
    
    for check_date in dates:
        print(f"\nChecking {check_date}...")
        try:
            scoreboard = api.get_scoreboard(check_date)
            games = scoreboard.get('games', [])
            
            for game in games:
                home_name = game.get('home', {}).get('names', {}).get('short', '')
                away_name = game.get('away', {}).get('names', {}).get('short', '')
                
                for team_name in [home_name, away_name]:
                    if not team_name:
                        continue
                    
                    total_count += 1
                    team = mapper.find_team(team_name, 'ncaa')
                    
                    if team:
                        mapped_count += 1
                    else:
                        unmapped_teams[team_name] = unmapped_teams.get(team_name, 0) + 1
        
        except Exception as e:
            print(f"  Error: {e}")
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC RESULTS")
    print("=" * 60)
    print(f"Total team instances checked: {total_count}")
    print(f"Mapped: {mapped_count}")
    print(f"Unmapped: {total_count - mapped_count}")
    print(f"Unique unmapped teams: {len(unmapped_teams)}")
    
    if unmapped_teams:
        print("\nTop Unmapped Teams (by frequency):")
        sorted_unmapped = sorted(unmapped_teams.items(), key=lambda x: x[1], reverse=True)
        for team_name, count in sorted_unmapped[:30]:
            print(f"  {team_name:30s} ({count} occurrences)")
    
    # Check which teams in our database don't have NCAA mappings
    print("\n" + "=" * 60)
    print("TEAMS WITHOUT NCAA MAPPINGS")
    print("=" * 60)
    teams_without_ncaa = Team.objects.exclude(
        external_ids__source='ncaa'
    ).order_by('name')
    
    print(f"Total teams without NCAA mapping: {teams_without_ncaa.count()}/365")
    print("\nTeams:")
    for team in teams_without_ncaa[:50]:
        print(f"  {team.name}")

if __name__ == '__main__':
    main()
