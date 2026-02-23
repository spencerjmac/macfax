import os
import sys
import django
import pandas as pd
from collections import defaultdict

# Add parent directory to path to access backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team

# Read Torvik CSV for conference data
torvik_csv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                          'Bart Torvik', 'torvik_tableau.csv')

df = pd.read_csv(torvik_csv)

# Get the most recent data (latest date)
latest_date = df['date'].max()
latest_data = df[df['date'] == latest_date]

# Create team -> conference mapping from Torvik
torvik_conf_map = {}
for _, row in latest_data.iterrows():
    team_name = row['team_name']
    conference = row['conference']
    torvik_conf_map[team_name] = conference

# Get all teams from database
db_teams = Team.objects.all().order_by('name')

# Manual overrides for teams with different names in Torvik
name_overrides = {
    'Miami (FL)': 'Miami FL',
    'Miami (OH)': 'Miami OH',
    'NC State': 'N.C. State',
}

# Group teams by conference
teams_by_conf = defaultdict(list)
teams_no_match = []

for team in db_teams:
    # Check manual overrides first
    search_name = name_overrides.get(team.name, team.name)
    
    # Try to find conference from Torvik data
    if search_name in torvik_conf_map:
        conf = torvik_conf_map[search_name]
        teams_by_conf[conf].append(team.name)
    elif team.name in torvik_conf_map:
        conf = torvik_conf_map[team.name]
        teams_by_conf[conf].append(team.name)
    else:
        # Try fuzzy match on team name
        found = False
        for torvik_name, conf in torvik_conf_map.items():
            if team.name.lower() in torvik_name.lower() or torvik_name.lower() in team.name.lower():
                teams_by_conf[conf].append(team.name)
                found = True
                break
        if not found:
            teams_no_match.append(team.name)

# Conference name mapping for readability
conf_names = {
    'A10': 'Atlantic 10',
    'ACC': 'ACC',
    'AE': 'America East',
    'ASun': 'ASUN',
    'Amer': 'American',
    'B10': 'Big Ten',
    'B12': 'Big 12',
    'BE': 'Big East',
    'BSky': 'Big Sky',
    'BSth': 'Big South',
    'BW': 'Big West',
    'CAA': 'Colonial',
    'CUSA': 'Conference USA',
    'Horz': 'Horizon',
    'Ivy': 'Ivy League',
    'MAAC': 'MAAC',
    'MAC': 'MAC',
    'MEAC': 'MEAC',
    'MVC': 'Missouri Valley',
    'MWC': 'Mountain West',
    'NEC': 'Northeast',
    'OVC': 'Ohio Valley',
    'P12': 'Pac-12',
    'Pat': 'Patriot League',
    'SB': 'Sun Belt',
    'SC': 'Southern',
    'SEC': 'SEC',
    'Slnd': 'Southland',
    'Sum': 'Summit',
    'SWAC': 'SWAC',
    'WAC': 'WAC',
    'WCC': 'West Coast',
}

# Sort conferences
sorted_conferences = sorted(teams_by_conf.keys(), key=lambda x: conf_names.get(x, x))

print("ALL 365 D1 TEAMS IN DATABASE (Sorted by Conference):")
print("=" * 60)
print()

team_number = 1
for conf in sorted_conferences:
    conf_full_name = conf_names.get(conf, conf)
    conf_teams = sorted(teams_by_conf[conf])
    print(f"\n{conf_full_name} ({len(conf_teams)} teams)")
    print("-" * 60)
    for team_name in conf_teams:
        print(f"{team_number:3d}. {team_name}")
        team_number += 1

if teams_no_match:
    print(f"\n\nNo Conference Match ({len(teams_no_match)} teams)")
    print("-" * 60)
    for team_name in sorted(teams_no_match):
        print(f"{team_number:3d}. {team_name}")
        team_number += 1

print()
print("=" * 60)
print(f"Total: {db_teams.count()} teams")
print(f"Conferences: {len(sorted_conferences)}")
