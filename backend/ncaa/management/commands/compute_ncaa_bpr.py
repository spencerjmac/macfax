"""
compute_ncaa_bpr — Management command to run the full BPR pipeline.

Usage:
    python manage.py compute_ncaa_bpr --season 2026
    python manage.py compute_ncaa_bpr --season 2026 --skip-box-bpr
    python manage.py compute_ncaa_bpr --season 2026 --lambda 1.0
    python manage.py compute_ncaa_bpr --season 2026 --validate-only
    python manage.py compute_ncaa_bpr --season 2026 --rapm-years 2024 2025 2026

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
        parser.add_argument(
            "--rapm-years",
            nargs="+",
            type=int,
            default=None,
            help=(
                "Explicit list of season years to pool for RAPM estimation. "
                "When provided, --rapm-window is ignored. "
                "In multi-year mode, observations from all listed seasons are pooled "
                "into a single design matrix. Coefficients are estimated at the "
                "player-season level — keyed by (player_id, season_year) — so the "
                "same player in different seasons receives independent coefficients, "
                "not a single pooled coefficient across seasons. "
                "Only the target season's (largest year's) coefficients and possession "
                "totals are written back to PlayerSeasonStats; earlier seasons "
                "contribute estimation power only. "
                "Example: --rapm-years 2024 2025 2026"
            ),
        )
        parser.add_argument(
            "--no-em-calibrate",
            dest="no_em_calibrate",
            action="store_true",
            default=False,
            help=(
                "Disable Evan Miya calibration for Box BPR training. "
                "When omitted (default), the pipeline uses EM adj_obpr/adj_dbpr from "
                "evan_miya_reference.RAW_DATA as box model training targets when available, "
                "fixing scale compression vs EM's published ratings. "
                "Pass this flag to fall back to multi-year RAPM or DB baseline targets."
            ),
        )
        parser.add_argument(
            "--rapm-window",
            dest="rapm_window_size",
            type=int,
            default=4,
            help=(
                "Number of seasons to pool for RAPM estimation (default: 4, matching "
                "EvanMiya methodology). The window is [season_year - N + 1, season_year]. "
                "Ignored if --rapm-years is specified explicitly. "
                "Pass 1 to revert to single-season mode."
            ),
        )
        parser.add_argument(
            "--no-truthful-targets",
            dest="truthful_targets",
            action="store_false",
            default=True,
            help=(
                "DEPRECATED ESCAPE HATCH (v1.7 default is truthful): re-admit "
                "pre-2025 placeholder-stint seasons to the RAPM pool, internal "
                "Box BPR targets, prior-history blend, and preseason training. "
                "Those seasons contain no substitution data (ESPN never served "
                "it — probed 2026-07); their 'RAPM' is starter-unit plus-minus. "
                "Use only for legacy comparisons."
            ),
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

        from ncaa.analytics.player_value.bpr.pipeline import run_bpr_season
        from ncaa.analytics.player_value.bpr.validation import run_validation

        try:
            summary = run_bpr_season(
                season_year=season_year,
                skip_box_bpr=options["skip_box_bpr"],
                skip_prior_rapm=options["skip_prior_rapm"],
                rapm_lambda_override=options.get("lambda_override"),
                rapm_years=options.get("rapm_years"),
                rapm_window_size=options.get("rapm_window_size", 4),
                em_calibrate=not options.get("no_em_calibrate", False),
                truthful_targets=options.get("truthful_targets", True),
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
        from ncaa.analytics.player_value.bpr.validation import run_validation

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"\nBPR Validation — season {season_year}\n")
        )
        results = run_validation(season_year, pipeline_summary=None)
        self._print_validation(results)

    def _print_validation(self, results: dict):
        core_passed   = results.get("all_passed_core")
        strict_passed = results.get("all_passed_strict")
        for key, val in results.items():
            style = self.style.SUCCESS if val is True else (
                self.style.ERROR if val is False else self.style.HTTP_INFO
            )
            self.stdout.write(f"  {key}: {style(str(val))}")

        self.stdout.write("")
        if core_passed:
            self.stdout.write(self.style.SUCCESS("  ✓ all_passed_core  (BPR arithmetic + plausible range)"))
        else:
            self.stdout.write(self.style.ERROR("  ✗ all_passed_core  — model output has errors, do not publish."))

        if strict_passed:
            self.stdout.write(self.style.SUCCESS("  ✓ all_passed_strict (core + completeness + HCA + predictive gain + partial rate)"))
        elif strict_passed is False:
            self.stdout.write(
                self.style.WARNING(
                    "  ✗ all_passed_strict — one or more quality checks failed. "
                    "Review qualified_player_check, hca_plausible, predictive_eval, n_partial_bpr."
                )
            )
