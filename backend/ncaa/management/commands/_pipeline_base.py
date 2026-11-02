"""
Shared base class for Macfax pipeline management commands.

Not discovered by Django (underscore prefix). All update_* commands
inherit from BasePipelineCommand for consistent step execution and output.
"""

import sys
from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from ncaa.models import Season
from ncaa.seasons import selection_sunday_for

# Ratings (pre-tournament rows with WAB) needed before a snapshot counts as complete
MIN_SNAPSHOT_TEAMS = 300
# Same chain as backfill_pre_tournament, in dependency order
PRE_TOURNAMENT_CHAIN = (
    "compute_team_metrics",
    "compute_adjusted_ratings",
    "compute_adjusted_four_factors",
    "compute_four_factor_index",
    "compute_sos",
    "compute_wab",
)


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
        if season.selection_sunday_date is None:
            # Needed for the pre-tournament snapshot; only read when that snapshot is taken
            season.selection_sunday_date = selection_sunday_for(season_year)
            season.save(update_fields=["selection_sunday_date"])
            self.stdout.write(f"[SETUP] Selection Sunday set to {season.selection_sunday_date}\n")
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

    def _run_tournament_steps(self, season_year: int, steps: list, today: date | None = None):
        """
        March: after Selection Sunday, (1) freeze the pre-tournament snapshot once, and
        (2) refresh tournament seeds daily (best effort) through the tournament.

        The snapshot uses only games on or before Selection Sunday, so it can be taken
        any time after; it is skipped once complete. Seeds come from Wikipedia and a
        failure never fails the run. Before Selection Sunday this is a no-op.
        """
        from ncaa.models import TeamSeasonRatings

        today = today or date.today()
        season = Season.objects.get(year=season_year)
        sunday = season.selection_sunday_date
        if sunday is None or today <= sunday:
            note = f"Skipped: before Selection Sunday ({sunday})" if sunday else "Skipped: no Selection Sunday date"
            steps.append(("Tournament snapshot + seeds", True, note))
            return

        complete = TeamSeasonRatings.all_objects.filter(
            season=season, is_pre_tournament=True, wab__isnull=False
        ).count() >= MIN_SNAPSHOT_TEAMS
        if complete:
            steps.append(("Pre-tournament snapshot", True, "Skipped: already complete"))
        else:
            for command in PRE_TOURNAMENT_CHAIN:
                self._run_step(
                    f"Pre-tournament: {command}",
                    command,
                    {"season": season_year, "pre_tournament": True},
                    steps,
                    fatal=False,
                    label="[tourney]",
                )
        self._run_step(
            "Tournament seeds (Wikipedia)",
            "backfill_tournament",
            {"season": season_year},
            steps,
            fatal=False,
            label="[tourney]",
        )

    @staticmethod
    def _season_has_final_games(season_year: int) -> bool:
        """True once enough of the field has played to rate the season (see MIN_TEAMS_PLAYED)."""
        from ncaa.seasons import season_is_underway

        return season_is_underway(season_year)

    def _finish_without_games(self, title: str, season_year: int, steps: list, start_time):
        """
        Stop a pipeline cleanly when its season has no final games yet (e.g. Nov 1, the
        day the daily gate opens, before the first tip-off). Computing on an empty
        season would write all-zero ratings rows and list a game-less season in the
        season picker, so nothing is computed and the run does not fail.
        """
        from ncaa.seasons import MIN_TEAMS_PLAYED, teams_with_final_games

        played = teams_with_final_games(season_year)
        note = f"Skipped: too early for {season_year} -- {played} teams have played (need {MIN_TEAMS_PLAYED})"
        self.stdout.write(self.style.WARNING(f"[SKIP] {note} -- nothing to compute\n"))
        steps.append((title, True, note))
        end_time = timezone.now()
        self._print_summary(start_time, end_time, (end_time - start_time).total_seconds(), steps, title=title)
        if any(not s[1] for s in steps):
            sys.exit(1)   # e.g. the ingest step failed: don't let "too early" mask it

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
