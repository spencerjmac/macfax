"""
Diagnostic script to find unmapped NCAA team names
Fetches games from NCAA API and identifies teams that aren't mapping
"""

import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.utils.ncaa_api import NCAAAPIClient
from core.utils.team_mapping import TeamMapper
from datetime import date
from collections import defaultdict

print("="*70)
print(" NCAA Team Name Diagnostic")
print("="*70)

# Initialize
client = NCAAAPIClient()
mapper = TeamMapper(source='ncaa')

# Sample a few dates
test_dates = [
    date(2025, 11, 5),  # Early season
    date(2025, 12, 15), # Mid non-conf
    date(2026, 1, 15),  # Conference play
    date(2026, 2, 15),  # Late season
]

unmapped_teams = defaultdict(int)
mapped_teams = set()

print("\nScanning games from sample dates...")
for test_date in test_dates:
    print(f"  {test_date}...", end='')
    try:
        games = client.get_scoreboard(test_date)
        print(f" {len(games)} games")
        
        for game in games:
            home_name = game.get('home', {}).get('name', '')
            away_name = game.get('away', {}).get('name', '')
            
            for team_name in [home_name, away_name]:
                if not team_name:
                    continue
                
                team, confidence, _ = mapper.find_team(team_name)
                
                if team:
                    mapped_teams.add(team_name)
                else:
                    unmapped_teams[team_name] += 1
                    
    except Exception as e:
        print(f" Error: {e}")

print(f"\n{'='*70}")
print(" RESULTS")
print(f"{'='*70}")
print(f"\nMapped teams: {len(mapped_teams)}")
print(f"Unmapped teams: {len(unmapped_teams)}")

if unmapped_teams:
    print(f"\n{'='*70}")
    print(" UNMAPPED TEAMS (NCAA API name)")
    print(f"{'='*70}")
    
    sorted_unmapped = sorted(unmapped_teams.items(), key=lambda x: x[1], reverse=True)
    
    for i, (team_name, count) in enumerate(sorted_unmapped, 1):
        print(f"{i:2d}. {team_name:40s} (seen {count} times)")
    
    print(f"\n{'='*70}")
    print(" SUGGESTED MAPPINGS FOR team_alias_overrides.yml")
    print(f"{'='*70}")
    print("\nncaa:")
    
    for team_name, _ in sorted_unmapped:
        # Try to suggest the correct mapping
        print(f'  "{team_name}": "???"  # TODO: Find correct team name')

print("\n")
