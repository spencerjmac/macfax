
"""
Management command: compute_adjusted_ratings
Computes adjusted offensive/defensive ratings using iterative opponent-adjustment

Usage:
    python manage.py compute_adjusted_ratings --season 2026 --iterations 3
"""

import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q, Count, Case, When, IntegerField, F

from core.models import (
    Season, Team, TeamGameStats, TeamSeasonMetrics,
    TeamSeasonRatings, NationalAverages
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Compute adjusted offensive/defensive ratings (iterative)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (ending year, e.g., 2026 for 2025-26 season)'
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
            help='Convergence threshold for max AdjEM change (default: from PipelineConfig)'
        )
        parser.add_argument(
            '--shrinkage',
            type=int,
            default=None,
            help='Shrinkage constant in possessions (default: from PipelineConfig ceiling; auto-adjusts)'
        )
    
    def handle(self, *args, **options):
        from core.models import PipelineConfig
        cfg = PipelineConfig.get_config()

        season_year = options['season']
        max_iterations = options['iterations'] or cfg.adj_ratings_iterations
        convergence_threshold = options['convergence'] or cfg.adj_ratings_convergence
        shrinkage_k = options['shrinkage'] or cfg.adj_ratings_shrinkage_ceiling
        
        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(f"Season {season_year} not found")
            return
        
        # Get national averages
        try:
            nat_avg = NationalAverages.objects.get(season=season)
        except NationalAverages.DoesNotExist:
            self.stderr.write(f"National averages not found. Run compute_national_averages first.")
            return
        
        self.stdout.write(f"\nComputing Adjusted Ratings for {season.display_name}")
        self.stdout.write(f"National Average ORtg: {nat_avg.avg_ortg:.2f}")
        self.stdout.write(f"National Average Pace: {nat_avg.avg_pace:.2f}")
        self.stdout.write(f"Max Iterations: {max_iterations}")
        self.stdout.write(f"Convergence Threshold: {convergence_threshold}")
        
        # Get all D1 teams with season metrics
        teams = Team.objects.filter(season_metrics__season=season, is_d1=True)
        
        if teams.count() == 0:
            self.stderr.write("No teams found with season metrics")
            return
        
        num_d1_teams = teams.count()
        
        # Calculate dynamic shrinkage k based on average games played
        # Count team-games (NOT matchups - each game counts twice, once per team)
        team_games_count = TeamGameStats.objects.filter(
            game__season_year=season_year,
            game__status='final',
            opponent__is_d1=True,
            team__is_d1=True
        ).count()
        
        avg_games_played = team_games_count / num_d1_teams if num_d1_teams > 0 else 0
        
        # Dynamic k: starts at 300, decays to floor of 170
        # At 16 games (midseason): k ≈ 200
        # At 21+ games: k = 170 (floor)
        # Clamped between 170 and 300 for safety
        if options['shrinkage'] is None:  # Only use dynamic if user didn't override via CLI
            shrinkage_k = min(
                cfg.adj_ratings_shrinkage_ceiling,
                max(cfg.adj_ratings_shrinkage_floor,
                    cfg.adj_ratings_shrinkage_ceiling - (avg_games_played * cfg.adj_ratings_shrinkage_decay))
            )
            self.stdout.write(f"Dynamic Shrinkage: k={shrinkage_k:.1f} (avg {avg_games_played:.1f} games/team)")
        else:
            self.stdout.write(f"Fixed Shrinkage: k={shrinkage_k} possessions (user override)")
        
        self.stdout.write("=" * 60)
        self.stdout.write(f"Processing {num_d1_teams} teams...")
        
        # Initialize ratings dictionary {team_id: {'aor': float, 'adr': float, 'pace': float}}
        ratings = {}
        
        # Step 1: Initialize with raw ORtg/DRtg/Pace
        self.stdout.write("\n[1/1] Initializing with raw ratings...")
        for team in teams:
            metrics = TeamSeasonMetrics.objects.get(team=team, season=season)
            ratings[team.id] = {
                'aor': metrics.ortg,
                'adr': metrics.drtg,
                'pace': metrics.pace,
            }
        
        # Step 2: Iterate until convergence
        converged = False
        iteration = 0
        
        for iteration in range(1, max_iterations + 1):
            self.stdout.write(f"\n[Iteration {iteration}]")
            
            new_ratings = {}
            max_aem_change = 0.0
            
            for team in teams:
                # Get all games for this team (D1 vs D1 only)
                games = TeamGameStats.objects.filter(
                    team=team,
                    game__season_year=season_year,
                    game__status='final',
                    opponent__is_d1=True  # Only include games vs D1 opponents
                ).select_related('game', 'opponent')
                
                if games.count() == 0:
                    continue
                
                # Pre-fetch opponent stats for all games (optimize: single query instead of N queries)
                game_ids = [g.game_id for g in games]
                all_game_stats = TeamGameStats.objects.filter(
                    game_id__in=game_ids
                ).select_related('team')
                
                # Build dict: (game_id, team_id) -> stats
                stats_lookup = {(gs.game_id, gs.team_id): gs for gs in all_game_stats}
                
                # Compute game-level adjusted ratings
                sum_weighted_aor = 0.0
                sum_weighted_adr = 0.0
                sum_weighted_pace = 0.0
                sum_weights = 0.0
                
                for game_stat in games:
                    # Get opponent's current ratings
                    opp_id = game_stat.opponent.id
                    if opp_id not in ratings:
                        continue  # Skip if opponent has no ratings
                    
                    opp_aor = ratings[opp_id]['aor']
                    opp_adr = ratings[opp_id]['adr']
                    opp_pace = ratings[opp_id]['pace']
                    
                    # Get game possessions (use poss_team directly to avoid property queries)
                    poss_g = game_stat.poss_team
                    if not poss_g or poss_g == 0:
                        continue
                    
                    # Get opponent stats for this game (use dict lookup)
                    opp_stats = stats_lookup.get((game_stat.game_id, game_stat.opponent_id))
                    
                    if not opp_stats:
                        continue
                    
                    # Calculate raw game efficiencies and pace manually
                    raw_oe_g = 100 * game_stat.pts / poss_g if poss_g > 0 else None
                    raw_de_g = 100 * opp_stats.pts / poss_g if poss_g > 0 else None
                    minutes = game_stat.game_minutes or 40
                    raw_pace_g = 40 * poss_g / minutes if minutes > 0 else None
                    
                    if raw_oe_g is None or raw_de_g is None or raw_pace_g is None:
                        continue
                    
                    # Get site factors (different for offense vs defense)
                    off_site_factor = game_stat.site_factor  # Home: 0.9862, Away: 1.0140
                    def_site_factor = game_stat.defensive_site_factor  # Home: 1.0140, Away: 0.9862
                    
                    # Compute adjusted game ratings
                    # AOR_g = RawOE_g * (NatAvg / OppAdjD) * OffSiteFactor
                    aor_g = raw_oe_g * (nat_avg.avg_ortg / opp_adr) * off_site_factor if opp_adr > 0 else raw_oe_g
                    
                    # ADR_g = RawDE_g * (NatAvg / OppAdjO) * DefSiteFactor
                    adr_g = raw_de_g * (nat_avg.avg_ortg / opp_aor) * def_site_factor if opp_aor > 0 else raw_de_g
                    
                    # AdjPace_g = RawPace_g * (NatAvgPace / OppPace)
                    # Note: Site factor is typically not applied to pace
                    pace_g = raw_pace_g * (nat_avg.avg_pace / opp_pace) if opp_pace > 0 else raw_pace_g
                    
                    # Weight by possessions (recency multiplier = 1.0 for now)
                    weight = poss_g
                    
                    sum_weighted_aor += weight * aor_g
                    sum_weighted_adr += weight * adr_g
                    sum_weighted_pace += weight * pace_g
                    sum_weights += weight
                
                # Aggregate to season rating with shrinkage
                # AOR = (SUM(w*AOR_g) + k*NatAvg) / (SUM(w) + k)
                if sum_weights > 0:
                    aor_season = (sum_weighted_aor + shrinkage_k * nat_avg.avg_ortg) / (sum_weights + shrinkage_k)
                    adr_season = (sum_weighted_adr + shrinkage_k * nat_avg.avg_ortg) / (sum_weights + shrinkage_k)
                    pace_season = (sum_weighted_pace + shrinkage_k * nat_avg.avg_pace) / (sum_weights + shrinkage_k)
                else:
                    aor_season = nat_avg.avg_ortg
                    adr_season = nat_avg.avg_ortg
                    pace_season = nat_avg.avg_pace
                
                new_ratings[team.id] = {
                    'aor': aor_season,
                    'adr': adr_season,
                    'pace': pace_season,
                }
                
                # Track max change in AdjEM for convergence check
                if team.id in ratings:
                    old_aem = ratings[team.id]['aor'] - ratings[team.id]['adr']
                    new_aem = aor_season - adr_season
                    aem_change = abs(new_aem - old_aem)
                    max_aem_change = max(max_aem_change, aem_change)
            
            # Check for convergence
            self.stdout.write(f"  Max AdjEM change: {max_aem_change:.4f}")
            
            if max_aem_change < convergence_threshold:
                self.stdout.write(f"  ✓ Converged! (change < {convergence_threshold})")
                converged = True
                # Update ratings one last time before breaking
                ratings = new_ratings
                break
            
            # Update ratings for next iteration
            ratings = new_ratings
        
        # Report convergence status
        if converged:
            self.stdout.write(f"\n✓ Converged after {iteration} iterations")
        else:
            self.stdout.write(f"\n⚠ Did not converge after {max_iterations} iterations (max change: {max_aem_change:.4f})")
        
        # Step 3: Save to database
        self.stdout.write(f"\n[3/3] Saving to database...")
        
        created = 0
        updated = 0
        
        with transaction.atomic():
            for team in teams:
                if team.id not in ratings:
                    continue
                
                metrics = TeamSeasonMetrics.objects.get(team=team, season=season)
                
                # Count ALL games (including non-D1) for complete record
                all_games = TeamGameStats.objects.filter(
                    team=team,
                    game__season_year=season_year,
                    game__status='final'
                ).select_related('game', 'opponent')
                
                total_games = all_games.count()
                total_wins = 0
                
                # Count wins by comparing team pts to opponent pts
                for game_stat in all_games:
                    # Get opponent's stats for this game
                    opp_stats = TeamGameStats.objects.filter(
                        game=game_stat.game,
                        team=game_stat.opponent
                    ).first()
                    
                    if opp_stats and game_stat.pts > opp_stats.pts:
                        total_wins += 1
                
                total_losses = total_games - total_wins
                
                # D1 games count (from metrics which filters to D1 only)
                d1_games_count = metrics.games
                
                aor = ratings[team.id]['aor']
                adr = ratings[team.id]['adr']
                aem = aor - adr
                adj_pace = ratings[team.id]['pace']
                
                rating_obj, is_created = TeamSeasonRatings.objects.update_or_create(
                    team=team,
                    season=season,
                    defaults={
                        'adj_o': round(aor, 4),
                        'adj_d': round(adr, 4),
                        'adj_em': round(aem, 4),
                        'adj_tempo': round(adj_pace, 4),
                        'games_played': total_games,  # All games for record
                        'wins': total_wins,
                        'losses': total_losses,
                        'd1_games_played': d1_games_count,  # D1 games only
                        'total_possessions': metrics.total_possessions,
                    }
                )
                
                if is_created:
                    created += 1
                else:
                    updated += 1
        
        # Compute rankings — only among D1 teams so non-D1 stale records don't skew numbers
        self.stdout.write(f"Computing rankings...")
        d1_ratings_qs = TeamSeasonRatings.objects.filter(season=season, team__is_d1=True)

        all_ratings = d1_ratings_qs.order_by('-adj_em')
        for rank, rating in enumerate(all_ratings, start=1):
            rating.rank_adj_em = rank
            rating.save(update_fields=['rank_adj_em'])
        
        all_ratings = d1_ratings_qs.order_by('-adj_o')
        for rank, rating in enumerate(all_ratings, start=1):
            rating.rank_adj_o = rank
            rating.save(update_fields=['rank_adj_o'])
        
        all_ratings = d1_ratings_qs.order_by('adj_d')
        for rank, rating in enumerate(all_ratings, start=1):
            rating.rank_adj_d = rank
            rating.save(update_fields=['rank_adj_d'])
        
        # Update nat_avg.avg_ortg to match actual average of D1 adjusted ratings
        self.stdout.write(f"Updating national average offensive rating...")
        from django.db.models import Avg
        
        old_avg_ortg = nat_avg.avg_ortg
        actual_avg_adj_o = d1_ratings_qs.aggregate(
            Avg('adj_o')
        )['adj_o__avg']
        
        if actual_avg_adj_o:
            nat_avg.avg_ortg = round(actual_avg_adj_o, 4)
            nat_avg.save(update_fields=['avg_ortg'])
            self.stdout.write(
                f"  Updated avg_ortg: {old_avg_ortg:.4f} → {nat_avg.avg_ortg:.4f} "
                f"(Δ {abs(nat_avg.avg_ortg - old_avg_ortg):.4f})"
            )
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("SUMMARY")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Created:  {created}")
        self.stdout.write(f"Updated:  {updated}")
        self.stdout.write("=" * 60)
        
        # Show top 10
        self.stdout.write("\nTop 10 Teams by Adjusted Net Rating:")
        self.stdout.write("=" * 60)
        top_10 = d1_ratings_qs.order_by('-adj_em')[:10]
        for i, rating in enumerate(top_10, start=1):
            self.stdout.write(
                f"{i:2}. {rating.team.name:30} AOR={rating.adj_o:6.2f} ADR={rating.adj_d:6.2f} "
                f"Net={rating.adj_em:+6.2f} Pace={rating.adj_tempo:5.1f}"
            )
        self.stdout.write("=" * 60)
