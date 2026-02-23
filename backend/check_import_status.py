import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Game, TeamGameStats, TeamExternalId

print('=' * 80)
print('GAMELOG IMPORT STATUS')
print('=' * 80)

game_count = Game.objects.filter(season_year=2026).count()
tgs_count = TeamGameStats.objects.filter(game__season_year=2026).count()
ext_id_count = TeamExternalId.objects.count()

print(f'\nGames imported: {game_count}')
print(f'TeamGameStats records: {tgs_count}')
print(f'TeamExternalId mappings: {ext_id_count}')

if game_count > 0:
    print('\n✓ Import has started and is in progress or complete')
    
    # Check if still running by looking at recent games
    recent_games = Game.objects.filter(season_year=2026).order_by('-game_date')[:5]
    print(f'\nMost recent games imported:')
    for game in recent_games:
        print(f'  {game.game_date}: {game.home_team.name} vs {game.away_team.name}')
else:
    print('\n✗ No games imported yet')
