import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ncaa.models import TeamSeasonRatings
from django.db import transaction

print("Syncing tournament seeds from post-tournament to pre-tournament records...")

# Get all post-tournament records that have a seed
full_season_seeded = TeamSeasonRatings.all_objects.filter(
    is_pre_tournament=False, 
    tournament_seed__isnull=False
)

updated = 0
with transaction.atomic():
    for fs_rating in full_season_seeded:
        # Find the corresponding pre-tournament record
        pre_qs = TeamSeasonRatings.all_objects.filter(
            team=fs_rating.team,
            season=fs_rating.season,
            is_pre_tournament=True
        )
        
        rows = pre_qs.update(
            tournament_seed=fs_rating.tournament_seed,
            tournament_region=fs_rating.tournament_region,
            tournament_finish=fs_rating.tournament_finish
        )
        updated += rows

print(f"Successfully synced tournament seeding data to {updated} pre-tournament team records.")
