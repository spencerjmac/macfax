import requests

# Test the rankings API
response = requests.get('http://localhost:8000/api/rankings/?season=2026&search=Mississippi')

if response.status_code == 200:
    data = response.json()
    print(f"Found {data['count']} Mississippi teams:\n")
    
    for team in data['results']:
        print(f"{team['rank']:3d}. {team['team_name']:30s}")
        print(f"      Conference: {team.get('conference', 'N/A')}")
        print(f"      AdjEM: {team['adj_em']:+.2f}")
        print(f"      Adj O: {team['adj_o']:.2f}")
        print(f"      Adj D: {team['adj_d']:.2f}")
        print()
else:
    print(f"Error: {response.status_code}")
    print(response.text)
