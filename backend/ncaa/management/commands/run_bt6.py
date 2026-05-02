"""
Management command: run_bt6

BT-6: Uncertainty band coverage calibration.

Measures whether projected_adj_em_low / projected_adj_em_high bands correctly
bracket actual outcomes ~68% of the time (±1σ target for a normal distribution).
Target range: 0.60–0.75 coverage.

Usage:
    python manage.py run_bt6
    python manage.py run_bt6 --years 2023 2024 2025
    python manage.py run_bt6 --apply    # write recommended constants if not no_change
"""

import os

from django.core.management.base import BaseCommand

from backtesting.roster_outlook.bt6_coverage_calibration import run_bt6
from ncaa.analytics.player_value.team_projection.constants import (
    UNCERTAINTY_SIGMA_SCALE,
    UNCERTAINTY_SIGMA_MAX,
)


class Command(BaseCommand):
    help = "BT-6: calibrate uncertainty band coverage against actual adj_em outcomes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--years",
            nargs="+",
            type=int,
            default=None,
            metavar="YEAR",
            help="Restrict to these source years. Default: all available.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write recommended constants to team_projection/constants.py (only when not 'no_change').",
        )

    def handle(self, *args, **options):
        years  = options["years"]
        apply  = options["apply"]

        self.stdout.write("\n[BT-6] Loading backtest data...")
        result = run_bt6(source_years=years)

        if result.n_teams == 0:
            self.stdout.write(self.style.WARNING(
                "\n[BT-6] No TeamSeasonProjection data found for the requested years.\n"
                "Phase 5 must have been run before BT-6 can evaluate coverage.\n"
            ))
            return

        # ── Print table ───────────────────────────────────────────────────────
        self.stdout.write(
            f"\nBT-6 Uncertainty Band Coverage Calibration"
            f"\n{'=' * 44}"
            f"\nSource years: {result.source_years_used}"
            f"\nTeams evaluated: {result.n_teams}"
            f"\nOverall coverage rate: {result.overall_coverage_rate:.4f}  (target: 0.60–0.75)"
            f"\nMean band width:   {result.mean_band_width:.3f} pts/100 poss"
            f"\nMedian band width: {result.median_band_width:.3f} pts/100 poss"
        )

        if result.n_teams < 100:
            self.stdout.write(self.style.WARNING(
                f"\n  ⚠ WARNING: Only {result.n_teams} team-season observations. "
                "Recommend caution before applying constant changes (need ≥100)."
            ))

        if result.by_uncertainty_bucket:
            self.stdout.write("\nBy uncertainty quartile:")
            for q in result.by_uncertainty_bucket:
                self.stdout.write(
                    f"  {q['label']}: coverage = {q['coverage_rate']:.4f}  "
                    f"mean_width = {q['mean_band_width']:.3f}  n = {q['n']}"
                )

        if result.by_source_year:
            self.stdout.write("\nPer-year:")
            for yr in result.by_source_year:
                self.stdout.write(
                    f"  {yr['source_year']}→{yr['target_year']}: "
                    f"coverage = {yr['coverage_rate']:.4f}  n = {yr['n']}"
                )

        self.stdout.write(
            f"\nCurrent UNCERTAINTY_SIGMA_SCALE: {result.current_sigma_scale}"
            f"\nCurrent UNCERTAINTY_SIGMA_MAX:   {result.current_sigma_max}"
            f"\nRecommendation: {result.recommendation}"
            f"\n→ {result.recommendation_detail}"
        )

        if result.recommendation != "no_change":
            self.stdout.write(
                f"\n→ Recommended UNCERTAINTY_SIGMA_SCALE: {result.recommended_sigma_scale}"
                f"\n→ Recommended UNCERTAINTY_SIGMA_MAX:   {result.recommended_sigma_max}"
            )

        # ── Apply ─────────────────────────────────────────────────────────────
        if apply:
            if result.recommendation == "no_change":
                self.stdout.write(self.style.SUCCESS(
                    "\n[BT-6] Recommendation is 'no_change' — constants not modified."
                ))
                return

            if result.n_teams < 100:
                self.stdout.write(self.style.WARNING(
                    "\n[BT-6] --apply skipped: fewer than 100 observations. "
                    "Re-run after more Phase 5 data is available."
                ))
                return

            constants_path = os.path.normpath(os.path.join(
                os.path.dirname(__file__),
                "..", "..", "analytics", "player_value",
                "team_projection", "constants.py",
            ))
            _write_bt6_constants(
                constants_path,
                result.overall_coverage_rate,
                result.recommended_sigma_scale,
                result.recommended_sigma_max,
            )
            self.stdout.write(self.style.SUCCESS(
                f"\n[BT-6] Constants written to {constants_path}"
            ))
        else:
            self.stdout.write(
                "\n[BT-6] Dry run. Use --apply to write constants.\n"
            )


def _write_bt6_constants(
    constants_path: str,
    coverage_rate: float,
    new_scale: float,
    new_max: float,
) -> None:
    """Overwrite UNCERTAINTY_SIGMA_SCALE and UNCERTAINTY_SIGMA_MAX in constants.py."""
    from datetime import date
    today = date.today().isoformat()

    with open(constants_path, "r", encoding="utf-8") as f:
        content = f.read()

    import re
    comment = (
        f"# Updated by BT-6 (Sprint 5, {today}). "
        f"Coverage was {coverage_rate:.2f} (target 0.60–0.75). "
        f"{UNCERTAINTY_SIGMA_SCALE} → {new_scale}"
    )

    content = re.sub(
        r"(UNCERTAINTY_SIGMA_SCALE\s*=\s*)[\d.]+",
        f"\\g<1>{new_scale}",
        content,
    )
    content = re.sub(
        r"(UNCERTAINTY_SIGMA_MAX\s*=\s*)[\d.]+",
        f"\\g<1>{new_max}",
        content,
    )

    # Insert comment before the UNCERTAINTY_SIGMA_SCALE line
    content = re.sub(
        r"(UNCERTAINTY_SIGMA_SCALE\s*=)",
        f"{comment}\n\\1",
        content,
        count=1,
    )

    with open(constants_path, "w", encoding="utf-8") as f:
        f.write(content)
