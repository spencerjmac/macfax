"""
Management command: update_all
Runs the complete data pipeline to update all statistics and rankings.

Sequence:
1. Ingest game logs from NCAA API (optional in-process parallel via --ingest-workers)
2. Compute team metrics
3. Compute national averages
4-10. Adjusted ratings, adjusted four factors, four factor index, NET rankings, SOR, game values, SOS

Usage:
    python manage.py update_all --season 2026
    python manage.py update_all --season 2026 --ingest-workers 4
    python manage.py update_all --season 2026 --skip-ingest
"""

import sys
import os
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from django.db import connection
from core.models import Season


class Command(BaseCommand):
    help = "Run complete data pipeline to update all statistics and rankings with parallelization"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True, help="Season year (e.g., 2026)"
        )
        parser.add_argument(
            "--skip-ingest",
            action="store_true",
            help="Skip game ingestion (only recompute metrics)",
        )
        parser.add_argument(
            "--days",
            type=int,
            help="Ingest only games from last N days (e.g., --days 7 for last week)",
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=25,
            help="Number of iterations for adjusted ratings (default: 25)",
        )
        parser.add_argument(
            "--sor-trials",
            type=int,
            default=10000,
            help="Number of Monte Carlo trials for SOR (default: 10000)",
        )
        parser.add_argument(
            "--ingest-workers",
            type=int,
            default=1,
            metavar="N",
            help="In-process workers for game ingestion (default: 1). Use 2+ for parallel ingest without Redis.",
        )

    def handle(self, *args, **options):
        from datetime import datetime, timedelta
        
        season_year = options["season"]
        skip_ingest = options["skip_ingest"]
        days = options.get("days")
        iterations = options["iterations"]
        sor_trials = options["sor_trials"]
        ingest_workers = max(1, int(options.get("ingest_workers", 1)))

        start_time = timezone.now()

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("CBB ANALYTICS DASHBOARD - AUTOMATED UPDATE")
        self.stdout.write("=" * 80)
        self.stdout.write(
            f"Season: {season_year} ({season_year-1}-{str(season_year)[2:]})"
        )
        ncaa_base = getattr(settings, "NCAA_API_BASE_URL", "https://ncaa-api.henrygd.me").rstrip("/")
        if "ncaa-api.henrygd.me" in ncaa_base:
            self.stdout.write(f"NCAA API: public demo (fallback) — {ncaa_base}")
        else:
            self.stdout.write(self.style.SUCCESS(f"NCAA API: local/self-hosted — {ncaa_base}"))
        self.stdout.write(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write("=" * 80 + "\n")

        # Ensure all D1 teams exist in DB (idempotent)
        try:
            self.stdout.write("[0/9] Ensuring all D1 teams exist in Team table...")
            call_command("ensure_ncaa_teams")
            self.stdout.write(self.style.SUCCESS("[OK] Team table up to date\n"))
        except Exception as e:
            self.stderr.write(self.style.WARNING(f"[WARN] ensure_ncaa_teams failed: {e}\n"))

        # Ensure season exists
        try:
            self.stdout.write(f"[0/9] Ensuring Season {season_year} exists...")
            season, created = Season.objects.get_or_create(
                year=season_year,
                defaults={
                    "display_name": f"{season_year-1}-{str(season_year)[2:]}",
                    "is_current": True,
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"[OK] Created Season {season}\n"))
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"[OK] Using existing Season {season}\n")
                )
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f"[FAIL] Failed to create/get season: {e}\n")
            )
            sys.exit(1)

        # Track success/failure
        steps = []
        failed = False

        # Step 1: Ingest game logs (parallel if workers available)
        if not skip_ingest:
            try:
                self.stdout.write("[1/9] Ingesting game logs from NCAA API...")
                # In-process parallel ingest via --workers (no RQ); avoids racing step 2
                ingest_options = {"season": season_year, "workers": ingest_workers}
                
                # If --days specified, calculate date range ending yesterday.
                # Games are never available for the current day, so end_date
                # is always yesterday regardless of how many days are requested.
                #   --days 1  →  yesterday only
                #   --days 3  →  3 days ending yesterday
                if days:
                    from datetime import datetime, timedelta
                    yesterday = datetime.now().date() - timedelta(days=1)
                    start_date = yesterday - timedelta(days=days - 1)
                    end_date = yesterday
                    ingest_options["start"] = start_date.strftime("%Y-%m-%d")
                    ingest_options["end"] = end_date.strftime("%Y-%m-%d")
                    self.stdout.write(f"  Ingesting last {days} day(s): {start_date} to {end_date}")
                
                call_command("ingest_gamelogs", **ingest_options)
                steps.append(("Ingest game logs", True, None))
                self.stdout.write(self.style.SUCCESS("[OK] Game logs ingested\n"))
            except Exception as e:
                steps.append(("Ingest game logs", False, str(e)))
                self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
                failed = True
        else:
            self.stdout.write("\n[SKIP] [1/9] Skipping game ingestion\n")
            steps.append(("Ingest game logs", True, "Skipped"))

        # Step 2: Compute team metrics (BLOCKING - prerequisite for compute tasks)
        try:
            connection.close()
            self.stdout.write("[2/9] Computing team metrics (raw statistics)...")
            call_command("compute_team_metrics", season=season_year)
            steps.append(("Compute team metrics", True, None))
            self.stdout.write(self.style.SUCCESS("[OK] Team metrics computed\n"))
        except Exception as e:
            steps.append(("Compute team metrics", False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
            failed = True

        # Step 3: National averages (required by adjusted ratings, HCA, etc.)
        if not failed:
            try:
                self.stdout.write("[3/9] Computing national averages...")
                call_command("compute_national_averages", season=season_year)
                steps.append(("Compute national averages", True, None))
                self.stdout.write(self.style.SUCCESS("[OK] National averages computed\n"))
            except Exception as e:
                steps.append(("Compute national averages", False, str(e)))
                self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
                failed = True

        if failed:
            self._print_summary(start_time, steps, True)
            sys.exit(1)

        # Steps 4-10: Run compute tasks serially
        self._run_compute_serial(season_year, iterations, sor_trials, steps)

        # Summary
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()

        failed = any(not s[1] for s in steps)
        self._print_summary(start_time, steps, failed, duration)

        # Exit with error code if any step failed
        if failed:
            sys.exit(1)

    def _run_compute_serial(self, season_year, iterations, sor_trials, steps):
        """Run compute tasks sequentially (debugging/fallback)"""
        self.stdout.write("\n[SERIAL MODE] Running compute tasks sequentially...\n")

        tasks = [
            (
                4,
                "Compute adjusted ratings",
                "compute_adjusted_ratings",
                {"season": season_year, "iterations": iterations},
            ),
            (
                5,
                "Compute adjusted four factors",
                "compute_adjusted_four_factors",
                {"season": season_year},
            ),
            (
                6,
                "Compute four factor index",
                "compute_four_factor_index",
                {"season": season_year},
            ),
            (
                7,
                "Fetch NCAA NET rankings",
                "fetch_net_rankings",
                {"season": season_year},
            ),
            (
                8,
                "Compute Strength of Record",
                "compute_sor",
                {"season": season_year, "trials": sor_trials},
            ),
            (9, "Compute game values", "compute_game_value", {"season": season_year}),
            (10, "Compute Strength of Schedule", "compute_sos", {"season": season_year}),
        ]

        for idx, task_name, cmd_name, cmd_kwargs in tasks:
            try:
                self.stdout.write(f"[{idx}/10] {task_name}...")
                call_command(cmd_name, **cmd_kwargs)
                steps.append((task_name, True, None))
                self.stdout.write(self.style.SUCCESS(f"[OK] {task_name}\n"))
            except Exception as e:
                steps.append((task_name, False, str(e)))
                self.stderr.write(self.style.ERROR(f"[FAIL] {task_name}: {e}\n"))

    def _print_summary(self, start_time, steps, failed, duration=None):
        """Print execution summary"""
        end_time = timezone.now()
        if duration is None:
            duration = (end_time - start_time).total_seconds()

        self.stdout.write("\n" + "=" * 80)
        if not failed:
            self.stdout.write(
                self.style.SUCCESS("UPDATE COMPLETE - ALL STEPS SUCCESSFUL")
            )
        else:
            self.stdout.write(self.style.ERROR("UPDATE COMPLETED WITH ERRORS"))
        self.stdout.write("=" * 80)

        # Step summary
        self.stdout.write("\nStep Summary:")
        for step_name, success, error in steps:
            if success:
                if error == "Skipped":
                    self.stdout.write(f"  [SKIP] {step_name}: Skipped")
                else:
                    self.stdout.write(self.style.SUCCESS(f"  [OK] {step_name}"))
            else:
                self.stdout.write(self.style.ERROR(f"  [FAIL] {step_name}: {error}"))

        # Timing
        self.stdout.write(f"\nStarted:  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(
            f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)"
        )

        self.stdout.write("\n" + "=" * 80 + "\n")

        if not failed:
            self.stdout.write(self.style.SUCCESS("All data updated successfully!"))
            self.stdout.write("Website data is now current.")
