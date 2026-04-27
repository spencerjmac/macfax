"""
Update all NBA team data for a season.

Usage:
  python manage.py update_nba_teams --season 2026
  python manage.py update_nba_teams --season 2026 --skip-ingest
  python manage.py update_nba_teams --season 2024  # backfill example
"""

import sys

from django.core.management.base import CommandError
from django.utils import timezone

from ncaa.management.commands._pipeline_base import BasePipelineCommand

TOTAL_STEPS = 2


class Command(BasePipelineCommand):
    help = "Update all NBA team data for a season (ingest + compute ratings)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--skip-ingest",
            action="store_true",
            help="Skip NBA game ingestion",
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        season_year = options["season"]
        skip_ingest = options["skip_ingest"]

        if season_year < 1947:
            raise CommandError("--season must be a valid NBA season ending year")

        self._header("NBA TEAM DATA", season_year)
        self._run_setup(ncaa=False, nba=True)
        self._ensure_season(season_year)
        steps = []

        if not skip_ingest:
            self._run_step(
                "NBA sync games",
                "nba_sync_games",
                {"season": season_year},
                steps,
                fatal=False,
                label=f"[1/{TOTAL_STEPS}]",
            )
        else:
            self._skip_step("NBA sync games", steps, "Skipped (--skip-ingest)")

        self._run_step(
            "NBA compute ratings",
            "nba_compute_ratings",
            {"season": season_year},
            steps,
            fatal=True,
            label=f"[2/{TOTAL_STEPS}]",
        )

        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        self._print_summary(
            start_time,
            end_time,
            duration,
            steps,
            title="NBA TEAM DATA UPDATE",
        )
        if any(not s[1] for s in steps):
            sys.exit(1)
