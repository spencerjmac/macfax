import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamExternalId

print("MICHIGAN-RELATED TEAMS IN DATABASE:")
print("=" * 60)

michigan_teams = Team.objects.filter(name__icontains='michigan')
for team in michigan_teams:
    print(f"\n{team.name}:")
    external_ids = TeamExternalId.objects.filter(team=team)
    print(f"  External IDs: {external_ids.count()}")
    for ext_id in external_ids:
        print(f"    - {ext_id.source}: '{ext_id.external_name}'")

print("\n\nBOSTON-RELATED TEAMS IN DATABASE:")
print("=" * 60)

boston_teams = Team.objects.filter(name__icontains='boston')
for team in boston_teams:
    print(f"\n{team.name}:")
    external_ids = TeamExternalId.objects.filter(team=team)
    print(f"  External IDs: {external_ids.count()}")
    for ext_id in external_ids:
        print(f"    - {ext_id.source}: '{ext_id.external_name}'")

print("\n\n" + "=" * 60)
print("SUMMARY:")
print("=" * 60)
print(f"Total D1 Teams: {Team.objects.count()}")
print(f"Teams with external IDs: {Team.objects.filter(external_ids__isnull=False).distinct().count()}")
print(f"Total external ID mappings: {TeamExternalId.objects.count()}")
