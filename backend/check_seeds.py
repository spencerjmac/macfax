import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from ncaa.models import TeamSeasonRatings
qs = TeamSeasonRatings.all_objects.filter(season__year=2026, is_pre_tournament=True, tournament_seed__isnull=False)
print(f'2026 pre-tournament teams with seed: {qs.count()}')
for t in qs:
    print(t.team.name, t.tournament_seed, t.tournament_finish)

qs_full = TeamSeasonRatings.all_objects.filter(season__year=2026, is_pre_tournament=False, tournament_seed__isnull=False)
print(f'2026 full-season teams with seed: {qs_full.count()}')
