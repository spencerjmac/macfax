import requests

response = requests.get('http://localhost:8000/api/rankings/', params={'season': 2026})
teams = response.json()['results']

# Let me show you what I need: List some teams from each conference so you can spot check
from collections import defaultdict
by_conf = defaultdict(list)

for team in teams:
    conf = team.get('conference', 'Ind')
    by_conf[conf].append(team['team_name'])

print('\nQUICK CONFERENCE SAMPLES (first 5 teams from each):')
print('=' * 80)

for conf in sorted(by_conf.keys()):
    sample = sorted(by_conf[conf])[:5]
    print(f'\n{conf} ({len(by_conf[conf])} total):')
    for team in sample:
        print(f'  • {team}')
    if len(by_conf[conf]) > 5:
        print(f'  ... and {len(by_conf[conf]) - 5} more')

print('\n' + '=' * 80)
print('\nPlease identify ANY teams you see in the wrong conference!')
print('For example: "Team X should be in Conference Y, not Z"')
