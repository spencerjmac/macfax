"""
Test ingestion for Michigan's missing games (Feb 12-21, 2026)
"""
import os
import sys
import django
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.utils.ncaa_api import NCAAAPIClient
from core.utils.team_mapping import TeamMapper
from core.models import Team, Game

print("=" * 100)
print("TESTING NCAA API FOR MICHIGAN'S MISSING GAMES (Feb 12-21, 2026)")
print("=" * 100)

# Initialize NCAA client
client = NCAAAPIClient()

# Date range for missing games
start_date = date(2026, 2, 12)
end_date = date(2026, 2, 21)

print(f"\nFetching games from {start_date} to {end_date}...")
print("-" * 100)

current_date = start_date
michigan_games = []

while current_date <= end_date:
    print(f"\n📅 Checking {current_date}...")
    
    try:
        # Fetch games for this date
        games = client.get_scoreboard(current_date)
        
        print(f"   Found {len(games)} D1 games on this date")
        
        # Check if any involve Michigan
        for game in games:
            home_team = game.get('home', {}).get('name', '')
            away_team = game.get('away', {}).get('name', '')
            
            if 'Michigan' in home_team or 'Michigan' in away_team:
                home_score = game.get('home', {}).get('score', 0)
                away_score = game.get('away', {}).get('score', 0)
                status = game.get('status', '')
                game_id = game.get('id', game.get('gameID', ''))
                
                print(f"\n   🏀 FOUND MICHIGAN GAME!")
                print(f"      Game ID: {game_id}")
                print(f"      {away_team} @ {home_team}")
                print(f"      Score: {away_score} - {home_score}")
                print(f"      Status: {status}")
                
                michigan_games.append({
                    'date': current_date,
                    'game_id': game_id,
                    'home': home_team,
                    'away': away_team,
                    'home_score': home_score,
                    'away_score': away_score,
                    'status': status
                })
                
    except Exception as e:
        print(f"   ⚠ ERROR: {e}")
    
    current_date += timedelta(days=1)

print("\n" + "=" * 100)
print("SUMMARY OF MICHIGAN'S MISSING GAMES")
print("=" * 100)

if michigan_games:
    print(f"\nFound {len(michigan_games)} Michigan games that should be imported:\n")
    
    for i, game in enumerate(michigan_games, 1):
        is_home = 'Michigan' in game['home']
        opponent = game['away'] if is_home else game['home']
        location = 'vs' if is_home else '@'
        
        mich_score = game['home_score'] if is_home else game['away_score']
        opp_score = game['away_score'] if is_home else game['home_score']
        result = 'W' if mich_score > opp_score else 'L'
        
        print(f"{i}. {game['date']} - {location} {opponent}")
        print(f"   Result: {result} {mich_score}-{opp_score}")
        print(f"   Game ID: {game['game_id']}")
        print(f"   Status: {game['status']}")
        
        # Check if already in database
        exists = Game.objects.filter(source_game_id=game['game_id']).exists()
        print(f"   In DB: {'Yes' if exists else 'No'}")
        print()
else:
    print("\n⚠ No Michigan games found in this date range")
    print("This could mean:")
    print("  1. NCAA API is not returning the data")
    print("  2. The date range is wrong")
    print("  3. Michigan didn't play during this period")

print("=" * 100)
