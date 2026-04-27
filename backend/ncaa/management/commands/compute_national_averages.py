"""
Management command: compute_national_averages
Computes possession-weighted national averages for adjusted ratings

Usage:
    python manage.py compute_national_averages --season 2026
"""

import logging
from django.core.management.base import BaseCommand
from django.db.models import Sum

from ncaa.models import Season, TeamGameStats, NationalAverages

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Compute national averages from all game stats'
    
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
            self.stderr.write(f"Season {season_year} not found")
            return
        
        self.stdout.write(f"\nComputing national averages for {season.display_name}...")
        
        # Get all completed games
        game_stats = TeamGameStats.objects.filter(
            game__season_year=season_year,
            game__status='final'
        )
        
        total_games = game_stats.values('game').distinct().count()
        
        if total_games == 0:
            self.stderr.write("No completed games found")
            return
        
        self.stdout.write(f"Processing {game_stats.count()} team game stats from {total_games} games...")
        
        # Compute totals
        total_pts = 0
        total_possessions = 0.0
        total_fgm = 0
        total_fga = 0
        total_fg3m = 0
        total_tov = 0
        total_oreb = 0
        total_opp_dreb = 0
        total_fta = 0
        total_minutes = 0
        
        for stat in game_stats:
            poss = stat.poss_game
            if poss:
                total_pts += stat.pts
                total_possessions += poss
                total_fgm += stat.fgm
                total_fga += stat.fga
                total_fg3m += stat.fg3m
                total_tov += stat.tov
                total_oreb += stat.oreb
                total_fta += stat.fta
                total_minutes += stat.game_minutes
                
                # Get opponent dreb
                opp = stat._get_opp_stats()
                if opp:
                    total_opp_dreb += opp.dreb
        
        # Compute averages (possession-weighted)
        avg_ortg = (100 * total_pts / total_possessions) if total_possessions > 0 else 0.0
        avg_pace = (40 * total_possessions / total_minutes) if total_minutes > 0 else 0.0
        
        # Four Factors
        avg_efg = ((total_fgm + 0.5 * total_fg3m) / total_fga * 100) if total_fga > 0 else 0.0
        avg_tov = (total_tov / total_possessions * 100) if total_possessions > 0 else 0.0
        avg_orb = (total_oreb / (total_oreb + total_opp_dreb) * 100) if (total_oreb + total_opp_dreb) > 0 else 0.0
        avg_ftr = (total_fta / total_fga * 100) if total_fga > 0 else 0.0
        
        # Save to database
        nat_avg, created = NationalAverages.objects.update_or_create(
            season=season,
            defaults={
                'avg_ortg': round(avg_ortg, 4),
                'avg_pace': round(avg_pace, 4),
                'avg_efg': round(avg_efg, 4),
                'avg_tov': round(avg_tov, 4),
                'avg_orb': round(avg_orb, 4),
                'avg_ftr': round(avg_ftr, 4),
                'total_possessions': total_possessions,
                'total_games': total_games,
            }
        )
        
        action = "Created" if created else "Updated"
        self.stdout.write(f"\n{action} National Averages:")
        self.stdout.write("=" * 60)
        self.stdout.write(f"  ORtg:      {avg_ortg:.2f}")
        self.stdout.write(f"  Pace:      {avg_pace:.2f}")
        self.stdout.write(f"  eFG%:      {avg_efg:.2f}%")
        self.stdout.write(f"  TOV%:      {avg_tov:.2f}%")
        self.stdout.write(f"  ORB%:      {avg_orb:.2f}%")
        self.stdout.write(f"  FTR:       {avg_ftr:.2f}%")
        self.stdout.write(f"\n  Total Possessions: {total_possessions:,.0f}")
        self.stdout.write(f"  Total Games:       {total_games:,}")
        self.stdout.write("=" * 60)
