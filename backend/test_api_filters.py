import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.test import RequestFactory
from api.views import RankingsViewSet
from core.models import Conference

# Test conference filters
factory = RequestFactory()

# Test Big West (user reported Hawaii was showing as Ind)
print("\n" + "=" * 80)
print("Testing BW (Big West) Conference Filter:")
print("=" * 80)
request = factory.get('/api/rankings/', {'season': '2026', 'conference': 'BW'})
view = RankingsViewSet.as_view({'get': 'list'})
response = view(request)
if response.status_code == 200:
    teams = response.data if isinstance(response.data, list) else response.data.get('results', [])
    print(f"Found {len(teams)} teams:")
    for team in teams[:10]:  # Show first 10
        print(f"  {team.get('rank', '?'):3}. {team.get('team_name', 'Unknown'):30} → {team.get('conference', '?')}")
else:
    print(f"Error: {response.status_code}")

# Test WAC (user reported Utah Valley was showing as Ind)
print("\n" + "=" * 80)
print("Testing WAC (Western Athletic) Conference Filter:")
print("=" * 80)
request = factory.get('/api/rankings/', {'season': '2026', 'conference': 'WAC'})
response = view(request)
if response.status_code == 200:
    teams = response.data if isinstance(response.data, list) else response.data.get('results', [])
    print(f"Found {len(teams)} teams:")
    for team in teams[:10]:
        print(f"  {team.get('rank', '?'):3}. {team.get('team_name', 'Unknown'):30} → {team.get('conference', '?')}")
else:
    print(f"Error: {response.status_code}")

# Test MVC (Illinois-Chicago should be here)
print("\n" + "=" * 80)
print("Testing MVC (Missouri Valley) Conference Filter:")
print("=" * 80)
request = factory.get('/api/rankings/', {'season': '2026', 'conference': 'MVC'})
response = view(request)
if response.status_code == 200:
    teams = response.data if isinstance(response.data, list) else response.data.get('results', [])
    print(f"Found {len(teams)} teams:")
    for team in teams[:15]:  # Show up to 15
        print(f"  {team.get('rank', '?'):3}. {team.get('team_name', 'Unknown'):30} → {team.get('conference', '?')}")
else:
    print(f"Error: {response.status_code}")

print("\n" + "=" * 80)
