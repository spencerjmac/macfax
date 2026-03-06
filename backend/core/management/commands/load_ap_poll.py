"""
Management command: load_ap_poll
Loads AP Poll Week 6 rankings from CSV into TeamSeasonRatings.

Usage:
    python manage.py load_ap_poll --season 2026
    python manage.py load_ap_poll --season 2026 --csv /path/to/ap_poll_week6.csv
"""

import csv
import os

from django.core.management.base import BaseCommand, CommandError

from core.models import Season, TeamSeasonRatings

# Default CSV location (relative to this file: backend/mappings/)
DEFAULT_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    'mappings',
    'ap_poll_week6.csv',
)


class Command(BaseCommand):
    help = 'Load AP Poll Week 6 rankings from CSV into TeamSeasonRatings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            default=2026,
            help='Season year (default: 2026)',
        )
        parser.add_argument(
            '--csv',
            type=str,
            default=DEFAULT_CSV,
            help=f'Path to AP Poll CSV file (default: mappings/ap_poll_week6.csv)',
        )

    def handle(self, *args, **options):
        season_year = options['season']
        csv_path = options['csv']

        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(f'LOADING AP POLL WEEK 6 — Season {season_year}')
        self.stdout.write(f'{"="*60}\n')

        if not os.path.exists(csv_path):
            raise CommandError(f'CSV file not found: {csv_path}')

        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            raise CommandError(f'Season {season_year} not found')

        # Clear existing AP poll data for this season
        cleared = TeamSeasonRatings.objects.filter(
            season=season, ap_poll_week6__isnull=False
        ).update(ap_poll_week6=None)
        if cleared:
            self.stdout.write(f'Cleared {cleared} existing AP poll entries')

        updated = 0
        not_found = []

        with open(csv_path, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rank = int(row['rank'])
                team_name = row['team_kenpom'].strip()

                try:
                    ratings = TeamSeasonRatings.objects.get(
                        season=season, team__name=team_name
                    )
                    ratings.ap_poll_week6 = rank
                    ratings.save(update_fields=['ap_poll_week6'])
                    updated += 1
                    self.stdout.write(f'  #{rank:2d}  {team_name}')
                except TeamSeasonRatings.DoesNotExist:
                    not_found.append(team_name)

        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(self.style.SUCCESS(f'✓ Updated {updated} teams'))

        if not_found:
            self.stdout.write(
                self.style.WARNING(f'⚠ Teams not found in DB: {not_found}')
            )
            self.stdout.write(
                self.style.WARNING('  Check team_kenpom names in CSV match team names in DB.')
            )

        self.stdout.write(f'{"="*60}\n')
