"""
Management command: compute_wab
Computes WAB (Wins Above Bubble) for all teams in a season

WAB Definition:
  WAB_T = Σ_over_games_g ( Result_g - pBubble_g )
  where:
  - Result_g = 1 if team T won game g, else 0
  - pBubble_g = probability that the "Bubble Team" (#45 ranked) would win that same game

Usage:
    python manage.py compute_wab --season 2026
"""

import logging
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Season, TeamSeasonRatings, TeamSeasonStats, TeamGameStats, NationalAverages
from api.matchup_engine import compute_wab_for_team

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Compute WAB (Wins Above Bubble) for all teams'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (ending year, e.g., 2026 for 2025-26 season)'
        )
    
    def handle(self, *args, **options):
        season_year = options['season']
        
        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(f"❌ Season {season_year} not found")
            return
        
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(f"Computing WAB for {season.display_name}")
        self.stdout.write(f"{'='*80}\n")
        
        # Get national averages
        try:
            nat_avg = NationalAverages.objects.get(season=season)
            nat_avg_ortg = nat_avg.avg_ortg
            hca_points = nat_avg.hca_points if nat_avg.hca_points else 1.85
            sigma = nat_avg.prediction_sigma if nat_avg.prediction_sigma else 11.08
        except NationalAverages.DoesNotExist:
            self.stderr.write(f"❌ National averages not found for {season.display_name}")
            self.stderr.write("   Run 'compute_national_averages' first")
            return
        
        # Get all teams with ratings (sorted by adj_em descending)
        # IMPORTANT: Use ALL D1 teams, never filtered by conference
        all_teams = TeamSeasonRatings.objects.filter(
            season=season
        ).select_related('team').order_by('-adj_em')
        
        total_teams = all_teams.count()
        
        if total_teams < 45:
            self.stderr.write(f"❌ Need at least 45 teams to define Bubble Team, found {total_teams}")
            return
        
        # Identify Bubble Team (#45 ranked by adj_em)
        bubble_team_rating = all_teams[44]  # 0-indexed, so 44 = 45th team
        bubble_team = bubble_team_rating.team
        
        self.stdout.write(f"📊 Bubble Team (#45): {bubble_team.name}")
        self.stdout.write(f"   • Adj EM: {bubble_team_rating.adj_em:.2f}")
        self.stdout.write(f"   • Adj O: {bubble_team_rating.adj_o:.2f}")
        self.stdout.write(f"   • Adj D: {bubble_team_rating.adj_d:.2f}\n")
        
        self.stdout.write(f"Computing WAB for {total_teams} teams...\n")
        
        wab_results = []
        teams_updated = 0
        teams_skipped = 0
        
        with transaction.atomic():
            for i, team_rating in enumerate(all_teams, 1):
                team = team_rating.team
                
                # Get team's completed games
                team_games = TeamGameStats.objects.filter(
                    team=team,
                    game__season_year=season_year,
                    game__status='final'
                ).select_related('game', 'opponent')
                
                games_count = team_games.count()
                
                if games_count == 0:
                    teams_skipped += 1
                    continue
                
                # Compute WAB
                try:
                    wab = compute_wab_for_team(
                        team_ratings=team_rating,
                        bubble_ratings=bubble_team_rating,
                        team_games=team_games,
                        nat_avg_ortg=nat_avg_ortg,
                        hca_points=hca_points,
                        sigma=sigma
                    )
                    
                    # Update TeamSeasonRatings with WAB
                    team_rating.wab = wab
                    team_rating.save(update_fields=['wab'])
                    
                    # Also update TeamSeasonStats with WAB (for checklist)
                    try:
                        team_stats = TeamSeasonStats.objects.get(team=team, season=season)
                        team_stats.wab = wab
                        team_stats.save(update_fields=['wab'])
                    except TeamSeasonStats.DoesNotExist:
                        pass
                    
                    teams_updated += 1
                    
                    wab_results.append({
                        'team': team.name,
                        'wab': wab,
                        'games': games_count
                    })
                    
                except Exception as e:
                    self.stderr.write(f"❌ Error computing WAB for {team.name}: {e}")
                    teams_skipped += 1
                
                # Progress indicator
                if i % 50 == 0:
                    self.stdout.write(f"  Processed {i}/{total_teams} teams...")
        
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(f"✅ WAB Computation Complete")
        self.stdout.write(f"{'='*80}")
        self.stdout.write(f"  • Teams updated: {teams_updated}")
        self.stdout.write(f"  • Teams skipped: {teams_skipped}")
        
        # Show top 10 and bottom 10 WAB values
        if wab_results:
            wab_results.sort(key=lambda x: x['wab'], reverse=True)
            
            self.stdout.write(f"\n📈 TOP 10 WAB TEAMS:")
            for i, result in enumerate(wab_results[:10], 1):
                self.stdout.write(f"  {i:2d}. {result['team']:<30} WAB: {result['wab']:>6.2f} ({result['games']} games)")
            
            self.stdout.write(f"\n📉 BOTTOM 10 WAB TEAMS:")
            for i, result in enumerate(wab_results[-10:], 1):
                self.stdout.write(f"  {i:2d}. {result['team']:<30} WAB: {result['wab']:>6.2f} ({result['games']} games)")
        
        self.stdout.write(f"\n{'='*80}\n")
