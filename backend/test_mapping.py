#!/usr/bin/env python  
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.utils.team_mapping import TeamMapper
from core.models import Team

# Test the mapper
mapper = TeamMapper(source='ncaa')

# Test with a known team from NCAA API
test_teams = [
    ('UMBC', None),
    ('Duke', None),
    ('Penn St.-York', None),
    ('Kansas', None),
]

print("=== Testing Team Mapper ===\n")

for team_name, team_id in test_teams:
    print(f"Testing '{team_name}'...")
    
    team, confidence, is_override = mapper.find_team(
        external_name=team_name,
        external_id=team_id,
        min_confidence=0.80
    )
    
    if team:
        print(f"  ✓ Matched to: {team.name} (confidence: {confidence:.2f}, override: {is_override})")
        
        # Try to save
        mapping = mapper.map_and_save(
            external_name=team_name,
            external_id=team_name,  # Use name as ID for testing
            min_confidence=0.80,
            dry_run=False
        )
        
        if mapping:
            print(f"  ✓ Mapping saved: {mapping}")
        else:
            print(f"  ✗ Failed to save mapping")
    else:
        print(f"  ✗ No match found (confidence < 0.80)")
    
    print()

# Check results
from core.models import TeamExternalId
count = TeamExternalId.objects.filter(source='ncaa').count()
print(f"\nTotal NCAA mappings after test: {count}")

if count > 0:
    for m in TeamExternalId.objects.filter(source='ncaa')[:5]:
        print(f"  - '{m.external_name}' → {m.team.name} (ID: {m.external_id})")
