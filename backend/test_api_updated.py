import requests
import json

print("\n=== Testing Rankings API ===\n")

# Test rankings endpoint with Mississippi search
response = requests.get('http://127.0.0.1:8000/api/rankings/?season=2026&search=Mississippi')
data = response.json()

print(f"Found {data['count']} teams:\n")
for team in data['results'][:10]:  # Show first 10
    print(f"{team.get('rank', '?'):3d}. {team['team_name']:30s}")
    print(f"     AdjEM: {team.get('adj_em', 'N/A'):7.2f}  |  Record: {team.get('record', 'N/A')}")
    print()

print("\n=== Testing Team Season Stats API ===\n")

# Test individual team endpoints
try:
    ole_miss = requests.get('http://127.0.0.1:8000/api/teams/mississippi/season-stats?season=2026')
    if ole_miss.status_code == 200:
        data = ole_miss.json()
        print("Mississippi (Ole Miss) - via season-stats endpoint:")
        if data.get('ratings'):
            print(f"  Games: {data['ratings'].get('games_played', 'N/A')}")
            print(f"  AdjEM: {data['ratings'].get('adj_em', 'N/A')}")
        if data.get('metrics'):
            print(f"  Record: {data['metrics'].get('wins', '?')}-{data['metrics'].get('losses', '?')}")
    else:
        print(f"Ole Miss endpoint returned {ole_miss.status_code}")
    print()
    
    miss_valley = requests.get('http://127.0.0.1:8000/api/teams/mississippi-valley-st/season-stats?season=2026')
    if miss_valley.status_code == 200:
        data = miss_valley.json()
        print("Mississippi Valley St - via season-stats endpoint:")
        if data.get('ratings'):
            print(f"  Games: {data['ratings'].get('games_played', 'N/A')}")
            print(f"  AdjEM: {data['ratings'].get('adj_em', 'N/A')}")
        if data.get('metrics'):
            print(f"  Record: {data['metrics'].get('wins', '?')}-{data['metrics'].get('losses', '?')}")
    else:
        print(f"Miss Valley endpoint returned {miss_valley.status_code}")
        
except Exception as e:
    print(f"Error: {e}")
