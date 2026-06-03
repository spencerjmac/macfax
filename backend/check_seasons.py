import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from ncaa.models.base import Season
from ncaa.models.players import PlayerSeasonStats
from nba.models import NBASeason, NBAPlayerSeasonStats

print("NCAA PlayerSeasonStats Seasons:")
ncaa_seasons = PlayerSeasonStats.objects.values_list('season__year', flat=True).distinct().order_by('season__year')
print(list(ncaa_seasons))

print("\nNBA NBAPlayerSeasonStats Seasons:")
nba_seasons = NBAPlayerSeasonStats.objects.values_list('season__year', flat=True).distinct().order_by('season__year')
print(list(nba_seasons))
