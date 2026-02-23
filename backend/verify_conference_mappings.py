import requests

response = requests.get('http://localhost:8000/api/rankings/', params={'season': 2026})
teams = response.json()['results']

# Test specific teams user mentioned
test_teams = [
    ('Miami (OH)', 'miami-(oh)', 'MAC'),
    ('Oklahoma', 'oklahoma', 'SEC'),
]

print('\nVerifying user-reported teams:')
print('=' * 80)

for name, slug, expected_conf in test_teams:
    team = next((t for t in teams if t['team_slug'] == slug), None)
    if team:
        actual_conf = team.get('conference', 'Ind')
        status = '✓' if actual_conf == expected_conf else '✗'
        print(f"{status} {name:20} → {actual_conf:5} (expected: {expected_conf})")
    else:
        print(f"✗ {name:20} → NOT FOUND IN RANKINGS")

# Check how many IND teams remain
ind_teams = [t for t in teams if t.get('conference') == 'Ind']
print('\n' + '=' * 80)
print(f'\nRemaining IND teams: {len(ind_teams)}')
if ind_teams:
    for team in ind_teams:
        print(f"  - {team['team_name']} ({team['team_slug']})")
        
# Summary by conference
from collections import Counter
conf_counts = Counter(t.get('conference', 'Ind') for t in teams)

print('\n' + '=' * 80)
print('Teams by conference:')
print('=' * 80)
for conf, count in sorted(conf_counts.items()):
    print(f"{conf:6} : {count:3} teams")

print('\n' + '=' * 80)
print(f'Total teams: {len(teams)}')
