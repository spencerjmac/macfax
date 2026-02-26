#!/usr/bin/env python
"""Check if we have kill shot data in the database."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import TeamSeasonMetrics, Season

season = Season.objects.filter(year=2026).first()
print(f"Checking kill shot data for {season.year}")
print("=" * 60)

# Check if any teams have kill shot data
total_teams = TeamSeasonMetrics.objects.filter(season=season).count()
teams_with_kills = TeamSeasonMetrics.objects.filter(
    season=season,
    kill_shots_for__gt=0
).count()

print(f"\nTotal teams: {total_teams}")
print(f"Teams with kill shot data (>0): {teams_with_kills}")

# Sample a few teams
sample_teams = TeamSeasonMetrics.objects.filter(season=season).order_by('?')[:5]
print(f"\nSample teams:")
for metrics in sample_teams:
    print(f"  {metrics.team.name:30} | Kill shots: {metrics.kill_shots_for:3} | Per game: {metrics.kill_shots_pg:.2f}")

print("\n" + "=" * 60)
if teams_with_kills == 0:
    print("❌ NO KILL SHOT DATA FOUND")
    print("\nKill shots are NOT currently calculated from game logs.")
    print("The fields exist in TeamSeasonMetrics but are set to 0.")
    print("\nTo calculate kill shots, we would need:")
    print("  1. Play-by-play data (not currently scraped)")
    print("  2. Or a definition/formula to estimate from box score stats")
else:
    print("✅ Kill shot data IS available!")
