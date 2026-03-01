"""
Management command: populate_net_rank
Sets net_rank = rank_adj_em for all teams as a proxy for NCAA NET ranking

Usage:
    python manage.py populate_net_rank --season 2026
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Season, TeamSeasonRatings


class Command(BaseCommand):
    help = 'Populate net_rank using rank_adj_em as proxy'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (e.g., 2026)'
        )
    
    def handle(self, *args, **options):
        season_year = options['season']
        
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(f"❌ Season {season_year} not found")
            return
        
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(f"Populating NET ranks for {season.display_name}")
        self.stdout.write(f"Using rank_adj_em as proxy for NCAA NET ranking")
        self.stdout.write(f"{'='*80}\n")
        
        # Get all teams with ratings
        all_teams = TeamSeasonRatings.objects.filter(season=season)
        total_teams = all_teams.count()
        
        if total_teams == 0:
            self.stderr.write(f"❌ No teams found for {season_year}")
            return
        
        updated = 0
        with transaction.atomic():
            for team_rating in all_teams:
                team_rating.net_rank = team_rating.rank_adj_em
                team_rating.save(update_fields=['net_rank'])
                updated += 1
        
        self.stdout.write(f"✅ Updated {updated} teams with NET ranks\n")
        
        # Show some examples
        self.stdout.write("Sample NET Rankings:")
        sample_teams = TeamSeasonRatings.objects.filter(
            season=season,
            rank_adj_em__lte=10
        ).order_by('rank_adj_em')[:10]
        
        for team in sample_teams:
            self.stdout.write(
                f"  #{team.net_rank:3d}. {team.team.name:<30} (AdjEM Rank: #{team.rank_adj_em})"
            )
        
        self.stdout.write(f"\n{'='*80}\n")
