"""
Management command: load_tournament_bracket

Loads NCAA Tournament seeds and regions into TeamSeasonRatings.

Usage:
    # Load from a JSON file:
    python manage.py load_tournament_bracket --season 2026 --file bracket.json

    # Clear all tournament data for a season:
    python manage.py load_tournament_bracket --season 2026 --clear

JSON file format (team slug or exact team name accepted):
[
    {"team": "duke",          "seed": 1, "region": "South"},
    {"team": "kansas",        "seed": 1, "region": "Midwest"},
    {"team": "auburn",        "seed": 1, "region": "East"},
    {"team": "houston",       "seed": 1, "region": "West"},
    ...
]

Valid regions: South, East, West, Midwest
Valid seeds:   1-16

The "team" field is matched first against team slug, then team name (case-insensitive).
"""

import json
import os

from django.core.management.base import BaseCommand, CommandError

from ncaa.models import Season, Team, TeamSeasonRatings

VALID_REGIONS = {'South', 'East', 'West', 'Midwest'}


class Command(BaseCommand):
    help = 'Load NCAA Tournament seeds and regions into TeamSeasonRatings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            default=2026,
            help='Season year (default: 2026)',
        )
        parser.add_argument(
            '--file',
            type=str,
            dest='filepath',
            help='Path to bracket JSON file',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all tournament data for the season and exit',
        )

    def handle(self, *args, **options):
        season_year = options['season']

        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(f'NCAA TOURNAMENT BRACKET LOADER — Season {season_year}')
        self.stdout.write(f'{"="*60}\n')

        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            raise CommandError(f'Season {season_year} not found in the database.')

        # --clear flag: wipe all tournament data and exit
        if options['clear']:
            cleared = TeamSeasonRatings.objects.filter(season=season).update(
                tournament_seed=None,
                tournament_region=None,
            )
            self.stdout.write(
                self.style.SUCCESS(f'Cleared tournament data from {cleared} team records.')
            )
            return

        if not options['filepath']:
            raise CommandError('You must provide --file <path-to-bracket.json> or use --clear.')

        filepath = options['filepath']
        if not os.path.exists(filepath):
            raise CommandError(f'File not found: {filepath}')

        with open(filepath, 'r') as f:
            try:
                bracket = json.load(f)
            except json.JSONDecodeError as e:
                raise CommandError(f'Invalid JSON in bracket file: {e}')

        if not isinstance(bracket, list):
            raise CommandError('Bracket JSON must be a top-level array of team objects.')

        # Clear all existing tournament data for this season before loading
        TeamSeasonRatings.objects.filter(season=season).update(
            tournament_seed=None,
            tournament_region=None,
        )
        self.stdout.write('Cleared existing tournament data for season.')

        # Build a lookup: slug -> ratings, and name_lower -> ratings
        all_ratings = {
            r.team.slug: r
            for r in TeamSeasonRatings.objects.filter(season=season).select_related('team')
        }
        name_lookup = {r.team.name.lower(): r for r in all_ratings.values()}

        updated = 0
        not_found = []
        errors = []

        for entry in bracket:
            team_key = str(entry.get('team', '')).strip()
            seed = entry.get('seed')
            region = entry.get('region', '').strip().capitalize()

            # Validate
            if not team_key:
                errors.append(f'Entry missing "team" field: {entry}')
                continue
            if seed is None or not (1 <= int(seed) <= 16):
                errors.append(f'Invalid seed for {team_key}: {seed}')
                continue
            if region not in VALID_REGIONS:
                errors.append(
                    f'Invalid region for {team_key}: "{region}". '
                    f'Must be one of: {", ".join(sorted(VALID_REGIONS))}'
                )
                continue

            # Match team: try slug first, then lowercase name
            ratings = all_ratings.get(team_key.lower()) or name_lookup.get(team_key.lower())

            if not ratings:
                not_found.append(team_key)
                continue

            ratings.tournament_seed = int(seed)
            ratings.tournament_region = region
            ratings.save(update_fields=['tournament_seed', 'tournament_region'])
            updated += 1
            self.stdout.write(f'  [{region:8s}] #{seed:2d}  {ratings.team.name}')

        # Summary
        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(self.style.SUCCESS(f'Loaded {updated} tournament teams.'))

        if not_found:
            self.stdout.write(self.style.WARNING(f'\n{len(not_found)} teams not found in DB:'))
            for name in not_found:
                self.stdout.write(f'  - {name}')
            self.stdout.write(
                '\nTip: Use the team slug (e.g. "north-carolina" not "North Carolina").\n'
                'Run: python manage.py shell -c '
                '"from ncaa.models import Team; [print(t.slug, t.name) for t in Team.objects.filter(is_d1=True).order_by(\'name\')]"'
            )

        if errors:
            self.stdout.write(self.style.ERROR(f'\n{len(errors)} validation errors:'))
            for err in errors:
                self.stdout.write(f'  - {err}')

        if not_found or errors:
            self.stdout.write(
                self.style.WARNING(
                    f'\nWARNING: {len(not_found) + len(errors)} entries were skipped. '
                    'Re-run after fixing to ensure full bracket is loaded.'
                )
            )
