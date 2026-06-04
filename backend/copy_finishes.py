import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ncaa.models import TeamSeasonRatings
qs = TeamSeasonRatings.all_objects.filter(is_pre_tournament=False).exclude(tournament_finish__isnull=True)
count = 0
for r in qs:
    try:
        pre = TeamSeasonRatings.all_objects.get(team=r.team, season=r.season, is_pre_tournament=True)
        pre.tournament_finish = r.tournament_finish
        pre.tournament_seed = r.tournament_seed
        pre.save(update_fields=['tournament_finish', 'tournament_seed'])
        count += 1
    except TeamSeasonRatings.DoesNotExist:
        pass
print('Copied', count, 'finishes')
