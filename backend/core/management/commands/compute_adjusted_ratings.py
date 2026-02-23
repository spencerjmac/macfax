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
            default=3,
            help='Number of iterations (default: 3)'
        )
        parser.add_argument(
            '--shrinkage',
            type=int,
            default=300,
            help='Shrinkage constant in possessions (default: 300)'
        )
    
    def handle(self, *args, **options):
        season_year = options['season']
        iterations = options['iterations']
        shrinkage_k = options['shrinkage']
        
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
        self.stdout.write(f"Iterations: {iterations}")
        self.stdout.write(f"Shrinkage: {shrinkage_k} possessions")
        self.stdout.write("=" * 60)
        
        # Get all D1 teams with season metrics
        teams = Team.objects.filter(season_metrics__season=season, is_d1=True)
        
        if teams.count() == 0:
            self.stderr.write("No teams found with season metrics")
            return
        
        self.stdout.write(f"Processing {teams.count()} teams...")
        
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
        
        # Step 2: Iterate
        for iteration in range(1, iterations + 1):
            self.stdout.write(f"\n[2/{iterations}] Iteration {iteration}...")
            
            new_ratings = {}
            
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
                    
                    # Get game possessions
                    poss_g = game_stat.poss_game
                    if not poss_g or poss_g == 0:
                        continue
                    
                    # Get raw game efficiencies and pace
                    raw_oe_g = game_stat.ortg  # 100 * pts / poss_g
                    raw_de_g = game_stat.drtg  # 100 * opp_pts / poss_g
                    raw_pace_g = game_stat.pace  # Possessions per 40 minutes
                    
                    if raw_oe_g is None or raw_de_g is None or raw_pace_g is None:
                        continue
                    
                    # Get site factor
                    site_factor = game_stat.site_factor
                    
                    # Compute adjusted game ratings
                    # AOR_g = RawOE_g * (NatAvg / OppAdjD) * SiteFactor
                    aor_g = raw_oe_g * (nat_avg.avg_ortg / opp_adr) * site_factor if opp_adr > 0 else raw_oe_g
                    
                    # ADR_g = RawDE_g * (NatAvg / OppAdjO) * SiteFactor
                    adr_g = raw_de_g * (nat_avg.avg_ortg / opp_aor) * site_factor if opp_aor > 0 else raw_de_g
                    
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
            
            # Update ratings for next iteration
            ratings = new_ratings
        
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
        
        # Compute rankings
        self.stdout.write(f"Computing rankings...")
        
        all_ratings = TeamSeasonRatings.objects.filter(season=season).order_by('-adj_em')
        for rank, rating in enumerate(all_ratings, start=1):
            rating.rank_adj_em = rank
            rating.save(update_fields=['rank_adj_em'])
        
        all_ratings = TeamSeasonRatings.objects.filter(season=season).order_by('-adj_o')
        for rank, rating in enumerate(all_ratings, start=1):
            rating.rank_adj_o = rank
            rating.save(update_fields=['rank_adj_o'])
        
        all_ratings = TeamSeasonRatings.objects.filter(season=season).order_by('adj_d')
        for rank, rating in enumerate(all_ratings, start=1):
            rating.rank_adj_d = rank
            rating.save(update_fields=['rank_adj_d'])
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("SUMMARY")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Created:  {created}")
        self.stdout.write(f"Updated:  {updated}")
        self.stdout.write("=" * 60)
        
        # Show top 10
        self.stdout.write("\nTop 10 Teams by Adjusted Net Rating:")
        self.stdout.write("=" * 60)
        top_10 = TeamSeasonRatings.objects.filter(season=season).order_by('-adj_em')[:10]
        for i, rating in enumerate(top_10, start=1):
            self.stdout.write(
                f"{i:2}. {rating.team.name:30} AOR={rating.adj_o:6.2f} ADR={rating.adj_d:6.2f} "
                f"Net={rating.adj_em:+6.2f} Pace={rating.adj_tempo:5.1f}"
            )
        self.stdout.write("=" * 60)
