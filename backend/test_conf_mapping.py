import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.models import Team

# Test the specific teams mentioned by user
test_teams = ['hawaii', 'illinois-chicago', 'uic', 'utah-valley']

# Simulate what the serializer does
conf_map = {
    # Big West (BW)
    'hawaii': 'BW', 'uc-irvine': 'BW', 'uc-davis': 'BW', 'uc-santa-barbara': 'BW', 'ucsb': 'BW',
    # Missouri Valley (MVC) - UIC is here
    'uic': 'MVC', 'illinois-chicago': 'MVC',
    # WAC - Western Athletic Conference
    'utah-valley': 'WAC',
}

print("\nTesting conference mappings for user-reported teams:")
print("=" * 60)
for team_slug in test_teams:
    conf = conf_map.get(team_slug, 'Ind')
    print(f"{team_slug:20} → {conf}")

print("\nChecking if these teams exist in database:")
print("=" * 60)
for team_slug in test_teams:
    try:
        team = Team.objects.get(slug=team_slug)
        print(f"✓ Found: {team.name} (slug: {team.slug})")
    except Team.DoesNotExist:
        print(f"✗ Not found: {team_slug}")
