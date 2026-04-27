"""
Update all NCAA team data for a season.

Usage:
  python manage.py update_ncaa_teams --season 2026
  python manage.py update_ncaa_teams --season 2026 --skip-ingest
  python manage.py update_ncaa_teams --season 2026 --days 3
  python manage.py update_ncaa_teams --season 2021  # backfill example
"""

import sys
from datetime import datetime, timedelta

from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone

from core.management.commands._pipeline_base import BasePipelineCommand
from core.models import PipelineConfig

TOTAL_STEPS = 14


class Command(BasePipelineCommand):
    help = "Update all NCAA team data for a season (ingest + compute)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--skip-ingest",
            action="store_true",
            help="Skip game log ingestion, only recompute",
        )
        parser.add_argument(
            "--days",
            type=int,
            help="Ingest only the last N days of games",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            help="Parallel workers for ingest_gamelogs",
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=None,
            help="Override adj-ratings solver iterations",
        )
        parser.add_argument(
            "--sor-trials",
            type=int,
            default=None,
            help="Override Monte Carlo trials for SOR",
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        season_year = options["season"]
        skip_ingest = options["skip_ingest"]
        days = options.get("days")
        workers = max(1, int(options.get("workers", 1)))

        if days is not None and days < 1:
            raise CommandError("--days must be 1 or greater")

        cfg = PipelineConfig.get_config()
        iterations = options["iterations"] or cfg.adj_ratings_iterations
        sor_trials = options["sor_trials"] or cfg.sor_trials

        self._header("NCAA TEAM DATA", season_year)
        self._run_setup(ncaa=True, nba=False)
        self._ensure_season(season_year)
        steps = []

        if not skip_ingest:
            ingest_kwargs = {"season": season_year, "workers": workers}
            if days is not None:
                today = datetime.now().date()
                start_date = today - timedelta(days=days - 1)
                ingest_kwargs["start"] = start_date.strftime("%Y-%m-%d")
                ingest_kwargs["end"] = today.strftime("%Y-%m-%d")

            self._run_step(
                "Ingest game logs",
                "ingest_gamelogs",
                ingest_kwargs,
                steps,
                fatal=False,
                label=f"[1/{TOTAL_STEPS}]",
            )
        else:
            self._skip_step(
                "Ingest game logs",
                steps,
                "Skipped (--skip-ingest)",
            )

        connection.close()

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
        self._run_step(
            "Compute home-court advantage",
            "compute_hca",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[5/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute prediction sigma",
            "compute_sigma",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[6/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute adjusted four factors",
            "compute_adjusted_four_factors",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[7/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute four factor index",
            "compute_four_factor_index",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[8/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Train four factor regression",
            "train_four_factor_regression",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[9/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Fetch NET rankings",
            "fetch_net_rankings",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[10/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute Strength of Record",
            "compute_sor",
            {"season": season_year, "trials": sor_trials},
            steps,
            fatal=False,
            label=f"[11/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute game values",
            "compute_game_value",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[12/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute Strength of Schedule",
            "compute_sos",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[13/{TOTAL_STEPS}]",
        )
        self._run_step(
            "Compute Wins Above Bubble",
            "compute_wab",
            {"season": season_year},
            steps,
            fatal=False,
            label=f"[14/{TOTAL_STEPS}]",
        )

        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        self._print_summary(
            start_time,
            end_time,
            duration,
            steps,
            title="NCAA TEAM DATA UPDATE",
        )
        if any(not s[1] for s in steps):
            sys.exit(1)
