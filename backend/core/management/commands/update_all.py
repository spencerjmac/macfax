"""
Management command: update_all
Runs the complete data pipeline to update all statistics and rankings

This command executes all data update commands in the correct sequence:
1. Ingest game logs from NCAA API
2. Compute team metrics (raw statistics)
3. Compute adjusted ratings (efficiency)
4. Compute four factor index
5. Fetch NCAA NET rankings
6. Compute Strength of Record
7. Compute game values
8. Compute Strength of Schedule

Usage:
    python manage.py update_all --season 2026
    python manage.py update_all --season 2026 --skip-ingest  # Skip game ingestion
"""

import sys
from datetime import datetime
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone


class Command(BaseCommand):
    help = 'Run complete data pipeline to update all statistics and rankings'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (e.g., 2026)'
        )
        parser.add_argument(
            '--skip-ingest',
            action='store_true',
            help='Skip game ingestion (only recompute metrics)'
        )
        parser.add_argument(
            '--iterations',
            type=int,
            default=25,
            help='Number of iterations for adjusted ratings (default: 25)'
        )
        parser.add_argument(
            '--sor-trials',
            type=int,
            default=10000,
            help='Number of Monte Carlo trials for SOR (default: 10000)'
        )
    
    def handle(self, *args, **options):
        season_year = options['season']
        skip_ingest = options['skip_ingest']
        iterations = options['iterations']
        sor_trials = options['sor_trials']
        
        start_time = timezone.now()
        
        self.stdout.write("\n" + "="*80)
        self.stdout.write("CBB ANALYTICS DASHBOARD - AUTOMATED UPDATE")
        self.stdout.write("="*80)
        self.stdout.write(f"Season: {season_year}")
        self.stdout.write(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write("="*80 + "\n")
        
        # Track success/failure
        steps = []
        failed = False
        
        # Step 1: Ingest game logs
        if not skip_ingest:
            try:
                self.stdout.write("\n[1/8] Ingesting game logs from NCAA API...")
                call_command('ingest_gamelogs', season=season_year)
                steps.append(("Ingest game logs", True, None))
                self.stdout.write(self.style.SUCCESS("[OK] Game logs ingested\n"))
            except Exception as e:
                steps.append(("Ingest game logs", False, str(e)))
                self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
                failed = True
        else:
            self.stdout.write("\n[SKIP] [1/8] Skipping game ingestion\n")
            steps.append(("Ingest game logs", True, "Skipped"))
        
        # Step 2: Compute team metrics
        try:
            self.stdout.write("[2/8] Computing team metrics (raw statistics)...")
            call_command('compute_team_metrics', season=season_year)
            steps.append(("Compute team metrics", True, None))
            self.stdout.write(self.style.SUCCESS("[OK] Team metrics computed\n"))
        except Exception as e:
            steps.append(("Compute team metrics", False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
            failed = True
        
        # Step 3: Compute adjusted ratings
        try:
            self.stdout.write(f"[3/8] Computing adjusted ratings ({iterations} iterations)...")
            call_command('compute_adjusted_ratings', season=season_year, iterations=iterations)
            steps.append(("Compute adjusted ratings", True, None))
            self.stdout.write(self.style.SUCCESS("[OK] Adjusted ratings computed\n"))
        except Exception as e:
            steps.append(("Compute adjusted ratings", False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
            failed = True
        
        # Step 4: Compute four factor index
        try:
            self.stdout.write("[4/8] Computing four factor index...")
            call_command('compute_four_factor_index', season=season_year)
            steps.append(("Compute four factor index", True, None))
            self.stdout.write(self.style.SUCCESS("[OK] Four factor index computed\n"))
        except Exception as e:
            steps.append(("Compute four factor index", False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
            failed = True
        
        # Step 5: Fetch NET rankings
        try:
            self.stdout.write("[5/8] Fetching NCAA NET rankings...")
            call_command('fetch_net_rankings', season=season_year)
            steps.append(("Fetch NET rankings", True, None))
            self.stdout.write(self.style.SUCCESS("[OK] NET rankings fetched\n"))
        except Exception as e:
            steps.append(("Fetch NET rankings", False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
            failed = True
        
        # Step 6: Compute SOR
        try:
            self.stdout.write(f"[6/8] Computing Strength of Record ({sor_trials} trials)...")
            call_command('compute_sor', season=season_year, trials=sor_trials)
            steps.append(("Compute SOR", True, None))
            self.stdout.write(self.style.SUCCESS("[OK] SOR computed\n"))
        except Exception as e:
            steps.append(("Compute SOR", False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
            failed = True
        
        # Step 7: Compute game values
        try:
            self.stdout.write("[7/8] Computing game values...")
            call_command('compute_game_value', season=season_year)
            steps.append(("Compute game values", True, None))
            self.stdout.write(self.style.SUCCESS("[OK] Game values computed\n"))
        except Exception as e:
            steps.append(("Compute game values", False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
            failed = True
        
        # Step 8: Compute SOS
        try:
            self.stdout.write("[8/8] Computing Strength of Schedule...")
            call_command('compute_sos', season=season_year)
            steps.append(("Compute SOS", True, None))
            self.stdout.write(self.style.SUCCESS("[OK] SOS computed\n"))
        except Exception as e:
            steps.append(("Compute SOS", False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] Failed: {e}\n"))
            failed = True
        
        # Summary
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        
        self.stdout.write("\n" + "="*80)
        if not failed:
            self.stdout.write(self.style.SUCCESS("UPDATE COMPLETE - ALL STEPS SUCCESSFUL"))
        else:
            self.stdout.write(self.style.ERROR("UPDATE COMPLETED WITH ERRORS"))
        self.stdout.write("="*80)
        
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
        self.stdout.write(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
        
        self.stdout.write("\n" + "="*80 + "\n")
        
        # Exit with error code if any step failed
        if failed:
            self.stdout.write(self.style.WARNING("Some steps failed. Check errors above."))
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("All data updated successfully!"))
            self.stdout.write("Website data is now current.")
