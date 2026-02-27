#!/usr/bin/env python
"""
Export Django API data to Next.js static JSON file
Fetches from http://127.0.0.1:8000/api/rankings/ and writes to web/public/data/teams.json
"""
import requests
import json
from datetime import datetime
import os

# API endpoint
API_URL = "http://127.0.0.1:8000/api/rankings/"

# Output path
OUTPUT_PATH = os.path.join("..", "web", "public", "data", "teams.json")

def fetch_rankings(season=2026):
    """Fetch rankings from Django API"""
    print(f"Fetching rankings for season {season}...")
    response = requests.get(API_URL, params={'season': season}, timeout=30)
    response.raise_for_status()
    return response.json()

def transform_to_frontend_format(api_data):
    """Transform API response to frontend JSON format"""
    teams = api_data.get('results', [])
    
    # Transform each team
    frontend_teams = []
    for team in teams:
        # Parse record string "25-1" -> games: 26, record: "25-1"
        record = team.get('record', '0-0')
        wins, losses = record.split('-')
        games = int(wins) + int(losses)
        
        frontend_team = {
            'teamId': team.get('team_slug'),
            'teamName': team.get('team_name'),
            'teamNameAlt': [team.get('team_name')],  # Could expand with aliases
            'conference': team.get('conference', 'Ind'),
            'logoUrl': team.get('team_logo') or '/logos/default.png',
            'season': '2025-26',
            'lastUpdated': datetime.now().strftime('%Y-%m-%d'),
            'games': games,
            'record': record,
            'rank': team.get('rank'),
            
            ## Adjusted ratings
            'adjEM': team.get('adj_em'),
            'adjO': team.get('adj_o'),
            'adjD': team.get('adj_d'),
            'adjTempo': team.get('adj_tempo'),
            
            # Adjusted four factors - offense (convert from % to decimal)
            'eFG': team.get('efg_pct') / 100.0 if team.get('efg_pct') is not None else None,
            'tov': team.get('tov_pct') / 100.0 if team.get('tov_pct') is not None else None,
            'orb': team.get('orb_pct') / 100.0 if team.get('orb_pct') is not None else None,
            'ftr': team.get('ftr') / 100.0 if team.get('ftr') is not None else None,
            
            # Adjusted four factors - defense (convert from % to decimal)
            'eFG_d': team.get('efg_pct_d') / 100.0 if team.get('efg_pct_d') is not None else None,
            'tov_d': team.get('tov_pct_d') / 100.0 if team.get('tov_pct_d') is not None else None,
            'orb_d': team.get('orb_pct_d') / 100.0 if team.get('orb_pct_d') is not None else None,
            'drb': (100.0 - team.get('orb_pct_d', 0)) / 100.0 if team.get('orb_pct_d') is not None else None,  # DRB% = 100 - Opp ORB%
            'ftr_d': team.get('ftr_d') / 100.0 if team.get('ftr_d') is not None else None,
            
            # Adjusted margins (convert from % to decimal)
            'eFG_margin': team.get('efg_margin') / 100.0 if team.get('efg_margin') is not None else None,
            'tov_edge': team.get('tov_edge') / 100.0 if team.get('tov_edge') is not None else None,
            'reb_edge': team.get('reb_edge') / 100.0 if team.get('reb_edge') is not None else None,
            'ftr_margin': team.get('ftr_margin') / 100.0 if team.get('ftr_margin') is not None else None,
            
            # Raw four factors (already in decimal format from DB)
            'raw_eFG': team.get('raw_efg_pct') / 100.0 if team.get('raw_efg_pct') is not None else None,
            'raw_tov': team.get('raw_tov_pct') / 100.0 if team.get('raw_tov_pct') is not None else None,
            'raw_orb': team.get('raw_orb_pct') / 100.0 if team.get('raw_orb_pct') is not None else None,
            'raw_ftr': team.get('raw_ftr') / 100.0 if team.get('raw_ftr') is not None else None,
            'raw_eFG_d': team.get('raw_efg_pct_d') / 100.0 if team.get('raw_efg_pct_d') is not None else None,
            'raw_tov_d': team.get('raw_tov_pct_d') / 100.0 if team.get('raw_tov_pct_d') is not None else None,
            'raw_orb_d': team.get('raw_orb_pct_d') / 100.0 if team.get('raw_orb_pct_d') is not None else None,
            'raw_drb': (100.0 - team.get('raw_orb_pct_d', 0)) / 100.0 if team.get('raw_orb_pct_d') is not None else None,
            'raw_ftr_d': team.get('raw_ftr_d') / 100.0 if team.get('raw_ftr_d') is not None else None,
            'raw_eFG_margin': team.get('raw_efg_margin') / 100.0 if team.get('raw_efg_margin') is not None else None,
            'raw_tov_edge': team.get('raw_tov_edge') / 100.0 if team.get('raw_tov_edge') is not None else None,
            'raw_reb_edge': team.get('raw_reb_edge') / 100.0 if team.get('raw_reb_edge') is not None else None,
            'raw_ftr_margin': team.get('raw_ftr_margin') / 100.0 if team.get('raw_ftr_margin') is not None else None,
            
            # Four Factor Index
            'four_factor_index_100': team.get('four_factor_index_100'),
            'raw_four_factor_index_100': team.get('raw_four_factor_index_100'),
            'rank_four_factor_index_100': team.get('rank_four_factor_index_100'),
            
            # Shooting Splits (convert from percentage to decimal)
            'fg2_pct': team.get('fg2_pct') / 100.0 if team.get('fg2_pct') is not None else None,
            'fg2_pct_d': None,  # Not yet available
            'fg3_pct': team.get('fg3_pct') / 100.0 if team.get('fg3_pct') is not None else None,
            'fg3_pct_d': None,  # Not yet available
            'fg3_rate': team.get('fg3_rate') / 100.0 if team.get('fg3_rate') is not None else None,
            'fg3_rate_d': None,  # Not yet available
            'ft_pct': team.get('ft_pct') / 100.0 if team.get('ft_pct') is not None else None,
            
            # Resume metrics (not available in current API)
            'wab': None,
            'sor': None,
            'barthag': None,
            'luck': None,
            'sos_adjEM': None,
            'ncsos_adjEM': None,
            
            # Source metadata
            'sources': {
                'kenpom': False,
                'torvik': False,
                'cbbAnalytics': False,
            },
        }
        
        frontend_teams.append(frontend_team)
    
    # Create metadata
    metadata = {
        'lastUpdated': datetime.now().isoformat() + 'Z',
        'season': '2025-26',
        'teamCount': len(frontend_teams),
        'sources': {
            'api': 'Django CBB Analytics API',
            'd1_teams': len([t for t in frontend_teams]),
        }
    }
    
    return {
        'metadata': metadata,
        'teams': frontend_teams
    }

def main():
    print("=" * 80)
    print("EXPORT RANKINGS TO NEXT.JS JSON")
    print("=" * 80)
    print()
    
    try:
        # Fetch from API
        api_data = fetch_rankings(season=2026)
        print(f"✓ Fetched {api_data.get('count', 0)} teams from API")
        
        # Transform to frontend format
        frontend_data = transform_to_frontend_format(api_data)
        print(f"✓ Transformed {len(frontend_data['teams'])} teams")
        
        # Write to file
        output_file = OUTPUT_PATH
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(frontend_data, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Wrote to {output_file}")
        print()
        print("=" * 80)
        print("SUCCESS")
        print("=" * 80)
        print(f"Last Updated: {frontend_data['metadata']['lastUpdated']}")
        print(f"Team Count: {frontend_data['metadata']['teamCount']}")
        print()
        print("Next.js will load this data on the next page refresh.")
        print()
        
    except requests.exceptions.ConnectionError:
        print()
        print("ERROR: Could not connect to Django API at http://127.0.0.1:8000/")
        print("Make sure the Django server is running: python manage.py runserver")
        print()
    except Exception as e:
        print()
        print(f"ERROR: {e}")
        print()
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
