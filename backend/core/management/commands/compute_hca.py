"""
Management command to compute Home Court Advantage (HCA) from game logs

Estimates HCA by comparing actual home margins vs neutral expected margins
"""
from django.core.management.base import BaseCommand
from django.db.models import Avg, Count, F, Q
from core.models import TeamGameStats, NationalAverages, Season, TeamSeasonRatings
import statistics


class Command(BaseCommand):
    help = 'Compute Home Court Advantage from game logs and store in NationalAverages'

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
        self.stdout.write(f'COMPUTING HOME COURT ADVANTAGE (HCA)')
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
            self.stdout.write(self.style.ERROR('National averages not computed yet! Run compute_national_averages first.'))
            return
        
        # Get all home games with valid team stats
        home_games = TeamGameStats.objects.filter(
            game__season_year=season_year,
            home_away='H'
        ).select_related('team', 'opponent', 'game').prefetch_related('team__season_stats', 'opponent__season_stats')
        
        total_games = home_games.count()
        self.stdout.write(f'Total home games: {total_games}')
        
        if total_games == 0:
            self.stdout.write(self.style.ERROR('No home games found!'))
            return
        
        # Calculate HCA using multiple methods
        self.stdout.write(f'\n{"-"*80}')
        self.stdout.write('Method 1: Simple home margin average')
        self.stdout.write(f'{"-"*80}')
        
        home_margins = []
        for game_stat in home_games:
            # Get opponent stats from same game
            opp_stat = game_stat.game.team_stats.exclude(team=game_stat.team).first()
            if opp_stat:
                margin = game_stat.pts - opp_stat.pts
                home_margins.append(margin)
        
        if home_margins:
            simple_hca = statistics.mean(home_margins)
            self.stdout.write(f'  Average home margin: {simple_hca:.2f} points')
            self.stdout.write(f'  Median home margin: {statistics.median(home_margins):.2f} points')
            self.stdout.write(f'  Std dev: {statistics.stdev(home_margins) if len(home_margins) > 1 else 0:.2f} points')
        
        # Method 2: Adjusted for team strength (better estimate)
        self.stdout.write(f'\n{"-"*80}')
        self.stdout.write('Method 2: Strength-adjusted HCA')
        self.stdout.write(f'{"-"*80}')
        
        # Create team stats cache for faster lookup
        team_stats_cache = {}
        for ts in TeamSeasonRatings.objects.filter(season=season, team__is_d1=True).select_related('team'):
            team_stats_cache[ts.team.id] = ts
        
        self.stdout.write(f'  Team stats available: {len(team_stats_cache)} teams')
        
        adjusted_hca_values = []
        games_with_stats = 0
        
        for game_stat in home_games:
            # Get team season stats from cache
            home_team_stats = team_stats_cache.get(game_stat.team.id)
            away_team_stats = team_stats_cache.get(game_stat.opponent.id)
            
            if not home_team_stats or not away_team_stats:
                continue
            
            # Get opponent stats from same game
            opp_stat = game_stat.game.team_stats.exclude(team=game_stat.team).first()
            if not opp_stat:
                continue
            
            games_with_stats += 1
            
            # Actual margin
            actual_margin = game_stat.pts - opp_stat.pts
            
            # Expected margin on neutral court (using adjusted efficiency margin)
            neutral_expected = home_team_stats.adj_em - away_team_stats.adj_em
            
            # HCA contribution = actual - neutral_expected
            hca_contribution = actual_margin - neutral_expected
            adjusted_hca_values.append(hca_contribution)
        
        if adjusted_hca_values:
            adjusted_hca = statistics.mean(adjusted_hca_values)
            median_hca = statistics.median(adjusted_hca_values)
            std_hca = statistics.stdev(adjusted_hca_values) if len(adjusted_hca_values) > 1 else 0
            
            self.stdout.write(f'  Games with team stats: {games_with_stats}')
            self.stdout.write(f'  Strength-adjusted HCA: {adjusted_hca:.2f} points')
            self.stdout.write(f'  Median HCA: {median_hca:.2f} points')
            self.stdout.write(f'  Std dev: {std_hca:.2f} points')
            
            # Use the adjusted HCA as our final estimate
            final_hca = adjusted_hca
        else:
            self.stdout.write(self.style.WARNING('  Not enough data for strength-adjusted HCA'))
            final_hca = simple_hca if home_margins else 3.5  # Fallback to league average
        
        # Store in database
        nat_avg.hca_points = final_hca
        nat_avg.save()
        
        self.stdout.write(f'\n{"-"*80}')
        self.stdout.write(self.style.SUCCESS(f'✓ HCA stored: {final_hca:.2f} points'))
        self.stdout.write(f'{"-"*80}\n')
        
        # Summary statistics
        self.stdout.write(f'\n{"="*80}')
        self.stdout.write('SUMMARY')
        self.stdout.write(f'{"="*80}')
        self.stdout.write(f'  Home Court Advantage: {final_hca:.2f} points')
        self.stdout.write(f'  (applies {final_hca/2:.2f} to home team, -{final_hca/2:.2f} to away team)')
        self.stdout.write(f'  Based on {len(adjusted_hca_values)} home games with team ratings')
        self.stdout.write(f'{"="*80}\n')
