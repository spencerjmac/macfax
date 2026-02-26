import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Game, TeamGameStats, TeamSeasonMetrics, TeamSeasonRatings, Team
from datetime import date

print('=' * 60)
print('VERIFYING DATA UPDATE')
print('=' * 60)

# Check games
total_games = Game.objects.filter(season_year=2026).count()
games_with_stats = TeamGameStats.objects.filter(game__season_year=2026).count() // 2  # Divide by 2 since each game has 2 teams
final_games = Game.objects.filter(season_year=2026, status='final').count()

first_game = Game.objects.filter(season_year=2026).order_by('game_date').first()
last_game = Game.objects.filter(season_year=2026).order_by('-game_date').first()

print(f'\nGAMES:')
print(f'  Total games in DB: {total_games}')
print(f'  Games with stats: {games_with_stats}')
print(f'  Final games: {final_games}')
print(f'  Date range: {first_game.game_date if first_game else "N/A"} to {last_game.game_date if last_game else "N/A"}')

# Check if we have Feb 22-26 games
recent_games = Game.objects.filter(
    season_year=2026,
    game_date__gte=date(2026, 2, 22),
    game_date__lte=date(2026, 2, 26)
).count()
print(f'  Games Feb 22-26: {recent_games}')

# Check metrics
metrics_count = TeamSeasonMetrics.objects.filter(season__year=2026).count()
print(f'\nTEAM SEASON METRICS:')
print(f'  Total teams with metrics: {metrics_count}')

if metrics_count > 0:
    sample_metrics = TeamSeasonMetrics.objects.filter(season__year=2026).first()
    print(f'  Sample (updated_at): {sample_metrics.updated_at if sample_metrics else "N/A"}')

# Check ratings
ratings_count = TeamSeasonRatings.objects.filter(season__year=2026).count()
print(f'\nTEAM SEASON RATINGS:')
print(f'  Total teams with ratings: {ratings_count}')

if ratings_count > 0:
    sample_rating = TeamSeasonRatings.objects.filter(season__year=2026).first()
    print(f'  Sample (updated_at): {sample_rating.updated_at if sample_rating else "N/A"}')

# Check a specific team (Duke)
print(f'\nSPECIFIC TEAM CHECK (Duke):')
try:
    duke = Team.objects.get(slug='duke')
    duke_games = TeamGameStats.objects.filter(team=duke, game__season_year=2026).count()
    duke_metrics = TeamSeasonMetrics.objects.filter(team=duke, season__year=2026).first()
    duke_ratings = TeamSeasonRatings.objects.filter(team=duke, season__year=2026).first()
    
    print(f'  Games played: {duke_games}')
    if duke_metrics:
        print(f'  Games in metrics: {duke_metrics.games}')
        print(f'  PPG: {duke_metrics.ppg:.1f}')
        print(f'  Metrics updated: {duke_metrics.updated_at}')
    if duke_ratings:
        print(f'  Rank: {duke_ratings.rank_adj_em}')
        print(f'  Adj EM: {duke_ratings.adj_em:.2f}')
        print(f'  Record: {duke_ratings.wins}-{duke_ratings.losses}')
        print(f'  Ratings updated: {duke_ratings.updated_at}')
except Team.DoesNotExist:
    print('  Duke not found')

print('=' * 60)
