"""
Update all NBA player data for a season.

Dependency:
  NBA team data must already be computed for the season. Run update_nba_teams
  first so games, team logs, and ratings are available.

Usage:
  python manage.py update_nba_players --season 2026
  python manage.py update_nba_players --season 2026 --skip-ingest
  python manage.py update_nba_players --season 2026 --workers 4
  python manage.py update_nba_players --season 2024  # backfill example
"""

import sys

from django.core.management.base import CommandError
from django.utils import timezone

from core.management.commands._pipeline_base import BasePipelineCommand

TOTAL_STEPS = 3


class Command(BasePipelineCommand):
    help = "Update all NBA player data for a season (ingest + compute stats + advanced)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--skip-ingest",
            action="store_true",
            help="Skip NBA player box score ingestion",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            help="Parallel workers for nba_sync_team_logs",
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        season_year = options["season"]
        skip_ingest = options["skip_ingest"]
        workers = int(options.get("workers", 1))

        if workers < 1:
            raise CommandError("--workers must be 1 or greater")

        self._header("NBA PLAYER DATA", season_year)
        self._run_setup(ncaa=False, nba=True)
        self._ensure_season(season_year)
        steps = []

        if not skip_ingest:
            self._run_step(
                "NBA sync player box scores",
                "nba_sync_team_logs",
                {"season": season_year, "workers": workers},
                steps,
                fatal=False,
                label=f"[1/{TOTAL_STEPS}]",
            )
        else:
            self._skip_step(
                "NBA sync player box scores",
                steps,
                "Skipped (--skip-ingest)",
            )

        self._run_step(
            "NBA compute player stats",
            "nba_compute_player_stats",
            {"season": season_year},
            steps,
            fatal=True,
            label=f"[2/{TOTAL_STEPS}]",
        )
        self._run_step(
            "NBA sync player advanced",
            "nba_sync_player_advanced",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[3/{TOTAL_STEPS}]",
        )

        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        self._print_summary(
            start_time,
            end_time,
            duration,
            steps,
            title="NBA PLAYER DATA UPDATE",
        )
        if any(not s[1] for s in steps):
            sys.exit(1)
