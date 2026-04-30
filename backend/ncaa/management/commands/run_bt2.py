"""
Management command: run_bt2

Runs BT-2: sweep TRANSFER_COMP_WEIGHT candidates and print the result table.
If the winning weight differs from 0.03, prints a recommendation to update
projection/constants.py. Does NOT automatically write to constants.py —
the engineer reviews the table first, then applies the recommended change.

Usage:
    python manage.py run_bt2
    python manage.py run_bt2 --years 2023 2024 2025
"""

from django.core.management.base import BaseCommand

from backtesting.roster_outlook.bt2_transfer_sweep import run_bt2


class Command(BaseCommand):
    help = "BT-2: Sweep transfer competition weight candidates. Prints table + recommendation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--years",
            nargs="+",
            type=int,
            default=None,
            metavar="YEAR",
            help="Restrict to these source years. Default: all available (prior_year_has_data=True).",
        )

    def handle(self, *args, **options):
        run_bt2(source_years=options["years"])
