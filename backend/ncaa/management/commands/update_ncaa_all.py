"""
Management command: update_ncaa_all
Orchestrates the complete NCAA + NBA data pipeline by delegating to focused
sub-commands in dependency order.

Sub-commands (run independently or via this command):
  update_ncaa_teams   — steps 1-14:  ingest game logs + all team ratings/metrics
  update_ncaa_players — steps 1-11:  player box scores, PBP, BPR, projections, fit
  update_nba_all      — steps 1-10:  NBA full data pipeline (games, stats, BPR, playoffs)

Usage
─────
  python manage.py update_ncaa_all --season 2026
  python manage.py update_ncaa_all --season 2026 --skip-ingest
  python manage.py update_ncaa_all --season 2026 --days 3
  python manage.py update_ncaa_all --season 2026 --skip-player
  python manage.py update_ncaa_all --season 2026 --skip-nba
  python manage.py update_ncaa_all --season 2026 --ingest-workers 4 --player-workers 4
"""

import sys

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from ncaa.management.commands._pipeline_base import BasePipelineCommand
from ncaa.models import PipelineConfig


class Command(BasePipelineCommand):
    help = "Run the complete Macfax data pipeline (NCAA teams + players, NBA teams + players)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--skip-ingest",
            action="store_true",
            help="Skip all game log / PBP ingestion across every sub-pipeline",
        )
        parser.add_argument(
            "--days",
            type=int,
            help="NCAA team ingest: only fetch last N days of games",
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=None,
            help="Override adjusted-ratings solver iterations",
        )
        parser.add_argument(
            "--sor-trials",
            type=int,
            default=None,
            help="Override Monte Carlo trials for SOR",
        )
        parser.add_argument(
            "--ingest-workers",
            type=int,
            default=1,
            metavar="N",
            help="Workers for NCAA team game log ingest (default: 1)",
        )
        parser.add_argument(
            "--skip-player",
            action="store_true",
            help="Skip the NCAA player pipeline entirely",
        )
        parser.add_argument(
            "--player-workers",
            type=int,
            default=1,
            metavar="N",
            help="Workers for NCAA player gamelog + PBP ingest (default: 1)",
        )
        parser.add_argument(
            "--skip-nba",
            action="store_true",
            help="Skip both NBA sub-pipelines entirely",
        )
        parser.add_argument(
            "--nba-workers",
            type=int,
            default=1,
            metavar="N",
            help="Workers for NBA player box score ingest (default: 1)",
        )
        parser.add_argument(
            "--rapm-years",
            nargs="+",
            type=int,
            default=None,
            help="Years to pool for BPR RAPM estimation",
        )
        parser.add_argument(
            "--no-em-calibrate",
            dest="no_em_calibrate",
            action="store_true",
            default=False,
            help="Disable Evan Miya calibration for Box BPR training.",
        )

    def handle(self, *args, **options):
        season_year     = options["season"]
        skip_ingest     = options["skip_ingest"]
        skip_player     = options["skip_player"]
        skip_nba        = options["skip_nba"]
        days            = options.get("days")
        ingest_workers  = max(1, int(options.get("ingest_workers", 1)))
        player_workers  = max(1, int(options.get("player_workers", 1)))
        nba_workers     = max(1, int(options.get("nba_workers", 1)))
        rapm_years      = options.get("rapm_years")
        no_em_calibrate = options.get("no_em_calibrate", False)

        cfg = PipelineConfig.get_config()
        iterations = options["iterations"] or cfg.adj_ratings_iterations
        sor_trials  = options["sor_trials"]  or cfg.sor_trials

        start_time = timezone.now()
        self._header("FULL DATA PIPELINE UPDATE", season_year)

        ncaa_base = getattr(settings, "NCAA_API_BASE_URL", "https://ncaa-api.henrygd.me").rstrip("/")
        if "ncaa-api.henrygd.me" in ncaa_base:
            self.stdout.write(f"NCAA API: public demo — {ncaa_base}")
        else:
            self.stdout.write(self.style.SUCCESS(f"NCAA API: self-hosted — {ncaa_base}"))
        self.stdout.write("")

        steps = []

        # ── NCAA Team pipeline ────────────────────────────────────────────────
        self.stdout.write("─── NCAA Team Data ───────────────────────────────────")
        ncaa_team_kwargs = {
            "season":     season_year,
            "skip_ingest": skip_ingest,
            "workers":    ingest_workers,
            "iterations": iterations,
            "sor_trials": sor_trials,
        }
        if days:
            ncaa_team_kwargs["days"] = days
        self._run_step(
            "NCAA team pipeline",
            "update_ncaa_teams",
            ncaa_team_kwargs,
            steps,
            fatal=True,
            label="[A]",
        )

        # ── NCAA Player pipeline ──────────────────────────────────────────────
        if skip_player:
            self.stdout.write("[SKIP] NCAA player pipeline (--skip-player)\n")
            self._skip_step("NCAA player pipeline", steps, "Skipped (--skip-player)")
        else:
            self.stdout.write("─── NCAA Player Data ─────────────────────────────────")
            ncaa_player_kwargs = {
                "season":     season_year,
                "skip_ingest": skip_ingest,
                "workers":    player_workers,
            }
            if rapm_years:
                ncaa_player_kwargs["rapm_years"] = rapm_years
            if no_em_calibrate:
                ncaa_player_kwargs["no_em_calibrate"] = True
            self._run_step(
                "NCAA player pipeline",
                "update_ncaa_players",
                ncaa_player_kwargs,
                steps,
                fatal=False,
                label="[B]",
            )

        # ── NBA pipelines ─────────────────────────────────────────────────────
        if skip_nba:
            self.stdout.write("[SKIP] NBA pipelines (--skip-nba)\n")
            self._skip_step("NBA full pipeline",   steps, "Skipped (--skip-nba)")
        else:
            self.stdout.write("─── NBA Full Data Pipeline ───────────────────────────")
            self._run_step(
                "NBA full pipeline",
                "update_nba_all",
                {"season": season_year, "skip_ingest": skip_ingest, "workers": nba_workers},
                steps,
                fatal=False,
                label="[C]",
            )

        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        self._print_summary(start_time, end_time, duration, steps, title="FULL PIPELINE")
        if any(not s[1] for s in steps):
            sys.exit(1)
