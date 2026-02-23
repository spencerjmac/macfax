import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import TeamSeasonMetrics, TeamSeasonRatings, Game

print("All Games by season:")
for season in Game.objects.values_list('season_year', flat=True).distinct().order_by('season_year'):
    count = Game.objects.filter(season_year=season).count()
    print(f"  Season {season}: {count} games")

print("\nAll TeamSeasonMetrics by season:")
seasons = TeamSeasonMetrics.objects.values_list('season', flat=True).distinct().order_by('season')
if seasons:
    for season in seasons:
        count = TeamSeasonMetrics.objects.filter(season=season).count()
        print(f"  Season {season}: {count} teams")
else:
    print("  (No records found)")

print("\nAll TeamSeasonRatings by season:")
seasons = TeamSeasonRatings.objects.values_list('season', flat=True).distinct().order_by('season')
if seasons:
    for season in seasons:
        count = TeamSeasonRatings.objects.filter(season=season).count()
        print(f"  Season {season}: {count} teams")
else:
    print("  (No records found)")
    
print(f"\nTotal TeamSeasonMetrics: {TeamSeasonMetrics.objects.count()}")
print(f"Total TeamSeasonRatings: {TeamSeasonRatings.objects.count()}")
