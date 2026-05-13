"""
Management command: update_nba_all_seasons
Runs the complete NBA data pipeline for multiple seasons in a loop.

This is useful for backfilling historical NBA data or updating all seasons
at once. Each season is updated sequentially using update_nba_all.

Usage
─────
  # Update seasons 2010-2026
  python manage.py update_nba_all_seasons --start-season 2010 --end-season 2026

  # Update seasons 2010-2026 with 4 workers per season
  python manage.py update_nba_all_seasons --start-season 2010 --end-season 2026 --workers 4

  # Update specific seasons only (skip others)
  python manage.py update_nba_all_seasons --seasons 2020 2021 2022 2023 2024 2025 2026

  # Update and include play-by-play (takes much longer)
  python manage.py update_nba_all_seasons --start-season 2010 --end-season 2026 --with-pbp

  # Update and skip ingest (only recompute)
  python manage.py update_nba_all_seasons --start-season 2010 --end-season 2026 --skip-ingest
"""

import sys

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.utils import timezone


class Command(BaseCommand):
    help = "Run the complete NBA data pipeline for multiple seasons"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--start-season",
            type=int,
            help="Start season ending year (e.g. 2010)",
        )
        group.add_argument(
            "--seasons",
            nargs="+",
            type=int,
            help="Specific season(s) to update (space-separated, e.g. 2020 2021 2022)",
        )

        parser.add_argument(
            "--end-season",
            type=int,
            help="End season ending year (e.g. 2026) — required when using --start-season",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            metavar="N",
            help="Parallel workers for data ingest (default: 1)",
        )
        parser.add_argument(
            "--pbp-workers",
            type=int,
            default=1,
            metavar="N",
            help="Parallel workers for PBP ingest when --with-pbp (default: 1, max 3)",
        )
        parser.add_argument(
            "--skip-ingest",
            action="store_true",
            help="Skip all ingest — only recompute ratings/stats",
        )
        parser.add_argument(
            "--with-pbp",
            action="store_true",
            help="Also run PBP ingestion + baseline RAPM (takes hours per season)",
        )

    def handle(self, *args, **options):
        # Determine which seasons to update
        if options["seasons"]:
            seasons = sorted(options["seasons"])
        else:
            start_season = options["start_season"]
            end_season = options["end_season"]

            if end_season is None:
                raise CommandError(
                    "--end-season is required when using --start-season"
                )
            if start_season < 1947:
                raise CommandError("--start-season must be 1947 or later")
            if end_season < start_season:
                raise CommandError("--end-season must be >= --start-season")

            seasons = list(range(start_season, end_season + 1))

        workers = max(1, int(options.get("workers", 1)))
        pbp_workers = max(1, min(3, int(options.get("pbp_workers", 1))))
        skip_ingest = options.get("skip_ingest", False)
        with_pbp = options.get("with_pbp", False)

        total_seasons = len(seasons)
        start_time = timezone.now()

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("MACFAX — NBA MULTI-SEASON DATA PIPELINE")
        self.stdout.write("=" * 80)
        self.stdout.write(f"Seasons  : {seasons[0]}-{seasons[-1]} ({total_seasons} total)")
        self.stdout.write(f"Started  : {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write("=" * 80 + "\n")

        results = []
        failed_seasons = []

        for idx, season_year in enumerate(seasons, 1):
            season_num = f"[{idx}/{total_seasons}]"
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n{season_num} STARTING SEASON {season_year-1}-{str(season_year)[2:]}"
                )
            )
            self.stdout.write("-" * 80)

            try:
                update_kwargs = {
                    "season": season_year,
                    "workers": workers,
                }
                if skip_ingest:
                    update_kwargs["skip_ingest"] = True
                if with_pbp:
                    update_kwargs["with_pbp"] = True
                    update_kwargs["pbp_workers"] = pbp_workers

                call_command("update_nba_all", **update_kwargs)
                results.append((season_year, True, None))
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Season {season_year} completed successfully\n")
                )
            except Exception as e:
                results.append((season_year, False, str(e)))
                failed_seasons.append(season_year)
                self.stderr.write(
                    self.style.ERROR(f"✗ Season {season_year} failed: {e}\n")
                )

        # Summary
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()

        self.stdout.write("\n" + "=" * 80)
        if not failed_seasons:
            self.stdout.write(
                self.style.SUCCESS("✓ ALL SEASONS UPDATED SUCCESSFULLY")
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"✗ COMPLETED WITH ERRORS ({len(failed_seasons)} of {total_seasons} failed)"
                )
            )
        self.stdout.write("=" * 80)

        self.stdout.write(f"\nSeason Summary:")
        for season_year, success, error in results:
            if success:
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ {season_year-1}-{str(season_year)[2:]}")
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ {season_year-1}-{str(season_year)[2:]}: {error}")
                )

        self.stdout.write(f"\nStarted:  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        hours = duration / 3600
        mins = (duration % 3600) / 60
        self.stdout.write(f"Duration: {hours:.1f}h ({mins:.0f}m)")
        self.stdout.write("=" * 80 + "\n")

        if failed_seasons:
            self.stdout.write(
                self.style.ERROR(f"Failed seasons: {', '.join(str(s) for s in failed_seasons)}")
            )
            self.stdout.write("")
            sys.exit(1)
        else:
            self.stdout.write(
                self.style.SUCCESS("All NBA seasons updated! Website data is current.")
            )
