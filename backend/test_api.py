import requests
import json

# Test the API
response = requests.get('http://localhost:8000/api/rankings?sort=aem&dir=desc')
data = response.json()

if data['results']:
    team = data['results'][0]
    print("\n" + "="*60)
    print("TOP TEAM BY NET RATING")
    print("="*60)
    print(f"Team: {team['team_name']}")
    print(f"Conference: {team['conference']}")
    print(f"Record: {team['record']}")
    print("\n--- New Metrics ---")
    print(f"AOR (Adj Offensive Rating): {team['aor']:.2f}")
    print(f"ADR (Adj Defensive Rating): {team['adr']:.2f}")
    print(f"AEM (Net Rating): {team['aem']:.2f}")
    print("\n--- 0-100 Ratings ---")
    print(f"AOR_100: {team['aor_100']:.1f}/100")
    print(f"ADR_100: {team['adr_100']:.1f}/100")
    print(f"NET_100: {team['net_100']:.1f}/100")
    print("\n--- National Rankings ---")
    print(f"Offense Rank: #{team['rank_aor']}")
    print(f"Defense Rank: #{team['rank_adr']}")
    print(f"Net Rank: #{team['rank_aem']}")
    print("="*60)
    print("\n✅ SUCCESS! New metrics are available via API.\n")
else:
    print("❌ No data returned from API")
