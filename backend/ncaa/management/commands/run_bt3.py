"""
Management command: run_bt3

Runs BT-3: development adjustment analysis stratified by role bucket and
experience stage. Prints a grid table of actual BPR deltas vs current constants.

Without --apply: prints table and recommended constants only.
With --apply: also writes the new stratified constants to projection/constants.py.

Usage:
    python manage.py run_bt3
    python manage.py run_bt3 --apply
    python manage.py run_bt3 --years 2023 2024 2025
    python manage.py run_bt3 --years 2023 2024 2025 --apply
"""

import os

from django.core.management.base import BaseCommand

from backtesting.roster_outlook.bt3_dev_adjustment import run_bt3, write_stratified_constants


class Command(BaseCommand):
    help = "BT-3: Development adjustment analysis by role bucket and experience stage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--years",
            nargs="+",
            type=int,
            default=None,
            metavar="YEAR",
            help="Restrict to these source years. Default: all available.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write recommended constants to projection/constants.py.",
        )

    def handle(self, *args, **options):
        result = run_bt3(source_years=options["years"])

        if options["apply"]:
            constants_path = os.path.join(
                os.path.dirname(__file__),
                "..", "..", "analytics", "player_value", "projection", "constants.py"
            )
            constants_path = os.path.abspath(constants_path)
            if not os.path.exists(constants_path):
                self.stderr.write(f"ERROR: constants.py not found at {constants_path}")
                return
            write_stratified_constants(result, constants_path)
            self.stdout.write("[run_bt3] Constants written. Run tests before deploying.")
        else:
            self.stdout.write(
                "[run_bt3] Dry run. Pass --apply to write constants to projection/constants.py."
            )
