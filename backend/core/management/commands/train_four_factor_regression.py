"""
Management command to train four factor regression model.

Trains a linear regression model to predict game margins from four factor edges.
Stores coefficients in NationalAverages table for use in matchup predictions.

Usage:
    python manage.py train_four_factor_regression --season 2026
"""

from django.core.management.base import BaseCommand
from core.models import Season, TeamGameStats, NationalAverages
import statistics
from collections import defaultdict


class Command(BaseCommand):
    help = 'Train four factor regression model from game logs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (e.g., 2026 for 2025-26 season)'
        )

    def handle(self, *args, **options):
        season_year = options['season']
        
        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Season {season_year} not found'))
            return
        
        self.stdout.write(f'Training four factor regression for {season.display_name}...')
        
        # Get national averages
        try:
            nat_avg = NationalAverages.objects.get(season=season)
        except NationalAverages.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f'NationalAverages not found for {season.display_name}. '
                'Run compute_national_averages first.'
            ))
            return
        
        # Get all games
        all_games = TeamGameStats.objects.filter(
            game__season_year=season_year,
            game__isnull=False
        ).select_related('team', 'game').order_by('game_id', 'id')
        
        if all_games.count() == 0:
            self.stdout.write(self.style.ERROR('No games found'))
            return
        
        self.stdout.write(f'Found {all_games.count()} game records')
        
        # Build training data
        # Group by game to get both teams' stats
        games_by_id = defaultdict(list)
        for game_stat in all_games:
            games_by_id[game_stat.game_id].append(game_stat)
        
        # Filter to games with exactly 2 teams
        valid_games = {gid: stats for gid, stats in games_by_id.items() if len(stats) == 2}
        self.stdout.write(f'Found {len(valid_games)} complete games')
        
        # Extract features and targets
        X = []  # [efg_edge, tov_edge, orb_edge, ftr_edge]
        y = []  # actual margin
        
        for game_id, (stat_a, stat_b) in valid_games.items():
            # Compute four factor values for each team
            # Team A
            efg_a = stat_a.efg_pct if stat_a.efg_pct is not None else nat_avg.avg_efg
            tov_a = stat_a.tov_pct if stat_a.tov_pct is not None else nat_avg.avg_tov
            orb_a = stat_a.orb_pct if stat_a.orb_pct is not None else nat_avg.avg_orb
            ftr_a = stat_a.ftr if stat_a.ftr is not None else nat_avg.avg_ftr
            
            # Team B
            efg_b = stat_b.efg_pct if stat_b.efg_pct is not None else nat_avg.avg_efg
            tov_b = stat_b.tov_pct if stat_b.tov_pct is not None else nat_avg.avg_tov
            orb_b = stat_b.orb_pct if stat_b.orb_pct is not None else nat_avg.avg_orb
            ftr_b = stat_b.ftr if stat_b.ftr is not None else nat_avg.avg_ftr
            
            # Compute edges (Team A perspective)
            efg_edge = efg_a - efg_b
            tov_edge = tov_b - tov_a  # Lower TOV is better
            orb_edge = orb_a - orb_b
            ftr_edge = ftr_a - ftr_b
            
            # Actual margin (Team A perspective)
            margin = stat_a.pts - stat_b.pts
            
            # Normalize by possessions to get efficiency margin (per 100 poss)
            # This makes coefficients pace-aware
            poss_a = stat_a.poss_game if stat_a.poss_game else nat_avg.avg_pace
            efficiency_margin = (margin / poss_a) * 100 if poss_a > 0 else 0
            
            X.append([efg_edge, tov_edge, orb_edge, ftr_edge])
            y.append(efficiency_margin)
        
        self.stdout.write(f'Built training set with {len(X)} games')
        
        # Train regression model using manual linear regression
        # (Avoid sklearn dependency if not already installed)
        n = len(X)
        
        # Convert to column vectors
        efg_edges = [x[0] for x in X]
        tov_edges = [x[1] for x in X]
        orb_edges = [x[2] for x in X]
        ftr_edges = [x[3] for x in X]
        margins = y
        
        # Simple multivariate regression using normal equations
        # For simplicity, use univariate regression on each factor
        # then combine (not technically correct but good enough)
        
        # Better approach: Use sklearn if available
        try:
            from sklearn.linear_model import LinearRegression
            import numpy as np
            
            X_array = np.array(X)
            y_array = np.array(y)
            
            model = LinearRegression()
            model.fit(X_array, y_array)
            
            coef_efg = model.coef_[0]
            coef_tov = model.coef_[1]
            coef_orb = model.coef_[2]
            coef_ftr = model.coef_[3]
            intercept = model.intercept_
            
            # Compute R-squared
            y_pred = model.predict(X_array)
            ss_res = np.sum((y_array - y_pred) ** 2)
            ss_tot = np.sum((y_array - np.mean(y_array)) ** 2)
            r_squared = 1 - (ss_res / ss_tot)
            
            self.stdout.write(self.style.SUCCESS('✓ Sklearn regression successful'))
            
        except ImportError:
            self.stdout.write(self.style.WARNING(
                'sklearn not available, using simple univariate regression'
            ))
            
            # Fallback: Univariate regression on each factor
            def univariate_regression(x_vals, y_vals):
                """Simple linear regression: y = a*x + b"""
                n = len(x_vals)
                mean_x = statistics.mean(x_vals)
                mean_y = statistics.mean(y_vals)
                
                # Slope: sum((x - mean_x)(y - mean_y)) / sum((x - mean_x)^2)
                numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_vals, y_vals))
                denominator = sum((x - mean_x) ** 2 for x in x_vals)
                
                if denominator == 0:
                    return 0.0, mean_y
                
                slope = numerator / denominator
                intercept = mean_y - slope * mean_x
                
                return slope, intercept
            
            coef_efg, _ = univariate_regression(efg_edges, margins)
            coef_tov, _ = univariate_regression(tov_edges, margins)
            coef_orb, _ = univariate_regression(orb_edges, margins)
            coef_ftr, _ = univariate_regression(ftr_edges, margins)
            intercept = statistics.mean(margins)
            r_squared = None
        
        # Store coefficients
        nat_avg.coef_efg = coef_efg
        nat_avg.coef_tov = coef_tov
        nat_avg.coef_orb = coef_orb
        nat_avg.coef_ftr = coef_ftr
        nat_avg.coef_intercept = intercept
        nat_avg.coef_r_squared = r_squared
        nat_avg.save()
        
        self.stdout.write(self.style.SUCCESS('\n✓ Four factor coefficients computed and stored (PACE-AWARE):'))
        self.stdout.write(f'  eFG% edge:  {coef_efg:+.3f} efficiency pts per 100 poss per %')
        self.stdout.write(f'  TOV% edge:  {coef_tov:+.3f} efficiency pts per 100 poss per %')
        self.stdout.write(f'  ORB% edge:  {coef_orb:+.3f} efficiency pts per 100 poss per %')
        self.stdout.write(f'  FTR edge:   {coef_ftr:+.3f} efficiency pts per 100 poss per %')
        self.stdout.write(f'  Intercept:  {intercept:+.3f} efficiency pts per 100 poss')
        if r_squared is not None:
            self.stdout.write(f'  R²:         {r_squared:.3f}')
        
        # Interpretation
        self.stdout.write('\nInterpretation (at average pace of {:.1f} possessions):'.format(nat_avg.avg_pace))
        self.stdout.write(f'  • Each 1% advantage in eFG% is worth {coef_efg * nat_avg.avg_pace / 100:.2f} points')
        self.stdout.write(f'  • Each 1% advantage in TOV% is worth {coef_tov * nat_avg.avg_pace / 100:.2f} points')
        self.stdout.write(f'  • Each 1% advantage in ORB% is worth {coef_orb * nat_avg.avg_pace / 100:.2f} points')
        self.stdout.write(f'  • Each 1% advantage in FTR is worth {coef_ftr * nat_avg.avg_pace / 100:.2f} points')
        self.stdout.write(f'\n  Note: These coefficients scale with game pace automatically.')
