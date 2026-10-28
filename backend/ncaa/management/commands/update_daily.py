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

Usage
─────
  python manage.py update_daily
  python manage.py update_daily --dry-run          # show gates + plan, run nothing
  python manage.py update_daily --force-ncaa       # run NCAA even if its gate is closed
  python manage.py update_daily --skip-nba
  python manage.py update_daily --days 5           # NCAA: refetch the last 5 days
"""

import argparse
import sys
from datetime import date

from django.core.management import call_command
from django.utils import timezone

from config.season_calendar import season_in_play
from ncaa.management.commands._pipeline_base import BasePipelineCommand
from ncaa import seasons as ncaa_seasons
from nba import seasons as nba_seasons

RECENT_DAYS = 14


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

        if nba_run:
            self._run("NBA pipeline", "update_nba_all", {"season": season, "workers": workers}, steps)
        else:
            self._skip_step("NBA pipeline", steps, f"Skipped ({nba_why})")

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

        end_time = timezone.now()
        self._print_summary(
            start_time, end_time, (end_time - start_time).total_seconds(), steps, title="DAILY UPDATE"
        )
        if any(not s[1] for s in steps):
            sys.exit(1)

    def _run(self, name: str, cmd: str, kwargs: dict, steps: list):
        """
        Run one sub-pipeline without letting its failure stop the next league.

        The league pipelines end with ``sys.exit(1)`` when any step failed, which
        is a SystemExit (not an Exception), so it is caught explicitly here.
        """
        self.stdout.write(f"[RUN] {name}...")
        try:
            call_command(cmd, **kwargs)
        except SystemExit as e:
            if e.code in (0, None):
                steps.append((name, True, None))
                self.stdout.write(self.style.SUCCESS(f"[OK] {name}\n"))
            else:
                steps.append((name, False, f"exited with status {e.code}"))
                self.stderr.write(self.style.ERROR(f"[FAIL] {name}: exited with status {e.code}\n"))
        except Exception as e:
            steps.append((name, False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] {name}: {e}\n"))
        else:
            steps.append((name, True, None))
            self.stdout.write(self.style.SUCCESS(f"[OK] {name}\n"))
