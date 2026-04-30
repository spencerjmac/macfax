"""
Management command: run_bt1_bt4

Runs BT-1 (player BPR carry-forward RMSE baseline) and BT-4 (empirical
SLOPE_OFF / SLOPE_DEF derivation) for the roster outlook backtest suite.

Usage:
    python manage.py run_bt1_bt4
    python manage.py run_bt1_bt4 --years 2023 2024 2025
"""

from django.core.management.base import BaseCommand

from backtesting.roster_outlook.bt1_bt4_calibration import run_bt1, run_bt4


class Command(BaseCommand):
    help = "Run BT-1 (player BPR RMSE baseline) and BT-4 (empirical slope derivation)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--years",
            nargs="+",
            type=int,
            default=None,
            metavar="YEAR",
            help="Restrict to these source years (e.g. --years 2023 2024). Default: all available.",
        )

    def handle(self, *args, **options):
        years = options["years"]

        self.stdout.write("\n=== BT-1: Player BPR Carry-Forward Baseline ===")
        run_bt1(source_years=years)

        self.stdout.write("\n=== BT-4: Empirical Slope Derivation ===")
        run_bt4(source_years=years)
