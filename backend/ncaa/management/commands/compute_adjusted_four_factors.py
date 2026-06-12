"""
Management command to compute adjusted four factors for each team-season

Adjusted four factors account for opponent quality and site factors (home/away/neutral).

Formula for each game:
    Offensive (use offensive SiteFactor: Home=0.9862, Away=1.0140):
    Adj_eFG_g  = eFG_g  * (Nat_eFG / OppDef_eFG_allowed) * OffSiteFactor
    Adj_TOV_g  = TOV%_g * (Nat_TOV / OppDef_TOV_forced)  * OffSiteFactor
    Adj_ORB_g  = ORB%_g * (Nat_ORB / OppDef_ORB_allowed) * OffSiteFactor
    Adj_FTR_g  = FTR_g  * (Nat_FTR / OppDef_FTR_allowed) * OffSiteFactor

    Defensive (use defensive SiteFactor: Home=1.0140, Away=0.9862 — inverse of offensive):
    Adj_OppEFG_g = OppEFG_g * (Nat_eFG / OppOff_eFG) * DefSiteFactor
    Adj_OppTOV_g = OppTOV_g * (Nat_TOV / OppOff_TOV) * DefSiteFactor
    Adj_OppORB_g = OppORB_g * (Nat_ORB / OppOff_ORB) * DefSiteFactor
    Adj_FTR_g    = OppFTR_g * (Nat_FTR / OppOff_FTR) * DefSiteFactor

Each team-season value is the possession-weighted average of its game-level
adjusted values, blended toward the national average with a shrinkage
constant (in pseudo-possessions) — same approach as compute_adjusted_ratings.
Without this shrinkage the ratio-based update (each team's value depends on
its opponents' *previous-iteration* values) settles into a stable period-2
oscillation rather than converging; shrinkage damps that into a single
fixed point.

Usage:
    python manage.py compute_adjusted_four_factors --season 2026
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from ncaa.models import (
    Season, Team, TeamGameStats, TeamSeasonMetrics,
    TeamSeasonRatings, NationalAverages
)

KEYS = [
    'adj_efg', 'adj_tov', 'adj_orb', 'adj_ftr',
    'adj_opp_efg', 'adj_opp_tov', 'adj_opp_orb', 'adj_drb', 'adj_opp_ftr',
]


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
            default=None,
            help='Maximum number of iterations (default: from PipelineConfig)'
        )
        parser.add_argument(
            '--convergence',
            type=float,
            default=None,
            help='Convergence threshold for max stat change in pct points (default: from PipelineConfig)'
        )
        parser.add_argument(
            '--shrinkage',
            type=float,
            default=None,
            help='Shrinkage constant in possessions (default: from PipelineConfig; auto-adjusts by schedule depth)',
        )
        parser.add_argument(
            "--pre-tournament",
            action="store_true",
            help="If set, compute ratings using only games on or before Selection Sunday.",
        )

    def handle(self, *args, **options):
        from ncaa.models import PipelineConfig
        cfg = PipelineConfig.get_config()

        season_year = options['season']
        max_iterations = options['iterations'] or cfg.adj_ff_iterations
        convergence_threshold = options['convergence'] or cfg.adj_ff_convergence
        shrinkage_k = options['shrinkage']  # None = dynamic (computed below)
        is_pre_tournament = options['pre_tournament']

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
            f"(max {max_iterations} iterations, convergence < {convergence_threshold})..."
        )
        self.stdout.write(f"National Averages: eFG={nat_avg.avg_efg:.2f}%, "
                         f"TOV={nat_avg.avg_tov:.2f}%, ORB={nat_avg.avg_orb:.2f}%, "
                         f"FTR={nat_avg.avg_ftr:.2f}")

        # Per-stat shrinkage priors (national averages each stat regresses toward)
        priors = {
            'adj_efg': nat_avg.avg_efg,
            'adj_tov': nat_avg.avg_tov,
            'adj_orb': nat_avg.avg_orb,
            'adj_ftr': nat_avg.avg_ftr,
            'adj_opp_efg': nat_avg.avg_efg,
            'adj_opp_tov': nat_avg.avg_tov,
            'adj_opp_orb': nat_avg.avg_orb,
            'adj_drb': 100.0 - nat_avg.avg_orb,
            'adj_opp_ftr': nat_avg.avg_ftr,
        }

        # Get all team season metrics
        all_teams = Team.objects.filter(
            season_metrics__season=season
        ).distinct()

        # Initialize ratings dictionary with raw four factors
        four_factors = {}
        for team in all_teams:
            try:
                metrics = TeamSeasonMetrics.all_objects.get(team=team, season=season, is_pre_tournament=is_pre_tournament)
            except TeamSeasonMetrics.DoesNotExist:
                continue

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

        # Pre-fetch per-game data once (used every iteration). Avoids re-querying
        # the database on every one of up to `max_iterations` passes.
        self.stdout.write("Pre-fetching game data...")
        team_games_data = {}
        total_team_games = 0
        for team in all_teams:
            if team.id not in four_factors:
                continue

            tgs_filters = {'team': team, 'game__season_year': season.year}
            if is_pre_tournament and season.selection_sunday_date:
                tgs_filters['game__game_date__lte'] = season.selection_sunday_date

            # Exclude canceled games (0-0 score)
            team_games = TeamGameStats.objects.filter(
                ~Q(game__home_score=0, game__away_score=0),
                **tgs_filters
            ).select_related('game')

            games_data = []
            for tgs in team_games:
                opp_tgs = tgs._get_opp_stats()
                if not opp_tgs:
                    continue

                weight = tgs.poss_game or 0
                if weight == 0:
                    continue

                raw_opp_orb = tgs.opp_orb_pct
                games_data.append({
                    'opp_id': opp_tgs.team_id,
                    'weight': weight,
                    'site_factor': tgs.site_factor,
                    'def_site_factor': tgs.defensive_site_factor,
                    'raw_efg': tgs.efg_pct,
                    'raw_tov': tgs.tov_pct,
                    'raw_orb': tgs.orb_pct,
                    'raw_ftr': tgs.ftr,
                    'raw_opp_efg': tgs.opp_efg_pct,
                    'raw_opp_tov': tgs.opp_tov_pct,
                    'raw_opp_orb': raw_opp_orb,
                    'raw_drb': (100 - raw_opp_orb) if raw_opp_orb is not None else 0,
                    'raw_opp_ftr': tgs.opp_ftr,
                })

            team_games_data[team.id] = games_data
            total_team_games += len(games_data)

        # Dynamic shrinkage k based on average games played (mirrors compute_adjusted_ratings)
        avg_games_played = total_team_games / len(four_factors) if four_factors else 0

        if shrinkage_k is None:
            shrinkage_k = min(
                cfg.adj_ff_shrinkage_ceiling,
                max(
                    cfg.adj_ff_shrinkage_floor,
                    cfg.adj_ff_shrinkage_ceiling
                    - (avg_games_played * cfg.adj_ff_shrinkage_decay),
                ),
            )
            self.stdout.write(
                f"Dynamic Shrinkage: k={shrinkage_k:.1f} (avg {avg_games_played:.1f} games/team)"
            )
        else:
            self.stdout.write(
                f"Fixed Shrinkage: k={shrinkage_k:.1f} possessions (user override)"
            )

        # Iteratively compute adjusted four factors
        converged = False
        iteration = 0

        for iteration in range(1, max_iterations + 1):
            new_four_factors = {}
            max_change = 0.0

            for team_id, games_data in team_games_data.items():
                if not games_data:
                    continue

                sums = {k: 0.0 for k in KEYS}
                sum_weights = 0.0

                for g in games_data:
                    opp_id = g['opp_id']
                    if opp_id not in four_factors:
                        continue

                    opp = four_factors[opp_id]
                    weight = g['weight']

                    # Opponent's current adjusted defensive four factors (for our offense)
                    opp_adj_def_efg = opp['adj_opp_efg']
                    opp_adj_def_tov = opp['adj_opp_tov']
                    opp_adj_orb_allowed = opp['adj_opp_orb']
                    opp_adj_def_ftr = opp['adj_opp_ftr']

                    # Opponent's current adjusted offensive four factors (for our defense)
                    opp_adj_off_efg = opp['adj_efg']
                    opp_adj_off_tov = opp['adj_tov']
                    opp_adj_off_orb = opp['adj_orb']
                    opp_adj_off_ftr = opp['adj_ftr']

                    site_factor = g['site_factor']
                    def_site_factor = g['def_site_factor']

                    # Adjusted offensive four factors
                    if g['raw_efg'] is not None and opp_adj_def_efg > 0:
                        sums['adj_efg'] += weight * (g['raw_efg'] * (nat_avg.avg_efg / opp_adj_def_efg) * site_factor)

                    if g['raw_tov'] is not None and opp_adj_def_tov > 0:
                        sums['adj_tov'] += weight * (g['raw_tov'] * (nat_avg.avg_tov / opp_adj_def_tov) * site_factor)

                    if g['raw_orb'] is not None and opp_adj_orb_allowed > 0:
                        sums['adj_orb'] += weight * (g['raw_orb'] * (nat_avg.avg_orb / opp_adj_orb_allowed) * site_factor)

                    if g['raw_ftr'] is not None and opp_adj_def_ftr > 0:
                        sums['adj_ftr'] += weight * (g['raw_ftr'] * (nat_avg.avg_ftr / opp_adj_def_ftr) * site_factor)

                    # Adjusted defensive four factors (opponent's adjusted offensive stats)
                    if g['raw_opp_efg'] is not None and opp_adj_off_efg > 0:
                        sums['adj_opp_efg'] += weight * (g['raw_opp_efg'] * (nat_avg.avg_efg / opp_adj_off_efg) * def_site_factor)

                    if g['raw_opp_tov'] is not None and opp_adj_off_tov > 0:
                        sums['adj_opp_tov'] += weight * (g['raw_opp_tov'] * (nat_avg.avg_tov / opp_adj_off_tov) * def_site_factor)

                    if g['raw_opp_orb'] is not None and opp_adj_off_orb > 0:
                        sums['adj_opp_orb'] += weight * (g['raw_opp_orb'] * (nat_avg.avg_orb / opp_adj_off_orb) * def_site_factor)

                    if g['raw_drb'] is not None and opp_adj_off_orb > 0:
                        sums['adj_drb'] += weight * (g['raw_drb'] * (nat_avg.avg_orb / opp_adj_off_orb) * def_site_factor)

                    if g['raw_opp_ftr'] is not None and opp_adj_off_ftr > 0:
                        sums['adj_opp_ftr'] += weight * (g['raw_opp_ftr'] * (nat_avg.avg_ftr / opp_adj_off_ftr) * def_site_factor)

                    sum_weights += weight

                # Blend possession-weighted average with national average prior
                # (X_season = (sum_weighted_X + k*Prior_X) / (sum_weights + k))
                new_vals = {
                    k: (sums[k] + shrinkage_k * priors[k]) / (sum_weights + shrinkage_k)
                    for k in KEYS
                }
                new_four_factors[team_id] = new_vals

                old_vals = four_factors[team_id]
                for k in KEYS:
                    max_change = max(max_change, abs(new_vals[k] - old_vals[k]))

            four_factors = new_four_factors

            if max_change < convergence_threshold:
                self.stdout.write(f"Iteration {iteration}: max change={max_change:.5f} — converged")
                converged = True
                break
            else:
                self.stdout.write(f"Iteration {iteration}: max change={max_change:.5f}")

        if converged:
            self.stdout.write(self.style.SUCCESS(f"\nConverged after {iteration} iterations"))
        else:
            self.stdout.write(self.style.WARNING(
                f"\nDid not converge after {max_iterations} iterations (max change: {max_change:.5f})"
            ))

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
                # Only update existing TeamSeasonRatings — never create stubs for teams
                # that weren't processed by compute_adjusted_ratings (e.g. teams that
                # weren't D1 in this historical season).
                updated = TeamSeasonRatings.all_objects.filter(
                    team=team,
                    season=season,
                    is_pre_tournament=is_pre_tournament,
                ).update(
                    adj_efg_pct=round(ff['adj_efg'], 2),
                    adj_tov_pct=round(ff['adj_tov'], 2),
                    adj_orb_pct=round(ff['adj_orb'], 2),
                    adj_ftr=round(ff['adj_ftr'], 2),
                    adj_opp_efg_pct=round(ff['adj_opp_efg'], 2),
                    adj_opp_tov_pct=round(ff['adj_opp_tov'], 2),
                    adj_opp_orb_pct=round(ff['adj_opp_orb'], 2),
                    adj_drb_pct=round(ff['adj_drb'], 2),
                    adj_opp_ftr=round(ff['adj_opp_ftr'], 2),
                )

                if updated:
                    # Recompute margin fields separately (they depend on the adj fields)
                    rating = TeamSeasonRatings.all_objects.get(team=team, season=season, is_pre_tournament=is_pre_tournament)
                    rating.adj_efg_margin = round(rating.adj_efg_pct - rating.adj_opp_efg_pct, 2)
                    rating.adj_tov_edge = round(rating.adj_opp_tov_pct - rating.adj_tov_pct, 2)
                    rating.adj_reb_edge = round(rating.adj_orb_pct - rating.adj_opp_orb_pct, 2)
                    rating.adj_ftr_margin = round(rating.adj_ftr - rating.adj_opp_ftr, 2)
                    rating.save(update_fields=['adj_efg_margin', 'adj_tov_edge', 'adj_reb_edge', 'adj_ftr_margin'])
                    updated_count += 1
                # else: team has no ratings row yet (not yet processed by compute_adjusted_ratings) — skip

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
        top_teams = TeamSeasonRatings.all_objects.filter(
            season=season, is_pre_tournament=is_pre_tournament
        ).order_by('-adj_efg_margin')[:10]

        for i, rating in enumerate(top_teams, 1):
            self.stdout.write(
                f"{i:2d}. {rating.team.name:25s} - "
                f"Adj eFG: {rating.adj_efg_pct:5.1f}% (vs {rating.adj_opp_efg_pct:5.1f}%), "
                f"Margin: {rating.adj_efg_margin:+5.1f}, "
                f"Adj TOV: {rating.adj_tov_pct:5.1f}% (vs {rating.adj_opp_tov_pct:5.1f}%), "
                f"Edge: {rating.adj_tov_edge:+5.1f}"
            )
