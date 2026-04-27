"""
Update all NCAA player data for a season.

Dependency:
  NCAA team data must already be computed for the season before this runs.
  In particular, compute_national_averages and compute_adjusted_ratings must
  have completed successfully.

Usage:
  python manage.py update_ncaa_players --season 2026
  python manage.py update_ncaa_players --season 2026 --skip-ingest
  python manage.py update_ncaa_players --season 2026 --workers 4
  python manage.py update_ncaa_players --season 2026 --rapm-years 2024 2025 2026
  python manage.py update_ncaa_players --season 2021  # backfill example
"""

import sys

from django.core.management.base import CommandError
from django.utils import timezone

from ncaa.management.commands._pipeline_base import BasePipelineCommand

TOTAL_STEPS = 6


class Command(BasePipelineCommand):
    help = "Update all NCAA player data for a season (ingest + compute)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--skip-ingest",
            action="store_true",
            help="Skip player gamelog + PBP ingestion",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            help="Parallel workers for sync_ncaa_player_gamelogs and sync_ncaa_pbp",
        )
        parser.add_argument(
            "--rapm-years",
            nargs="+",
            type=int,
            default=None,
            help="Years to pool for RAPM; omitted means single-season mode",
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        season_year = options["season"]
        skip_ingest = options["skip_ingest"]
        workers = int(options.get("workers", 1))

        if workers < 1:
            raise CommandError("--workers must be 1 or greater")

        self._header("NCAA PLAYER DATA", season_year)
        self._run_setup(ncaa=True, nba=False)
        self._ensure_season(season_year)
        steps = []

        if not skip_ingest:
            self._run_step(
                "Sync NCAA player gamelogs",
                "sync_ncaa_player_gamelogs",
                {"season": season_year, "workers": workers, "skip_done": True},
                steps,
                fatal=False,
                label=f"[1/{TOTAL_STEPS}]",
            )
        else:
            self._skip_step(
                "Sync NCAA player gamelogs",
                steps,
                "Skipped (--skip-ingest)",
            )

        self._run_step(
            "Compute NCAA player season stats",
            "compute_ncaa_player_season_stats",
            {"season": season_year},
            steps,
            fatal=True,
            label=f"[2/{TOTAL_STEPS}]",
        )

        if not skip_ingest:
            self._run_step(
                "Sync NCAA PBP stints",
                "sync_ncaa_pbp",
                {"season": season_year, "workers": workers},
                steps,
                fatal=False,
                label=f"[3/{TOTAL_STEPS}]",
            )
        else:
            self._skip_step(
                "Sync NCAA PBP stints",
                steps,
                "Skipped (--skip-ingest)",
            )

        self._run_step(
            "Compute NCAA player impact",
            "compute_ncaa_player_impact",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[4/{TOTAL_STEPS}]",
        )

        bpr_kwargs = {"season": season_year}
        if options["rapm_years"]:
            bpr_kwargs["rapm_years"] = options["rapm_years"]

        self._run_step(
            "Compute NCAA BPR",
            "compute_ncaa_bpr",
            bpr_kwargs,
            steps,
            fatal=False,
            label=f"[5/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute NCAA player FFI",
            "compute_player_ffi",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[6/{TOTAL_STEPS}]",
        )

        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        self._print_summary(
            start_time,
            end_time,
            duration,
            steps,
            title="NCAA PLAYER DATA UPDATE",
        )
        if any(not s[1] for s in steps):
            sys.exit(1)
