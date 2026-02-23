import requests

response = requests.get('http://localhost:8000/api/rankings/', params={'season': 2026})
teams = response.json()['results']

ind_teams = [t for t in teams if t.get('conference') == 'Ind']

print(f'\nFound {len(ind_teams)} teams showing as IND:')
print('=' * 80)

for i, team in enumerate(sorted(ind_teams, key=lambda x: x['team_name']), 1):
    print(f"{i:3}. {team['team_name']:35} (slug: {team['team_slug']})")

print('\n' + '=' * 80)
print(f'Total IND teams: {len(ind_teams)}')
