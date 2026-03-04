"""
Management command to compute prediction sigma (standard deviation of errors)

Uses historical game results vs expected margins to calibrate win probability
"""
from django.core.management.base import BaseCommand
from core.models import TeamGameStats, NationalAverages, Season, TeamSeasonRatings
import statistics


class Command(BaseCommand):
    help = 'Compute prediction sigma from historical game residuals and store in NationalAverages'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            default=2026,
            help='Season year (default: 2026)'
        )

    def handle(self, *args, **options):
        season_year = options['season']
        
        self.stdout.write(f'\n{"="*80}')
        self.stdout.write(f'COMPUTING PREDICTION SIGMA (Error Standard Deviation)')
        self.stdout.write(f'{"="*80}\n')
        
        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Season {season_year} not found!'))
            return
        
        self.stdout.write(f'Season: {season.display_name}')
        
        # Get or create national averages
        nat_avg, created = NationalAverages.objects.get_or_create(season=season)
        if nat_avg.avg_ortg is None:
            self.stdout.write(self.style.ERROR('National averages not computed yet!'))
            return
        
        if nat_avg.hca_points is None:
            self.stdout.write(self.style.WARNING('HCA not computed yet. Run compute_hca first.'))
            self.stdout.write(self.style.WARNING('Using default HCA of 3.5 points for calculations.'))
            hca = 3.5
        else:
            hca = nat_avg.hca_points
            self.stdout.write(f'Using HCA: {hca:.2f} points')
        
        # Get all games with team stats
        all_games = TeamGameStats.objects.filter(
            game__season_year=season_year
        ).select_related('team', 'opponent', 'game')
        
        total_games = all_games.count()
        self.stdout.write(f'Total team-game records: {total_games}')
        
        if total_games == 0:
            self.stdout.write(self.style.ERROR('No games found!'))
            return
        
        # Calculate residuals (actual margin - predicted margin)
        residuals = []
        games_processed = 0
        
        # Create a dict of team stats for faster lookup
        team_stats_cache = {}
        for ts in TeamSeasonRatings.objects.filter(season=season, team__is_d1=True).select_related('team'):
            team_stats_cache[ts.team.id] = ts
        
        self.stdout.write(f'Team stats cached: {len(team_stats_cache)} teams')
        
        for game_stat in all_games:
            # Get team stats from cache
            team_stats = team_stats_cache.get(game_stat.team.id)
            opp_stats = team_stats_cache.get(game_stat.opponent.id)
            
            if not team_stats or not opp_stats:
                continue
            
            # Get opponent stats from same game
            opp_game_stat = game_stat.game.team_stats.exclude(team=game_stat.team).first()
            if not opp_game_stat:
                continue
            
            games_processed += 1
            
            # Actual margin
            actual_margin = game_stat.pts - opp_game_stat.pts
            
            # Predicted margin (neutral court expectation)
            neutral_predicted = team_stats.adj_em - opp_stats.adj_em
            
            # Apply HCA adjustment
            if game_stat.home_away == 'H':
                predicted_margin = neutral_predicted + hca
            elif game_stat.home_away == 'A':
                predicted_margin = neutral_predicted - hca
            else:  # Neutral
                predicted_margin = neutral_predicted
            
            # Residual = actual - predicted
            residual = actual_margin - predicted_margin
            residuals.append(residual)
        
        if not residuals:
            self.stdout.write(self.style.ERROR('No residuals computed (missing team stats)!'))
            return
        
        # Compute sigma
        sigma = statistics.stdev(residuals) if len(residuals) > 1 else 11.0
        mean_error = statistics.mean(residuals)
        median_error = statistics.median(residuals)
        
        # Store in database
        nat_avg.prediction_sigma = sigma
        nat_avg.save()
        
        self.stdout.write(f'\n{"-"*80}')
        self.stdout.write('RESIDUAL STATISTICS')
        self.stdout.write(f'{"-"*80}')
        self.stdout.write(f'  Games analyzed: {games_processed}')
        self.stdout.write(f'  Mean error: {mean_error:.2f} points')
        self.stdout.write(f'  Median error: {median_error:.2f} points')
        self.stdout.write(self.style.SUCCESS(f'  Sigma (std dev): {sigma:.2f} points'))
        
        # Distribution insights
        self.stdout.write(f'\n{"-"*80}')
        self.stdout.write('PREDICTION INTERVALS (assuming normal distribution)')
        self.stdout.write(f'{"-"*80}')
        self.stdout.write(f'  68% of games within ±{sigma:.1f} points of prediction')
        self.stdout.write(f'  95% of games within ±{2*sigma:.1f} points of prediction')
        self.stdout.write(f'  99% of games within ±{3*sigma:.1f} points of prediction')
        
        self.stdout.write(f'\n{"="*80}')
        self.stdout.write(self.style.SUCCESS(f'✓ Sigma stored: {sigma:.2f} points'))
        self.stdout.write(f'{"="*80}\n')
