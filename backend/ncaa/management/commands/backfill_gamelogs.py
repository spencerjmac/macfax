"""
Management command: backfill_gamelogs
Ingests historical game log data across one or more past seasons.

Usage:
    # Backfill a single season (creates Season object if needed)
    python manage.py backfill_gamelogs --season 2025

    # Backfill a range of seasons
    python manage.py backfill_gamelogs --from-season 2022 --to-season 2025

    # Backfill specific seasons
    python manage.py backfill_gamelogs --seasons 2022,2023,2024,2025

    # Use ESPN source (recommended for reliability; NCAA boxscore can be flaky)
    python manage.py backfill_gamelogs --from-season 2022 --to-season 2025 --source espn

    # Dry run to see what would be ingested
    python manage.py backfill_gamelogs --from-season 2023 --to-season 2025 --dry-run
"""

import logging
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command

logger = logging.getLogger(__name__)

# Known championship game dates per season year (to cap end_date correctly).
# April 15 is a safe default, but these let us stop exactly at the right time.
#
# ESPN API data availability notes:
#   2002-2004 (seasons 2002-03 through 2003-04): scoreboard works (~120 games/day)
#             BUT boxscore has no stats fields — you get scores only, no FG/REB/etc.
#   2005+    (season 2004-05 onward): full boxscore with all 23 stats fields
#
# Recommended minimum for meaningful analysis: --from-season 2005
SEASON_END_DATES = {
    2002: date(2002, 4, 1),
    2003: date(2003, 4, 7),
    2004: date(2004, 4, 5),
    2005: date(2005, 4, 4),
    2006: date(2006, 4, 3),
    2007: date(2007, 4, 2),
    2008: date(2008, 4, 7),
    2009: date(2009, 4, 6),
    2010: date(2010, 4, 5),
    2011: date(2011, 4, 4),
    2012: date(2012, 4, 2),
    2013: date(2013, 4, 8),
    2014: date(2014, 4, 7),
    2015: date(2015, 4, 6),
    2016: date(2016, 4, 4),
    2017: date(2017, 4, 3),
    2018: date(2018, 4, 2),
    2019: date(2019, 4, 8),
    2020: date(2020, 3, 12),   # Season canceled (COVID); last game March 12
    2021: date(2021, 4, 5),
    2022: date(2022, 4, 4),
    2023: date(2023, 4, 3),
    2024: date(2024, 4, 8),
    2025: date(2025, 4, 7),
}


class Command(BaseCommand):
    help = "Backfill historical game log data for one or more past seasons"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--season",
            type=int,
            metavar="YEAR",
            help="Single season year to backfill (e.g. 2025 for 2024-25)",
        )
        group.add_argument(
            "--from-season",
            type=int,
            metavar="YEAR",
            help="Starting season year for a range (inclusive)",
        )
        group.add_argument(
            "--seasons",
            type=str,
            metavar="YEARS",
            help="Comma-separated list of season years (e.g. 2022,2023,2024,2025)",
        )

        parser.add_argument(
            "--to-season",
            type=int,
            metavar="YEAR",
            default=None,
            help="Ending season year for a range (inclusive, used with --from-season)",
        )
        parser.add_argument(
            "--source",
            type=str,
            default="espn",
            choices=["espn", "ncaa"],
            help="Data source (default: espn — more reliable for historical seasons)",
        )
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Force re-fetch and update existing game records",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Dry run — fetch and parse but don't write to the database",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            metavar="N",
            help="Parallel workers per season (default: 1)",
        )

    def handle(self, *args, **options):
        source = options["source"]
        refresh = options["refresh"]
        dry_run = options["dry_run"]
        workers = options["workers"]

        # Build the list of season years to process
        if options.get("season"):
            years = [options["season"]]
        elif options.get("seasons"):
            try:
                years = [int(y.strip()) for y in options["seasons"].split(",")]
            except ValueError:
                raise CommandError("--seasons must be a comma-separated list of integers, e.g. 2022,2023,2024")
        else:
            from_year = options["from_season"]
            to_year = options.get("to_season") or (date.today().year if date.today().month >= 10 else date.today().year)
            if to_year < from_year:
                raise CommandError("--to-season must be >= --from-season")
            years = list(range(from_year, to_year + 1))

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'='*65}\n"
                f"HISTORICAL GAME LOG BACKFILL\n"
                f"Seasons: {', '.join(str(y) for y in years)}\n"
                f"Source: {source.upper()} | Refresh: {refresh} | Dry Run: {dry_run}\n"
                f"{'='*65}\n"
            )
        )

        overall_errors = []

        for season_year in years:
            end_date = SEASON_END_DATES.get(season_year)
            end_str = end_date.strftime("%Y-%m-%d") if end_date else None

            self.stdout.write(
                self.style.WARNING(
                    f"\n>>> Season {season_year} "
                    f"(end: {end_str or 'auto'}) <<<\n"
                )
            )

            try:
                kwargs = dict(
                    season=season_year,
                    source=source,
                    create_season=True,
                    refresh=refresh,
                    dry_run=dry_run,
                    workers=workers,
                    rebuild_mappings=False,
                    verbosity=options.get("verbosity", 1),
                )
                if end_str:
                    kwargs["end"] = end_str

                call_command("ingest_gamelogs", **kwargs)

            except Exception as exc:
                msg = f"Season {season_year} failed: {exc}"
                logger.error(msg, exc_info=True)
                overall_errors.append(msg)
                self.stdout.write(self.style.ERROR(f"  ERROR: {exc}"))
                continue

        # Final summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'='*65}\n"
                f"BACKFILL COMPLETE — {len(years)} season(s) processed, "
                f"{len(overall_errors)} error(s)\n"
                f"{'='*65}"
            )
        )
        if overall_errors:
            for err in overall_errors:
                self.stdout.write(self.style.ERROR(f"  {err}"))
