"""
Check if the 5 remaining teams have played games and what their NCAA API names are
"""
import os, django
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.utils.ncaa_api import NCAAAPIClient

api = NCAAAPIClient()

# Sample many dates throughout the season
dates = []
for month in [11, 12]:
    for day in range(1, 31):
        try:
            dates.append(date(2025, month, day))
        except:
            pass
for month in [1, 2]:
    for day in range(1, 20):
        try:
            dates.append(date(2026, month, day))
        except:
            pass

# Teams we're looking for
target_patterns = [
    'central conn', 'georgia southern', 'ga southern', 'ga. southern',
    'miss valley', 'mississippi valley', 'umkc', 'kansas city',
    'usc', 'southern cal'
]

found_teams = {}

print("Searching for 5 missing teams across the season...")
print("=" * 60)

for check_date in dates:
    try:
        scoreboard = api.get_scoreboard(check_date)
        games = scoreboard.get('games', [])
        
        for game in games:
            home_short = game.get('home', {}).get('names', {}).get('short', '').lower()
            away_short = game.get('away', {}).get('names', {}).get('short', '').lower()
            home_full = game.get('home', {}).get('names', {}).get('full', '').lower()
away_full = game.get('away', {}).get('names', {}).get('full', '').lower()
            
            for pattern in target_patterns:
                if (pattern in home_short or pattern in away_short or 
                    pattern in home_full or pattern in away_full):
                    
                    team_name = game.get('home', {}).get('names', {}).get('short', '')
                    if pattern not in team_name.lower():
                        team_name = game.get('away', {}).get('names', {}).get('short', '')
                    
                    if team_name not in found_teams:
                        found_teams[team_name] = {
                            'date': check_date,
                            'full': game.get('home', {}).get('names', {}).get('full', '') if pattern in home_short or pattern in home_full else game.get('away', {}).get('names', {}).get('full', '')
                        }
                        print(f"Found: '{team_name}' (full: {found_teams[team_name]['full']}) on {check_date}")
    except Exception as e:
        pass

print("\n" + "=" * 60)
print(f"Found {len(found_teams)} unique team names:")
for team_name, info in found_teams.items():
    print(f"  '{team_name}' -> {info['full']}")
