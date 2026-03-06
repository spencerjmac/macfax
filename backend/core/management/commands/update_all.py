"""
Management command: update_all
Runs the complete data pipeline to update all statistics and rankings.

Full pipeline sequence
──────────────────────
SETUP (always, fast, idempotent)
  • ensure_ncaa_teams   — create/update canonical D1 team stubs + aliases from YAML
  • fix_team_duplicates — merge informal-name duplicates (e.g. UConn→Connecticut)
                          guards against ingest having been run out of order
  • sync_team_d1_status — ensure is_d1 flags match the YAML canonical list
  • Season creation     — create Season row if it doesn't exist yet

INGEST (skipped when --skip-ingest)
  1. ingest_gamelogs    — fetch new box-scores from NCAA API

COMPUTE (always)
  2.  compute_team_metrics        — raw per-team/per-game aggregates
  3.  compute_national_averages   — national baseline stats (prereq for everything below)
  4.  compute_adjusted_ratings    — iterative AdjO / AdjD / AdjEM / AdjTempo
  5.  compute_hca                 — Home Court Advantage estimate → NationalAverages.hca_points
  6.  compute_sigma               — prediction error std-dev → NationalAverages.prediction_sigma
  7.  compute_adjusted_four_factors
  8.  compute_four_factor_index
  9.  train_four_factor_regression — OLS coefficients for pts_from_efg/tov/orb/ftr → matchup impact
  10. fetch_net_rankings          — pull NET rankings from NCAA (external API)
  11. compute_sor                 — Strength of Record (Monte Carlo, uses hca + sigma)
  12. compute_game_value          — per-game resume value (uses hca + sigma)
  13. compute_sos                 — Strength of Schedule (uses AdjEM)
  14. compute_wab                 — Wins Above Bubble (uses hca + sigma + AdjEM)

Usage
─────
  python manage.py update_all --season 2026
  python manage.py update_all --season 2026 --days 3
  python manage.py update_all --season 2026 --skip-ingest
  python manage.py update_all --season 2026 --ingest-workers 4
"""

import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from django.db import connection

from core.models import Season

TOTAL_STEPS = 14


