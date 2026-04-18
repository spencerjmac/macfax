"""
backtest_roster_outlook — Evaluate the roster outlook model against historical outcomes.

Runs 6-model ablation ladder over all available historical season pairs
(source year Y → actual year Y+1) and produces CSV, JSON, and Markdown reports.

Usage:
    python manage.py backtest_roster_outlook
    python manage.py backtest_roster_outlook --start 2023 --end 2025
    python manage.py backtest_roster_outlook --models A B C D
    python manage.py backtest_roster_outlook --output-dir /tmp/backtest
    python manage.py backtest_roster_outlook --dry-run
    python manage.py backtest_roster_outlook --no-subgroups

Available models:
    A  — Prior-year adj_em (simplest baseline)
    B  — Equal-minutes talent average (no mpg weighting)
    C  — Minutes-weighted talent  (no continuity/fit)
    D  — Minutes-weighted talent + continuity adjustment  [recommended]
    E  — Minutes-weighted talent + continuity + fit  (fit=0 if no historical data)
    F  — Direct-returner-bump counterfactual (returner ×1.05, no continuity formula)

Leakage guarantee:
    Target-year TeamSeasonRatings are loaded AFTER all predictions are made and
    are only ever used for computing prediction errors. No target-year data
    flows back into any model input.

Typical runtime:
    3 season pairs × ~330 teams × 6 models  ≈  5-30 seconds
    (dominated by DB queries; use --start/--end to narrow scope)
"""

import json
import logging
import os
import time

from django.core.management.base import BaseCommand, CommandError

from backtesting.roster_outlook.ablation import AblationResult, run_all_models, ALL_MODELS
from backtesting.roster_outlook.data_loader import BacktestPair, available_source_years, load_backtest_pair
from backtesting.roster_outlook.report import generate_reports

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),  # .../management/commands/
    "..", "..", "..",                             # → backend/
    "backtest_output",
)
DEFAULT_OUTPUT_DIR = os.path.normpath(DEFAULT_OUTPUT_DIR)


