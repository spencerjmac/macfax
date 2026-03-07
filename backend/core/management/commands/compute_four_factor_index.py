"""
Management command to compute Four Factor Index (FFI) for all teams

The Four Factor Index is a composite metric combining the four factors:
- eFG margin (45% weight)
- Turnover edge (24% weight)
- Rebounding edge (22% weight)
- FTR margin (9% weight)

Formula:
1. Compute z-scores for each margin across all teams
2. FFI_z = 0.45*z_eFG + 0.24*z_TOV + 0.22*z_REB + 0.09*z_FTR
3. FFI_100 = clamp(50 + 20*FFI_z, 0, 100)

Computes both raw FFI (from raw margins) and adjusted FFI (from adjusted margins).

Usage:
    python manage.py compute_four_factor_index --season 2026
"""

from django.core.management.base import BaseCommand
from core.models import Season, TeamSeasonMetrics, TeamSeasonRatings
import math


class Command(BaseCommand):
    help = 'Compute Four Factor Index for all teams in a season'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (e.g., 2026)'
        )

    def compute_z_score(self, value, mean, std_dev):
        """Compute z-score with protection against zero std dev"""
        if std_dev == 0:
            return 0.0
        return (value - mean) / std_dev

    def compute_stats(self, values):
        """Compute mean and standard deviation"""
        n = len(values)
        if n == 0:
            return 0.0, 0.0
        
        mean = sum(values) / n
        
        if n == 1:
            return mean, 0.0
        
        variance = sum((x - mean) ** 2 for x in values) / n
        std_dev = math.sqrt(variance)
        
        return mean, std_dev

    def handle(self, *args, **options):
        season_year = options['season']

        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Season {season_year} not found"))
            return

        self.stdout.write(f"Computing Four Factor Index for {season.display_name}...")

        # Get all D1 teams with metrics and ratings
        teams_with_metrics = TeamSeasonMetrics.objects.filter(season=season, team__is_d1=True)
        teams_with_ratings = TeamSeasonRatings.objects.filter(season=season, team__is_d1=True)

        if not teams_with_metrics.exists():
            self.stdout.write(self.style.ERROR(
                "No team season metrics found. Run compute_season_metrics first."
            ))
            return

        if not teams_with_ratings.exists():
            self.stdout.write(self.style.ERROR(
                "No team season ratings found. Run compute_adjusted_ratings first."
            ))
            return

        # ==========================
        # PART 1: Raw FFI from TeamSeasonMetrics
        # ==========================
        
        self.stdout.write("\n=== Computing Raw FFI ===")
        
        # Collect raw margins
        raw_efg_margins = []
        raw_tov_edges = []
        raw_reb_edges = []
        raw_ftr_margins = []
        
        for metrics in teams_with_metrics:
            raw_efg_margins.append(metrics.efg_margin)
            raw_tov_edges.append(metrics.tov_edge)
            raw_reb_edges.append(metrics.reb_edge)
            raw_ftr_margins.append(metrics.ftr_margin)

        # Compute means and std devs
        efg_mean, efg_std = self.compute_stats(raw_efg_margins)
        tov_mean, tov_std = self.compute_stats(raw_tov_edges)
        reb_mean, reb_std = self.compute_stats(raw_reb_edges)
        ftr_mean, ftr_std = self.compute_stats(raw_ftr_margins)

        self.stdout.write(
            f"Raw Margins - eFG: μ={efg_mean:.2f} σ={efg_std:.2f}, "
            f"TOV: μ={tov_mean:.2f} σ={tov_std:.2f}, "
            f"REB: μ={reb_mean:.2f} σ={reb_std:.2f}, "
            f"FTR: μ={ftr_mean:.2f} σ={ftr_std:.2f}"
        )

        # Compute raw FFI for each team and store in ratings
        raw_ffi_values = {}
        
        for metrics in teams_with_metrics:
            # Compute z-scores
            z_efg = self.compute_z_score(metrics.efg_margin, efg_mean, efg_std)
            z_tov = self.compute_z_score(metrics.tov_edge, tov_mean, tov_std)
            z_reb = self.compute_z_score(metrics.reb_edge, reb_mean, reb_std)
            z_ftr = self.compute_z_score(metrics.ftr_margin, ftr_mean, ftr_std)

            # Weighted FFI z-score
            ffi_z = (
                0.45 * z_efg +
                0.24 * z_tov +
                0.22 * z_reb +
                0.09 * z_ftr
            )

            # Scale to 0-100
            ffi_100 = max(0, min(100, 50 + 20 * ffi_z))

            raw_ffi_values[metrics.team_id] = ffi_100

        self.stdout.write(f"Computed raw FFI for {len(raw_ffi_values)} teams")

        # ==========================
        # PART 2: Adjusted FFI from TeamSeasonRatings
        # ==========================
        
        self.stdout.write("\n=== Computing Adjusted FFI ===")
        
        # Collect adjusted margins
        adj_efg_margins = []
        adj_tov_edges = []
        adj_reb_edges = []
        adj_ftr_margins = []
        
        for rating in teams_with_ratings:
            adj_efg_margins.append(rating.adj_efg_margin)
            adj_tov_edges.append(rating.adj_tov_edge)
            adj_reb_edges.append(rating.adj_reb_edge)
            adj_ftr_margins.append(rating.adj_ftr_margin)

        # Compute means and std devs
        adj_efg_mean, adj_efg_std = self.compute_stats(adj_efg_margins)
        adj_tov_mean, adj_tov_std = self.compute_stats(adj_tov_edges)
        adj_reb_mean, adj_reb_std = self.compute_stats(adj_reb_edges)
        adj_ftr_mean, adj_ftr_std = self.compute_stats(adj_ftr_margins)

        self.stdout.write(
            f"Adjusted Margins - eFG: μ={adj_efg_mean:.2f} σ={adj_efg_std:.2f}, "
            f"TOV: μ={adj_tov_mean:.2f} σ={adj_tov_std:.2f}, "
            f"REB: μ={adj_reb_mean:.2f} σ={adj_reb_std:.2f}, "
            f"FTR: μ={adj_ftr_mean:.2f} σ={adj_ftr_std:.2f}"
        )

        # Compute adjusted FFI and save to database
        updated_count = 0
        error_count = 0

        for rating in teams_with_ratings:
            try:
                # Compute adjusted z-scores
                z_efg = self.compute_z_score(rating.adj_efg_margin, adj_efg_mean, adj_efg_std)
                z_tov = self.compute_z_score(rating.adj_tov_edge, adj_tov_mean, adj_tov_std)
                z_reb = self.compute_z_score(rating.adj_reb_edge, adj_reb_mean, adj_reb_std)
                z_ftr = self.compute_z_score(rating.adj_ftr_margin, adj_ftr_mean, adj_ftr_std)

                # Weighted FFI z-score
                ffi_z = (
                    0.45 * z_efg +
                    0.24 * z_tov +
                    0.22 * z_reb +
                    0.09 * z_ftr
                )

                # Scale to 0-100
                ffi_100 = max(0, min(100, 50 + 20 * ffi_z))

                # Update rating with both raw and adjusted FFI
                rating.ffi_raw = round(raw_ffi_values.get(rating.team_id, 50.0), 1)
                rating.ffi_adj = round(ffi_100, 1)
                rating.save()

                updated_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Error updating {rating.team.name}: {e}")
                )
                error_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nComplete! Updated: {updated_count}, Errors: {error_count}"
            )
        )

        # Show sample results
        self.stdout.write("\n=== Top 10 Teams by Adjusted FFI ===")
        top_teams = TeamSeasonRatings.objects.filter(
            season=season
        ).order_by('-ffi_adj')[:10]

        for i, rating in enumerate(top_teams, 1):
            self.stdout.write(
                f"{i:2d}. {rating.team.name:25s} - "
                f"Raw FFI: {rating.ffi_raw:5.1f}, "
                f"Adj FFI: {rating.ffi_adj:5.1f}, "
                f"Adj eFG: {rating.adj_efg_margin:+5.1f}, "
                f"Adj TOV: {rating.adj_tov_edge:+5.1f}, "
                f"Adj REB: {rating.adj_reb_edge:+5.1f}"
            )

        self.stdout.write("\n=== Bottom 10 Teams by Adjusted FFI ===")
        bottom_teams = TeamSeasonRatings.objects.filter(
            season=season
        ).order_by('ffi_adj')[:10]

        for i, rating in enumerate(bottom_teams, 1):
            self.stdout.write(
                f"{i:2d}. {rating.team.name:25s} - "
                f"Raw FFI: {rating.ffi_raw:5.1f}, "
                f"Adj FFI: {rating.ffi_adj:5.1f}, "
                f"Adj eFG: {rating.adj_efg_margin:+5.1f}, "
                f"Adj TOV: {rating.adj_tov_edge:+5.1f}, "
                f"Adj REB: {rating.adj_reb_edge:+5.1f}"
            )
