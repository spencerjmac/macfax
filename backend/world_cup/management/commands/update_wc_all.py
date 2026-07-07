"""
Management command: update_wc_all
Runs the complete World Cup Elo pipeline (fetch latest FIFA rankings + latest results + recompute ratings).

Pipeline sequence
─────────────────
  1. fetch_fifa_rankings — fetch FIFA world rankings and update teams.json
  2. build_elo --refresh — fetch results.csv + shootouts.csv from martj42 dataset,
                            recompute Elo ratings for all 48 teams, write to DB

Usage
─────
  python manage.py update_wc_all
  python manage.py update_wc_all --skip-refresh   # recompute from cached CSVs only

Cron (6 AM UTC daily — catches all prior-day matches across all timezones)
──────────────────────────────────────────────────────────────────────────
  0 6 * * * cd /path/to/macfax/backend && uv run python manage.py update_wc_all >> /var/log/wc_daily.log 2>&1
"""

import sys

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

TOTAL_STEPS = 2


class Command(BaseCommand):
    help = "Run the complete World Cup Elo pipeline (fetch + compute + write DB)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-refresh",
            action="store_true",
            help="Recompute from cached CSVs — skip re-fetching from GitHub",
        )

    def handle(self, *args, **options):
        skip_refresh = options["skip_refresh"]
        start_time = timezone.now()

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("MACFAX — WORLD CUP ELO PIPELINE UPDATE")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        self.stdout.write("=" * 70 + "\n")

        steps = []

        self._run_step(
            "FIFA world rankings (fetch + update teams.json)",
            "fetch_fifa_rankings",
            {},
            steps,
            fatal=True,
            label=f"[1/{TOTAL_STEPS}]",
        )

        self._run_step(
            "World Cup Elo ratings (fetch + compute + write DB)",
            "build_elo",
            {} if skip_refresh else {"refresh": True},
            steps,
            fatal=True,
            label=f"[2/{TOTAL_STEPS}]",
        )

        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        self._print_summary(start_time, end_time, duration, steps)

        if any(not s[1] for s in steps):
            sys.exit(1)

    def _run_step(self, name, cmd, kwargs, steps, fatal=False, label=None):
        prefix = label or "[--]"
        self.stdout.write(f"{prefix} {name}...")
        try:
            call_command(cmd, stdout=self.stdout, stderr=self.stderr, **kwargs)
            steps.append((name, True, None))
            self.stdout.write(self.style.SUCCESS(f"[OK] {name}\n"))
        except Exception as e:
            steps.append((name, False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] {name}: {e}\n"))
            if fatal:
                sys.exit(1)

    def _print_summary(self, start_time, end_time, duration, steps):
        failed = any(not s[1] for s in steps)
        self.stdout.write("\n" + "=" * 70)
        if not failed:
            self.stdout.write(self.style.SUCCESS("UPDATE COMPLETE — ALL STEPS SUCCESSFUL"))
        else:
            self.stdout.write(self.style.ERROR("UPDATE COMPLETED WITH ERRORS"))
        self.stdout.write("=" * 70)

        self.stdout.write("\nStep Summary:")
        for step_name, success, note in steps:
            if success:
                self.stdout.write(self.style.SUCCESS(f"  [OK]   {step_name}"))
            else:
                self.stdout.write(self.style.ERROR(f"  [FAIL] {step_name}: {note}"))

        self.stdout.write(f"\nStarted:  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Duration: {duration:.1f}s")
        self.stdout.write("\n" + "=" * 70 + "\n")