class Command(BaseCommand):
    help = (
        "Run ablation backtesting for the roster outlook model "
        "(Phase 9: leakage-safe, historical, ablation-based)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--start",
            type=int,
            dest="start_year",
            metavar="YEAR",
            help="Earliest SOURCE season to include (default: all available).",
        )
        parser.add_argument(
            "--end",
            type=int,
            dest="end_year",
            metavar="YEAR",
            help="Latest SOURCE season to include (default: all available).",
        )
        parser.add_argument(
            "--models",
            nargs="+",
            choices=ALL_MODELS,
            metavar="MODEL",
            help=f"Subset of ablation models to run (default: all {ALL_MODELS}).",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default=DEFAULT_OUTPUT_DIR,
            metavar="PATH",
            help="Directory for CSV / JSON / Markdown output files.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Load data and show plan without writing any output files.",
        )
        parser.add_argument(
            "--no-subgroups",
            action="store_true",
            help="Skip per-subgroup metric breakdowns (faster for large datasets).",
        )
        parser.add_argument(
            "--min-mpg",
            type=float,
            default=5.0,
            metavar="MPG",
            help="Minimum minutes/game to qualify a player for inclusion (default: 5.0).",
        )
        parser.add_argument(
            "--min-gp",
            type=int,
            default=5,
            metavar="GP",
            help="Minimum games played to qualify a player for inclusion (default: 5).",
        )

    def handle(self, *args, **options):
        t0 = time.perf_counter()

        models = options["models"] or ALL_MODELS
        output_dir = options["output_dir"]
        dry_run = options["dry_run"]
        include_subgroups = not options["no_subgroups"]
        min_mpg = options["min_mpg"]
        min_gp = options["min_gp"]

        # ── Determine which source years to run ────────────────────────────
        available = available_source_years()
        if not available:
            raise CommandError(
                "No valid backtest pairs found. "
                "Need PlayerSeasonStats for year Y and TeamSeasonRatings for both Y and Y+1."
            )

        start_year = options.get("start_year") or min(available)
        end_year = options.get("end_year") or max(available)

        source_years = [yr for yr in available if start_year <= yr <= end_year]
        if not source_years:
            raise CommandError(
                f"No available source years in range {start_year}–{end_year}. "
                f"Available: {available}"
            )

        self.stdout.write(self.style.MIGRATE_HEADING("=" * 66))
        self.stdout.write(self.style.MIGRATE_HEADING("  Roster Outlook Backtest — Phase 9"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 66))
        self.stdout.write(f"  Source years : {source_years}")
        self.stdout.write(f"  Target years : {[yr + 1 for yr in source_years]}")
        self.stdout.write(f"  Models       : {models}")
        self.stdout.write(f"  Min MPG/GP   : {min_mpg}/{min_gp}")
        self.stdout.write(f"  Output dir   : {output_dir}")
        self.stdout.write(f"  Dry run      : {dry_run}")
        self.stdout.write("")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no files will be written."))

        # ── Load and run each season pair ──────────────────────────────────
        all_pairs: list[tuple[AblationResult, BacktestPair]] = []

        for src_year in source_years:
            t_load = time.perf_counter()
            self.stdout.write(f"  Loading {src_year}→{src_year + 1}... ", ending="")

            try:
                pair = load_backtest_pair(src_year, min_mpg=min_mpg, min_gp=min_gp)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"FAILED to load {src_year}: {exc}"))
                continue

            evaluable = pair.evaluable_teams()
            self.stdout.write(
                f"{pair.n_teams_with_pools} pools / {pair.n_teams_with_actuals} actuals "
                f"/ {len(evaluable)} evaluable"
            )

            if not evaluable:
                self.stderr.write(
                    self.style.WARNING(f"  No evaluable teams for {src_year}→{src_year + 1}; skipping.")
                )
                continue

            t_run = time.perf_counter()
            ablation_result = run_all_models(pair, models=models)
            elapsed = time.perf_counter() - t_run

            self.stdout.write(
                f"  {src_year}→{src_year + 1}: "
                f"{len(ablation_result.teams())} teams × {len(models)} models "
                f"in {elapsed:.2f}s"
            )

            all_pairs.append((ablation_result, pair))

        if not all_pairs:
            raise CommandError("No season pairs produced valid results. Aborting.")

        # ── Determine fit-capable source years ─────────────────────────────
        # Fit-capable = source years that have real TeamRosterFit rows in the DB
        # (backfilled via `backfill_roster_fit` for BPR-capable seasons).
        try:
            from core.models import TeamRosterFit
            fit_capable_source_years = set(
                TeamRosterFit.objects
                .values_list("from_season__year", flat=True)
                .distinct()
            ) & set(source_years)
        except Exception:
            fit_capable_source_years = set()

        # ── Print per-season summary ───────────────────────────────────────
        self._print_performance_summary(all_pairs, models, fit_capable_source_years)

        # ── Write outputs ─────────────────────────────────────────────────
        if not dry_run:
            paths = generate_reports(
                all_pairs,
                output_dir=output_dir,
                include_subgroups=include_subgroups,
                model_order=models,
                fit_capable_source_years=fit_capable_source_years,
            )
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("  Reports written:"))
            for kind, path in paths.items():
                self.stdout.write(f"    {kind:10s} → {path}")
        else:
            self.stdout.write(self.style.WARNING("  (dry run — no files written)"))

        elapsed_total = time.perf_counter() - t0
        self.stdout.write(f"\n  Total elapsed: {elapsed_total:.1f}s")
        self.stdout.write(self.style.SUCCESS("  Done."))

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _print_performance_summary(
        self,
        all_pairs: list[tuple[AblationResult, BacktestPair]],
        models: list[str],
        fit_capable_source_years: set = None,
    ) -> None:
        """Print a quick per-model RMSE/MAE summary to stdout."""
        from backtesting.roster_outlook.report import build_flat_records
        from backtesting.roster_outlook.metrics import compute_point_metrics

        fit_capable_source_years = fit_capable_source_years or set()

        def _print_table(label: str, pair_filter=None):
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(f"  {label}"))
            self.stdout.write(
                f"  {'Model':<8} {'N':>5} {'RMSE':>7} {'MAE':>7} {'Bias':>7} {'R²':>7} {'ρ':>7}"
            )
            self.stdout.write("  " + "-" * 58)

            for model in models:
                all_recs: list[dict] = []
                for ablation_result, pair in all_pairs:
                    if pair_filter and pair.source_year not in pair_filter:
                        continue
                    recs = build_flat_records(ablation_result, pair, model)
                    all_recs.extend(recs)

                preds = [r["pred_adj_em"] for r in all_recs if r["pred_adj_em"] is not None]
                actuals = [r["actual_adj_em"] for r in all_recs if r["actual_adj_em"] is not None]

                if len(preds) < 2:
                    self.stdout.write(f"  {model:<8} {'—':>5}")
                    continue

                m = compute_point_metrics(preds, actuals)
                self.stdout.write(
                    f"  {model:<8} {m.n:>5} {m.rmse:>7.3f} {m.mae:>7.3f} "
                    f"{m.bias:>+7.3f} {m.r_squared:>7.3f} {m.spearman_rho:>7.3f}"
                )

        _print_table("Performance Summary (adj_em, all seasons)")

        if fit_capable_source_years and "D" in models and "E" in models:
            fc_label = (
                f"Fit-Capable Window (source years with TeamRosterFit: "
                f"{sorted(fit_capable_source_years)})"
            )
            _print_table(fc_label, pair_filter=fit_capable_source_years)
