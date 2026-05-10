"""
backfill_adjusted_ratings — Re-run compute_adjusted_ratings for one or more
historical seasons, using the current PipelineConfig settings.

Useful after changing shrinkage parameters (e.g. lowering k_floor from 170→150)
to backfill all historical seasons with the updated configuration.

Usage:
    python manage.py backfill_adjusted_ratings --from-season 2015 --to-season 2026
    python manage.py backfill_adjusted_ratings --season 2023
    python manage.py backfill_adjusted_ratings --seasons 2022,2023,2024
    python manage.py backfill_adjusted_ratings --from-season 2015 --to-season 2026 --dry-run
"""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from ncaa.models import Season


class Command(BaseCommand):
    help = "Re-run compute_adjusted_ratings for one or more historical seasons."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--season",
            type=int,
            metavar="YEAR",
            help="Single season year (e.g. 2026 for 2025-26).",
        )
        group.add_argument(
            "--from-season",
            type=int,
            metavar="YEAR",
            help="Start of a year range (inclusive). Requires --to-season.",
        )
        group.add_argument(
            "--seasons",
            type=str,
            metavar="YEARS",
            help="Comma-separated list of season years (e.g. 2022,2023,2025).",
        )

        parser.add_argument(
            "--to-season",
            type=int,
            metavar="YEAR",
            help="End of year range (inclusive). Used with --from-season.",
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=None,
            help="Override solver iterations (default: PipelineConfig value).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print which seasons would be processed without running anything.",
        )

    def handle(self, *args, **options):
        # ── Resolve season list ────────────────────────────────────────────── #
        if options["season"]:
            years = [options["season"]]
        elif options["from_season"]:
            if not options["to_season"]:
                raise CommandError("--from-season requires --to-season")
            years = list(range(options["from_season"], options["to_season"] + 1))
        else:
            try:
                years = [int(y.strip()) for y in options["seasons"].split(",")]
            except ValueError:
                raise CommandError("--seasons must be comma-separated integers")

        # Filter to seasons that actually exist in the DB
        existing = set(Season.objects.filter(year__in=years).values_list("year", flat=True))
        missing = [y for y in years if y not in existing]
        if missing:
            self.stderr.write(f"Warning: seasons not found in DB, skipping: {missing}")
        years = [y for y in years if y in existing]

        if not years:
            raise CommandError("No valid seasons to process.")

        self.stdout.write(
            f"{'[DRY RUN] ' if options['dry_run'] else ''}"
            f"Processing {len(years)} season(s): {years[0]}–{years[-1]}\n"
        )

        # ── Run per season ─────────────────────────────────────────────────── #
        for i, year in enumerate(years, 1):
            label = f"[{i}/{len(years)}] Season {year}"
            if options["dry_run"]:
                self.stdout.write(f"  {label}  (skipped — dry run)")
                continue

            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"{label}")
            self.stdout.write(f"{'='*60}")

            kwargs: dict = {"season": year}
            if options["iterations"]:
                kwargs["iterations"] = options["iterations"]

            call_command("compute_adjusted_ratings", **kwargs)

        if not options["dry_run"]:
            self.stdout.write(f"\nDone. Processed {len(years)} season(s).")
