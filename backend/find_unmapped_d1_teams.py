"""
Find NCAA API names for the 5 unmapped D1 teams
"""
import os
import django
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamExternalId
from core.utils.ncaa_api import NCAAAPIClient

# The 5 teams we need to map
target_teams = [
    "Army",
    "Georgia Southern", 
    "Mississippi Valley St.",
    "North Carolina Central",
    "UMKC"
]

print(f"Finding NCAA API names for {len(target_teams)} unmapped teams...")
print("=" * 60)

api = NCAAAPIClient()

# Check multiple dates to find games with these teams
dates_to_check = [
    date(2025, 11, 4), date(2025, 11, 15), date(2025, 12, 1),
    date(2025, 12, 15), date(2026, 1, 5), date(2026, 1, 20),
    date(2026, 2, 1), date(2026, 2, 15)
]

found_mappings = {}

for check_date in dates_to_check:
    try:
        scoreboard = api.get_scoreboard(check_date)
        games = scoreboard.get('games', [])
        
        for game in games:
            home_name = game.get('home', {}).get('names', {}).get('short', '')
            away_name = game.get('away', {}).get('names', {}).get('short', '')
            home_full = game.get('home', {}).get('names', {}).get('full', '')
            away_full = game.get('away', {}).get('names', {}).get('full', '')
            
            # Check if any target team appears in the full name
            for target in target_teams:
                if target in found_mappings:
                    continue
                    
                # Check various name formats
                target_lower = target.lower()
                if (target_lower in home_full.lower() or 
                    target_lower in away_full.lower() or
                    'army' in home_name.lower() and 'army' in target_lower or
                    'army' in away_name.lower() and 'army' in target_lower or
                    'georgia southern' in home_full.lower() and 'georgia southern' in target_lower or
                    'georgia southern' in away_full.lower() and 'georgia southern' in target_lower or
                    'umkc' in home_name.lower() and 'umkc' in target_lower or
                    'umkc' in away_name.lower() and 'umkc' in target_lower or
                    'mississippi valley' in home_full.lower() and 'mississippi valley' in target_lower or
                    'mississippi valley' in away_full.lower() and 'mississippi valley' in target_lower or
                    'nc central' in home_full.lower() and 'north carolina central' in target_lower or
                    'nc central' in away_full.lower() and 'north carolina central' in target_lower):
                    
                    ncaa_name = home_name if target_lower in home_full.lower() or 'army' in home_name.lower() else away_name
                    found_mappings[target] = ncaa_name
                    print(f"  {target:30s} -> '{ncaa_name}'")
    
    except Exception as e:
        pass

print("\n" + "=" * 60)
print(f"Found {len(found_mappings)}/{len(target_teams)} mappings")

if len(found_mappings) < len(target_teams):
    print("\nStill missing:")
    for team in target_teams:
        if team not in found_mappings:
            print(f"  {team}")
