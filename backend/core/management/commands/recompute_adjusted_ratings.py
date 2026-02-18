"""
Django management command to recompute AOR/ADR/AEM ratings with proper z-score scaling

Usage:
    python manage.py recompute_adjusted_ratings --season 2026
"""

import numpy as np
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Season, TeamSeasonStats


class Command(BaseCommand):
    help = 'Recompute AOR/ADR/AEM ratings with proper 0-100 z-score scaling'
    
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
        self.stdout.write(self.style.SUCCESS(f"RECOMPUTING ADJUSTED RATINGS FOR SEASON {season_year}"))
        self.stdout.write(f"{'='*60}\n")
        
        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(f"ERROR: Season {season_year} not found")
            return
        
        # Get all teams in this season
        teams = TeamSeasonStats.objects.filter(season=season).select_related('team')
        count = teams.count()
        
        if count == 0:
            self.stderr.write("ERROR: No teams found for this season")
            return
        
        self.stdout.write(f"Found {count} teams\n")
        
        # Step 1: Copy KenPom values to AOR/ADR/AEM (temporary until we have game data)
        self.stdout.write(self.style.SUCCESS("[1/3] Setting base ratings from KenPom data..."))
        
        for team in teams:
            team.aor = team.adj_o
            team.adr = team.adj_d
            team.aem = team.adj_em
        
        # Bulk update
        TeamSeasonStats.objects.bulk_update(teams, ['aor', 'adr', 'aem'])
        self.stdout.write(f"  ✓ Updated {count} teams with base ratings")
        
        # Step 2: Compute 0-100 ratings via z-score mapping
        self.stdout.write(self.style.SUCCESS("\n[2/3] Computing 0-100 z-score ratings..."))
        
        # Get all values as numpy arrays
        teams_list = list(teams)
        aor_values = np.array([t.aor for t in teams_list])
        adr_values = np.array([t.adr for t in teams_list])
        aem_values = np.array([t.aem for t in teams_list])
        
        # Compute national average for defense inversion
        nat_avg = aor_values.mean()  # Use offensive average as baseline
        
        # AOR_100: higher is better
        aor_mean = aor_values.mean()
        aor_std = aor_values.std()
        aor_z = (aor_values - aor_mean) / aor_std
        aor_100 = np.clip(50 + 15 * aor_z, 0, 100)
        
        # ADR_100: lower is better, so invert via "defense plus"
        defplus = nat_avg - adr_values
        defplus_mean = defplus.mean()
        defplus_std = defplus.std()
        defplus_z = (defplus - defplus_mean) / defplus_std
        adr_100 = np.clip(50 + 15 * defplus_z, 0, 100)
        
        # NET_100: higher is better
        aem_mean = aem_values.mean()
        aem_std = aem_values.std()
        aem_z = (aem_values - aem_mean) / aem_std
        net_100 = np.clip(50 + 15 * aem_z, 0, 100)
        
        # Update teams with 100-scale ratings
        for i, team in enumerate(teams_list):
            team.aor_100 = round(float(aor_100[i]), 2)
            team.adr_100 = round(float(adr_100[i]), 2)
            team.net_100 = round(float(net_100[i]), 2)
        
        TeamSeasonStats.objects.bulk_update(teams_list, ['aor_100', 'adr_100', 'net_100'])
        
        self.stdout.write(f"  ✓ Z-score statistics:")
        self.stdout.write(f"    • AOR: μ={aor_mean:.2f}, σ={aor_std:.2f}")
        self.stdout.write(f"    • ADR: μ={adr_values.mean():.2f}, σ={adr_values.std():.2f}")
        self.stdout.write(f"    • Net: μ={aem_mean:.2f}, σ={aem_std:.2f}")
        
        # Step 3: Compute ranks
        self.stdout.write(self.style.SUCCESS("\n[3/3] Computing ranks..."))
        
        # Rank by AOR (desc: higher is better)
        sorted_by_aor = sorted(teams_list, key=lambda t: t.aor, reverse=True)
        for rank, team in enumerate(sorted_by_aor, 1):
            team.rank_aor = rank
        
        # Rank by ADR (asc: lower is better)
        sorted_by_adr = sorted(teams_list, key=lambda t: t.adr)
        for rank, team in enumerate(sorted_by_adr, 1):
            team.rank_adr = rank
        
        # Rank by AEM (desc: higher is better)
        sorted_by_aem = sorted(teams_list, key=lambda t: t.aem, reverse=True)
        for rank, team in enumerate(sorted_by_aem, 1):
            team.rank_aem = rank
        
        TeamSeasonStats.objects.bulk_update(teams_list, ['rank_aor', 'rank_adr', 'rank_aem'])
        self.stdout.write(f"  ✓ Computed ranks for {count} teams")
        
        # Summary
        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS("COMPUTATION COMPLETE"))
        self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
        
        # Show top 5 teams
        top_teams = sorted(teams_list, key=lambda t: t.aem, reverse=True)[:5]
        
        self.stdout.write("\nTop 5 Teams by Net Rating:")
        self.stdout.write("-" * 80)
        self.stdout.write(f"{'Rank':<6} {'Team':<25} {'AOR':<8} {'ADR':<8} {'Net':<8} {'O/100':<7} {'D/100':<7} {'N/100':<7}")
        self.stdout.write("-" * 80)
        
        for team in top_teams:
            self.stdout.write(
                f"#{team.rank_aem:<5} {team.team.name[:24]:<25} "
                f"{team.aor:<8.2f} {team.adr:<8.2f} {team.aem:<8.2f} "
                f"{team.aor_100:<7.1f} {team.adr_100:<7.1f} {team.net_100:<7.1f}"
            )
        
        self.stdout.write(f"\n✅ Done! Refresh your browser to see the updated ratings.\n")
