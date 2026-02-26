import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Game, TeamGameStats
from datetime import date

print('=' * 60)
print('CHECKING GAMES WITHOUT STATS (Feb 21-26)')
print('=' * 60)

# Get all games from Feb 21-26
games = Game.objects.filter(
    season_year=2026,
    game_date__gte=date(2026, 2, 21),
    game_date__lte=date(2026, 2, 26)
).order_by('game_date', 'source_game_id')

total_games = games.count()
games_with_stats = 0
games_without_stats = 0

by_status = {
    'scheduled': 0,
    'in_progress': 0,
    'final': 0,
    'postponed': 0,
    'canceled': 0,
}

games_without_stats_list = []

for game in games:
    stats_count = TeamGameStats.objects.filter(game=game).count()
    
    if stats_count >= 2:  # Both teams have stats
        games_with_stats += 1
    else:
        games_without_stats += 1
        by_status[game.status] += 1
        games_without_stats_list.append(game)

print(f'\nTotal games Feb 21-26: {total_games}')
print(f'Games WITH stats: {games_with_stats}')
print(f'Games WITHOUT stats: {games_without_stats}')

print(f'\nGames without stats by status:')
print(f'  Scheduled: {by_status["scheduled"]}')
print(f'  In Progress: {by_status["in_progress"]}')
print(f'  Final (missing box score): {by_status["final"]}')
print(f'  Postponed: {by_status["postponed"]}')
print(f'  Canceled: {by_status["canceled"]}')

if by_status['final'] > 0:
    print(f'\n⚠️  ATTENTION: {by_status["final"]} completed games missing box scores!')
    print('These should be re-scraped in 1-2 hours when NCAA posts stats.')

if by_status['scheduled'] > 0:
    print(f'\n✓ {by_status["scheduled"]} scheduled games (haven\'t been played yet)')

# Show some examples
if games_without_stats_list:
    print(f'\nFirst 10 games without stats:')
    for game in games_without_stats_list[:10]:
        score = ''
        if game.home_score is not None and game.away_score is not None:
            score = f' ({game.away_score}-{game.home_score})'
        print(f'  {game.game_date} | {game.status:12} | {game.away_team.name} @ {game.home_team.name}{score}')

print('=' * 60)
