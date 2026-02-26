import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamGameStats, TeamSeasonRatings
from datetime import date

# Check Michigan
michigan = Team.objects.get(slug='michigan')

print('=' * 60)
print('MICHIGAN DATA INVESTIGATION')
print('=' * 60)

# Get all Michigan games
all_games = TeamGameStats.objects.filter(
    team=michigan,
    game__season_year=2026,
    game__status='final'
).select_related('game', 'opponent').order_by('game__game_date')

print(f'\nTotal final games in database: {all_games.count()}')

# Count wins/losses manually
wins = 0
losses = 0

print('\nGames by date:')
for i, game_stat in enumerate(all_games, 1):
    # Get opponent's stats
    opp_stat = TeamGameStats.objects.filter(
        game=game_stat.game,
        team=game_stat.opponent
    ).first()
    
    if opp_stat:
        michigan_pts = game_stat.pts
        opp_pts = opp_stat.pts
        result = 'W' if michigan_pts > opp_pts else 'L'
        
        if michigan_pts > opp_pts:
            wins += 1
        else:
            losses += 1
            
        print(f'  {i}. {game_stat.game.game_date} - vs {game_stat.opponent.name:25} {michigan_pts}-{opp_pts} ({result})')

print(f'\nManual count: {wins}-{losses} ({wins + losses} games)')

# Check what TeamSeasonRatings says
ratings = TeamSeasonRatings.objects.get(team=michigan, season__year=2026)
print(f'\nTeamSeasonRatings says:')
print(f'  Record: {ratings.wins}-{ratings.losses}')
print(f'  Games: {ratings.games_played}')
print(f'  D1 Games: {ratings.d1_games_played}')

print('\n' + '=' * 60)
print('CHECKING OTHER TOP TEAMS')
print('=' * 60)

for team_slug in ['duke', 'arizona']:
    team = Team.objects.get(slug=team_slug)
    games_count = TeamGameStats.objects.filter(
        team=team,
        game__season_year=2026,
        game__status='final'
    ).count()
    
    ratings = TeamSeasonRatings.objects.get(team=team, season__year=2026)
    print(f'\n{team.name}:')
    print(f'  Games in DB: {games_count}')
    print(f'  Record in ratings: {ratings.wins}-{ratings.losses}')
    print(f'  Games in ratings: {ratings.games_played}')

print('=' * 60)
