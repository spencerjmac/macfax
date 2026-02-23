import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team

# Search for St. John's variations
print("Searching for St. John's variations:")
print("-" * 60)

teams = Team.objects.filter(name__icontains='john')
for team in teams:
    print(f"{team.id}: {team.name}")

print("\n" + "=" * 60)
print("Searching for variations with 'St':")
print("-" * 60)

teams = Team.objects.filter(name__icontains='st').filter(name__icontains='john')
for team in teams:
    print(f"{team.id}: {team.name}")
