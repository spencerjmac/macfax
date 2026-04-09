"""
compute_ncaa_bpr — Management command to run the full BPR pipeline.

Usage:
    python manage.py compute_ncaa_bpr --season 2026
    python manage.py compute_ncaa_bpr --season 2026 --skip-box-bpr
    python manage.py compute_ncaa_bpr --season 2026 --lambda 1.0
    python manage.py compute_ncaa_bpr --season 2026 --validate-only

Run order:
  1. datasets.py: extract lineup segments from PlayerGameStint
  2. rapm.py: baseline RAPM with CV-selected lambda
  3. box_bpr.py: Box BPR (leak-free: prior-season training or OOF)
  4. rapm.py: tune prior SD scale by CV
  5. preseason.py: build prior maps from leak-free Box BPR
  6. rapm.py: prior-informed final BPR
  7. Write to PlayerSeasonStats (bulk_update)
  8. validation.py: sanity + predictive checks
"""

import logging

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Compute BPR (Bayesian Performance Rating) for all NCAA players in a season."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            required=True,
            help="Season year (e.g. 2026 for the 2025-26 season).",
        )
        parser.add_argument(
            "--skip-box-bpr",
            action="store_true",
            default=False,
            help="Skip Box BPR training (use flat priors only).",
        )
        parser.add_argument(
            "--skip-prior-rapm",
            action="store_true",
            default=False,
            help="Use baseline RAPM as final output, skip prior-informed RAPM.",
        )
        parser.add_argument(
            "--lambda",
            dest="lambda_override",
            type=float,
            default=None,
            help="Override RAPM regularization lambda (skips CV).",
        )
        parser.add_argument(
            "--validate-only",
            action="store_true",
            default=False,
            help="Only run validation against previously computed BPR (skip pipeline).",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        validate_only = options["validate_only"]

        if validate_only:
            self._run_validation(season_year)
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"\nBPR Pipeline — season {season_year}\n")
        )

        from core.analytics.player_value.bpr.pipeline import run_bpr_season
        from core.analytics.player_value.bpr.validation import run_validation

        try:
            summary = run_bpr_season(
                season_year=season_year,
                skip_box_bpr=options["skip_box_bpr"],
                skip_prior_rapm=options["skip_prior_rapm"],
                rapm_lambda_override=options.get("lambda_override"),
                verbose=True,
            )
        except Exception as exc:
            logger.exception(f"BPR pipeline failed for season {season_year}")
            raise CommandError(f"BPR pipeline failed: {exc}") from exc

        # Print per-phase summary
        self.stdout.write(self.style.SUCCESS("\nPhase summary:"))
        for phase, stats in summary.get("phases", {}).items():
            self.stdout.write(f"  {phase}: {stats}")

        # Validation
        self.stdout.write(self.style.MIGRATE_HEADING("\nRunning post-compute validation …"))
        validation_results = run_validation(season_year, pipeline_summary=summary)
        self._print_validation(validation_results)

    def _run_validation(self, season_year: int):
        from core.analytics.player_value.bpr.validation import run_validation

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"\nBPR Validation — season {season_year}\n")
        )
        results = run_validation(season_year, pipeline_summary=None)
        self._print_validation(results)

    def _print_validation(self, results: dict):
        all_passed = results.get("all_passed")
        for key, val in results.items():
            style = self.style.SUCCESS if val is True else (
                self.style.ERROR if val is False else self.style.HTTP_INFO
            )
            self.stdout.write(f"  {key}: {style(str(val))}")

        if all_passed:
            self.stdout.write(self.style.SUCCESS("\nAll validation checks passed."))
        elif all_passed is False:
            self.stdout.write(
                self.style.WARNING("\nSome validation checks failed. Review logs above.")
            )
