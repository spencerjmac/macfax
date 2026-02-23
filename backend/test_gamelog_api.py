"""
Test script for Game Log API endpoints

Tests:
1. /api/teams/{slug}/gamelog?season=2026 - Game-by-game stats
2. /api/teams/{slug}/season-stats?season=2026 - Combined season metrics
"""

import requests
import json
from datetime import datetime


BASE_URL = "http://localhost:8000/api"
SEASON_YEAR = 2026


def print_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def test_game_log_endpoint(team_slug="duke"):
    """Test the game log endpoint"""
    print_section(f"Testing Game Log for {team_slug.upper()}")
    
    url = f"{BASE_URL}/teams/{team_slug}/gamelog?season={SEASON_YEAR}"
    print(f"\nURL: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Display summary
        print(f"\n✅ Status: {response.status_code}")
        print(f"Team: {data['team']['name']}")
        print(f"Season: {data['season_year']}")
        print(f"Total Games: {data['total_games']}")
        
        if data['last_updated']:
            print(f"Last Updated: {data['last_updated']}")
        
        # Display first few games
        game_log = data['game_log']
        if game_log:
            print(f"\n--- First 5 Games ---")
            for i, game in enumerate(game_log[:5], 1):
                loc = game['home_away']
                opp = game['opponent_name']
                result = game['result']
                score = f"{game['pts']}-{game.get('opp_pts', '?')}"
                ortg = game.get('ortg', 0)
                drtg = game.get('drtg', 0)
                
                print(f"{i}. {game['game_date']} vs {opp} ({loc}) - {result} {score}")
                print(f"   ORtg: {ortg:.1f} | DRtg: {drtg:.1f} | eFG%: {game.get('efg_pct', 0):.1f}")
            
            # Summary stats
            total_poss = sum(g.get('possessions', 0) for g in game_log)
            avg_ortg = sum(g.get('ortg', 0) for g in game_log) / len(game_log)
            avg_drtg = sum(g.get('drtg', 0) for g in game_log) / len(game_log)
            
            print(f"\n--- Season Averages ---")
            print(f"Avg ORtg: {avg_ortg:.1f}")
            print(f"Avg DRtg: {avg_drtg:.1f}")
            print(f"Net Rating: {avg_ortg - avg_drtg:.1f}")
            print(f"Total Possessions: {total_poss:.0f}")
        else:
            print("\n⚠️  No games found in game log")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: {e}")
        return False


def test_season_stats_endpoint(team_slug="duke"):
    """Test the combined season stats endpoint"""
    print_section(f"Testing Season Stats for {team_slug.upper()}")
    
    url = f"{BASE_URL}/teams/{team_slug}/season-stats?season={SEASON_YEAR}"
    print(f"\nURL: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        print(f"\n✅ Status: {response.status_code}")
        print(f"Team: {data['team']['name']}")
        print(f"Season: {data['season_year']}")
        
        # Display metrics
        if 'metrics' in data and data['metrics']:
            metrics = data['metrics']
            print(f"\n--- Four Factors Metrics ---")
            print(f"Games: {metrics.get('games', 0)}")
            print(f"ORtg: {metrics.get('ortg', 0):.1f}")
            print(f"DRtg: {metrics.get('drtg', 0):.1f}")
            print(f"Net: {metrics.get('net_rating', 0):.1f}")
            print(f"\neFG%: {metrics.get('efg_pct', 0):.1f}")
            print(f"TOV%: {metrics.get('tov_pct', 0):.1f}")
            print(f"ORB%: {metrics.get('orb_pct', 0):.1f}")
            print(f"FTR: {metrics.get('ftr', 0):.2f}")
        
        # Display ratings
        if 'ratings' in data and data['ratings']:
            ratings = data['ratings']
            print(f"\n--- Adjusted Ratings ---")
            print(f"AOR: {ratings.get('aor', 0):.2f}")
            print(f"ADR: {ratings.get('adr', 0):.2f}")
            print(f"AEM: {ratings.get('aem', 0):.2f}")
        
        # Display kill shots
        if 'kill_shots' in data and data['kill_shots']:
            ks = data['kill_shots']
            print(f"\n--- Kill Shots ---")
            print(f"Offensive: {ks.get('kill_shot_off', 0):.2f}")
            print(f"Defensive: {ks.get('kill_shot_def', 0):.2f}")
            print(f"Total: {ks.get('kill_shot_total', 0):.2f}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: {e}")
        return False


def test_teams_list():
    """Test getting list of teams"""
    print_section("Testing Teams List")
    
    url = f"{BASE_URL}/teams?limit=5"
    print(f"\nURL: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        print(f"\n✅ Status: {response.status_code}")
        print(f"Total Teams: {data.get('count', 0)}")
        
        if data.get('results'):
            print(f"\n--- First 5 Teams ---")
            for team in data['results'][:5]:
                print(f"  • {team['name']} ({team['slug']})")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: {e}")
        return False


def main():
    """Run all tests"""
    print_section("🏀 Game Log API Test Suite")
    print(f"Base URL: {BASE_URL}")
    print(f"Season: {SEASON_YEAR}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test multiple teams to verify data
    test_teams = ["duke", "north-carolina", "kansas"]
    
    results = []
    
    # Test teams list
    results.append(("Teams List", test_teams_list()))
    
    # Test each team
    for team_slug in test_teams:
        results.append((f"{team_slug} - Game Log", test_game_log_endpoint(team_slug)))
        results.append((f"{team_slug} - Season Stats", test_season_stats_endpoint(team_slug)))
    
    # Summary
    print_section("📊 Test Summary")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
