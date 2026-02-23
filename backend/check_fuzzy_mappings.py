import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import TeamExternalId
from core.utils.team_mapping import TeamMapper

# Check what external mappings we have for problematic teams
print("="*70)
print("Checking External Team Mappings for Suspicious Matches")
print("="*70)

# Check for Saint Louis mappings
print("\nSaint Louis mapped names:")
saint_louis_mappings = TeamExternalId.objects.filter(team__name='Saint Louis')
for mapping in saint_louis_mappings:
    print(f"  {mapping.external_name} (source: {mapping.source}, confidence: {mapping.confidence:.2f})")

# Check for fuzzy/low confidence matches across all teams
print("\n" + "="*70)
print("All fuzzy matches with confidence < 1.0:")
print("="*70)

fuzzy_matches = TeamExternalId.objects.filter(confidence__lt=1.0).order_by('confidence')
for mapping in fuzzy_matches:
    print(f"{mapping.external_name:30s} -> {mapping.team.name:25s} (confidence: {mapping.confidence:.3f})")

print(f"\nTotal fuzzy matches: {fuzzy_matches.count()}")
