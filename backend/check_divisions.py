#!/usr/bin/env python
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamSeasonRatings

print("\n=== TEAM DIVISION CHECK ===\n")

# Total teams
total = Team.objects.count()
print(f"Total teams in database: {total}")

# Check if division field exists
sample_team = Team.objects.first()
has_division = hasattr(sample_team, 'division')
print(f"Has division field: {has_division}")

if has_division:
    d1_count = Team.objects.filter(division='I').count()
    d2_count = Team.objects.filter(division='II').count()
    d3_count = Team.objects.filter(division='III').count()
    no_div = Team.objects.filter(division__isnull=True).count()
    
    print(f"\nDivision I teams: {d1_count}")
    print(f"Division II teams: {d2_count}")
    print(f"Division III teams: {d3_count}")
    print(f"No division: {no_div}")
    
    print("\nSample Division II/III teams:")
    for t in Team.objects.exclude(division='I')[:10]:
        print(f"  - {t.name} ({t.division})")

# Teams with ratings
ratings_count = TeamSeasonRatings.objects.filter(season__year=2026).count()
print(f"\nTeams with 2025-26 ratings: {ratings_count}")

# Check what API returns
print("\n=== Sample teams from database ===")
for t in Team.objects.all()[:5]:
    division = getattr(t, 'division', 'N/A')
    print(f"{t.name} - Division: {division}")
