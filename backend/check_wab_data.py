import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import TeamSeasonStats, TeamSeasonRatings

# Check TeamSeasonStats
stats_count = TeamSeasonStats.objects.filter(season__year=2026).count()
print(f"TeamSeasonStats records for 2026: {stats_count}")

# Check TeamSeasonRatings
ratings_count = TeamSeasonRatings.objects.filter(season__year=2026).count()
print(f"TeamSeasonRatings records for 2026: {ratings_count}")

# Check if Michigan exists in either
michigan_stats = TeamSeasonStats.objects.filter(team__slug='michigan', season__year=2026).first()
michigan_ratings = TeamSeasonRatings.objects.filter(team__slug='michigan', season__year=2026).first()

print(f"\nMichigan in TeamSeasonStats: {michigan_stats is not None}")
if michigan_stats:
    print(f"  WAB: {michigan_stats.wab}")

print(f"Michigan in TeamSeasonRatings: {michigan_ratings is not None}")
if michigan_ratings:
    print(f"  WAB: {michigan_ratings.wab}")

# Show some example teams from each table
print(f"\nSample teams in TeamSeasonStats:")
for team in TeamSeasonStats.objects.filter(season__year=2026).select_related('team')[:5]:
    print(f"  - {team.team.name} (WAB: {team.wab})")

print(f"\nSample teams in TeamSeasonRatings with WAB:")
for team in TeamSeasonRatings.objects.filter(season__year=2026, wab__isnull=False).select_related('team')[:5]:
    print(f"  - {team.team.name} (WAB: {team.wab:.2f})")
