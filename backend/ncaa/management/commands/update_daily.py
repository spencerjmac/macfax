"""
Management command: update_daily
The one command the scheduler runs. Updates whichever leagues are in season.

Each league runs only when its gate is open:
  NBA   window Oct 1 - Jun 30, or a final game in the last 14 days
  NCAA  window Nov 1 - Apr 15, or a final game in the last 14 days
Closed gates are skipped (and logged), so nothing needs enabling or disabling
at the start or end of a season. Both leagues ingest the season IN PLAY (see
config.season_calendar), then the pipelines move ``is_current`` forward once the
new season has a final game (see nba.seasons / ncaa.seasons).

Order: NCAA first (in this process), then NBA in a subprocess
(``manage.py update_nba_all``) with a timeout of NBA_TIMEOUT_MIN minutes (env
NBA_TIMEOUT_MIN, default 120). The native NBA chain is the long, memory-heavy
part (box fit ~2.5 GB), so a hang, a timeout or a crash there (an OOM kill
included) is logged as a failed NBA step after NCAA is already done, and the
subprocess hands its memory back when it exits.

Usage
─────
  python manage.py update_daily
  python manage.py update_daily --dry-run          # show gates + plan, run nothing
  python manage.py update_daily --force-ncaa       # run NCAA even if its gate is closed
  python manage.py update_daily --skip-nba
  python manage.py update_daily --days 5           # NCAA: refetch the last 5 days
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import date

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from config.season_calendar import season_in_play
from ncaa.management.commands._pipeline_base import BasePipelineCommand
from ncaa import seasons as ncaa_seasons
from nba import seasons as nba_seasons

RECENT_DAYS = 14
NBA_TIMEOUT_MIN = 120   # default; env NBA_TIMEOUT_MIN overrides


def nba_timeout_minutes() -> float:
    """Minutes the NBA subprocess may run: env NBA_TIMEOUT_MIN, else NBA_TIMEOUT_MIN."""
    raw = os.getenv("NBA_TIMEOUT_MIN")
    try:
        value = float(raw) if raw else NBA_TIMEOUT_MIN
    except ValueError:
        value = NBA_TIMEOUT_MIN
    return value if value > 0 else NBA_TIMEOUT_MIN


def decide(league: str, today: date, skip: bool, force: bool) -> tuple[bool, str]:
    """Gate for one league: (run?, human-readable reason). Pure apart from DB reads."""
    mod = nba_seasons if league == "NBA" else ncaa_seasons
    if skip:
        return False, f"--skip-{league.lower()}"
    if force:
        return True, f"--force-{league.lower()}"
    if mod.in_season_window(today):
        return True, "inside the season window"
    if mod.has_recent_final_games(RECENT_DAYS, today):
        return True, f"final games in the last {RECENT_DAYS} days"
    return False, "outside the season window and no recent final games"


class Command(BasePipelineCommand):
    help = "Daily scheduled update: NBA and NCAA, each only when in season."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print gates and plan; run nothing")
        parser.add_argument("--skip-nba", action="store_true")
        parser.add_argument("--skip-ncaa", action="store_true")
        parser.add_argument("--force-nba", action="store_true", help="Run NBA even if its gate is closed")
        parser.add_argument("--force-ncaa", action="store_true", help="Run NCAA even if its gate is closed")
        parser.add_argument(
            "--skip-ncaa-players",
            action="store_true",
            help="NCAA: team pipeline only (skip the heavy player/BPR pipeline)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=3,
            help="NCAA team ingest: refetch the last N days of games (default: 3)",
        )
        parser.add_argument("--workers", type=int, default=1, help="Parallel workers for ingest (default: 1)")
        parser.add_argument("--today", help=argparse.SUPPRESS, default=None)

    def handle(self, *args, **options):
        today = date.fromisoformat(options["today"]) if options["today"] else date.today()
        season = season_in_play(today)
        days = max(1, options["days"])
        workers = max(1, options["workers"])

        self._header("DAILY UPDATE", season)
        self.stdout.write(f"Date: {today}")

        nba_run, nba_why = decide("NBA", today, options["skip_nba"], options["force_nba"])
        ncaa_run, ncaa_why = decide("NCAA", today, options["skip_ncaa"], options["force_ncaa"])
        self.stdout.write(f"[GATE] NBA : {'RUN ' if nba_run else 'SKIP'} - {nba_why}")
        self.stdout.write(f"[GATE] NCAA: {'RUN ' if ncaa_run else 'SKIP'} - {ncaa_why}\n")

        if options["dry_run"]:
            self.stdout.write("[DRY RUN] nothing executed")
            return

        start_time = timezone.now()
        steps: list = []

        if ncaa_run:
            self._run(
                "NCAA team pipeline",
                "update_ncaa_teams",
                {"season": season, "days": days, "workers": workers},
                steps,
            )
            if options["skip_ncaa_players"]:
                self._skip_step("NCAA player pipeline", steps, "Skipped (--skip-ncaa-players)")
            else:
                self._run(
                    "NCAA player pipeline",
                    "update_ncaa_players",
                    {"season": season, "workers": workers},
                    steps,
                )
        else:
            self._skip_step("NCAA pipeline", steps, f"Skipped ({ncaa_why})")

        if nba_run:
            self._run_nba_subprocess(season, workers, steps)
        else:
            self._skip_step("NBA pipeline", steps, f"Skipped ({nba_why})")

        end_time = timezone.now()
        self._print_summary(
            start_time, end_time, (end_time - start_time).total_seconds(), steps, title="DAILY UPDATE"
        )
        if any(not s[1] for s in steps):
            sys.exit(1)

    def _run_nba_subprocess(self, season: int, workers: int, steps: list):
        """
        update_nba_all in a child process with a timeout. A timeout (the child is killed), a
        non-zero exit or a death by signal is a failed step; nothing here raises.
        """
        name = "NBA pipeline"
        minutes = nba_timeout_minutes()
        cmd = [sys.executable, "manage.py", "update_nba_all", "--season", str(season), "--workers", str(workers)]
        self.stdout.write(f"[RUN] {name} (subprocess, timeout {minutes:g} min)...")
        self.stdout.flush()
        sys.stdout.flush()
        t0 = time.monotonic()
        rc = None
        try:
            result = subprocess.run(cmd, cwd=settings.BASE_DIR, timeout=minutes * 60)
        except subprocess.TimeoutExpired:
            reason = f"timed out after {minutes:g} min (killed)"
        except OSError as e:
            reason = f"could not start: {e}"
        else:
            rc = result.returncode
            if result.returncode == 0:
                steps.append((name, True, None))
                self._time_step(steps, t0, rc=0)
                self.stdout.write(self.style.SUCCESS(f"[OK] {name}\n"))
                return
            if result.returncode < 0:
                reason = f"killed by signal {-result.returncode}"
            else:
                reason = f"exited with status {result.returncode}"
        steps.append((name, False, reason))
        self._time_step(steps, t0, rc=rc)
        self.stderr.write(self.style.ERROR(f"[FAIL] {name}: {reason}\n"))

    def _run(self, name: str, cmd: str, kwargs: dict, steps: list):
        """
        Run one sub-pipeline without letting its failure stop the next league.

        The league pipelines end with ``sys.exit(1)`` when any step failed, which
        is a SystemExit (not an Exception), so it is caught explicitly here.
        """
        self.stdout.write(f"[RUN] {name}...")
        t0 = time.monotonic()
        try:
            call_command(cmd, **kwargs)
        except SystemExit as e:
            if e.code in (0, None):
                steps.append((name, True, None))
                self._time_step(steps, t0, rc=0)
                self.stdout.write(self.style.SUCCESS(f"[OK] {name}\n"))
            else:
                steps.append((name, False, f"exited with status {e.code}"))
                self._time_step(steps, t0, rc=e.code if isinstance(e.code, int) else 1)
                self.stderr.write(self.style.ERROR(f"[FAIL] {name}: exited with status {e.code}\n"))
        except Exception as e:
            steps.append((name, False, str(e)))
            self._time_step(steps, t0, rc=1)
            self.stderr.write(self.style.ERROR(f"[FAIL] {name}: {e}\n"))
        else:
            steps.append((name, True, None))
            self._time_step(steps, t0, rc=0)
            self.stdout.write(self.style.SUCCESS(f"[OK] {name}\n"))
