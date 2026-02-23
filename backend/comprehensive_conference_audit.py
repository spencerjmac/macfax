"""
Comprehensive Conference Audit for 2025-26 Season
Verifies ALL 365 D1 teams against official conference rosters
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.views import RankingsViewSet
from rest_framework.test import APIRequestFactory

# Official 2025-26 Conference Rosters (365 D1 teams)
OFFICIAL_CONFERENCES_2025_26 = {
    # Big Ten (18 teams)
    'B10': [
        'illinois', 'indiana', 'iowa', 'maryland', 'michigan', 'michigan-state', 'michigan-st',
        'minnesota', 'nebraska', 'northwestern', 'ohio-state', 'ohio-st', 'penn-state', 'penn-st',
        'purdue', 'rutgers', 'ucla', 'usc', 'wisconsin', 'oregon', 'washington'
    ],
    
    # ACC (18 teams)
    'ACC': [
        'boston-college', 'california', 'clemson', 'duke', 'florida-state', 'florida-st',
        'georgia-tech', 'louisville', 'miami', 'miami-fl', 'miami-(fl)', 'north-carolina', 'unc',
        'nc-state', 'notre-dame', 'pitt', 'pittsburgh', 'smu', 'stanford',
        'syracuse', 'virginia', 'virginia-tech', 'wake-forest'
    ],
    
    # Big 12 (17 teams) - includes new members
    'B12': [
        'arizona', 'arizona-state', 'arizona-st', 'baylor', 'byu', 'cincinnati', 'colorado',
        'houston', 'iowa-state', 'iowa-st', 'kansas', 'kansas-state', 'kansas-st',
        'oklahoma-state', 'oklahoma-st', 'tcu', 'texas-tech', 'ucf', 'utah', 'west-virginia'
    ],
    
    # SEC (16 teams) - includes Texas and Oklahoma
    'SEC': [
        'alabama', 'arkansas', 'auburn', 'florida', 'georgia', 'kentucky', 'lsu',
        'mississippi', 'ole-miss', 'mississippi-state', 'mississippi-st', 'missouri',
        'oklahoma', 'south-carolina', 'tennessee', 'texas', 'texas-am', 'texas-a-m', 'texas-a&m',
        'vanderbilt'
    ],
    
    # Big East (11 teams)
    'BE': [
        'butler', 'connecticut', 'uconn', 'creighton', 'depaul', 'georgetown',
        'marquette', 'providence', 'seton-hall', 'st-johns', 'st-john-s', "st-john's",
        'villanova', 'xavier'
    ],
    
    # WCC (12 teams) - includes Oregon St, Washington St, Seattle (new for 2025-26)
    'WCC': [
        'gonzaga', 'loyola-marymount', 'oregon-st', 'oregon-state', 'pacific', 'pepperdine',
        'portland', 'saint-marys', 'saint-mary-s', "saint-mary's", 'st-marys',
        'san-diego', 'san-francisco', 'santa-clara', 'seattle', 'seattle-u',
        'washington-st', 'washington-state'
    ],
    
    # Mountain West (12 teams) - includes Grand Canyon (new for 2025-26)
    'MWC': [
        'air-force', 'boise-state', 'boise-st', 'colorado-state', 'colorado-st',
        'fresno-state', 'fresno-st', 'grand-canyon', 'nevada', 'new-mexico',
        'san-diego-state', 'san-diego-st', 'sdsu', 'san-jose-state', 'san-jose-st',
        'unlv', 'utah-state', 'utah-st', 'wyoming'
    ],
    
    # Atlantic 10 (15 teams) - UMass is NOT in A10 (moved to MAC)
    'A10': [
        'davidson', 'dayton', 'duquesne', 'fordham', 'george-mason',
        'george-washington', 'la-salle', 'loyola-chicago', 'richmond',
        'rhode-island', 'st-bonaventure', 'saint-bonaventure', 'st-josephs', 'saint-josephs', "saint-joseph's",
        'saint-louis', 'st-louis', 'vcu'
    ],
    
    # American (14 teams)
    'Amer': [
        'charlotte', 'east-carolina', 'florida-atlantic', 'memphis', 'north-texas',
        'rice', 'south-florida', 'temple', 'tulane', 'tulsa', 'uab', 'utsa',
        'wichita-state', 'wichita-st'
    ],
    
    # Conference USA (10 teams) - includes Liberty (new for 2025-26)
    'CUSA': [
        'fiu', 'jacksonville-state', 'jacksonville-st', 'kennesaw-state', 'kennesaw-st',
        'liberty', 'louisiana-tech', 'middle-tennessee', 'new-mexico-state', 'new-mexico-st',
        'sam-houston-state', 'sam-houston-st', 'utep', 'western-kentucky'
    ],
    
    # Missouri Valley (12 teams)
    'MVC': [
        'belmont', 'bradley', 'drake', 'evansville', 'illinois-chicago', 'uic',
        'illinois-state', 'illinois-st', 'indiana-state', 'indiana-st',
        'missouri-state', 'missouri-st', 'murray-state', 'murray-st',
        'northern-iowa', 'southern-illinois', 'valparaiso'
    ],
    
    # Big West (11 teams)
    'BW': [
        'cal-poly', 'cal-state-bakersfield', 'cal-st-bakersfield', 'cal-state-fullerton', 'cal-st-fullerton',
        'cal-state-northridge', 'cal-st-northridge', 'csun', 'hawaii', 'long-beach-state', 'long-beach-st',
        'uc-davis', 'uc-irvine', 'uc-riverside', 'uc-san-diego', 'uc-santa-barbara', 'ucsb'
    ],
    
    # Summit League (9 teams)
    'Sum': [
        'denver', 'kansas-city', 'umkc', 'north-dakota', 'north-dakota-state', 'north-dakota-st',
        'nebraska-omaha', 'omaha', 'oral-roberts', 'south-dakota', 'south-dakota-state', 'south-dakota-st',
        'st-thomas'
    ],
    
    # WAC (8 teams)
    'WAC': [
        'abilene-christian', 'cal-baptist', 'california-baptist', 'southern-utah',
        'stephen-f-austin', 'tarleton-state', 'tarleton-st', 'ut-arlington', 'utah-tech',
        'utah-valley'
    ],
    
    # Horizon (11 teams)
    'Horz': [
        'cleveland-state', 'cleveland-st', 'detroit-mercy', 'green-bay',
        'iu-indy', 'iupui', 'milwaukee', 'northern-kentucky', 'oakland',
        'purdue-fort-wayne', 'robert-morris', 'wright-state', 'wright-st',
        'youngstown-state', 'youngstown-st'
    ],
    
    # MAAC (13 teams)
    'MAAC': [
        'canisius', 'fairfield', 'iona', 'manhattan', 'marist',
        'mount-st-marys', 'mount-st-mary-s', "mount-st-mary's", 'niagara', 'quinnipiac',
        'rider', 'sacred-heart', 'siena', 'saint-peters', 'saint-peter-s', "saint-peter's", 'st-peters'
    ],
    
    # MAC (13 teams) - includes UMass (new for 2025-26)
    'MAC': [
        'akron', 'ball-state', 'ball-st', 'bowling-green', 'buffalo',
        'central-michigan', 'eastern-michigan', 'kent-state', 'kent-st',
        'massachusetts', 'umass', 'miami-oh', 'miami-(oh)', 'northern-illinois',
        'ohio', 'toledo', 'western-michigan'
    ],
    
    # NEC (10 teams)
    'NEC': [
        'central-connecticut', 'central-connecticut-st', 'chicago-state', 'chicago-st',
        'fairleigh-dickinson', 'le-moyne', 'liu', 'mercyhurst', 'merrimack',
        'saint-francis', 'stonehill', 'wagner'
    ],
    
    # Big Sky (10 teams)
    'BSky': [
        'eastern-washington', 'idaho', 'idaho-state', 'idaho-st', 'montana',
        'montana-state', 'montana-st', 'northern-arizona', 'northern-colorado',
        'portland-state', 'portland-st', 'sacramento-state', 'sacramento-st',
        'weber-state', 'weber-st'
    ],
    
    # OVC (11 teams)
    'OVC': [
        'eastern-illinois', 'lindenwood', 'little-rock', 'morehead-state', 'morehead-st',
        'siu-edwardsville', 'southeast-missouri-st', 'southern-indiana',
        'tennessee-martin', 'ut-martin', 'tennessee-state', 'tennessee-st',
        'tennessee-tech', 'western-illinois'
    ],
    
    # CAA (14 teams)
    'CAA': [
        'campbell', 'charleston', 'delaware', 'drexel', 'elon',
        'hampton', 'hofstra', 'monmouth', 'north-carolina-at', 'north-carolina-a&t', 'nc-at', 'nc-a&t',
        'northeastern', 'stony-brook', 'towson', 'unc-wilmington',
        'william-mary', 'william-&-mary'
    ],
    
    # Southern (10 teams)
    'SC': [
        'chattanooga', 'citadel', 'the-citadel', 'east-tennessee-state', 'east-tennessee-st', 'etsu',
        'furman', 'mercer', 'samford', 'unc-greensboro', 'vmi', 'western-carolina', 'wofford'
    ],
    
    # Sun Belt (14 teams)
    'SB': [
        'appalachian-state', 'appalachian-st', 'app-state', 'arkansas-state', 'arkansas-st',
        'coastal-carolina', 'georgia-southern', 'georgia-state', 'georgia-st',
        'james-madison', 'louisiana', 'louisiana-monroe', 'ulm', 'marshall',
        'old-dominion', 'south-alabama', 'southern-miss', 'southern-mississippi',
        'texas-state', 'texas-st', 'troy'
    ],
    
    # Southland (11 teams)
    'Slnd': [
        'east-texas-a&m', 'houston-christian', 'incarnate-word', 'lamar',
        'mcneese', 'mcneese-state', 'mcneese-st', 'new-orleans',
        'nicholls', 'nicholls-state', 'nicholls-st', 'northwestern-state', 'northwestern-st',
        'southeastern-louisiana', 'texas-a&m-corpus-chris', 'ut-rio-grande-valley'
    ],
    
    # ASUN (14 teams) - Liberty moved to CUSA
    'ASun': [
        'austin-peay', 'bellarmine', 'central-arkansas', 'eastern-kentucky',
        'florida-gulf-coast', 'fgcu', 'jacksonville', 'lipscomb', 'north-alabama',
        'north-florida', 'queens', 'stetson', 'west-georgia'
    ],
    
    # America East (9 teams)
    'AE': [
        'albany', 'binghamton', 'bryant', 'maine', 'new-hampshire', 'unh',
        'njit', 'umass-lowell', 'umbc', 'vermont'
    ],
    
    # Ivy League (8 teams)
    'Ivy': [
        'brown', 'columbia', 'cornell', 'dartmouth', 'harvard',
        'penn', 'pennsylvania', 'princeton', 'yale'
    ],
    
    # Patriot (10 teams)
    'Pat': [
        'american', 'army', 'boston-university', 'bucknell', 'colgate',
        'holy-cross', 'lafayette', 'lehigh', 'loyola-maryland', 'loyola-md', 'navy'
    ],
    
    # MEAC (8 teams)
    'MEAC': [
        'coppin-state', 'coppin-st', 'delaware-state', 'delaware-st', 'howard',
        'maryland-eastern-shore', 'umes', 'morgan-state', 'morgan-st',
        'norfolk-state', 'norfolk-st', 'north-carolina-central', 'nc-central',
        'south-carolina-state', 'south-carolina-st'
    ],
    
    # SWAC (12 teams)
    'SWAC': [
        'alabama-am', 'alabama-a&m', 'alabama-state', 'alabama-st', 'alcorn-state', 'alcorn-st',
        'arkansas-pine-bluff', 'bethune-cookman', 'florida-am', 'florida-a&m', 'famu',
        'grambling-state', 'grambling-st', 'jackson-state', 'jackson-st',
        'mississippi-valley-state', 'mississippi-valley-st', 'prairie-view-am', 'prairie-view-a&m',
        'southern', 'texas-southern'
    ],
    
    # Big South (9 teams)
    'BSth': [
        'charleston-southern', 'gardner-webb', 'high-point', 'longwood',
        'presbyterian', 'radford', 'unc-asheville', 'usc-upstate', 'winthrop'
    ],
}

def build_reverse_lookup():
    """Build team -> expected conference mapping"""
    team_to_conf = {}
    for conf, teams in OFFICIAL_CONFERENCES_2025_26.items():
        for team_slug in teams:
            team_to_conf[team_slug] = conf
    return team_to_conf

def main():
    print("=" * 100)
    print("COMPREHENSIVE CONFERENCE AUDIT - 2025-26 SEASON (ALL 31 CONFERENCES)")
    print("=" * 100)
    print()
    
    # Build official mapping
    official_mapping = build_reverse_lookup()
    
    # Get current API data
    factory = APIRequestFactory()
    request = factory.get('/api/rankings/?season=2026')
    view = RankingsViewSet.as_view({'get': 'list'})
    response = view(request)
    teams_data = response.data.get('results', [])
    
    print(f"Total teams in API: {len(teams_data)}")
    print()
    
    # Track errors
    wrong_conference = []
    missing_teams = []
    
    # Check each team
    for team in teams_data:
        team_name = team.get('team_name', '')
        team_slug = team.get('team_slug', '').lower()
        current_conf = team.get('conference', '')
        
        # Skip Independent teams not in our official list
        if team_slug == 'new-haven':
            continue
        
        # Check if team is in official mapping
        if team_slug not in official_mapping:
            # Try common variations
            variations = [
                team_slug.replace('-state', '-st'),
                team_slug.replace('-st', '-state'),
                team_slug.replace('umass', 'massachusetts'),
                team_slug.replace('uconn', 'connecticut'),
            ]
            
            found = False
            for var in variations:
                if var in official_mapping:
                    expected_conf = official_mapping[var]
                    found = True
                    break
            
            if not found:
                missing_teams.append({
                    'name': team_name,
                    'slug': team_slug,
                    'current_conf': current_conf
                })
                continue
        else:
            expected_conf = official_mapping[team_slug]
        
        # Compare conferences
        if current_conf != expected_conf:
            wrong_conference.append({
                'name': team_name,
                'slug': team_slug,
                'current': current_conf,
                'expected': expected_conf
            })
    
    # Report findings
    if wrong_conference:
        print(f"\n❌ Found {len(wrong_conference)} teams in WRONG conferences:")
        print("=" * 100)
        for team in sorted(wrong_conference, key=lambda x: x['name']):
            print(f"  • {team['name']:35} (slug: {team['slug']:30}) | "
                  f"Currently: {team['current']:6} → Should be: {team['expected']}")
        print()
    else:
        print("✅ All teams are in the CORRECT conferences!")
        print()
    
    if missing_teams:
        print(f"\n⚠️ Found {len(missing_teams)} teams NOT in official mapping:")
        print("=" * 100)
        for team in sorted(missing_teams, key=lambda x: x['name']):
            print(f"  • {team['name']:35} (slug: {team['slug']:30}) | Current: {team['current']}")
        print()
    
    # Summary
    print("=" * 100)
    print(f"SUMMARY:")
    print(f"  Total teams audited: {len(teams_data)}")
    print(f"  Teams in wrong conferences: {len(wrong_conference)}")
    print(f"  Teams missing from mapping: {len(missing_teams)}")
    print("=" * 100)

if __name__ == '__main__':
    main()
