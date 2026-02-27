"""
Create TeamExternalId records for all teams in team_alias_overrides.yml
This ensures fuzzy matching works for existing games
"""
import os
import django
import yaml

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamExternalId

def main():
    # Load overrides
    with open('team_alias_overrides.yml', 'r') as f:
        overrides = yaml.safe_load(f)
    
    ncaa_mappings = overrides.get('ncaa', {})
    
    print(f"Found {len(ncaa_mappings)} NCAA mappings in overrides file")
    print("=" * 60)
    
    created_count = 0
    existing_count = 0
    missing_count = 0
    
    for external_name, canonical_name in ncaa_mappings.items():
        # Find team by canonical name
        try:
            team = Team.objects.get(name=canonical_name)
        except Team.DoesNotExist:
            print(f"⚠ Team not found in DB: {canonical_name}")
            missing_count += 1
            continue
        
        # Check if external ID already exists
        external_id, created = TeamExternalId.objects.get_or_create(
            team=team,
            source='ncaa',
            defaults={'external_id': external_name, 'external_name': external_name}
        )
        
        if created:
            print(f"✓ Created: {external_name} → {canonical_name}")
            created_count += 1
        else:
            existing_count += 1
    
    print("\n" + "=" * 60)
    print(f"Created: {created_count}")
    print(f"Already existed: {existing_count}")
    print(f"Missing from DB: {missing_count}")
    print(f"Total mappings: {len(ncaa_mappings)}")
    
    # Verify coverage
    total_teams = Team.objects.count()
    teams_with_ncaa = TeamExternalId.objects.filter(source='ncaa').count()
    print(f"\nTeam coverage: {teams_with_ncaa}/{total_teams} ({teams_with_ncaa/total_teams*100:.1f}%)")

if __name__ == '__main__':
    main()
