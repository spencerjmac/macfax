"""
Management command: calibrate_continuity

Sweeps CONTINUITY_NEUTRAL_FRACTION over candidate values, evaluates each
against Models C and D on valid (prior-year-PSS-available) backtest pairs,
and reports which neutral point best improves continuity-adjusted predictions.

Usage:
    python manage.py calibrate_continuity
    python manage.py calibrate_continuity --candidates 0.35 0.40 0.45 0.50
    python manage.py calibrate_continuity --source-years 2024 2025
    python manage.py calibrate_continuity --cap-sweep
    python manage.py calibrate_continuity --verbose
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sweep continuity neutral fraction candidates and report C vs D backtest comparison."

    def add_arguments(self, parser):
        parser.add_argument(
            "--candidates",
            nargs="+",
            type=float,
            default=None,
            metavar="FRAC",
            help=(
                "List of CONTINUITY_NEUTRAL_FRACTION values to test "
                "(default: 0.30 0.35 0.40 0.42 0.45 0.48 0.50)"
            ),
        )
        parser.add_argument(
            "--source-years",
            nargs="+",
            type=int,
            default=None,
            metavar="YEAR",
            help="Restrict calibration to specific source years (default: all available).",
        )
        parser.add_argument(
            "--cap-sweep",
            action="store_true",
            help=(
                "After finding the best neutral fraction, also sweep MAX_CONTINUITY_ADJ "
                "values to check whether amplitude tuning helps further."
            ),
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-pair details for each candidate.",
        )

    def handle(self, *args, **options):
        from backtesting.roster_outlook.calibrate_continuity import (
            run_continuity_sweep,
            DEFAULT_NEUTRAL_CANDIDATES,
        )
        import core.analytics.player_value.team_projection.constants as const_mod

        candidates = options["candidates"] or DEFAULT_NEUTRAL_CANDIDATES
        source_years = options["source_years"]
        run_cap_sweep = options["cap_sweep"]
        verbose = options["verbose"]

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Phase 9b: Continuity Calibration Sweep ===\n"))
        self.stdout.write(f"  Candidate neutral fractions : {candidates}")
        self.stdout.write(f"  Source years filter         : {source_years or 'all available'}")
        self.stdout.write(f"  Cap sweep                   : {run_cap_sweep}")
        self.stdout.write(f"  Current production neutral  : {const_mod.CONTINUITY_NEUTRAL_FRACTION:.2f}")
        self.stdout.write(f"  Current MAX_ADJ_OFF/DEF     : {const_mod.MAX_CONTINUITY_ADJ_OFF:.1f} / {const_mod.MAX_CONTINUITY_ADJ_DEF:.1f}")
        self.stdout.write("")

        try:
            sweep = run_continuity_sweep(
                neutral_candidates=candidates,
                source_years=source_years,
                run_cap_sweep=run_cap_sweep,
            )
        except RuntimeError as exc:
            self.stderr.write(self.style.ERROR(f"Sweep failed: {exc}"))
            return

        self.stdout.write(self.style.MIGRATE_HEADING("--- Sweep Results ---\n"))

        # Header
        self.stdout.write(
            f"{'Neutral':>8}  {'N':>5}  "
            f"{'C_RMSE':>8}  {'D_RMSE':>8}  {'ΔRMSE':>8}  "
            f"{'C_bias':>7}  {'D_bias':>7}  {'D_R²':>6}  "
            f"{'D>C?':>5}  {'AvgRetFrac':>11}"
        )
        self.stdout.write("-" * 95)

        for r in sweep.candidates:
            marker = " ★" if abs(r.neutral_fraction - sweep.winning_neutral) < 0.001 else ""
            row = (
                f"{r.neutral_fraction:>8.2f}  {r.n_teams:>5}  "
                f"{r.c_rmse:>8.3f}  {r.d_rmse:>8.3f}  {r.delta_rmse:>+8.3f}  "
                f"{r.c_bias:>+7.3f}  {r.d_bias:>+7.3f}  {r.d_r2:>6.3f}  "
                f"{'✓' if r.d_beats_c_rmse else '✗':>5}  "
                f"{r.mean_returner_frac:>11.3f}{marker}"
            )
            if r.d_beats_c_rmse:
                self.stdout.write(self.style.SUCCESS(row))
            elif abs(r.neutral_fraction - sweep.winning_neutral) < 0.001:
                self.stdout.write(self.style.WARNING(row))
            else:
                self.stdout.write(row)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Recommended winner : neutral={sweep.winning_neutral:.2f}"
        ))
        self.stdout.write(f"Reason             : {sweep.winner_reason}")

        if verbose:
            self.stdout.write(self.style.MIGRATE_HEADING("\n--- Per-pair details ---\n"))
            for r in sweep.candidates:
                self.stdout.write(f"\nneutral={r.neutral_fraction:.2f}:")
                for pp in r.per_pair:
                    mr = pp.get("mean_returner_frac")
                    rf_str = f"{mr:.3f}" if mr is not None else "N/A"
                    self.stdout.write(
                        f"  {pp['source_year']}→{pp['target_year']}  N={pp['n']:>4}  "
                        f"C_RMSE={pp['c_rmse']:.3f}  D_RMSE={pp['d_rmse']:.3f}  "
                        f"ΔRMSE={pp['delta_rmse']:+.3f}  D_bias={pp['d_bias']:+.3f}  "
                        f"AvgRetFrac={rf_str}"
                    )

        if run_cap_sweep and sweep.cap_sweep_results:
            self.stdout.write(self.style.MIGRATE_HEADING("\n--- Cap Sweep (at winning neutral) ---\n"))
            self.stdout.write(
                f"{'MaxOff':>7}  {'MaxDef':>7}  {'D_RMSE':>8}  {'ΔRMSE':>8}  {'D_bias':>8}  {'D>C?':>5}"
            )
            self.stdout.write("-" * 55)
            for r in sweep.cap_sweep_results:
                row = (
                    f"{r.max_adj_off:>7.1f}  {r.max_adj_def:>7.1f}  "
                    f"{r.d_rmse:>8.3f}  {r.delta_rmse:>+8.3f}  "
                    f"{r.d_bias:>+8.3f}  {'✓' if r.d_beats_c_rmse else '✗':>5}"
                )
                if r.d_beats_c_rmse:
                    self.stdout.write(self.style.SUCCESS(row))
                else:
                    self.stdout.write(row)

        self.stdout.write("")
        self.stdout.write(self.style.WARNING(
            "Note: To apply the winning neutral fraction, update CONTINUITY_NEUTRAL_FRACTION "
            "in core/analytics/player_value/team_projection/constants.py, then rerun the "
            "full backtest with: python manage.py backtest_roster_outlook"
        ))
        self.stdout.write("")
