#!/usr/bin/env python
"""Manual smoke check: rankings API returns only D1 teams."""

import requests


print("\n=== TESTING API - D1 TEAMS ONLY ===\n")

# Test rankings endpoint
response = requests.get('http://localhost:8000/api/rankings/?season=2026')

if response.status_code == 200:
    data = response.json()
    results = data.get('results', [])
    count = len(results)

    print(f"✓ API returned {count} teams")

    if count == 365:
        print("✅ CORRECT! Exactly 365 Division I teams")
    else:
        print(f"❌ WRONG! Expected 365, got {count}")

    # Check for any non-D1 teams
    print("\nSample teams (first 5):")
    for team in results[:5]:
        print(f"  {team['rank_adj_em']}. {team['team_name']} - AdjEM: {team['adj_em']:.2f}")

    # Check for any Division II/III indicators in names
    non_d1_indicators = [
        'JWU',
        'Johnson & Wales',
        'NAIA',
        'NCAA D2',
        'NCAA DIII',
        'Adams St',
        'Adrian',
    ]
    found_non_d1 = []
    for team in results:
        for indicator in non_d1_indicators:
            if indicator.lower() in team['team_name'].lower():
                found_non_d1.append(team['team_name'])

    if found_non_d1:
        print("\n⚠️  Found possible non-D1 teams:")
        for name in found_non_d1[:10]:
            print(f"  - {name}")
    else:
        print("\n✅ No obvious non-D1 teams found in results")

else:
    print(f"❌ API request failed: {response.status_code}")
