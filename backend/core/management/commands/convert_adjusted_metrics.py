"""
Django management command to convert existing adj_o/adj_d/adj_em to AOR/ADR/AEM

This is a temporary solution to populate the new fields using existing KenPom data
so the metrics show on the website immediately, without waiting for game-level data.

Usage:
    python manage.py convert_adjusted_metrics --season 2026
"""

import numpy as np
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Season, TeamSeasonStats


def compute_z_score_rating(values, invert=False):
    """
    Convert array of values to 0-100 rating via z-score mapping.
    rating = clamp(50 + 15 * z_score, 0, 100)
    """
    arr = np.array([v for v in values if v is not None])
    if len(arr) == 0:
        return []
    
    if invert:
        # For defense: lower is better, so invert
        nat_avg = arr.mean()
        arr = nat_avg - arr
    
    mean = arr.mean()
    std = arr.std()
    
    if std == 0:
        return [50.0] * len(arr)
    
    z_scores = (arr - mean) / std
    ratings = 50 + 15 * z_scores
    ratings = np.clip(ratings, 0, 100)
    
    return ratings.tolist()


class Command(BaseCommand):
    help = 'Convert existing adj_o/adj_d/adj_em to AOR/ADR/AEM for immediate display'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (e.g., 2026 for 2025-26 season)'
        )
    
    def handle(self, *args, **options):
        season_year = options['season']
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"CONVERTING ADJUSTED METRICS FOR SEASON {season_year}")
        self.stdout.write(f"{'='*60}\n")
        
        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(f"ERROR: Season {season_year} not found")
            return
        
        # Get all teams with stats
        teams = TeamSeasonStats.objects.filter(season=season).select_related('team')
        
        if teams.count() == 0:
            self.stderr.write("ERROR: No teams found for this season")
            return
        
        self.stdout.write(f"Found {teams.count()} teams\n")
        
        # Step 1: Copy adj_o/adj_d/adj_em to aor/adr/aem
        self.stdout.write(self.style.SUCCESS("[1/4] Copying adjusted metrics..."))
        
        aor_values = []
        adr_values = []
        aem_values = []
        team_ids = []
        
        for team in teams:
            team.aor = team.adj_o
            team.adr = team.adj_d
            team.aem = team.adj_em
            
            aor_values.append(team.adj_o)
            adr_values.append(team.adj_d)
            aem_values.append(team.adj_em)
            team_ids.append(team.id)
        
        self.stdout.write(f"  ✓ Copied {len(aor_values)} teams")
        
        # Step 2: Compute 0-100 ratings
        self.stdout.write(self.style.SUCCESS("\n[2/4] Computing 0-100 ratings..."))
        
        # AOR_100: higher is better
        aor_100_list = compute_z_score_rating(aor_values, invert=False)
        
        # ADR_100: lower ADR is better, so invert
        adr_100_list = compute_z_score_rating(adr_values, invert=True)
        
        # NET_100: higher is better
        net_100_list = compute_z_score_rating(aem_values, invert=False)
        
        # Assign back to teams
        for i, team in enumerate(teams):
            team.aor_100 = round(aor_100_list[i], 2)
            team.adr_100 = round(adr_100_list[i], 2)
            team.net_100 = round(net_100_list[i], 2)
        
        self.stdout.write("  ✓ Computed 0-100 ratings")
        
        # Step 3: Compute ranks
        self.stdout.write(self.style.SUCCESS("\n[3/4] Computing ranks..."))
        
        # Create list of (team, aor, adr, aem) for ranking
        team_data = [(team, team.aor, team.adr, team.aem) for team in teams]
        
        # Rank by AOR (desc: higher is better)
        team_data_aor = sorted(team_data, key=lambda x: x[1], reverse=True)
        for rank, (team, _, _, _) in enumerate(team_data_aor, 1):
            team.rank_aor = rank
        
        # Rank by ADR (asc: lower is better)
        team_data_adr = sorted(team_data, key=lambda x: x[2])
        for rank, (team, _, _, _) in enumerate(team_data_adr, 1):
            team.rank_adr = rank
        
        # Rank by AEM (desc: higher is better)
        team_data_aem = sorted(team_data, key=lambda x: x[3], reverse=True)
        for rank, (team, _, _, _) in enumerate(team_data_aem, 1):
            team.rank_aem = rank
        
        self.stdout.write("  ✓ Computed ranks")
        
        # Step 4: Save to database
        self.stdout.write(self.style.SUCCESS("\n[4/4] Saving to database..."))
        
        with transaction.atomic():
            for team in teams:
                team.save()
        
        self.stdout.write(f"  ✓ Updated {teams.count()} teams")
        
        # Summary
        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS("CONVERSION COMPLETE"))
        self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
        
        # Display top 10 teams by Net Rating
        top_teams = sorted(teams, key=lambda x: x.aem, reverse=True)[:10]
        
        self.stdout.write("\nTop 10 Teams by Net Rating (AEM):")
        self.stdout.write("-" * 90)
        self.stdout.write(f"{'Rank':<6} {'Team':<30} {'AOR':<10} {'ADR':<10} {'Net':<10} {'Net_100':<10}")
        self.stdout.write("-" * 90)
        
        for team in top_teams:
            self.stdout.write(
                f"{team.rank_aem:<6} {team.team.name:<30} "
                f"{team.aor:<10.2f} {team.adr:<10.2f} "
                f"{team.aem:<10.2f} {team.net_100:<10.2f}"
            )
        
        self.stdout.write("\n✅ Done! The new metrics are now visible on the website.\n")
        self.stdout.write("Note: These use existing KenPom data (adj_o/adj_d).")
        self.stdout.write("Run compute_adjusted_ratings.py later for game-level calculations.\n")
