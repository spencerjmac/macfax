"""
Management command: compute_game_value
Computes game_value for all completed games in a season

game_value = result - p_bubble
where:
- result = 1 if team won, 0 if lost
- p_bubble = probability that bubble team (#45 by AdjEM) would win that game

Usage:
    python manage.py compute_game_value --season 2026
"""

import logging
from django.core.management.base import BaseCommand
from django.db import transaction

from ncaa.models import Season, TeamSeasonRatings, TeamGameStats, NationalAverages
from api.matchup_engine import forecast_game

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Compute game_value for all completed games'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (e.g., 2026)'
        )
    
    def handle(self, *args, **options):
        from ncaa.models import PipelineConfig
        cfg = PipelineConfig.get_config()

        season_year = options['season']

        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(f"❌ Season {season_year} not found")
            return

        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(f"Computing Game Value for {season.display_name}")
        self.stdout.write(f"{'='*80}\n")

        # Get national averages
        nat_avg = NationalAverages.objects.filter(season=season).first()
        if not nat_avg:
            self.stderr.write(f"❌ National averages not found for {season_year}")
            return

        nat_avg_ortg = nat_avg.avg_ortg if nat_avg.avg_ortg is not None else cfg.fallback_avg_ortg
        hca_points = nat_avg.hca_points if nat_avg.hca_points is not None else cfg.fallback_hca
        sigma = nat_avg.prediction_sigma if nat_avg.prediction_sigma is not None else cfg.fallback_sigma

        self.stdout.write(f"📊 National Context:")
        self.stdout.write(f"  • Avg ORtg: {nat_avg_ortg:.2f}")
        self.stdout.write(f"  • HCA: {hca_points:.2f} pts")
        self.stdout.write(f"  • Sigma: {sigma:.2f}\n")

        # Get bubble team (configured rank by AdjEM)
        bubble_rank = cfg.wab_bubble_rank
        try:
            bubble_team = TeamSeasonRatings.objects.get(season=season, rank_adj_em=bubble_rank)
        except TeamSeasonRatings.DoesNotExist:
            self.stderr.write(f"❌ Bubble team (rank #{bubble_rank}) not found")
            return

        self.stdout.write(f"🎯 Bubble Team: {bubble_team.team.name} (Rank #{bubble_team.rank_adj_em})")
        self.stdout.write(f"  • AdjEM: {bubble_team.adj_em:.2f}")
        self.stdout.write(f"  • AdjO: {bubble_team.adj_o:.2f}")
        self.stdout.write(f"  • AdjD: {bubble_team.adj_d:.2f}\n")
        
        # Get all completed games for this season
        all_games = TeamGameStats.objects.filter(
            game__season_year=season_year,
            game__status='final'
        ).select_related('team', 'opponent', 'game')
        
        total_games = all_games.count()
        if total_games == 0:
            self.stderr.write(f"❌ No completed games found for {season_year}")
            return
       
        self.stdout.write(f"Found {total_games:,} completed game stats to process\n")
        
        games_updated = 0
        games_skipped = 0
        
        with transaction.atomic():
            for i, game_stat in enumerate(all_games, 1):
                # Get opponent ratings
                try:
                    opp_ratings = TeamSeasonRatings.objects.get(
                        team=game_stat.opponent,
                        season=season
                    )
                except TeamSeasonRatings.DoesNotExist:
                    # Skip non-D1 opponents
                    games_skipped += 1
                    continue
                
                # Determine result
                opp_stat = game_stat._get_opp_stats()
                if not opp_stat:
                    games_skipped += 1
                    continue
                
                result = 1.0 if game_stat.pts > opp_stat.pts else 0.0
                
                # Determine site from team perspective
                if game_stat.home_away == 'H':
                    site = 'home'
                elif game_stat.home_away == 'A':
                    site = 'away'
                else:
                    site = 'neutral'
                
                # Forecast with bubble team vs opponent
                forecast = forecast_game(
                    adj_o_a=bubble_team.adj_o,
                    adj_d_a=bubble_team.adj_d,
                    adj_em_a=bubble_team.adj_em,
                    tempo_a=bubble_team.adj_tempo,
                    adj_o_b=opp_ratings.adj_o,
                    adj_d_b=opp_ratings.adj_d,
                    adj_em_b=opp_ratings.adj_em,
                    tempo_b=opp_ratings.adj_tempo,
                    nat_avg_ortg=nat_avg_ortg,
                    hca_points=hca_points,
                    sigma=sigma,
                    site=site
                )
                
                p_bubble = forecast['prob_a']
                game_value = result - p_bubble
                
                # Update game_value
                game_stat.game_value = game_value
                game_stat.save(update_fields=['game_value'])
                
                games_updated += 1
                
                # Progress indicator
                if i % 500 == 0:
                    self.stdout.write(f"  Processed {i:,}/{total_games:,} games...")
        
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(f"✅ Game Value Computation Complete")
        self.stdout.write(f"{'='*80}")
        self.stdout.write(f"  • Games updated: {games_updated:,}")
        self.stdout.write(f"  • Games skipped: {games_skipped:,}\n")
        
        # Show some examples
        self.stdout.write(f"📈 Top 10 Best Game Values (biggest resume wins):")
        best_games = TeamGameStats.objects.filter(
            game__season_year=season_year,
            game_value__isnull=False
        ).select_related('team', 'opponent', 'game').order_by('-game_value')[:10]
        
        for i, g in enumerate(best_games, 1):
            self.stdout.write(
                f"  {i:2d}. {g.team.name} vs {g.opponent.name} "
                f"({g.home_away}): GV={g.game_value:.3f}"
            )
        
        self.stdout.write(f"\n📉 Top 10 Worst Game Values (biggest resume losses):")
        worst_games = TeamGameStats.objects.filter(
            game__season_year=season_year,
            game_value__isnull=False
        ).select_related('team', 'opponent', 'game').order_by('game_value')[:10]
        
        for i, g in enumerate(worst_games, 1):
            self.stdout.write(
                f"  {i:2d}. {g.team.name} vs {g.opponent.name} "
                f"({g.home_away}): GV={g.game_value:.3f}"
            )
        
        self.stdout.write(f"\n{'='*80}\n")
