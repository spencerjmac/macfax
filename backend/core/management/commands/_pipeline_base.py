"""
Shared base class for Macfax pipeline management commands.

Not discovered by Django (underscore prefix). All update_* commands
inherit from BasePipelineCommand for consistent step execution and output.
"""

import sys

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from core.models import Season


class BasePipelineCommand(BaseCommand):

    def _ensure_season(self, season_year: int) -> "Season":
        season, created = Season.objects.get_or_create(
            year=season_year,
            defaults={
                "display_name": f"{season_year - 1}-{str(season_year)[2:]}",
                "is_current": True,
            },
        )
        verb = "Created" if created else "Using existing"
        self.stdout.write(self.style.SUCCESS(f"[SETUP] {verb} Season {season}\n"))
        return season

    def _run_setup(self, ncaa: bool = True, nba: bool = False):
        """Idempotent pre-flight: ensures team tables are consistent."""
        steps = []
        if ncaa:
            steps += [
                ("ensure_ncaa_teams",  {}, "D1 team stubs + aliases up to date"),
                ("fix_team_duplicates", {}, "Informal/canonical duplicates merged"),
                ("sync_team_d1_status", {}, "is_d1 flags synced"),
            ]
        if nba:
            steps += [
                ("nba_sync_teams", {}, "NBA teams seeded"),
            ]
        for cmd, kwargs, ok_msg in steps:
            try:
                self.stdout.write(f"[SETUP] Running {cmd}...")
                call_command(cmd, **kwargs)
                self.stdout.write(self.style.SUCCESS(f"[SETUP] {ok_msg}\n"))
            except Exception as e:
                self.stderr.write(self.style.WARNING(f"[SETUP WARN] {cmd} failed: {e}\n"))

    def _run_step(
        self,
        name: str,
        cmd: str,
        kwargs: dict,
        steps: list,
        fatal: bool = False,
        label: str = "",
    ):
        prefix = label or "[--]"
        self.stdout.write(f"{prefix} {name}...")
        try:
            call_command(cmd, **kwargs)
            steps.append((name, True, None))
            self.stdout.write(self.style.SUCCESS(f"[OK] {name}\n"))
        except Exception as e:
            steps.append((name, False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] {name}: {e}\n"))
            if fatal:
                self._print_summary(timezone.now(), timezone.now(), 0.0, steps)
                sys.exit(1)

    def _skip_step(self, name: str, steps: list, reason: str = "Skipped"):
        steps.append((name, True, reason))

    def _print_summary(
        self,
        start_time,
        end_time,
        duration: float,
        steps: list,
        title: str = "PIPELINE",
    ):
        failed = any(not s[1] for s in steps)
        self.stdout.write("\n" + "=" * 70)
        if not failed:
            self.stdout.write(self.style.SUCCESS(f"{title} — ALL STEPS SUCCESSFUL"))
        else:
            self.stdout.write(self.style.ERROR(f"{title} — COMPLETED WITH ERRORS"))
        self.stdout.write("=" * 70)

        self.stdout.write("\nStep Summary:")
        for step_name, success, note in steps:
            if success:
                tag = f"[{note}]" if note and note != "None" else "[OK]  "
                self.stdout.write(self.style.SUCCESS(f"  {tag} {step_name}"))
            else:
                self.stdout.write(self.style.ERROR(f"  [FAIL] {step_name}: {note}"))

        self.stdout.write(f"\nStarted:  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Duration: {duration:.1f}s ({duration / 60:.1f} min)")
        self.stdout.write("=" * 70 + "\n")

    def _header(self, title: str, season_year: int):
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(f"MACFAX — {title}")
        self.stdout.write(f"Season: {season_year} ({season_year - 1}-{str(season_year)[2:]})")
        self.stdout.write("=" * 70 + "\n")
