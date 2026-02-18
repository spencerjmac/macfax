"""
Update team logo URLs in the database

This script maps team names to logo files using fuzzy matching
"""
import os
import sys
import django
from pathlib import Path

# Setup Django
sys.path.insert(0, r'C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team

# Path to logos
LOGOS_DIR = Path(r'C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard\frontend\public\logos')

# Get all logo files (without extension)
logo_files = {f.stem: f.name for f in LOGOS_DIR.glob('*.png')}

print(f"Found {len(logo_files)} logo files")

def find_logo_for_team(team_name):
    """Find a logo file that matches the team name"""
    # Normalize team name for comparison
    normalized = team_name.lower().replace('.', '').replace(' ', '_').replace('&', '').replace('-', '_')
    
    # Try exact match first
    for logo_stem, logo_file in logo_files.items():
        if logo_stem.lower() == normalized:
            return logo_file
    
    # Try partial match - logo starts with team name
    for logo_stem, logo_file in logo_files.items():
        if logo_stem.lower().startswith(normalized):
            return logo_file
    
    # Try removing common suffixes from team name
    for suffix in [' st', ' state', ' university', ' a&m']:
        if suffix in team_name.lower():
            short_name = team_name.lower().replace(suffix, '').replace(' ', '_').replace('.', '')
            for logo_stem, logo_file in logo_files.items():
                if logo_stem.lower().startswith(short_name):
                    return logo_file
    
    # Try word-by-word match
    team_words = [w for w in normalized.split('_') if len(w) > 2]
    best_match = None
    best_score = 0
    
    for logo_stem, logo_file in logo_files.items():
        logo_words = set(logo_stem.lower().split('_'))
        matches = sum(1 for word in team_words if word in logo_words)
        if matches > best_score and matches >= len(team_words) * 0.5:
            best_score = matches
            best_match = logo_file
    
    return best_match

# Update teams
updated = 0
not_found = []

for team in Team.objects.all():
    logo_filename = find_logo_for_team(team.name)
    
    if logo_filename:
        team.logo_url = f'/logos/{logo_filename}'
        team.save(update_fields=['logo_url'])
        updated += 1
        print(f"[OK] {team.name} -> {logo_filename}")
    else:
        not_found.append(team.name)
        print(f"[NO] {team.name} -> NO MATCH")

print(f"\n{'='*60}")
print(f"Updated: {updated} teams")
print(f"Not found: {len(not_found)} teams")

if not_found:
    print("\nTeams without logos:")
    for name in not_found[:20]:
        print(f"  - {name}")
    if len(not_found) > 20:
        print(f"  ... and {len(not_found) - 20} more")

