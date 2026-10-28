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

from ncaa.models import Season


class BasePipelineCommand(BaseCommand):

    def _ensure_season(self, season_year: int) -> "Season":
        season, created = Season.objects.get_or_create(
            year=season_year,
            defaults={
                "display_name": f"{season_year - 1}-{str(season_year)[2:]}",
                # Never born current: a backfill or a not-yet-started season must not
                # steal the flag. ncaa.seasons.activate_latest_season() flips it once
                # the season has a final game.
                "is_current": False,
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

    @staticmethod
    def _season_has_final_games(season_year: int) -> bool:
        from ncaa.models import Game

        return Game.objects.filter(season_year=season_year, status="final").exists()

    def _finish_without_games(self, title: str, season_year: int, steps: list, start_time):
        """
        Stop a pipeline cleanly when its season has no final games yet (e.g. Nov 1, the
        day the daily gate opens, before the first tip-off). Computing on an empty
        season would write all-zero ratings rows and list a game-less season in the
        season picker, so nothing is computed and the run does not fail.
        """
        note = f"Skipped: no final {season_year} games yet"
        self.stdout.write(self.style.WARNING(f"[SKIP] {note} -- nothing to compute\n"))
        steps.append((title, True, note))
        end_time = timezone.now()
        self._print_summary(start_time, end_time, (end_time - start_time).total_seconds(), steps, title=title)

    def _activate_latest_season(self, steps: list):
        """Move is_current to the newest season with a final game (non-fatal)."""
        from ncaa.seasons import activate_latest_season

        name = "Activate latest season"
        try:
            flip = activate_latest_season()
        except Exception as e:
            steps.append((name, False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] {name}: {e}\n"))
            return
        if flip:
            old, new = flip
            note = f"is_current: {old or 'none'} -> {new}"
            self.stdout.write(self.style.SUCCESS(f"[SEASON] {note}\n"))
        else:
            note = "no change"
        steps.append((name, True, note))

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
