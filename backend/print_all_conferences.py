import requests

response = requests.get('http://localhost:8000/api/rankings/', params={'season': 2026})
teams = response.json()['results']

# Group teams by conference
from collections import defaultdict
by_conference = defaultdict(list)

for team in teams:
    conf = team.get('conference', 'Ind')
    by_conference[conf].append(team['team_name'])

print('\n2025-26 CONFERENCE ROSTERS (Alphabetical by Team)')
print('=' * 80)

for conf in sorted(by_conference.keys()):
    print(f'\n{conf} ({len(by_conference[conf])} teams):')
    print('-' * 80)
    for team in sorted(by_conference[conf]):
        print(f'  {team}')

# Save to file for easy review
with open('conference_rosters_2025_26.txt', 'w') as f:
    f.write('2025-26 NCAA D1 Basketball Conference Rosters\n')
    f.write('=' * 80 + '\n\n')
    
    for conf in sorted(by_conference.keys()):
        f.write(f'\n{conf} ({len(by_conference[conf])} teams):\n')
        f.write('-' * 80 + '\n')
        for team in sorted(by_conference[conf]):
            f.write(f'  {team}\n')

print('\n' + '=' * 80)
print(f'\nTotal: {len(teams)} teams across {len(by_conference)} conferences')
print('Saved detailed roster to: conference_rosters_2025_26.txt')
print('\nPlease review each conference to verify all teams are correctly assigned!')
