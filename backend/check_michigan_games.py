import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game

michigan = Team.objects.get(name='Michigan')
home = Game.objects.filter(home_team=michigan, season_year=2026).count()
away = Game.objects.filter(away_team=michigan, season_year=2026).count()
latest = Game.objects.filter(season_year=2026).order_by('-game_date').first()

print(f'Michigan: {home + away} games ({home} home, {away} away)')
print(f'Latest game date in DB: {latest.game_date if latest else "None"}')
