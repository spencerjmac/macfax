"""
Management command: fetch_net_rankings
Fetches actual NCAA NET rankings from ncaa-api and updates database

Usage:
    python manage.py fetch_net_rankings --season 2026
"""

import requests
import yaml
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Season, Team, TeamSeasonRatings


class Command(BaseCommand):
    help = 'Fetch and populate actual NCAA NET rankings from ncaa-api'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (e.g., 2026)'
        )
    
    def load_name_mappings(self):
        """Load NCAA team name mappings from YAML file"""
        mappings_file = Path(__file__).resolve().parent.parent.parent.parent / 'ncaa_team_name_mappings.yml'
        
        if mappings_file.exists():
            with open(mappings_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data.get('ncaa', {})
        return {}
    
    def find_team(self, ncaa_school_name, name_mappings):
        """Find team in database by NCAA school name"""
        # First try direct mapping
        if ncaa_school_name in name_mappings:
            mapped_name = name_mappings[ncaa_school_name]
            try:
                return Team.objects.get(name=mapped_name)
            except Team.DoesNotExist:
                pass
        
        # Try exact match
        try:
            return Team.objects.get(name=ncaa_school_name)
        except Team.DoesNotExist:
            pass
        
        # Try case-insensitive match
        try:
            return Team.objects.get(name__iexact=ncaa_school_name)
        except Team.DoesNotExist:
            pass
        
        return None
    
    def handle(self, *args, **options):
        season_year = options['season']
        
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(f"❌ Season {season_year} not found")
            return
        
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(f"Fetching NCAA NET Rankings for {season.display_name}")
        self.stdout.write(f"Source: ncaa-api.henrygd.me")
        self.stdout.write(f"{'='*80}\n")
        
        # Load name mappings
        name_mappings = self.load_name_mappings()
        self.stdout.write(f"📋 Loaded {len(name_mappings)} team name mappings")
        
        # Fetch NET rankings from API
        api_url = "https://ncaa-api.henrygd.me/rankings/basketball-men/d1/ncaa-mens-basketball-net-rankings"
        
        try:
            self.stdout.write(f"🌐 Fetching from {api_url}...")
            response = requests.get(api_url, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            self.stderr.write(f"❌ Failed to fetch NET rankings: {e}")
            return
        
        # Check if data has rankings
        if 'data' not in data:
            self.stderr.write("❌ No ranking data found in API response")
            return
        
        rankings = data['data']
        self.stdout.write(f"✅ Fetched {len(rankings)} teams")
        self.stdout.write(f"📅 Updated: {data.get('updated', 'Unknown')}\n")
        
        # Process rankings
        updated = 0
        not_found = []
        
        with transaction.atomic():
            for entry in rankings:
                rank = int(entry['Rank'])
                school_name = entry['School']
                
                # Find team in database
                team = self.find_team(school_name, name_mappings)
                
                if team is None:
                    not_found.append((rank, school_name))
                    continue
                
                # Update or create TeamSeasonRatings
                team_rating, created = TeamSeasonRatings.objects.get_or_create(
                    team=team,
                    season=season
                )
                
                team_rating.net_rank = rank
                team_rating.save()
                
                updated += 1
                
                if updated <= 10 or updated % 50 == 0:
                    self.stdout.write(f"  #{rank:3d} {team.name:30s}")
        
        # Summary
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(f"✅ Updated NET rankings for {updated} teams")
        
        if not_found:
            self.stdout.write(f"\n⚠️  {len(not_found)} teams not found in database:")
            for rank, school in not_found[:20]:  # Show first 20
                self.stdout.write(f"  #{rank:3d} {school}")
            if len(not_found) > 20:
                self.stdout.write(f"  ... and {len(not_found) - 20} more")
        
        self.stdout.write(f"{'='*80}\n")
