"""
Comprehensive search for the 3 missing teams across ALL dates
"""
import os, django
from datetime import date, timedelta
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.utils.ncaa_api import NCAAAPIClient

api = NCAAAPIClient()

# Generate ALL dates from Nov 1 to Feb 19
start_date = date(2025, 11, 1)
end_date = date(2026, 2, 19)
current_date = start_date

all_dates = []
while current_date <= end_date:
    all_dates.append(current_date)
    current_date += timedelta(days=1)

print(f"Searching {len(all_dates)} dates for Georgia Southern, Mississippi Valley St., and UMKC...")
print("=" * 60)

search_terms = ['georgia', 'southern', 'miss', 'valley', 'umkc', 'kansas city']
found_teams = set()
game_count = 0

for check_date in all_dates:
    try:
        scoreboard = api.get_scoreboard(check_date)
        games = scoreboard.get('games', [])
        
        for game in games:
            game_count += 1
            home_short = game.get('home', {}).get('names', {}).get('short', '').lower()
            away_short = game.get('away', {}).get('names', {}).get('short', '').lower()
            home_full = game.get('home', {}).get('names', {}).get('full', '').lower()
            away_full = game.get('away', {}).get('names', {}).get('full', '').lower()
            
            # Check for any of our search terms
            all_text = f"{home_short} {away_short} {home_full} {away_full}"
            
            if 'ga' in home_short and 'southern' in home_short:
                found_teams.add(f"FOUND: {check_date} - {game.get('home', {}).get('names', {}).get('short', '')}")
            if 'ga' in away_short and 'southern' in away_short:
                found_teams.add(f"FOUND: {check_date} - {game.get('away', {}).get('names', {}).get('short', '')}")
                
            if 'miss' in home_short and 'val' in home_short:
                found_teams.add(f"FOUND: {check_date} - {game.get('home', {}).get('names', {}).get('short', '')}")
            if 'miss' in away_short and 'val' in away_short:
                found_teams.add(f"FOUND: {check_date} - {game.get('away', {}).get('names', {}).get('short', '')}")
                
            if 'kansas' in all_text and 'city' in all_text:
                found_teams.add(f"FOUND: {check_date} - Home: {game.get('home', {}).get('names', {}).get('short', '')} / Away: {game.get('away', {}).get('names', {}).get('short', '')}")
            if 'umkc' in all_text:
                found_teams.add(f"FOUND: {check_date} - Home: {game.get('home', {}).get('names', {}).get('short', '')} / Away: {game.get('away', {}).get('names', {}).get('short', '')}")
                
    except Exception as e:
        pass

print(f"\nSearched {game_count:,} total games across {len(all_dates)} dates")
print(f"Found {len(found_teams)} matches:")
print("=" * 60)
for match in sorted(found_teams):
    print(match)

if not found_teams:
    print("\nNO GAMES FOUND for these 3 teams in the NCAA API!")
    print("This suggests these teams may not have played D1 games this season.")
