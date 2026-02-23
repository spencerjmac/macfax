import requests
import json

# Test Mississippi teams via API
response = requests.get('http://127.0.0.1:8000/api/teams/?season=2026&search=Mississippi')
data = response.json()

print(f"\nFound {data['count']} Mississippi teams:\n")
for team in data['results']:
    print(f"Team: {team['name']}")
    print(f"  Games Played: {team.get('games_played', 'N/A')}")
    print(f"  Record: {team.get('wins', '?')}-{team.get('losses', '?')}")
    if 'adj_em' in team:
        print(f"  AdjEM: {team['adj_em']}")
    print()
