"""
Derive REPLACEMENT_FILL_OBPR / REPLACEMENT_FILL_DBPR empirically.

The scenario projection view pads incomplete rosters (total minutes share
< 5.0) with a synthetic replacement-level player. This command derives what
"replacement level" means from data: the minutes-weighted mean projected
obpr/dbpr of deep-bench players (rotation_rank > 8) for a given source season.

Usage:
    python manage.py derive_replacement_fill --season 2026

The printed values are hardcoded into
ncaa/analytics/player_value/team_projection/constants.py as
REPLACEMENT_FILL_OBPR / REPLACEMENT_FILL_DBPR.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from ncaa.models import PlayerSeasonProjection, Season


class Command(BaseCommand):
    help = (
        "Derive replacement-level fill constants (minutes-weighted mean "
        "projected obpr/dbpr of rotation_rank > 8 players) for a season."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True,
            help="Source season year (from_season) to derive from",
        )

    def handle(self, *args, **options):
        year = options["season"]
        try:
            season = Season.objects.get(year=year)
        except Season.DoesNotExist:
            raise CommandError(f"Season {year} not found")

        pool = list(
            PlayerSeasonProjection.objects.filter(
                from_season=season,
                rotation_rank__gt=8,
                minutes_share_p2__isnull=False,
                projected_obpr__isnull=False,
                projected_dbpr__isnull=False,
            ).values_list("minutes_share_p2", "projected_obpr", "projected_dbpr")
        )

        n = len(pool)
        if n == 0:
            raise CommandError(f"No qualifying deep-bench rows for season {year}")

        total_share = sum(share for share, _, _ in pool)
        if total_share <= 0:
            raise CommandError(
                f"Deep-bench pool for season {year} has zero total minutes share"
            )

        obpr = sum(share * o for share, o, _ in pool) / total_share
        dbpr = sum(share * d for share, _, d in pool) / total_share

        self.stdout.write(f"Season {year} — deep-bench pool (rotation_rank > 8)")
        self.stdout.write(f"  N players           : {n}")
        self.stdout.write(f"  Total minutes share : {total_share:.3f}")
        self.stdout.write(f"  REPLACEMENT_FILL_OBPR = {obpr:.4f}")
        self.stdout.write(f"  REPLACEMENT_FILL_DBPR = {dbpr:.4f}")
        self.stdout.write(f"  (sum / fill BPR       = {obpr + dbpr:.4f})")
