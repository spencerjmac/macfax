"""
Management command: update_nba_all
Runs the complete NBA data pipeline (game ingest + player stats + ratings).

Full pipeline sequence
──────────────────────
SETUP (always, fast, idempotent)
  • nba_sync_teams — seed/update all 30 NBA franchises

NBA PIPELINE
  INGEST (skipped when --skip-ingest)
    1. nba_sync_games         — NBA.com season game log + team box scores
    2. nba_sync_team_logs     — per-player box scores (BoxScoreTraditionalV3)

  COMPUTE
    3. nba_compute_ratings    — opponent-adjusted ratings + FFI
    4. nba_compute_player_stats — roll up player season averages
    5. nba_sync_player_advanced — advanced + impact stats from NBA.com
    6. nba_compute_box_bpr    — box-score BPR + archetype classification
    ...
   10. nba_compute_player_stats (Playoffs)
   11. nba_sync_injury_report — today's ESPN injury report → NBAPlayerAvailability

  NATIVE PATH (task 5.9): when the season before --season holds native ratings
  (bpr_model 'native-1'), steps 3-11 above are replaced, after the same ingest, by
    N3  nba_compute_player_stats (Regular Season)
    N4  minutes vs game logs check (nba.native_pipeline): any mismatch is logged; over
        1% of players mismatching skips N8-N10 and keeps yesterday's ratings
    N5  nba_compute_ratings (Regular Season)    -- the box fit reads team ratings
    N6  nba_sync_player_advanced                -- and NBA.com rate stats
    N7  nba_sync_play_by_play (resumes: games already synced are skipped)
    N8  nba_compute_baseline_rapm
    N9  nba_fit_box_pooled --write              -- box rows only for players meeting the box rule
    N10 nba_compute_native_bpr --write          -- one transaction: on failure yesterday's
                                                   ratings stay, and the run logs it
    N11 nba_compute_career_bpr, then the playoff steps and the injury report as today.
  nba_compute_box_bpr and nba_compute_final_bpr do not run on the native path, and
  --with-pbp is ignored there (play-by-play always runs). Otherwise the steps are
  today's, unchanged.

  PBP + RAPM (only when --with-pbp, takes hours on first run)
    7. nba_sync_play_by_play  — PBP ingestion into NBAPlayerGameStint
    8. nba_compute_baseline_rapm — fit baseline RAPM, write baseline_obpr/dbpr
    9. nba_compute_box_bpr (re-run) — retrain box BPR with RAPM targets
   10. nba_compute_final_bpr  — prior-informed RAPM, writes final bpr/obpr/dbpr

Usage
─────
  python manage.py update_nba_all --season 2026
  python manage.py update_nba_all --season 2026 --skip-ingest
  python manage.py update_nba_all --season 2026 --workers 4
  python manage.py update_nba_all --season 2026 --with-pbp         # add PBP+RAPM
  python manage.py update_nba_all --season 2026 --with-pbp --pbp-workers 3
"""

import sys
import time
from datetime import date

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone

from config.season_calendar import season_in_play
from nba.analytics.lebron_utils import lebron_csv_path
from nba.models import NBAGame, NBAPlayerSeasonStats
from nba.native_pipeline import MAX_MISMATCH_SHARE, last_season_is_native, minutes_check
from nba.seasons import activate_latest_season, resolve_season_year

TOTAL_STEPS = 11
NATIVE_TOTAL_STEPS = 14
# Mismatching players printed by the minutes check (all are counted)
MISMATCH_LINES = 10

# nba_compute_box_bpr trains on RAPM targets and refuses to run with fewer than this many players
MIN_RAPM_TARGETS = 20


