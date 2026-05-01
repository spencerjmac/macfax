"""
Management command: run_bt10

BT-10: Role-bucket-relative archetype threshold calibration.
Collects player data from all valid backtest source years, computes per-bucket
and per-conference-group stat percentiles, and recommends replacement values for:
  • RIM_PROTECTOR_BLK_THRESHOLD  → Big p50 blk/game
  • DISRUPTOR_STL_THRESHOLD      → Guard/Wing p70 stl/game
  • SPACER_FG3A_THRESHOLD        → per-bucket p60 fg3a/game
  • WEAK_DEFENDER_DBPR_MAX       → per-conf-group p25 projected_dbpr

Usage:
    python manage.py run_bt10               # print recommendation table only
    python manage.py run_bt10 --years 2023 2024 2025
    python manage.py run_bt10 --apply       # print + write constants to fit/constants.py
"""

import os

from django.core.management.base import BaseCommand

from backtesting.roster_outlook.bt10_threshold_calibration import (
    collect_threshold_data,
    compute_bucket_percentiles,
    recommend_thresholds,
    write_bt10_constants,
)


class Command(BaseCommand):
    help = "BT-10: compute per-bucket archetype threshold recommendations from historical data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--years",
            nargs="+",
            type=int,
            default=None,
            metavar="YEAR",
            help="Restrict to these source years (e.g. --years 2023 2024). Default: all available.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write recommended constants to fit/constants.py after printing the table.",
        )

    def handle(self, *args, **options):
        years = options["years"]
        apply = options["apply"]

        self.stdout.write("\n[BT-10] Collecting player threshold data...")
        dataset = collect_threshold_data(source_years=years)
        self.stdout.write(
            f"[BT-10] Loaded {dataset.n_players} players across years: {dataset.source_years}"
        )

        self.stdout.write("[BT-10] Computing bucket percentiles...")
        percentiles = compute_bucket_percentiles(dataset)

        self.stdout.write("[BT-10] Generating threshold recommendations...")
        result = recommend_thresholds(percentiles)

        self.stdout.write(result.summary_table)

        if apply:
            constants_path = os.path.join(
                os.path.dirname(__file__),
                "..", "..", "analytics", "player_value", "fit", "constants.py",
            )
            constants_path = os.path.normpath(constants_path)
            self.stdout.write(f"\n[BT-10] --apply: writing constants to {constants_path}")
            write_bt10_constants(result, constants_path)
            self.stdout.write(self.style.SUCCESS("[BT-10] Done. Reload the fit engine to apply."))
        else:
            self.stdout.write(
                "\n[BT-10] Dry run. Use --apply to write constants to fit/constants.py."
            )
