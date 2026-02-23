"""Simple API test - clean version without emojis"""
import requests

print("\n" + "="*70)
print(" Testing Game Log API")
print("="*70)

# Test Duke game log
try:
    url = 'http://localhost:8000/api/teams/duke/gamelog?season=2026'
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    data = response.json()
    
    print(f"\n[PASS] Game Log Endpoint")
    print(f"  Team: {data['team']['name']}")
    print(f"  Total Games: {data['total_games']}")
    
    if data['game_log']:
        print(f"\n  Last 3 Games:")
        for game in data['game_log'][-3:]:
            print(f"    {game['game_date']} vs {game['opponent_name']}: {game['pts']} pts")
            print(f"      ORtg: {game.get('ortg', 0):.1f} | DRtg: {game.get('drtg', 0):.1f}")
    
except Exception as e:
    print(f"\n[FAIL] Game Log: {e}")

# Test season stats endpoint
try:
    url = 'http://localhost:8000/api/teams/duke/season-stats?season=2026'
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    data = response.json()
    
    print(f"\n[PASS] Season Stats Endpoint")
    print(f"  Team: {data['team']['name']}")
    
    if data.get('metrics'):
        m = data['metrics']
        print(f"  Season Metrics:")
        print(f"    Games: {m.get('games', 0)}")
        print(f"    ORtg: {m.get('ortg', 0):.1f}")
        print(f"    DRtg: {m.get('drtg', 0):.1f}")
    
except Exception as e:
    print(f"\n[FAIL] Season Stats: {e}")

print("\n" + "="*70)
print(" API Test Complete")
print("="*70 + "\n")
