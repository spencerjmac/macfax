#!/usr/bin/env python
"""
Test that the API is returning correct records
"""
import requests
import json

# Test the rankings API
url = "http://127.0.0.1:8000/api/rankings?season=2026"

try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    results = data.get('results', [])
    
    print("=" * 80)
    print("API RANKINGS - TESTING RECORDS")
    print("=" * 80)
    print()
    
    # Test teams
    test_teams = ['Michigan', 'New Mexico', 'Saint Louis', 'Houston', 'Duke', 'Arizona']
    
    for team_name in test_teams:
        team_data = next((t for t in results if t['team_name'] == team_name), None)
        if team_data:
            record = team_data.get('record', 'N/A')
            print(f"{team_name:25} | Record: {record}")
        else:
            print(f"{team_name:25} | NOT FOUND IN API")
    
    print()
    print("=" * 80)
    print(f"Total teams in API: {len(results)}")
    print("=" * 80)
    
except requests.exceptions.RequestException as e:
    print(f"Error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
