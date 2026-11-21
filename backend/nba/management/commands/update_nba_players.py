"""
Update all NBA player data for a season.

Pipeline sequence:
  1. nba_sync_team_logs      — per-player box scores from NBA.com
  2. nba_compute_player_stats — roll up season averages
  3. nba_sync_player_advanced — advanced + impact stats from NBA.com
  4. nba_compute_box_bpr     — career-stabilized box BPR prior
  5. nba_compute_final_bpr   — prior-informed RAPM, writes final bpr/obpr/dbpr/wins_added
  6. nba_compute_career_bpr  — writes peak_bpr / career_bpr to NBAPlayer

Native path (task 5.9): when the season before --season holds native ratings
(bpr_model 'native-1'), steps 4-5 are replaced by
  a minutes vs game logs check (nba.native_pipeline; over 1% of players
  mismatching skips the rating steps and keeps yesterday's ratings),
  nba_sync_play_by_play (resume; skipped with --skip-ingest),
  nba_compute_baseline_rapm, nba_fit_box_pooled --write and
  nba_compute_native_bpr --write (one transaction: on failure yesterday's
  ratings stay). nba_compute_box_bpr and nba_compute_final_bpr do not run.
Otherwise the steps are today's, unchanged.

Dependency:
  NBA team data must already be computed for the season. Run update_nba_teams
  first so games, team logs, and ratings are available.
  Steps 4-5 require baseline_obpr/dbpr from nba_compute_baseline_rapm
  (run update_nba_all --with-pbp to regenerate RAPM targets if needed).

Usage:
  python manage.py update_nba_players --season 2026
  python manage.py update_nba_players --season 2026 --skip-ingest
  python manage.py update_nba_players --season 2026 --workers 4
  python manage.py update_nba_players --season 2024  # backfill example
"""

import sys

from django.core.management.base import CommandError
from django.utils import timezone

from ncaa.management.commands._pipeline_base import BasePipelineCommand
from nba.native_pipeline import MAX_MISMATCH_SHARE, last_season_is_native, minutes_check
from nba.seasons import resolve_season_year

TOTAL_STEPS = 6


class Command(BasePipelineCommand):
    help = "Update all NBA player data for a season (ingest + compute stats + advanced)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, default=None,
            help='Season ending year (default: the season in play, e.g. 2027 for 2026-27)',
        )
        parser.add_argument(
            "--skip-ingest",
            action="store_true",
            help="Skip NBA player box score ingestion",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            help="Parallel workers for nba_sync_team_logs",
        )
        parser.add_argument(
            "--pbp-workers",
            type=int,
            default=1,
            help="Native path: parallel workers for nba_sync_play_by_play (max 3)",
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        season_year = resolve_season_year(options["season"])
        skip_ingest = options["skip_ingest"]
        workers = int(options.get("workers", 1))

        if workers < 1:
            raise CommandError("--workers must be 1 or greater")

        self._header("NBA PLAYER DATA", season_year)
        self._run_setup(ncaa=False, nba=True)
        self._ensure_season(season_year)
        steps = []

        if not skip_ingest:
            self._run_step(
                "NBA sync player box scores",
                "nba_sync_team_logs",
                {"season": season_year, "workers": workers},
                steps,
                fatal=False,
                label=f"[1/{TOTAL_STEPS}]",
            )
        else:
            self._skip_step(
                "NBA sync player box scores",
                steps,
                "Skipped (--skip-ingest)",
            )

        self._run_step(
            "NBA compute player stats",
            "nba_compute_player_stats",
            {"season": season_year},
            steps,
            fatal=True,
            label=f"[2/{TOTAL_STEPS}]",
        )
        self._run_step(
            "NBA sync player advanced",
            "nba_sync_player_advanced",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[3/{TOTAL_STEPS}]",
        )
        if last_season_is_native(season_year):
            pbp_workers = max(1, min(3, int(options.get("pbp_workers") or 1)))
            self._run_native_ratings(season_year, steps, skip_ingest, pbp_workers)
        else:
            self._run_step(
                "NBA compute box BPR",
                "nba_compute_box_bpr",
                {"season": season_year},
                steps,
                fatal=False,
                label=f"[4/{TOTAL_STEPS}]",
            )
            self._run_step(
                "NBA compute final BPR",
                "nba_compute_final_bpr",
                {"season": season_year},
                steps,
                fatal=False,
                label=f"[5/{TOTAL_STEPS}]",
            )
        self._run_step(
            "NBA compute career BPR (peak + career averages)",
            "nba_compute_career_bpr",
            {},
            steps,
            fatal=False,
            label=f"[6/{TOTAL_STEPS}]",
        )

        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        self._print_summary(
            start_time,
            end_time,
            duration,
            steps,
            title="NBA PLAYER DATA UPDATE",
        )
        if any(not s[1] for s in steps):
            sys.exit(1)

    def _run_native_ratings(self, season_year, steps, skip_ingest, pbp_workers):
        """Native path in place of steps 4-5 (see the module docstring)."""
        self.stdout.write(f"[NATIVE] {season_year - 1} holds native ratings: native rating steps for {season_year}\n")
        name = "Minutes vs game logs check"
        check = minutes_check(season_year)
        for m in check.mismatches[:10]:
            self.stdout.write(self.style.WARNING(
                f"  [WARN] {m['name'] or m['nba_id']}: season rows {m['row_gp']} games / {m['row_min']} min, "
                f"game logs {m['log_gp']} games / {m['log_min']} min"))
        summary = f"{len(check.mismatches)} of {check.players} players mismatch ({check.share:.1%})"
        if check.too_many:
            note = f"{summary}, over {MAX_MISMATCH_SHARE:.0%}: rating steps skipped, yesterday's ratings kept"
            steps.append((name, False, note))
            self.stderr.write(self.style.ERROR(f"[FAIL] {name}: {note}\n"))
        else:
            steps.append((name, True, None))
            self.stdout.write(f"[{'WARN' if check.mismatches else 'OK'}] {name}: {summary}\n")
        if skip_ingest:
            self._skip_step("NBA sync play-by-play (resume)", steps, "Skipped (--skip-ingest)")
        else:
            self._run_step("NBA sync play-by-play (resume)", "nba_sync_play_by_play",
                           {"season": season_year, "workers": pbp_workers}, steps, fatal=False, label="[N]")
        rating_steps = [
            ("NBA compute baseline RAPM", "nba_compute_baseline_rapm", {"season": season_year}),
            ("NBA fit box BPR (pooled)", "nba_fit_box_pooled", {"season": season_year, "write": True}),
            ("NBA compute native BPR", "nba_compute_native_bpr", {"season": season_year, "write": True}),
        ]
        for step_name, cmd, kwargs in rating_steps:
            if check.too_many:
                self._skip_step(step_name, steps, "Skipped (minutes check failed; yesterday's ratings kept)")
            else:
                self._run_step(step_name, cmd, kwargs, steps, fatal=False, label="[N]")
        _, ok, note = steps[-1]
        if not ok:
            self.stderr.write(self.style.ERROR(
                f"[KEEP] native BPR failed for {season_year}; its write is one transaction, so yesterday's "
                f"ratings stay: {note}\n"))
