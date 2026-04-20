"""
calibrate_fit — Phase 9e fit recalibration management command.

Diagnoses why Model E performs slightly worse than Model D on the fit-capable
window (source years 2023–2025) and sweeps 15 calibration variants covering:

  Group 1 — Global shrinkage (neutral=50, both axes)
  Group 2 — Offense / defense independence
  Group 3 — Recentering to empirical neutral (adj_off_fit mean ≈ 45.7, not 50)
  Group 4 — Phase 3 vs Phase 4 adjusted scores

Root cause summary:
  adjusted_off_fit is systematically ~4.3 pts below the nominal neutral of 50
  (empirical mean ≈ 45.7), so the production formula
      fit_adj_off = 2.5 × (score − 50) / 50
  applies a mean negative adjustment of ≈ −0.21 pts to every team's adj_o.
  77.5% of teams receive a below-neutral offensive fit score.  This is the
  primary cause of Model E's systematic negative bias vs Model D.

Usage:
    python manage.py calibrate_fit
    python manage.py calibrate_fit --source-years 2023 2024 2025
    python manage.py calibrate_fit --fit-capable-only
    python manage.py calibrate_fit --min-mpg 10 --min-gp 10
"""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand

from backtesting.roster_outlook.data_loader import available_source_years, load_backtest_pair
from backtesting.roster_outlook.ablation import run_all_models
from backtesting.roster_outlook.fit_calibration import (
    DEFAULT_FIT_CAPABLE_SOURCE_YEARS,
    EMPIRICAL_NEUTRAL_OFF,
    EMPIRICAL_NEUTRAL_DEF,
    STANDARD_FIT_CONFIGS,
    FitCalibResult,
    compute_fit_diagnostics,
    run_fit_calibration_sweep,
)


