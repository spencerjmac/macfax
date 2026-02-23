import requests
import json

print("\n=== Testing Mississippi Teams API ===\n")

# Test 1: Get all teams and filter for Mississippi
response = requests.get('http://127.0.0.1:8000/api/teams/?season=2026')
all_teams = response.json()

miss_teams = [t for t in all_teams['results'] if 'Mississippi' in t['name']]

print(f"Found {len(miss_teams)} Mississippi teams:\n")
for team in miss_teams:
    print(f"Team: {team['name']}")
    print(f"  Slug: {team.get('slug', 'N/A')}")
    print(f"  Games: {team.get('games_played', 'N/A')}")
    print(f"  Record: {team.get('wins', '?')}-{team.get('losses', '?')}")
    print()

# Test 2: Try to get Mississippi specifically
try:
    ole_miss = requests.get('http://127.0.0.1:8000/api/teams/mississippi/?season=2026')
    if ole_miss.status_code == 200:
        data = ole_miss.json()
        print("\nMississippi (via slug 'mississippi'):")
        print(json.dumps(data, indent=2)[:500])
except Exception as e:
    print(f"Error getting Mississippi: {e}")

# Test 3: Try Mississippi Valley St
try:
    miss_valley = requests.get('http://127.0.0.1:8000/api/teams/mississippi-valley-st/?season=2026')
    if miss_valley.status_code == 200:
        data = miss_valley.json()
        print("\nMississippi Valley St (via slug):")
        print(json.dumps(data, indent=2)[:500])
except Exception as e:
    print(f"Error getting Miss Valley: {e}")
