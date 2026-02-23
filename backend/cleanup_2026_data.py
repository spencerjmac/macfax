import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import (
    TeamExternalId, Game, TeamGameStats, 
    TeamSeasonMetrics, TeamSeasonRatings
)

print("Deleting all 2026 season data...")
print("=" * 60)

# Delete external ID mappings (will be recreated during import)
ext_ids_deleted = TeamExternalId.objects.all().delete()[0]
print(f"Deleted {ext_ids_deleted} TeamExternalId mappings")

# Delete games and related data
games_deleted = Game.objects.filter(season_year=2026).delete()[0]
print(f"Deleted {games_deleted} total records (games, stats, etc.)")

# Delete metrics and ratings
metrics_deleted = TeamSeasonMetrics.objects.filter(season__year=2026).delete()[0]
print(f"Deleted {metrics_deleted} TeamSeasonMetrics records")

ratings_deleted = TeamSeasonRatings.objects.filter(season__year=2026).delete()[0]
print(f"Deleted {ratings_deleted} TeamSeasonRatings records")

print("\n" + "=" * 60)
print("Cleanup complete! Ready to re-import.")
print("=" * 60)