class Command(BaseCommand):
    help = (
        "Phase 9e: fit recalibration sweep.  Sweeps 15 calibration variants "
        "to find the optimal fit layer configuration for Model E."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-years",
            nargs="+",
            type=int,
            default=None,
            metavar="YEAR",
            help="Source years to include (default: all available).",
        )
        parser.add_argument(
            "--fit-capable-only",
            action="store_true",
            help=(
                "Restrict the sweep to fit-capable source years only "
                f"({sorted(DEFAULT_FIT_CAPABLE_SOURCE_YEARS)})."
            ),
        )
        parser.add_argument(
            "--min-mpg",
            type=float,
            default=8.0,
            metavar="MPG",
            help="Minimum MPG threshold for player qualification (default: 8.0).",
        )
        parser.add_argument(
            "--min-gp",
            type=int,
            default=8,
            metavar="GP",
            help="Minimum games-played threshold for player qualification (default: 8).",
        )

    def handle(self, *args, **options):  # noqa: C901
        fit_capable_years = DEFAULT_FIT_CAPABLE_SOURCE_YEARS
        available = set(available_source_years())

        if options["source_years"]:
            source_years = sorted(yr for yr in options["source_years"] if yr in available)
        elif options["fit_capable_only"]:
            source_years = sorted(fit_capable_years & available)
        else:
            source_years = sorted(available)

        if not source_years:
            self.stderr.write(
                "No valid source years found. "
                f"Available in DB: {sorted(available)}"
            )
            sys.exit(1)

        sweep_years = fit_capable_years & set(source_years)

        self.stdout.write("=" * 76)
        self.stdout.write("Phase 9e: Fit Recalibration Sweep")
        self.stdout.write("=" * 76)
        self.stdout.write(f"  Source years loaded : {source_years}")
        self.stdout.write(f"  Fit-capable window  : {sorted(sweep_years)}")
        self.stdout.write(
            f"  Empirical neutrals  : off={EMPIRICAL_NEUTRAL_OFF} "
            f"def={EMPIRICAL_NEUTRAL_DEF} (vs. nominal 50.0)"
        )

        # ── 1. Fit diagnostic stats (DB query, no pair loading needed) ────────
        self.stdout.write("\n── Current fit adjustment diagnostics ──")
        self._print_diagnostics(sweep_years)

        # ── 2. Load backtest pairs ────────────────────────────────────────────
        self.stdout.write("\n── Loading backtest pairs ──")
        all_pairs = []
        for src_year in source_years:
            try:
                pair = load_backtest_pair(
                    src_year,
                    min_mpg=options["min_mpg"],
                    min_gp=options["min_gp"],
                )
                # Run D and E for reference metrics printed below
                ab = run_all_models(pair, models=["D", "E"])
                all_pairs.append((ab, pair))
                n_eval = len(pair.evaluable_teams())
                n_fit = sum(
                    1 for t in pair.evaluable_teams()
                    if pair.source_year in sweep_years
                )
                self.stdout.write(
                    f"  {src_year}→{src_year + 1}: "
                    f"{n_eval} evaluable teams"
                    + (f" ({n_fit} in fit-capable window)" if src_year in sweep_years else "")
                )
            except Exception as exc:
                self.stdout.write(f"  {src_year}: FAILED — {exc}")

        if not all_pairs:
            self.stderr.write("No pairs loaded. Exiting.")
            sys.exit(1)

        # ── 3. Print D vs E reference metrics on fit-capable window ──────────
        self.stdout.write("\n── D vs E reference (fit-capable window) ──")
        self._print_d_vs_e_reference(all_pairs, sweep_years)

        # ── 4. Run calibration sweep ──────────────────────────────────────────
        self.stdout.write("\n── Running fit calibration sweep (15 variants) ──")
        results = run_fit_calibration_sweep(
            all_pairs=all_pairs,
            configs=STANDARD_FIT_CONFIGS,
            fit_capable_source_years=sweep_years,
        )

        if not results:
            self.stdout.write(
                "  No results — no fit-capable pairs found in selected window.\n"
                "  Re-run with source years that include 2023, 2024, or 2025."
            )
            return

        # ── 5. Print results table ────────────────────────────────────────────
        self.stdout.write("\n── Calibration results (fit-capable window) ──")
        self._print_results_table(results)

        # ── 6. Print recommendation ───────────────────────────────────────────
        self.stdout.write("\n── Recommendation ──")
        self._print_recommendation(results)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _print_diagnostics(self, sweep_years: set[int]) -> None:
        diag = compute_fit_diagnostics(fit_capable_source_years=sweep_years)
        if not diag.get("n_teams", 0):
            self.stdout.write("  No TeamRosterFit rows found for fit-capable window.")
            return

        self.stdout.write(f"  N teams (fit-capable window) : {diag['n_teams']}")
        self.stdout.write(
            f"  adjusted_off_fit mean        : {diag['mean_adj_off_fit']:.3f} "
            f"(nominal neutral: 50.0 → offset: {diag['mean_adj_off_fit'] - 50:+.3f})"
        )
        self.stdout.write(
            f"  adjusted_def_fit mean        : {diag['mean_adj_def_fit']:.3f} "
            f"(nominal neutral: 50.0 → offset: {diag['mean_adj_def_fit'] - 50:+.3f})"
        )
        self.stdout.write(
            f"  mean fit_adj_off applied     : {diag['mean_fit_adj_off']:+.4f} pts/100  "
            f"(std: {diag['std_fit_adj_off']:.4f})"
        )
        self.stdout.write(
            f"  mean fit_adj_def applied     : {diag['mean_fit_adj_def']:+.4f} pts/100  "
            f"(std: {diag['std_fit_adj_def']:.4f})"
        )
        self.stdout.write(
            f"  mean net adj_em impact       : {diag['mean_net_adj_em']:+.4f} pts/100"
        )
        self.stdout.write(
            f"  teams with negative off adj  : {diag['pct_negative_off'] * 100:.1f}%"
        )
        self.stdout.write(
            f"  teams with negative def adj  : {diag['pct_negative_def'] * 100:.1f}%"
        )

    def _print_d_vs_e_reference(self, all_pairs: list, sweep_years: set[int]) -> None:
        """Print D and E metrics on the fit-capable window for context."""
        from backtesting.roster_outlook.metrics import compute_point_metrics

        for model_name in ("D", "E"):
            preds, actuals = [], []
            for ab_result, pair in all_pairs:
                if pair.source_year not in sweep_years:
                    continue
                for team_slug in pair.evaluable_teams():
                    pred = ab_result.get(team_slug, model_name)
                    actual = pair.actual_outcomes.get(team_slug)
                    if pred is not None and actual is not None:
                        preds.append(pred.pred_adj_em)
                        actuals.append(actual.adj_em)
            if len(preds) >= 2:
                m = compute_point_metrics(preds, actuals)
                self.stdout.write(
                    f"  {model_name}: N={m.n}  RMSE={m.rmse:.4f}  MAE={m.mae:.4f}  "
                    f"bias={m.bias:+.4f}  R²={m.r_squared:.4f}  ρ={m.spearman_rho:.4f}"
                )
            else:
                self.stdout.write(f"  {model_name}: insufficient data")

    def _print_results_table(self, results: list[FitCalibResult]) -> None:
        header = (
            f"{'Label':<22} {'N':>5} {'RMSE':>7} {'MAE':>7} "
            f"{'Bias':>7} {'R²':>6} {'ρ':>6} {'ΔMAE vs D':>10} {'ΔRMSE vs D':>11}"
        )
        sep = "-" * len(header)
        self.stdout.write(header)
        self.stdout.write(sep)

        best_mae = min(r.mae for r in results)

        for r in results:
            marker = " ← BEST" if abs(r.mae - best_mae) < 1e-6 else ""
            beats = " ✓" if r.delta_mae_vs_d < 0 else ""
            self.stdout.write(
                f"{r.label:<22} {r.n:>5} {r.rmse:>7.4f} {r.mae:>7.4f} "
                f"{r.bias:>+7.4f} {r.r_squared:>6.4f} {r.spearman_rho:>6.4f} "
                f"{r.delta_mae_vs_d:>+10.4f} {r.delta_rmse_vs_d:>+11.4f}"
                f"{beats}{marker}"
            )
        self.stdout.write(sep)
        self.stdout.write("  ✓ = beats D baseline on MAE")

    def _print_recommendation(self, results: list[FitCalibResult]) -> None:
        best = min(results, key=lambda r: r.mae)
        d_result = next((r for r in results if r.label == "zero_fit"), None)
        e_result = next((r for r in results if r.label == "E_current"), None)

        self.stdout.write(f"  Best variant: {best.label}")
        self.stdout.write(
            f"    MAE  = {best.mae:.4f}  "
            f"(ΔMAE vs D = {best.delta_mae_vs_d:+.4f}, "
            f"ΔRMSE vs D = {best.delta_rmse_vs_d:+.4f})"
        )
        if e_result is not None:
            self.stdout.write(
                f"    vs current E: ΔMAE = {best.mae - e_result.mae:+.4f}"
            )

        self.stdout.write("")
        if best.label == "zero_fit":
            self.stdout.write(
                "  FINDING: The fit layer provides no detectable predictive value.\n"
                "  RECOMMENDATION: Consider setting FIT_TO_RATING_OFF = FIT_TO_RATING_DEF = 0\n"
                "  (or routing all production to Model D).\n"
                "  Validate this finding across multiple hold-out windows before committing."
            )
        elif best.delta_mae_vs_d < 0:
            if best.label == "recentered":
                self.stdout.write(
                    f"  FINDING: Recentering the offensive neutral from 50 → {EMPIRICAL_NEUTRAL_OFF}\n"
                    f"  and defensive neutral from 50 → {EMPIRICAL_NEUTRAL_DEF} corrects the\n"
                    "  systematic negative bias and improves over D.\n"
                    "  RECOMMENDATION: Update EMPIRICAL_NEUTRAL_OFF / EMPIRICAL_NEUTRAL_DEF in\n"
                    "  fit_calibration.py and adjust the production formula in engine.py or\n"
                    "  constants.py after confirming the finding holds across all seasons."
                )
            elif "shrink" in best.label:
                self.stdout.write(
                    f"  FINDING: Shrinkage factor {best.config.shrink_off:.2f} outperforms both\n"
                    "  D and the current fit scale.\n"
                    "  RECOMMENDATION: Update FIT_TO_RATING_OFF / FIT_TO_RATING_DEF in\n"
                    "  constants.py by multiplying by the winning shrinkage factor."
                )
            else:
                self.stdout.write(
                    f"  FINDING: '{best.label}' outperforms D on the fit-capable window.\n"
                    "  RECOMMENDATION: Investigate the specific config and update production\n"
                    "  constants accordingly after validation."
                )
        else:
            self.stdout.write(
                "  FINDING: No variant beats D.  The fit layer provides no detectable signal\n"
                "  on the fit-capable window under any tested configuration."
            )

        self.stdout.write(
            "\n  NOTE: Production constants (constants.py / engine.py) should only be\n"
            "  updated after confirming these findings across multiple hold-out windows.\n"
            "  Do NOT update production constants based on a single sweep run."
        )
