"""
Standalone LEBRON data freshness check.

Usage:
    python manage.py check_lebron_data --season-year 2026

Exit codes:
    0 = all files OK
    1 = at least one warning (stale)
    2 = at least one error (missing)
"""
import sys
from pathlib import Path

from django.core.management.base import BaseCommand

from nba.analytics.lebron_utils import check_all_lebron_files

SCRIPT_DIR = Path(__file__).parent.parent.parent.parent.parent  # project root


class Command(BaseCommand):
    help = "Check LEBRON CSV data freshness without running BPR."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season-year",
            type=int,
            required=True,
            help="Ending season year (e.g. 2026)",
        )

    def handle(self, *args, **options):
        season_year = options["season_year"]
        data_dir = SCRIPT_DIR / "data" / "nba"
        results = check_all_lebron_files(str(data_dir), season_year)

        worst_exit = 0

        for result in results:
            label = f"lebron-data-{result['year']}.csv"
            tag = "(current)" if result["is_current"] else "(prior) "

            status_icon = {"ok": "✓", "warning": "⚠", "error": "✗"}[result["status"]]
            if result["status"] == "error":
                status_str = "MISSING"
            elif result["status"] == "warning":
                status_str = f"STALE ({result['age_days']:.0f} days old)"
            else:
                status_str = f"OK  ({result['age_days']:.0f} days old)"

            last_mod = (
                result["last_modified"].strftime("%Y-%m-%d")
                if result["last_modified"]
                else "N/A"
            )
            season_str = "ACTIVE" if result["season_active"] else "OFFSEASON"

            w = 46
            self.stdout.write("╔" + "═" * w + "╗")
            header_inner = f"  LEBRON Data Freshness Check  {tag}"
            self.stdout.write("║" + header_inner + " " * (w - len(header_inner)) + "║")
            self.stdout.write("╠" + "═" * w + "╣")
            self.stdout.write(f"║  File:        {label:<{w - 15}}║")
            self.stdout.write(f"║  Status:      {status_icon} {status_str:<{w - 18}}║")
            self.stdout.write(f"║  Last update: {last_mod:<{w - 15}}║")
            self.stdout.write(f"║  Season:      {season_str:<{w - 15}}║")
            self.stdout.write("╚" + "═" * w + "╝")
            self.stdout.write("")

            if result["status"] == "error":
                self.stdout.write(self.style.ERROR(
                    f"  ACTION REQUIRED: {label} not found.\n"
                    f"  Download from BBall Index and place at:\n"
                    f"  {result['path']}"
                ))
                worst_exit = max(worst_exit, 2)
            elif result["status"] == "warning":
                self.stdout.write(self.style.WARNING(
                    f"  ACTION RECOMMENDED: {label} may be stale.\n"
                    f"  Download fresh data from BBall Index."
                ))
                worst_exit = max(worst_exit, 1)

        sys.exit(worst_exit)
