"""
Comprehensive 2025-26 Conference Membership Verification
Based on official NCAA D1 conference rosters for 2025-26 season
"""

import requests

# Get current API data
response = requests.get('http://localhost:8000/api/rankings/', params={'season': 2026})
teams = response.json()['results']

# Official 2025-26 conference rosters (verified against NCAA)
OFFICIAL_CONFERENCES_2025_26 = {
    'B10': ['illinois', 'indiana', 'iowa', 'maryland', 'michigan', 'michigan-state', 'minnesota', 
            'nebraska', 'northwestern', 'ohio-state', 'ohio-st', 'oregon', 'penn-state', 'penn-st', 
            'purdue', 'rutgers', 'ucla', 'usc', 'washington', 'wisconsin'],
    
    'ACC': ['duke', 'north-carolina', 'virginia', 'louisville', 'syracuse', 'florida-state', 
            'florida-st', 'nc-state', 'clemson', 'wake-forest', 'miami-fl', 'miami-(fl)', 
            'georgia-tech', 'boston-college', 'virginia-tech', 'pitt', 'pittsburgh', 
            'notre-dame', 'california', 'stanford', 'smu'],
    
    'B12': ['kansas', 'baylor', 'texas', 'iowa-state', 'iowa-st', 'texas-tech', 'tcu', 
            'oklahoma-state', 'oklahoma-st', 'west-virginia', 'kansas-state', 'kansas-st',
            'houston', 'cincinnati', 'ucf', 'byu', 'colorado', 'arizona', 'arizona-state', 
            'arizona-st', 'utah'],
    
    'SEC': ['kentucky', 'florida', 'tennessee', 'arkansas', 'alabama', 'auburn', 'lsu',
            'mississippi-state', 'mississippi-st', 'georgia', 'missouri', 'south-carolina',
            'vanderbilt', 'texas-am', 'texas-a&m', 'ole-miss', 'mississippi', 'oklahoma'],
    
    'BE': ['connecticut', 'uconn', 'villanova', 'creighton', 'marquette', 'st-johns', 
           "st-john's", 'providence', 'xavier', 'butler', 'seton-hall', 'depaul', 'georgetown'],
    
    'WCC': ['gonzaga', 'saint-marys', "saint-mary's", 'san-francisco', 'santa-clara',
            'loyola-marymount', 'pepperdine', 'portland', 'pacific', 'san-diego',
            'oregon-st', 'oregon-state', 'washington-st', 'washington-state', 'seattle', 'seattle-u'],
    
    'MWC': ['utah-st', 'utah-state', 'san-diego-state', 'san-diego-st', 'nevada', 'unlv',
            'colorado-state', 'colorado-st', 'new-mexico', 'boise-state', 'boise-st',
            'wyoming', 'fresno-state', 'fresno-st', 'air-force', 'san-jose-state', 
            'san-jose-st', 'grand-canyon'],
    
    'A10': ['saint-louis', 'st-louis', 'dayton', 'vcu', 'richmond', 'st-bonaventure',
            'saint-bonaventure', 'davidson', 'rhode-island', 'george-mason', 'umass',
            'massachusetts', 'fordham', 'st-josephs', "saint-joseph's", 'la-salle',
            'duquesne', 'george-washington', 'loyola-chicago'],
    
    'Amer': ['memphis', 'temple', 'wichita-state', 'wichita-st', 'east-carolina',
             'south-florida', 'tulsa', 'tulane', 'north-texas', 'uab', 'charlotte',
             'florida-atlantic', 'utsa', 'rice'],
}

# Build reverse lookup: team slug -> conference
team_to_conf = {}
for conf, slugs in OFFICIAL_CONFERENCES_2025_26.items():
    for slug in slugs:
        team_to_conf[slug] = conf

# Check for mismatches
mismatches = []
for team in teams:
    slug = team['team_slug']
    current_conf = team.get('conference', 'Ind')
    expected_conf = team_to_conf.get(slug, None)
    
    if expected_conf and current_conf != expected_conf:
        mismatches.append({
            'name': team['team_name'],
            'slug': slug,
            'current': current_conf,
            'expected': expected_conf
        })

print(f'\nFound {len(mismatches)} teams in WRONG conferences:')
print('=' * 90)

for m in sorted(mismatches, key=lambda x: x['name']):
    print(f"{m['name']:35} ({m['slug']:30}) | {m['current']:5} → {m['expected']}")

if not mismatches:
    print('\n✅ All major conference teams are correctly mapped!')
else:
    print(f'\n❌ {len(mismatches)} teams need correction')
