"""
Management command to compute adjusted four factors for each team-season

Adjusted four factors account for opponent quality and site factors (home/away/neutral).

Formula for each game:
    Adj_eFG_g = eFG_g * (Nat_eFG / OppDef_eFG_allowed) * SiteFactor
    Adj_TOV_g = TOV%_g * (Nat_TOV / OppDef_TOV_forced) * SiteFactor
    Adj_ORB_g = ORB%_g * (Nat_ORB / OppDef_ORB_allowed) * SiteFactor
    Adj_FTR_g = FTR_g * (Nat_FTR / OppDef_FTR_allowed) * SiteFactor

Aggregated using possession-weighted averaging.

Usage:
    python manage.py compute_adjusted_four_factors --season 2026 --iterations 3
"""

from django.core.management.base import BaseCommand
from django.db.models import Sum, Avg
from core.models import (
    Season, Team, TeamGameStats, TeamSeasonMetrics,
    TeamSeasonRatings, NationalAverages
)


class Command(BaseCommand):
    help = 'Compute adjusted four factors for all teams in a season'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (e.g., 2026)'
        )
        parser.add_argument(
            '--iterations',
            type=int,
            default=3,
            help='Number of iterations for convergence (default: 3)'
        )

    def handle(self, *args, **options):
        season_year = options['season']
        iterations = options['iterations']

        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Season {season_year} not found"))
            return

        # Get national averages
        try:
            nat_avg = NationalAverages.objects.get(season=season)
        except NationalAverages.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f"National averages not found for {season_year}. "
                "Run compute_national_averages first."
            ))
            return

        self.stdout.write(
            f"Computing adjusted four factors for {season.display_name} "
            f"({iterations} iterations)..."
        )
        self.stdout.write(f"National Averages: eFG={nat_avg.avg_efg:.2f}%, "
                         f"TOV={nat_avg.avg_tov:.2f}%, ORB={nat_avg.avg_orb:.2f}%, "
                         f"FTR={nat_avg.avg_ftr:.2f}")

        # Get all team season metrics
        all_teams = Team.objects.filter(
            season_metrics__season=season
        ).distinct()

        # Initialize ratings dictionary with raw four factors
        four_factors = {}
        for team in all_teams:
            metrics = TeamSeasonMetrics.objects.get(team=team, season=season)
            four_factors[team.id] = {
                # Offensive four factors
                'adj_efg': metrics.efg_pct,
                'adj_tov': metrics.tov_pct,
                'adj_orb': metrics.orb_pct,
                'adj_ftr': metrics.ftr,
                # Defensive four factors (opponent's offensive stats)
                'adj_opp_efg': metrics.opp_efg_pct,
                'adj_opp_tov': metrics.opp_tov_pct,
                'adj_opp_orb': metrics.opp_orb_pct,
                'adj_drb': metrics.drb_pct,
                'adj_opp_ftr': metrics.opp_ftr,
            }

        self.stdout.write(f"Initialized {len(four_factors)} teams with raw four factors")

        # Iteratively compute adjusted four factors
        for iteration in range(1, iterations + 1):
            self.stdout.write(f"\n--- Iteration {iteration} ---")
            
            new_four_factors = {}
            
            for team in all_teams:
                # Get all games for this team
                team_games = TeamGameStats.objects.filter(
                    team=team,
                    game__season_year=season.year
                ).select_related('game')

                if not team_games.exists():
                    continue

                # Accumulators for weighted averaging
                sum_weighted_efg = 0.0
                sum_weighted_tov = 0.0
                sum_weighted_orb = 0.0
                sum_weighted_ftr = 0.0
                
                sum_weighted_opp_efg = 0.0
                sum_weighted_opp_tov = 0.0
                sum_weighted_opp_orb = 0.0
                sum_weighted_drb = 0.0
                sum_weighted_opp_ftr = 0.0
                
                sum_weights = 0.0

                for tgs in team_games:
                    # Get opponent stats
                    opp_tgs = tgs._get_opp_stats()
                    if not opp_tgs:
                        continue

                    opp_id = opp_tgs.team_id
                    
                    # Get opponent's current adjusted defensive four factors
                    if opp_id not in four_factors:
                        continue
                    
                    opp_adj_def_efg = four_factors[opp_id]['adj_opp_efg']
                    opp_adj_def_tov = four_factors[opp_id]['adj_opp_tov']
                    opp_adj_off_orb = four_factors[opp_id]['adj_orb']  # Opponent's ORB%
                    opp_adj_def_ftr = four_factors[opp_id]['adj_opp_ftr']
                    
                    # Get opponent's adjusted offensive four factors (for our defense)
                    opp_adj_off_efg = four_factors[opp_id]['adj_efg']
                    opp_adj_off_tov = four_factors[opp_id]['adj_tov']
                    opp_adj_off_orb = four_factors[opp_id]['adj_orb']
                    opp_adj_off_ftr = four_factors[opp_id]['adj_ftr']

                    # Get raw game stats
                    raw_efg = tgs.efg_pct
                    raw_tov = tgs.tov_pct
                    raw_orb = tgs.orb_pct
                    raw_ftr = tgs.ftr
                    
                    raw_opp_efg = tgs.opp_efg_pct
                    raw_opp_tov = tgs.opp_tov_pct
                    raw_opp_orb = tgs.opp_orb_pct if hasattr(tgs, 'opp_orb_pct') else (100 - tgs.drb_pct)  # Opponent ORB%
                    raw_drb = 100 - tgs.orb_pct if opp_tgs else 0  # DRB% = 100 - opp's ORB%
                    raw_opp_ftr = tgs.opp_ftr

                    # Site factor
                    site_factor = tgs.site_factor

                    # Weight by possessions
                    weight = tgs.poss_game or 0
                    if weight == 0:
                        continue

                    # Compute adjusted offensive four factors
                    if raw_efg is not None and opp_adj_def_efg > 0:
                        adj_efg_g = raw_efg * (nat_avg.avg_efg / opp_adj_def_efg) * site_factor
                        sum_weighted_efg += weight * adj_efg_g
                    
                    if raw_tov is not None and opp_adj_def_tov > 0:
                        adj_tov_g = raw_tov * (nat_avg.avg_tov / opp_adj_def_tov) * site_factor
                        sum_weighted_tov += weight * adj_tov_g
                    
                    if raw_orb is not None and opp_adj_off_orb > 0:
                        adj_orb_g = raw_orb * (nat_avg.avg_orb / opp_adj_off_orb) * site_factor
                        sum_weighted_orb += weight * adj_orb_g
                    
                    if raw_ftr is not None and opp_adj_def_ftr > 0:
                        adj_ftr_g = raw_ftr * (nat_avg.avg_ftr / opp_adj_def_ftr) * site_factor
                        sum_weighted_ftr += weight * adj_ftr_g

                    # Compute adjusted defensive four factors (opponent's adjusted offensive stats)
                    if raw_opp_efg is not None and opp_adj_off_efg > 0:
                        adj_opp_efg_g = raw_opp_efg * (nat_avg.avg_efg / opp_adj_off_efg) * site_factor
                        sum_weighted_opp_efg += weight * adj_opp_efg_g
                    
                    if raw_opp_tov is not None and opp_adj_off_tov > 0:
                        # For defense, we want high TOV% forced (opponent's low TOV%)
                        adj_opp_tov_g = raw_opp_tov * (nat_avg.avg_tov / opp_adj_off_tov) * site_factor
                        sum_weighted_opp_tov += weight * adj_opp_tov_g
                    
                    if raw_opp_orb is not None and opp_adj_off_orb > 0:
                        # Opponent ORB% (defensive stat - lower is better)
                        adj_opp_orb_g = raw_opp_orb * (nat_avg.avg_orb / opp_adj_off_orb) * site_factor
                        sum_weighted_opp_orb += weight * adj_opp_orb_g
                    
                    if raw_drb is not None and opp_adj_off_orb > 0:
                        adj_drb_g = raw_drb * (nat_avg.avg_orb / opp_adj_off_orb) * site_factor
                        sum_weighted_drb += weight * adj_drb_g
                    
                    if raw_opp_ftr is not None and opp_adj_off_ftr > 0:
                        adj_opp_ftr_g = raw_opp_ftr * (nat_avg.avg_ftr / opp_adj_off_ftr) * site_factor
                        sum_weighted_opp_ftr += weight * adj_opp_ftr_g

                    sum_weights += weight

                # Compute weighted averages (no shrinkage for four factors)
                if sum_weights > 0:
                    new_four_factors[team.id] = {
                        'adj_efg': sum_weighted_efg / sum_weights,
                        'adj_tov': sum_weighted_tov / sum_weights,
                        'adj_orb': sum_weighted_orb / sum_weights,
                        'adj_ftr': sum_weighted_ftr / sum_weights,
                        'adj_opp_efg': sum_weighted_opp_efg / sum_weights,
                        'adj_opp_tov': sum_weighted_opp_tov / sum_weights,
                        'adj_opp_orb': sum_weighted_opp_orb / sum_weights,
                        'adj_drb': sum_weighted_drb / sum_weights,
                        'adj_opp_ftr': sum_weighted_opp_ftr / sum_weights,
                    }
                else:
                    # No valid games, keep previous values
                    new_four_factors[team.id] = four_factors[team.id]

            # Update for next iteration
            four_factors = new_four_factors
            self.stdout.write(f"Iteration {iteration} complete: {len(four_factors)} teams updated")

        # Save final adjusted four factors to TeamSeasonRatings
        self.stdout.write("\nSaving adjusted four factors to database...")
        
        created_count = 0
        updated_count = 0
        error_count = 0

        for team in all_teams:
            if team.id not in four_factors:
                continue

            ff = four_factors[team.id]
            
            try:
                # Get or create TeamSeasonRatings
                rating, created = TeamSeasonRatings.objects.get_or_create(
                    team=team,
                    season=season,
                    defaults={
                        'adj_o': 0.0,
                        'adj_d': 0.0,
                        'adj_em': 0.0,
                        'adj_tempo': 0.0,
                    }
                )

                # Update adjusted four factors
                rating.adj_efg_pct = round(ff['adj_efg'], 2)
                rating.adj_tov_pct = round(ff['adj_tov'], 2)
                rating.adj_orb_pct = round(ff['adj_orb'], 2)
                rating.adj_ftr = round(ff['adj_ftr'], 2)
                
                rating.adj_opp_efg_pct = round(ff['adj_opp_efg'], 2)
                rating.adj_opp_tov_pct = round(ff['adj_opp_tov'], 2)
                rating.adj_opp_orb_pct = round(ff['adj_opp_orb'], 2)
                rating.adj_drb_pct = round(ff['adj_drb'], 2)
                rating.adj_opp_ftr = round(ff['adj_opp_ftr'], 2)

                # Compute adjusted margins
                rating.adj_efg_margin = round(rating.adj_efg_pct - rating.adj_opp_efg_pct, 2)
                rating.adj_tov_edge = round(rating.adj_opp_tov_pct - rating.adj_tov_pct, 2)
                rating.adj_reb_edge = round(rating.adj_orb_pct - rating.adj_opp_orb_pct, 2)
                rating.adj_ftr_margin = round(rating.adj_ftr - rating.adj_opp_ftr, 2)

                rating.save()

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Error saving {team.name}: {e}")
                )
                error_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nComplete! Created: {created_count}, Updated: {updated_count}, Errors: {error_count}"
            )
        )

        # Show sample results
        self.stdout.write("\nSample Adjusted Four Factors (Top 10 by Adj eFG margin):")
        top_teams = TeamSeasonRatings.objects.filter(
            season=season
        ).order_by('-adj_efg_margin')[:10]

        for i, rating in enumerate(top_teams, 1):
            self.stdout.write(
                f"{i:2d}. {rating.team.name:25s} - "
                f"Adj eFG: {rating.adj_efg_pct:5.1f}% (vs {rating.adj_opp_efg_pct:5.1f}%), "
                f"Margin: {rating.adj_efg_margin:+5.1f}, "
                f"Adj TOV: {rating.adj_tov_pct:5.1f}% (vs {rating.adj_opp_tov_pct:5.1f}%), "
                f"Edge: {rating.adj_tov_edge:+5.1f}"
            )
