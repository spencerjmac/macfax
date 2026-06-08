"""
Management command: backfill_ap_polls
Backfills historical Week 6 AP Poll data by parsing sports-reference.com.

Usage:
    python manage.py backfill_ap_polls
    python manage.py backfill_ap_polls --season 2024
"""

import sys
import time
import requests
import pandas as pd
from io import StringIO
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from ncaa.models import Season, TeamSeasonRatings
from ncaa.utils.team_mapping import TeamMapper


class Command(BaseCommand):
    help = "Backfill historical Week 6 AP Poll data from Sports-Reference"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            help="Optional: specific season to backfill (e.g. 2024). Defaults to all past seasons.",
        )

    def handle(self, *args, **options):
        season_arg = options["season"]
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write("BACKFILLING HISTORICAL AP POLLS")
        self.stdout.write(f"{'='*60}\n")

        if season_arg:
            seasons = Season.objects.filter(year=season_arg)
        else:
            current_year = timezone.now().year + 1
            # We filter for seasons where we probably have poll data
            seasons = Season.objects.filter(year__lte=current_year, year__gte=2005).order_by("year")
            
        mapper = TeamMapper(source="ncaa")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        total_updated = 0
        total_missing = []
        
        for season in seasons:
            year = season.year
            url = f"https://www.sports-reference.com/cbb/seasons/{year}-polls.html"
            self.stdout.write(f"\nFetching {year} AP Polls: {url}")
            
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
            except requests.RequestException as e:
                self.stderr.write(self.style.WARNING(f"  Failed to fetch {year} (might not exist): {e}"))
                continue
                
            try:
                tables = pd.read_html(StringIO(resp.text))
                df = tables[0]
            except Exception as e:
                self.stderr.write(self.style.WARNING(f"  Failed to parse tables for {year}: {e}"))
                continue
                
            school_col = df.columns[0]
            
            # Find the Week 6 column (second level is '6' or contains '6')
            week6_cols = [c for c in df.columns if len(c) >= 2 and c[0] == 'Week Poll' and str(c[1]).strip() == '6']
            if not week6_cols:
                self.stderr.write(self.style.WARNING(f"  Could not find 'Week 6' column for {year}."))
                continue
                
            week6_col = week6_cols[0]
            
            data = df[[school_col, week6_col]].copy()
            data.columns = ['School', 'Rank']
            data = data.dropna()
            
            # Convert Rank to numeric, dropping non-numeric (like text headers repeated in SR tables)
            data['Rank'] = pd.to_numeric(data['Rank'], errors='coerce')
            data = data.dropna().sort_values('Rank')
            
            # Ensure it's integers
            data['Rank'] = data['Rank'].astype(int)
            
            season_updated = 0
            
            for _, row in data.iterrows():
                # Clean up SR name noise
                sr_name = str(row['School']).replace('NCAA', '').replace('NIT', '').replace('CBI', '').replace('\xa0', ' ').strip()
                sr_name = sr_name.replace(' State', ' St.')
                if sr_name == 'UNC': sr_name = 'North Carolina'
                if sr_name == 'USC': sr_name = 'Southern California'
                if sr_name == "Saint Mary's": sr_name = "Saint Mary's (CA)"
                
                rank = row['Rank']
                
                # Match team
                team, conf, is_override = mapper.find_team(sr_name, min_confidence=0.88)
                
                if team:
                    ratings_qs = TeamSeasonRatings.all_objects.filter(season=season, team=team)
                    if ratings_qs.exists():
                        ratings_qs.update(ap_poll_week6=rank)
                        season_updated += 1
                        self.stdout.write(f"  #{rank:2d} {team.name} (matched from '{sr_name}')")
                    else:
                        self.stderr.write(self.style.WARNING(f"  TeamSeasonRatings missing for {team.name} in {year}"))
                else:
                    self.stderr.write(self.style.ERROR(f"  UNMATCHED TEAM: #{rank} {sr_name}"))
                    total_missing.append(f"{year} - {sr_name}")
            
            self.stdout.write(self.style.SUCCESS(f"✓ Updated {season_updated} teams for {year}"))
            total_updated += season_updated
            time.sleep(3.5) # Be polite to SR
            
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS(f"Finished. Total ratings updated: {total_updated}"))
        if total_missing:
            self.stdout.write(self.style.ERROR(f"Could not match {len(total_missing)} teams:"))
            for m in total_missing:
                self.stdout.write(f"  - {m}")
        self.stdout.write(f"{'='*60}\n")
