"""
Management command: update_all
Runs the complete data pipeline to update all statistics and rankings

This command executes all data update commands in the correct sequence with parallelization:
1. Ingest game logs from NCAA API (single, blocking)
2. Compute team metrics (single, blocking - prerequisite for all compute tasks)
3-8. Run all compute tasks in parallel via django-rq job queue:
   - Compute adjusted ratings
   - Compute four factor index
   - Fetch NCAA NET rankings
   - Compute Strength of Record
   - Compute game values
   - Compute Strength of Schedule

Usage:
    python manage.py update_all --season 2026
    python manage.py update_all --season 2026 --skip-ingest  # Skip game ingestion
    python manage.py update_all --season 2026 --serial  # Run without job queue (debugging)
"""

import sys
import os
from datetime import datetime
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from core.models import Season
import django_rq


def run_compute_task(task_name, command_name, **kwargs):
    """Helper to run a single compute task"""
    try:
        call_command(command_name, **kwargs)
        return {"task": task_name, "success": True, "error": None}
    except Exception as e:
        return {"task": task_name, "success": False, "error": str(e)}


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
            "--serial",
            action="store_true",
            help="Run without job queue (for debugging or if Redis unavailable)",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        skip_ingest = options["skip_ingest"]
        iterations = options["iterations"]
        sor_trials = options["sor_trials"]
        serial_mode = options["serial"]

        start_time = timezone.now()

        # Detect active workers from Redis rq:workers set
        workers = 0
        if not serial_mode:
            try:
                import redis

                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                r = redis.from_url(redis_url)
                workers = r.scard("rq:workers")  # Get count of workers in the set
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(
                        f"Warning: Could not connect to Redis or detect workers: {e}"
                    )
                )
                workers = 0

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("CBB ANALYTICS DASHBOARD - AUTOMATED UPDATE")
        self.stdout.write("=" * 80)
        self.stdout.write(
            f"Season: {season_year} ({season_year-1}-{str(season_year)[2:]})"
        )

        if serial_mode:
            mode = "Serial (single-threaded)"
        elif workers == 0:
            mode = "Serial (no workers detected - fallback mode)"
            serial_mode = True  # Force serial if no workers
        else:
            mode = f"Parallel ({workers} active workers via job queue)"

        self.stdout.write(f"Mode: {mode}")
        self.stdout.write(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write("=" * 80 + "\n")

        # Ensure season exists
        try:
            self.stdout.write(f"[0/8] Ensuring Season {season_year} exists...")
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
                self.stdout.write("[1/8] Ingesting game logs from NCAA API...")
                # Always run ingestion serially in update_all to avoid racing downstream steps
                ingest_options = {"season": season_year}
                call_command("ingest_gamelogs", **ingest_options)
                steps.append(("Ingest game logs", True, None))
                self.stdout.write(self.style.SUCCESS("[OK] Game logs ingested\n"))
            except Exception as e:
                steps.append(("Ingest game logs", False, str(e)))
                self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
                failed = True
        else:
            self.stdout.write("\n[SKIP] [1/8] Skipping game ingestion\n")
            steps.append(("Ingest game logs", True, "Skipped"))

        # Step 2: Compute team metrics (BLOCKING - prerequisite for compute tasks)
        try:
            self.stdout.write("[2/8] Computing team metrics (raw statistics)...")
            call_command("compute_team_metrics", season=season_year)
            steps.append(("Compute team metrics", True, None))
            self.stdout.write(self.style.SUCCESS("[OK] Team metrics computed\n"))
        except Exception as e:
            steps.append(("Compute team metrics", False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
            failed = True

        if failed:
            # Don't proceed with parallel tasks if prerequisites failed
            self._print_summary(start_time, steps, True)
            sys.exit(1)

        # Steps 3-8: Run compute tasks in parallel or serial
        if serial_mode:
            self._run_compute_serial(season_year, iterations, sor_trials, steps)
        else:
            self._run_compute_parallel(
                season_year, iterations, sor_trials, steps, workers
            )

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
                3,
                "Compute adjusted ratings",
                "compute_adjusted_ratings",
                {"season": season_year, "iterations": iterations},
            ),
            (
                4,
                "Compute four factor index",
                "compute_four_factor_index",
                {"season": season_year},
            ),
            (
                5,
                "Fetch NCAA NET rankings",
                "fetch_net_rankings",
                {"season": season_year},
            ),
            (
                6,
                "Compute Strength of Record",
                "compute_sor",
                {"season": season_year, "trials": sor_trials},
            ),
            (7, "Compute game values", "compute_game_value", {"season": season_year}),
            (8, "Compute Strength of Schedule", "compute_sos", {"season": season_year}),
        ]

        for idx, task_name, cmd_name, cmd_kwargs in tasks:
            try:
                self.stdout.write(f"[{idx}/8] {task_name}...")
                call_command(cmd_name, **cmd_kwargs)
                steps.append((task_name, True, None))
                self.stdout.write(self.style.SUCCESS(f"[OK] {task_name}\n"))
            except Exception as e:
                steps.append((task_name, False, str(e)))
                self.stderr.write(self.style.ERROR(f"[FAIL] {task_name}: {e}\n"))

    def _run_compute_parallel(
        self, season_year, iterations, sor_trials, steps, workers
    ):
        """Run compute tasks in parallel using django-rq"""
        self.stdout.write(
            f"\n[PARALLEL MODE] Queueing compute tasks with {workers} workers...\n"
        )
        self.stdout.write(
            f"Note: Make sure you have at least {workers} rqworker processes running for full parallelism.\n"
        )
        self.stdout.write(
            f"      Run: python manage.py rqworker default high low (in {workers} separate terminals)\n\n"
        )

        try:
            queue = django_rq.get_queue("default")
            self.stdout.write(f"Connected to Redis queue: {queue}\n")
            jobs = []

            # Queue all compute tasks
            self.stdout.write("Enqueueing task 1/6: Compute adjusted ratings...\n")
            jobs.append(
                queue.enqueue(
                    run_compute_task,
                    "Compute adjusted ratings",
                    "compute_adjusted_ratings",
                    season=season_year,
                    iterations=iterations,
                    job_timeout=3600,
                )
            )

            jobs.append(
                queue.enqueue(
                    run_compute_task,
                    "Compute four factor index",
                    "compute_four_factor_index",
                    season=season_year,
                    job_timeout=3600,
                )
            )

            jobs.append(
                queue.enqueue(
                    run_compute_task,
                    "Fetch NCAA NET rankings",
                    "fetch_net_rankings",
                    season=season_year,
                    job_timeout=3600,
                )
            )

            jobs.append(
                queue.enqueue(
                    run_compute_task,
                    "Compute Strength of Record",
                    "compute_sor",
                    season=season_year,
                    trials=sor_trials,
                    job_timeout=3600,
                )
            )

            jobs.append(
                queue.enqueue(
                    run_compute_task,
                    "Compute game values",
                    "compute_game_value",
                    season=season_year,
                    job_timeout=3600,
                )
            )

            jobs.append(
                queue.enqueue(
                    run_compute_task,
                    "Compute Strength of Schedule",
                    "compute_sos",
                    season=season_year,
                    job_timeout=3600,
                )
            )

            self.stdout.write(f"Queued {len(jobs)} compute tasks\n")
            self.stdout.write("Waiting for jobs to complete...\n\n")

            # Monitor job completion
            import time

            completed = set()

            while len(completed) < len(jobs):
                for i, job in enumerate(jobs):
                    if i not in completed:
                        job.refresh()

                        if job.is_finished:
                            completed.add(i)
                            result = job.result
                            task_name = result["task"]

                            if result["success"]:
                                steps.append((task_name, True, None))
                                self.stdout.write(
                                    self.style.SUCCESS(f"[OK] {task_name}")
                                )
                            else:
                                steps.append((task_name, False, result["error"]))
                                self.stdout.write(
                                    self.style.ERROR(
                                        f"[FAIL] {task_name}: {result['error']}"
                                    )
                                )
                        elif job.is_failed:
                            completed.add(i)
                            task_name = f"Job {i}"
                            error = job.exc_info or "Unknown error"
                            steps.append((task_name, False, error))
                            self.stdout.write(
                                self.style.ERROR(f"[FAIL] {task_name}: {error}")
                            )

                if len(completed) < len(jobs):
                    time.sleep(2)  # Check every 2 seconds

            self.stdout.write(self.style.SUCCESS("\n✓ All compute tasks completed\n"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"[ERROR] Job queue error: {e}"))
            self.stdout.write("\nFalling back to serial mode...\n")
            self._run_compute_serial(season_year, iterations, sor_trials, steps)

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
