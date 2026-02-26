import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Season, TeamSeasonStats

season = Season.objects.get(year=2026)
michigan = Team.objects.get(slug='michigan')

try:
    stats = TeamSeasonStats.objects.get(team=michigan, season=season)
    print(f'Michigan stats exist:')
    print(f'  fg3_rate={stats.fg3_rate}')
    print(f'  fg3_pct={stats.fg3_pct}')
    print(f'  fg2_pct={stats.fg2_pct}')
except TeamSeasonStats.DoesNotExist:
    print('Michigan has NO TeamSeasonStats record')