class Command(BaseCommand):
    help = "Run the complete NBA data pipeline"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, default=None,
            help="Season ending year (e.g. 2026) (default: the season in play)",
        )
        parser.add_argument(
            "--skip-ingest",
            action="store_true",
            help="Skip game ingestion — only recompute stats/ratings",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            metavar="N",
            help="Parallel workers for nba_sync_team_logs (default: 1)",
        )
        parser.add_argument(
            "--with-pbp",
            action="store_true",
            help="Also run PBP ingestion + baseline RAPM (takes hours on first run)",
        )
        parser.add_argument(
            "--pbp-workers",
            type=int,
            default=1,
            metavar="N",
            help="Parallel workers for nba_sync_play_by_play (default: 1, max 3)",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Entry point
    # ──────────────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        season_year = resolve_season_year(options["season"])
        skip_ingest = options["skip_ingest"]
        workers = max(1, int(options.get("workers", 1)))
        with_pbp = options.get("with_pbp", False)
        pbp_workers = max(1, min(3, int(options.get("pbp_workers", 1))))

        start_time = timezone.now()

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("MACFAX — NBA DATA PIPELINE UPDATE")
        self.stdout.write("=" * 80)
        self.stdout.write(
            f"Season : {season_year} ({season_year-1}-{str(season_year)[2:]})"
        )
        self.stdout.write(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write("=" * 80 + "\n")

        # ── SETUP (idempotent pre-flight, not counted in step numbers) ────────
        self._run_setup()

        # ── Pipeline steps ────────────────────────────────────────────────────
        steps = []

        # Step 1 — NBA game log ingest (Regular Season + PlayIn + Playoffs)
        if not skip_ingest:
            for season_type in ["Regular Season", "PlayIn", "Playoffs"]:
                self._run_unless(
                    None if season_type == "Regular Season" else self._skip_reason_postseason(season_year, season_type),
                    f"NBA sync games ({season_type})",
                    "nba_sync_games",
                    {"season": season_year, "season_type": season_type},
                    steps,
                    fatal=False,
                    label=f"[1/{TOTAL_STEPS}]",
                )
        else:
            self.stdout.write(f"[SKIP] [1/{TOTAL_STEPS}] Skipping NBA game log ingest\n")
            steps.append(("NBA sync games", True, "Skipped (--skip-ingest)"))

        # Step 2 — NBA per-player box scores
        if not skip_ingest:
            self._run_step(
                "NBA sync player box scores",
                "nba_sync_team_logs",
                {"season": season_year, "workers": workers},
                steps,
                fatal=False,
                label=f"[2/{TOTAL_STEPS}]",
            )
        else:
            self.stdout.write(f"[SKIP] [2/{TOTAL_STEPS}] Skipping NBA player box score ingest\n")
            steps.append(("NBA sync player box scores", True, "Skipped (--skip-ingest)"))

        if last_season_is_native(season_year):
            if with_pbp:
                self.stdout.write("[NATIVE] --with-pbp ignored: the native path always syncs play-by-play\n")
            self._run_native_steps(season_year, steps, skip_ingest, pbp_workers)
        else:
            self._run_legacy_steps(season_year, steps, with_pbp, pbp_workers)

        # Show the new season once it has a final regular-season game
        self._activate_latest_season(steps)

        # Summary
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        failed = any(not s[1] for s in steps)
        self._print_summary(start_time, end_time, duration, steps, failed)

        if failed:
            sys.exit(1)

    # ──────────────────────────────────────────────────────────────────────────
    # Rating paths
    # ──────────────────────────────────────────────────────────────────────────

    def _run_legacy_steps(self, season_year, steps, with_pbp, pbp_workers):
        """Steps 3-11 and the optional PBP block: the pipeline before native BPR, unchanged."""
        self._run_step(
            "NBA compute ratings (Regular Season)",
            "nba_compute_ratings",
            {"season": season_year, "season_type": "regular"},
            steps,
            label=f"[3/{TOTAL_STEPS}]",
        )
        self._run_step(
            "NBA compute player stats (Regular Season)",
            "nba_compute_player_stats",
            {"season": season_year, "season_type": "regular"},
            steps,
            label=f"[4/{TOTAL_STEPS}]",
        )
        self._run_step(
            "NBA sync player advanced",
            "nba_sync_player_advanced",
            {"season": season_year},
            steps,
            label=f"[5/{TOTAL_STEPS}]",
        )
        self._run_unless(
            self._skip_reason_box_bpr(season_year),
            "NBA compute box BPR",
            "nba_compute_box_bpr",
            {"season": season_year},
            steps,
            label=f"[6/{TOTAL_STEPS}]",
        )
        self._run_unless(
            self._skip_reason_final_bpr(season_year),
            "NBA compute final BPR",
            "nba_compute_final_bpr",
            {"season": season_year},
            steps,
            label=f"[7/{TOTAL_STEPS}]",
        )
        self._run_step(
            "NBA compute career BPR (peak + career averages)",
            "nba_compute_career_bpr",
            {},
            steps,
            label=f"[8/{TOTAL_STEPS}]",
        )
        playoffs_skip = self._skip_reason_playoffs(season_year)
        self._run_unless(
            playoffs_skip,
            "NBA compute ratings (Playoffs)",
            "nba_compute_ratings",
            {"season": season_year, "season_type": "playoffs"},
            steps,
            fatal=False,
            label=f"[9/{TOTAL_STEPS}]",
        )
        self._run_unless(
            playoffs_skip,
            "NBA compute player stats (Playoffs)",
            "nba_compute_player_stats",
            {"season": season_year, "season_type": "playoffs"},
            steps,
            fatal=False,
            label=f"[10/{TOTAL_STEPS}]",
        )
        self._run_step(
            "NBA sync injury report (ESPN)",
            "nba_sync_injury_report",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[11/{TOTAL_STEPS}]",
        )

        # ── Optional PBP + RAPM (--with-pbp only) ────────────────────────────
        if with_pbp:
            self._run_step(
                "NBA sync play-by-play",
                "nba_sync_play_by_play",
                {"season": season_year, "workers": pbp_workers},
                steps,
                label="[PBP-1/5]",
            )
            self._run_step(
                "NBA compute baseline RAPM",
                "nba_compute_baseline_rapm",
                {"season": season_year},
                steps,
                label="[PBP-2/5]",
            )
            self._run_step(
                "NBA compute box BPR (RAPM targets)",
                "nba_compute_box_bpr",
                {"season": season_year},
                steps,
                label="[PBP-3/5]",
            )
            self._run_step(
                "NBA compute final BPR (prior-informed RAPM)",
                "nba_compute_final_bpr",
                {"season": season_year},
                steps,
                label="[PBP-4/5]",
            )
            self._run_step(
                "NBA compute career BPR (peak + career averages)",
                "nba_compute_career_bpr",
                {},
                steps,
                label="[PBP-5/5]",
            )

    def _run_native_steps(self, season_year, steps, skip_ingest, pbp_workers):
        """Steps N3-N11 (see the module docstring): native BPR for a season whose previous season is native."""
        total = NATIVE_TOTAL_STEPS
        self.stdout.write(f"[NATIVE] {season_year - 1} holds native ratings: native rating steps for {season_year}\n")
        self._run_step(
            "NBA compute player stats (Regular Season)",
            "nba_compute_player_stats",
            {"season": season_year, "season_type": "regular"},
            steps,
            label=f"[N3/{total}]",
        )
        ratings_ok = self._minutes_check(season_year, steps, label=f"[N4/{total}]")
        self._run_step(
            "NBA compute ratings (Regular Season)",
            "nba_compute_ratings",
            {"season": season_year, "season_type": "regular"},
            steps,
            label=f"[N5/{total}]",
        )
        self._run_step(
            "NBA sync player advanced",
            "nba_sync_player_advanced",
            {"season": season_year},
            steps,
            label=f"[N6/{total}]",
        )
        self._run_unless(
            "--skip-ingest" if skip_ingest else None,
            "NBA sync play-by-play (resume)",
            "nba_sync_play_by_play",
            {"season": season_year, "workers": pbp_workers},
            steps,
            label=f"[N7/{total}]",
        )
        skip_ratings = None if ratings_ok else "minutes check failed; yesterday's ratings kept"
        self._run_unless(
            skip_ratings,
            "NBA compute baseline RAPM",
            "nba_compute_baseline_rapm",
            {"season": season_year},
            steps,
            label=f"[N8/{total}]",
        )
        self._run_unless(
            skip_ratings,
            "NBA fit box BPR (pooled)",
            "nba_fit_box_pooled",
            {"season": season_year, "write": True},
            steps,
            label=f"[N9/{total}]",
        )
        self._run_unless(
            skip_ratings,
            "NBA compute native BPR",
            "nba_compute_native_bpr",
            {"season": season_year, "write": True},
            steps,
            label=f"[N10/{total}]",
        )
        name, ok, note = steps[-1]
        if not ok:
            self.stderr.write(self.style.ERROR(
                f"[KEEP] native BPR failed for {season_year}; its write is one transaction, so yesterday's "
                f"ratings stay: {note}\n"))
        self._run_step(
            "NBA compute career BPR (peak + career averages)",
            "nba_compute_career_bpr",
            {},
            steps,
            label=f"[N11/{total}]",
        )
        playoffs_skip = self._skip_reason_playoffs(season_year)
        self._run_unless(
            playoffs_skip,
            "NBA compute ratings (Playoffs)",
            "nba_compute_ratings",
            {"season": season_year, "season_type": "playoffs"},
            steps,
            fatal=False,
            label=f"[N12/{total}]",
        )
        self._run_unless(
            playoffs_skip,
            "NBA compute player stats (Playoffs)",
            "nba_compute_player_stats",
            {"season": season_year, "season_type": "playoffs"},
            steps,
            fatal=False,
            label=f"[N13/{total}]",
        )
        self._run_step(
            "NBA sync injury report (ESPN)",
            "nba_sync_injury_report",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[N14/{total}]",
        )

    def _minutes_check(self, season_year, steps, label) -> bool:
        """Season rows vs game logs; logs every mismatch. False (step failed) when over the share limit."""
        name = "Minutes vs game logs check"
        self.stdout.write(f"{label} {name}...")
        t0 = time.monotonic()
        try:
            check = minutes_check(season_year)
        except Exception as e:
            steps.append((name, False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] {name}: {e}\n"))
            return False
        n = len(check.mismatches)
        for m in check.mismatches[:MISMATCH_LINES]:
            self.stdout.write(self.style.WARNING(
                f"  [WARN] {m['name'] or m['nba_id']}: season rows {m['row_gp']} games / {m['row_min']} min, "
                f"game logs {m['log_gp']} games / {m['log_min']} min"))
        if n > MISMATCH_LINES:
            self.stdout.write(self.style.WARNING(f"  [WARN] ... and {n - MISMATCH_LINES} more"))
        summary = f"{n} of {check.players} players mismatch ({check.share:.1%})"
        secs = time.monotonic() - t0
        if check.too_many:
            note = f"{summary}, over {MAX_MISMATCH_SHARE:.0%}: rating steps skipped, yesterday's ratings kept"
            steps.append((name, False, note))
            self.stderr.write(self.style.ERROR(f"[FAIL] {name}: {note} ({secs:.1f}s)\n"))
            return False
        steps.append((name, True, None))
        style = self.style.WARNING if n else self.style.SUCCESS
        self.stdout.write(style(f"[{'WARN' if n else 'OK'}] {name}: {summary} ({secs:.1f}s)\n"))
        return True

    # ──────────────────────────────────────────────────────────────────────────
    # Prerequisite checks: a step whose input doesn't exist yet is skipped with a
    # reason in the summary instead of failing (and failing the whole daily run).
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _skip_reason_postseason(season_year: int, season_type: str, today: date | None = None) -> str | None:
        """Play-in and playoff games can't exist while the season in play is still in its Oct-Mar stretch."""
        today = today or date.today()
        if season_year == season_in_play(today) and today.month in (10, 11, 12, 1, 2, 3):
            return f"{season_type} games can't exist before April"
        return None

    @staticmethod
    def _skip_reason_playoffs(season_year: int) -> str | None:
        if NBAGame.objects.filter(season__year=season_year, season_type="playoffs").exists():
            return None
        return f"no playoff games for {season_year} yet"

    @staticmethod
    def _skip_reason_box_bpr(season_year: int) -> str | None:
        n = NBAPlayerSeasonStats.objects.filter(
            season__year=season_year,
            baseline_obpr__isnull=False,
            baseline_dbpr__isnull=False,
        ).count()
        if n >= MIN_RAPM_TARGETS:
            return None
        return (
            f"no RAPM targets for {season_year} ({n} players, need {MIN_RAPM_TARGETS}); "
            "run update_nba_all --with-pbp"
        )

    @staticmethod
    def _skip_reason_final_bpr(season_year: int) -> str | None:
        path = lebron_csv_path(season_year)
        if path.exists():
            return None
        return f"missing LEBRON prior {path.name}"

    def _run_unless(self, skip_reason, name, cmd, kwargs, steps, **run_kwargs):
        """Run a step, or record it as skipped with the reason when a prerequisite is missing."""
        if skip_reason:
            label = run_kwargs.get("label", "")
            self.stdout.write(self.style.WARNING(f"[SKIP] {label} {name}: {skip_reason}\n"))
            steps.append((name, True, f"Skipped: {skip_reason}"))
            return
        self._run_step(name, cmd, kwargs, steps, **run_kwargs)

    def _activate_latest_season(self, steps):
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

    # ──────────────────────────────────────────────────────────────────────────
    # Setup (pre-flight, idempotent)
    # ──────────────────────────────────────────────────────────────────────────

    def _run_setup(self):
        try:
            self.stdout.write("[SETUP] Running nba_sync_teams...")
            call_command("nba_sync_teams")
            self.stdout.write(self.style.SUCCESS("[SETUP] NBA teams seeded\n"))
        except Exception as e:
            self.stderr.write(
                self.style.WARNING(f"[SETUP WARN] nba_sync_teams failed: {e}\n")
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _run_step(self, name, cmd, kwargs, steps, fatal=False, label=None):
        prefix = label or f"[--/{TOTAL_STEPS}]"
        self.stdout.write(f"{prefix} {name}...")
        t0 = time.monotonic()
        try:
            call_command(cmd, **kwargs)
            steps.append((name, True, None))
            self.stdout.write(self.style.SUCCESS(f"[OK] {name} ({time.monotonic() - t0:.1f}s)\n"))
        except Exception as e:
            steps.append((name, False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] {name}: {e} ({time.monotonic() - t0:.1f}s)\n"))
            if fatal:
                self._print_summary(timezone.now(), timezone.now(), 0, steps, True)
                sys.exit(1)

    def _print_summary(self, start_time, end_time, duration, steps, failed):
        self.stdout.write("\n" + "=" * 80)
        if not failed:
            self.stdout.write(
                self.style.SUCCESS("UPDATE COMPLETE — ALL STEPS SUCCESSFUL")
            )
        else:
            self.stdout.write(self.style.ERROR("UPDATE COMPLETED WITH ERRORS"))
        self.stdout.write("=" * 80)

        self.stdout.write("\nStep Summary:")
        for step_name, success, note in steps:
            if success and note and note.startswith("Skipped"):
                self.stdout.write(self.style.WARNING(f"  [SKIP] {step_name} -- {note.removeprefix('Skipped').lstrip(': ')}"))
            elif success:
                self.stdout.write(self.style.SUCCESS(f"  [OK]   {step_name}"))
            else:
                self.stdout.write(self.style.ERROR(f"  [FAIL] {step_name}: {note}"))

        self.stdout.write(f"\nStarted:  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Duration: {duration:.1f}s ({duration / 60:.1f} min)")
        self.stdout.write("\n" + "=" * 80 + "\n")

        if not failed:
            self.stdout.write(self.style.SUCCESS("All NBA data updated successfully!"))
            self.stdout.write("Website data is now current.")
