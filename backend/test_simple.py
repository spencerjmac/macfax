"""
Simple API test for Duke only
"""
import requests

print("Testing Duke game log endpoint...")
try:
    response = requests.get('http://localhost:8000/api/teams/duke/gamelog?season=2026', timeout=5)
    response.raise_for_status()
    data = response.json()
    
    print(f"✅ Game Log: {response.status_code}")
    print(f"   Team: {data['team']['name']}")
    print(f"   Games: {data['total_games']}")
    print(f"   First game: {data['game_log'][0]['game_date'] if data['game_log'] else 'No games'}")
except Exception as e:
    print(f"❌ Error: {e}")

print("\nTesting Duke season stats endpoint...")
try:
    response = requests.get('http://localhost:8000/api/teams/duke/season-stats?season=2026', timeout=5)
    response.raise_for_status()
    data = response.json()
    
    print(f"✅ Season Stats: {response.status_code}")
    print(f"   Team: {data['team']['name']}")
    if data.get('metrics'):
        print(f"   Games: {data['metrics'].get('games', 0)}")
        print(f"   ORtg: {data['metrics'].get('ortg', 0):.1f}")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n✅ Tests complete!")