class Command(BaseCommand):
    help = "Run the complete CBB Analytics data pipeline"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True, help="Season ending year (e.g. 2026)"
        )
        parser.add_argument(
            "--skip-ingest",
            action="store_true",
            help="Skip game ingestion — only recompute metrics/ratings",
        )
        parser.add_argument(
            "--days",
            type=int,
            help="Ingest only the last N days of games (including today)",
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=None,
            help="Iterations for adjusted-ratings solver (default: from PipelineConfig)",
        )
        parser.add_argument(
            "--sor-trials",
            type=int,
            default=None,
            help="Monte-Carlo trials for SOR (default: from PipelineConfig)",
        )
        parser.add_argument(
            "--ingest-workers",
            type=int,
            default=1,
            metavar="N",
            help="Parallel ingest workers (default: 1)",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Entry point
    # ──────────────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        from datetime import datetime, timedelta
        from core.models import PipelineConfig

        cfg = PipelineConfig.get_config()

        season_year = options["season"]
        skip_ingest = options["skip_ingest"]
        days = options.get("days")
        # CLI args override config; config values are the stored defaults
        iterations = options["iterations"] or cfg.adj_ratings_iterations
        sor_trials = options["sor_trials"] or cfg.sor_trials
        ingest_workers = max(1, int(options.get("ingest_workers", 1)))

        start_time = timezone.now()

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("CBB ANALYTICS DASHBOARD — AUTOMATED UPDATE")
        self.stdout.write("=" * 80)
        self.stdout.write(
            f"Season : {season_year} ({season_year-1}-{str(season_year)[2:]})"
        )
        ncaa_base = getattr(
            settings, "NCAA_API_BASE_URL", "https://ncaa-api.henrygd.me"
        ).rstrip("/")
        if "ncaa-api.henrygd.me" in ncaa_base:
            self.stdout.write(f"NCAA API: public demo (fallback) — {ncaa_base}")
        else:
            self.stdout.write(
                self.style.SUCCESS(f"NCAA API: self-hosted — {ncaa_base}")
            )
        self.stdout.write(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write("=" * 80 + "\n")

        # ── SETUP (idempotent pre-flight, not counted in step numbers) ────────
        self._run_setup()

        # ── Create / fetch Season row ─────────────────────────────────────────
        try:
            season, created = Season.objects.get_or_create(
                year=season_year,
                defaults={
                    "display_name": f"{season_year-1}-{str(season_year)[2:]}",
                    "is_current": True,
                },
            )
            verb = "Created" if created else "Using existing"
            self.stdout.write(self.style.SUCCESS(f"[SETUP] {verb} Season {season}\n"))
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f"[SETUP FATAL] Cannot create season: {e}\n")
            )
            sys.exit(1)

        # ── Pipeline steps ────────────────────────────────────────────────────
        steps = []

        # Step 1 — Ingest
        if not skip_ingest:
            ingest_options = {"season": season_year, "workers": ingest_workers}
            if days:
                today = datetime.now().date()
                start_date = today - timedelta(days=days - 1)
                ingest_options["start"] = start_date.strftime("%Y-%m-%d")
                ingest_options["end"] = today.strftime("%Y-%m-%d")
                self.stdout.write(
                    f"[1/{TOTAL_STEPS}] Ingesting last {days} day(s): "
                    f"{ingest_options['start']} → {ingest_options['end']}..."
                )
            else:
                self.stdout.write(
                    f"[1/{TOTAL_STEPS}] Ingesting game logs from NCAA API..."
                )
            self._run_step(
                "Ingest game logs",
                "ingest_gamelogs",
                ingest_options,
                steps,
                fatal=False,
            )
        else:
            self.stdout.write(f"[SKIP] [1/{TOTAL_STEPS}] Skipping game ingestion\n")
            steps.append(("Ingest game logs", True, "Skipped"))

        # Compute steps — exit early only if the foundations fail
        connection.close()  # fresh connection after potential parallel ingest

        self._run_step(
            "Compute team metrics",
            "compute_team_metrics",
            {"season": season_year},
            steps,
            fatal=True,
            label=f"[2/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute national averages",
            "compute_national_averages",
            {"season": season_year},
            steps,
            fatal=True,
            label=f"[3/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute adjusted ratings",
            "compute_adjusted_ratings",
            {"season": season_year, "iterations": iterations},
            steps,
            fatal=True,
            label=f"[4/{TOTAL_STEPS}]",
        )

        # HCA and sigma are derived from adjusted ratings — must come before
        # compute_sor, compute_game_value, and compute_wab which all depend on them.
        self._run_step(
            "Compute home-court advantage",
            "compute_hca",
            {"season": season_year},
            steps,
            label=f"[5/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute prediction sigma",
            "compute_sigma",
            {"season": season_year},
            steps,
            label=f"[6/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute adjusted four factors",
            "compute_adjusted_four_factors",
            {"season": season_year},
            steps,
            label=f"[7/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute four factor index",
            "compute_four_factor_index",
            {"season": season_year},
            steps,
            label=f"[8/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Train four factor regression",
            "train_four_factor_regression",
            {"season": season_year},
            steps,
            label=f"[9/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Fetch NET rankings",
            "fetch_net_rankings",
            {"season": season_year},
            steps,
            label=f"[10/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute Strength of Record",
            "compute_sor",
            {"season": season_year, "trials": sor_trials},
            steps,
            label=f"[11/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute game values",
            "compute_game_value",
            {"season": season_year},
            steps,
            label=f"[12/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute Strength of Schedule",
            "compute_sos",
            {"season": season_year},
            steps,
            label=f"[13/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute Wins Above Bubble",
            "compute_wab",
            {"season": season_year},
            steps,
            label=f"[14/{TOTAL_STEPS}]",
        )

        # Summary
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        failed = any(not s[1] for s in steps)
        self._print_summary(start_time, end_time, duration, steps, failed)

        if failed:
            sys.exit(1)

    # ──────────────────────────────────────────────────────────────────────────
    # Setup (pre-flight, idempotent)
    # ──────────────────────────────────────────────────────────────────────────

    def _run_setup(self):
        """
        Run idempotent pre-flight steps that ensure the Team table is correct
        before any ingestion or computation happens.

        1. ensure_ncaa_teams  — create canonical D1 stubs + populate aliases
        2. fix_team_duplicates — merge informal/canonical duplicates left over
                                 from any previous out-of-order ingest
        3. sync_team_d1_status — align is_d1 flags with the YAML canonical list
        """
        setup_steps = [
            ("ensure_ncaa_teams", {}, "D1 team stubs + aliases up to date"),
            ("fix_team_duplicates", {}, "Informal/canonical duplicates merged"),
            ("sync_team_d1_status", {}, "is_d1 flags synced"),
        ]

        for cmd, kwargs, ok_msg in setup_steps:
            try:
                self.stdout.write(f"[SETUP] Running {cmd}...")
                call_command(cmd, **kwargs)
                self.stdout.write(self.style.SUCCESS(f"[SETUP] {ok_msg}\n"))
            except Exception as e:
                # Setup failures are warnings — pipeline continues but may have
                # data-integrity issues that the operator should investigate.
                self.stderr.write(
                    self.style.WARNING(f"[SETUP WARN] {cmd} failed: {e}\n")
                )

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _run_step(self, name, cmd, kwargs, steps, fatal=False, label=None):
        """Run a single pipeline step, recording success/failure."""
        prefix = label or f"[--/{TOTAL_STEPS}]"
        self.stdout.write(f"{prefix} {name}...")
        try:
            call_command(cmd, **kwargs)
            steps.append((name, True, None))
            self.stdout.write(self.style.SUCCESS(f"[OK] {name}\n"))
        except Exception as e:
            steps.append((name, False, str(e)))
            self.stderr.write(self.style.ERROR(f"[FAIL] {name}: {e}\n"))
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
            if success:
                tag = "[SKIP]" if note == "Skipped" else "[OK]  "
                self.stdout.write(self.style.SUCCESS(f"  {tag} {step_name}"))
            else:
                self.stdout.write(self.style.ERROR(f"  [FAIL] {step_name}: {note}"))

        self.stdout.write(f"\nStarted:  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Duration: {duration:.1f}s ({duration / 60:.1f} min)")
        self.stdout.write("\n" + "=" * 80 + "\n")

        if not failed:
            self.stdout.write(self.style.SUCCESS("All data updated successfully!"))
            self.stdout.write("Website data is now current.")
