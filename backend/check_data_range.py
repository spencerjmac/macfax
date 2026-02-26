import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Game
from django.db.models import Count
from django.db.models.functions import TruncMonth

games = Game.objects.filter(season_year=2026).order_by('game_date')
first = games.first()
last = games.last()
total = games.count()

print('=' * 60)
print('CURRENT DATABASE STATUS')
print('=' * 60)
print(f'Total games: {total}')
print(f'First game date: {first.game_date if first else "None"}')
print(f'Last game date: {last.game_date if last else "None"}')

if total > 0:
    print(f'\nGames by month:')
    monthly = (Game.objects.filter(season_year=2026)
               .annotate(month=TruncMonth('game_date'))
               .values('month')
               .annotate(count=Count('id'))
               .order_by('month'))
    
    for m in monthly:
        print(f"  {m['month'].strftime('%B %Y')}: {m['count']} games")
    
    # Check recent dates
    print(f'\nLast 10 game dates:')
    recent = Game.objects.filter(season_year=2026).order_by('-game_date')[:10]
    for g in recent:
        print(f"  {g.game_date} - {g.away_team.name} @ {g.home_team.name}")
        
print('=' * 60)
