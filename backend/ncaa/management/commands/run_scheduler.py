"""
Management command: run_scheduler
Tiny always-on scheduler for the docker-compose `scheduler` service: waits until
the next DAILY_UPDATE_AT (UTC), runs `update_daily` in a subprocess, repeats.
No cron or extra dependencies; a failed run is logged and tomorrow still runs.

Usage
─────
  python manage.py run_scheduler                 # daily at DAILY_UPDATE_AT (default 10:00 UTC)
  python manage.py run_scheduler --at 09:30
  python manage.py run_scheduler --run-now       # run once immediately, then keep the schedule
  python manage.py run_scheduler --once          # run once and exit
"""

import os
import subprocess
import sys
import time as time_module
from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# 10:00 UTC is 06:00 ET: after the last West Coast NBA / NCAA finals are posted.
DEFAULT_AT = "10:00"
MAX_SLEEP_SECONDS = 60  # wake often so docker stop / clock changes are noticed


def parse_at(value: str) -> time:
    try:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))
    except (ValueError, AttributeError):
        raise CommandError(f"--at must be HH:MM (24h, UTC), got {value!r}")


def next_run_at(now: datetime, at: time) -> datetime:
    """Next occurrence of `at` strictly after `now` (same tzinfo as `now`)."""
    candidate = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return candidate if candidate > now else candidate + timedelta(days=1)


class Command(BaseCommand):
    help = "Run update_daily every day at a fixed UTC time (for the compose scheduler service)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--at",
            default=os.environ.get("DAILY_UPDATE_AT", DEFAULT_AT),
            help=f"Daily run time, HH:MM UTC (env DAILY_UPDATE_AT, default {DEFAULT_AT})",
        )
        parser.add_argument("--run-now", action="store_true", help="Run once immediately, then keep the schedule")
        parser.add_argument("--once", action="store_true", help="Run once immediately and exit")

    def handle(self, *args, **options):
        at = parse_at(options["at"])

        if options["once"] or options["run_now"]:
            self._run_update()
            if options["once"]:
                return

        self.stdout.write(f"[scheduler] daily update at {at:%H:%M} UTC")
        while True:
            now = datetime.now(dt_timezone.utc)
            target = next_run_at(now, at)
            self.stdout.write(f"[scheduler] next run {target:%Y-%m-%d %H:%M} UTC")
            while datetime.now(dt_timezone.utc) < target:
                remaining = (target - datetime.now(dt_timezone.utc)).total_seconds()
                time_module.sleep(max(1.0, min(MAX_SLEEP_SECONDS, remaining)))
            self._run_update()

    def _run_update(self):
        started = datetime.now(dt_timezone.utc)
        self.stdout.write(f"[scheduler] {started:%Y-%m-%d %H:%M:%S} UTC: starting update_daily")
        self.stdout.flush()
        # Subprocess, so a crash or SystemExit in the pipeline can't kill the scheduler.
        result = subprocess.run(
            [sys.executable, "manage.py", "update_daily"],
            cwd=settings.BASE_DIR,
        )
        elapsed = (datetime.now(dt_timezone.utc) - started).total_seconds()
        level = "finished" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
        self.stdout.write(f"[scheduler] update_daily {level} after {elapsed / 60:.1f} min")
        self.stdout.flush()
