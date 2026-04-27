"""
calibrate_continuity.py — Phase 9b continuity neutral-point calibration sweep.

Sweeps CONTINUITY_NEUTRAL_FRACTION over a range of candidates and evaluates
each against Models C and D on out-of-sample backtest pairs.

Only pairs where prior_year_has_data=True are used (i.e. source_year-1
PlayerSeasonStats exist), so recruitment types are trustworthy.  For example,
source_year=2023 is excluded if the DB contains no 2022 PSS rows.

Optionally sweeps MAX_CONTINUITY_ADJ_OFF / MAX_CONTINUITY_ADJ_DEF (cap sweep)
only when the neutral-point fix alone does not bring Model D above Model C.

Usage (from management command or shell):
    from backtesting.roster_outlook.calibrate_continuity import run_continuity_sweep
    results = run_continuity_sweep()
"""

from __future__ import annotations

import importlib
import logging
import math
import statistics
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── Default candidate neutral fractions ──────────────────────────────────────
# Range covers empirical observations: 2024 source avg≈52%, 2025 source avg≈44%.
# Current production default is 0.50. Minimum tested is 0.30 to avoid
# under-penalizing unusually low-continuity teams.
DEFAULT_NEUTRAL_CANDIDATES: list[float] = [0.30, 0.35, 0.40, 0.42, 0.45, 0.48, 0.50]

# ── Optional cap sweep candidates ─────────────────────────────────────────────
# Only tested when neutral_point fix alone is insufficient.
# Format: (max_adj_off, max_adj_def)
DEFAULT_CAP_CANDIDATES: list[tuple[float, float]] = [
    (1.0, 1.5),   # reduced caps
    (1.5, 2.0),   # current production (control)
    (1.2, 1.6),   # moderate reduction
]

# Number of valid years required to include a result (informational guard)
_MIN_VALID_PAIRS = 1


@dataclass
class CandidateResult:
    """Metrics for a single (neutral_fraction, max_off, max_def) candidate."""
    neutral_fraction: float
    max_adj_off: float
    max_adj_def: float
    n_pairs: int            # number of backtest pairs evaluated
    n_teams: int            # total team-season observations

    # Model C metrics (fixed; does NOT depend on continuity constants)
    c_rmse: float
    c_mae: float
    c_bias: float
    c_r2: float
    c_rho: float

    # Model D metrics under this candidate
    d_rmse: float
    d_mae: float
    d_bias: float
    d_r2: float
    d_rho: float

    # Delta: positive = D better (lower error / higher accuracy)
    delta_rmse: float    # C.rmse - D.rmse  (positive = D wins)
    delta_mae: float     # C.mae  - D.mae   (positive = D wins)
    delta_bias: float    # D.bias - C.bias  (shows centering shift)
    delta_r2: float      # D.r2   - C.r2    (positive = D wins)

    # Per-pair details for transparency
    per_pair: list[dict]  # list of {source_year, n, d_rmse, d_mae, d_bias, delta_rmse}

    # Continuity distribution summary (from valid pairs)
    mean_returner_frac: float = 0.0
    median_returner_frac: float = 0.0
    mean_blended_frac: float = 0.0   # BPR-weighted blend, if available

    @property
    def d_beats_c_rmse(self) -> bool:
        return self.delta_rmse > 0

    @property
    def d_beats_c_mae(self) -> bool:
        return self.delta_mae > 0


@dataclass
class SweepResult:
    """Full sweep output: all candidates + recommended winner."""
    candidates: list[CandidateResult]
    winning_neutral: float
    winning_candidate: CandidateResult
    winner_reason: str
    # Whether a cap sweep was also run
    cap_sweep_run: bool = False
    cap_sweep_results: list[CandidateResult] = None

    def summary_table(self) -> str:
        """Render a compact human-readable comparison table."""
        lines = [
            "Continuity Calibration Sweep — Model C vs D",
            "",
            f"{'Neutral':>8} {'MaxOff':>6} {'MaxDef':>6} {'N':>5} "
            f"{'C_RMSE':>8} {'D_RMSE':>8} {'ΔRMSE':>8} "
            f"{'C_Bias':>8} {'D_Bias':>8} {'D_R²':>7} {'D>C?':>5}",
            "-" * 90,
        ]
        for r in self.candidates:
            winner_flag = " ★" if abs(r.neutral_fraction - self.winning_neutral) < 0.001 else ""
            lines.append(
                f"{r.neutral_fraction:>8.2f} {r.max_adj_off:>6.1f} {r.max_adj_def:>6.1f} "
                f"{r.n_teams:>5} "
                f"{r.c_rmse:>8.3f} {r.d_rmse:>8.3f} {r.delta_rmse:>+8.3f} "
                f"{r.c_bias:>+8.3f} {r.d_bias:>+8.3f} {r.d_r2:>7.3f} "
                f"{'✓' if r.d_beats_c_rmse else '✗':>5}{winner_flag}"
            )
        lines.append("")
        lines.append(f"Winner: neutral={self.winning_neutral:.2f} — {self.winner_reason}")
        return "\n".join(lines)


# ── Public entry point ────────────────────────────────────────────────────────

def run_continuity_sweep(
    neutral_candidates: Optional[list[float]] = None,
    source_years: Optional[list[int]] = None,
    run_cap_sweep: bool = False,
    cap_candidates: Optional[list[tuple[float, float]]] = None,
) -> SweepResult:
    """
    Run the continuity calibration sweep.

    Args:
        neutral_candidates: List of CONTINUITY_NEUTRAL_FRACTION values to test.
                            Defaults to DEFAULT_NEUTRAL_CANDIDATES.
        source_years:       Restrict to specific source years.  If None, uses all
                            available years where prior_year_has_data=True.
        run_cap_sweep:      If True, also sweep MAX_CONTINUITY_ADJ values using
                            the winning neutral fraction.
        cap_candidates:     (max_off, max_def) pairs for the cap sweep.

    Returns:
        SweepResult with all CandidateResult objects and the recommended winner.
    """
    if neutral_candidates is None:
        neutral_candidates = DEFAULT_NEUTRAL_CANDIDATES

    # Load all available pairs (respects prior_year_has_data)
    pairs = _load_valid_pairs(source_years)
    if not pairs:
        raise RuntimeError(
            "No valid backtest pairs found with prior_year_has_data=True. "
            "Ensure source_year-1 PlayerSeasonStats are loaded in the DB."
        )

    logger.info(
        "[ContinuitySweep] %d valid pair(s) for calibration: %s",
        len(pairs),
        [f"{p.source_year}→{p.target_year}" for p in pairs],
    )

    # Current production caps (read from constants module)
    import ncaa.analytics.player_value.team_projection.constants as const_mod
    current_max_off = const_mod.MAX_CONTINUITY_ADJ_OFF
    current_max_def = const_mod.MAX_CONTINUITY_ADJ_DEF

    # Run neutral-fraction sweep at current caps
    results: list[CandidateResult] = []
    for nf in neutral_candidates:
        cr = _evaluate_candidate(pairs, nf, current_max_off, current_max_def)
        results.append(cr)
        logger.info(
            "[ContinuitySweep] neutral=%.2f → D_RMSE=%.3f D_bias=%+.3f ΔRMSE=%+.3f (D>C: %s)",
            nf, cr.d_rmse, cr.d_bias, cr.delta_rmse, cr.d_beats_c_rmse,
        )

    # Pick winner: minimize D RMSE.  Tie-break by delta_bias (closer to zero wins).
    winning_candidate = min(results, key=lambda r: (r.d_rmse, abs(r.d_bias)))
    winning_neutral = winning_candidate.neutral_fraction

    # Construct reason string
    prev = results[[r.neutral_fraction for r in results].index(0.50)] if 0.50 in neutral_candidates else None
    if winning_candidate.d_beats_c_rmse:
        reason = (
            f"D RMSE={winning_candidate.d_rmse:.3f} < C RMSE={winning_candidate.c_rmse:.3f}; "
            f"bias={winning_candidate.d_bias:+.3f} (was {prev.d_bias:+.3f} at neutral=0.50)."
            if prev else
            f"D RMSE={winning_candidate.d_rmse:.3f} < C RMSE={winning_candidate.c_rmse:.3f}; "
            f"bias={winning_candidate.d_bias:+.3f}."
        )
    else:
        reason = (
            f"No candidate beats C on RMSE; neutral={winning_neutral:.2f} minimizes D's RMSE "
            f"({winning_candidate.d_rmse:.3f}) and bias ({winning_candidate.d_bias:+.3f})."
        )

    # Optional cap sweep with the winning neutral fraction
    cap_results = None
    if run_cap_sweep:
        if cap_candidates is None:
            cap_candidates = DEFAULT_CAP_CANDIDATES
        cap_results = []
        for max_off, max_def in cap_candidates:
            cr = _evaluate_candidate(pairs, winning_neutral, max_off, max_def)
            cap_results.append(cr)
            logger.info(
                "[ContinuitySweep] CAP max_off=%.1f max_def=%.1f → D_RMSE=%.3f ΔRMSE=%+.3f",
                max_off, max_def, cr.d_rmse, cr.delta_rmse,
            )
        # Check if a different cap combination improves on the current
        best_cap = min(cap_results, key=lambda r: (r.d_rmse, abs(r.d_bias)))
        if best_cap.max_adj_off != current_max_off or best_cap.max_adj_def != current_max_def:
            reason += (
                f"  Cap sweep also run: best caps are "
                f"off={best_cap.max_adj_off:.1f}/def={best_cap.max_adj_def:.1f} "
                f"(D_RMSE={best_cap.d_rmse:.3f})."
            )

    return SweepResult(
        candidates=results,
        winning_neutral=winning_neutral,
        winning_candidate=winning_candidate,
        winner_reason=reason,
        cap_sweep_run=run_cap_sweep,
        cap_sweep_results=cap_results,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_valid_pairs(source_years: Optional[list[int]]) -> list:
    """Load backtest pairs, filtering to those with prior_year_has_data=True."""
    from backtesting.roster_outlook.data_loader import load_backtest_pair, available_source_years

    if source_years is None:
        source_years = available_source_years()

    valid_pairs = []
    for yr in source_years:
        pair = load_backtest_pair(yr)
        if pair.prior_year_has_data:
            valid_pairs.append(pair)
        else:
            logger.info(
                "[ContinuitySweep] Excluding %d→%d: no prior-year PSS (returner "
                "classification unavailable).", yr, yr + 1,
            )

    return valid_pairs


def _evaluate_candidate(
    pairs: list,
    neutral_fraction: float,
    max_adj_off: float,
    max_adj_def: float,
) -> CandidateResult:
    """
    Patch engine constants, run ablation Models C & D on all pairs, collect metrics.
    Restores original constants after evaluation (even on exception).
    """
    import ncaa.analytics.player_value.team_projection.engine as engine_mod
    import ncaa.analytics.player_value.team_projection.constants as const_mod
    from backtesting.roster_outlook.ablation import run_all_models
    from backtesting.roster_outlook.metrics import compute_point_metrics

    # Snapshot originals
    orig_neutral = engine_mod.CONTINUITY_NEUTRAL_FRACTION
    orig_max_off = engine_mod.MAX_CONTINUITY_ADJ_OFF
    orig_max_def = engine_mod.MAX_CONTINUITY_ADJ_DEF

    try:
        # Patch engine module's local names (these are what _compute_continuity() reads)
        engine_mod.CONTINUITY_NEUTRAL_FRACTION = neutral_fraction
        engine_mod.MAX_CONTINUITY_ADJ_OFF = max_adj_off
        engine_mod.MAX_CONTINUITY_ADJ_DEF = max_adj_def

        all_c_preds: list[float] = []
        all_c_actuals: list[float] = []
        all_d_preds: list[float] = []
        all_d_actuals: list[float] = []
        returner_fracs: list[float] = []
        per_pair: list[dict] = []

        for pair in pairs:
            ablation = run_all_models(pair, models=["C", "D"])

            c_pred, c_act, d_pred, d_act = [], [], [], []
            r_fracs = []

            for slug in ablation.teams():
                actual = pair.actual_outcomes.get(slug)
                if actual is None:
                    continue
                cp = ablation.get(slug, "C")
                dp = ablation.get(slug, "D")
                if cp is not None:
                    c_pred.append(cp.pred_adj_em)
                    c_act.append(actual.adj_em)
                if dp is not None:
                    d_pred.append(dp.pred_adj_em)
                    d_act.append(actual.adj_em)
                if dp is not None and dp.returner_fraction is not None:
                    r_fracs.append(dp.returner_fraction)

            # Only include pair if we have predictions for both C and D
            if not c_pred or not d_pred:
                continue

            cm = compute_point_metrics(c_pred, c_act)
            dm = compute_point_metrics(d_pred, d_act)

            per_pair.append({
                "source_year": pair.source_year,
                "target_year": pair.target_year,
                "n": len(d_pred),
                "c_rmse": cm.rmse,
                "c_mae": cm.mae,
                "c_bias": cm.bias,
                "d_rmse": dm.rmse,
                "d_mae": dm.mae,
                "d_bias": dm.bias,
                "delta_rmse": cm.rmse - dm.rmse,  # positive = D wins
                "delta_mae": cm.mae - dm.mae,
                "mean_returner_frac": statistics.mean(r_fracs) if r_fracs else None,
            })

            all_c_preds.extend(c_pred)
            all_c_actuals.extend(c_act)
            all_d_preds.extend(d_pred)
            all_d_actuals.extend(d_act)
            returner_fracs.extend(r_fracs)

    finally:
        # Always restore original constants
        engine_mod.CONTINUITY_NEUTRAL_FRACTION = orig_neutral
        engine_mod.MAX_CONTINUITY_ADJ_OFF = orig_max_off
        engine_mod.MAX_CONTINUITY_ADJ_DEF = orig_max_def

    if not all_c_preds:
        raise RuntimeError("No predictions generated — check that DB is populated.")

    c_metrics = compute_point_metrics(all_c_preds, all_c_actuals)
    d_metrics = compute_point_metrics(all_d_preds, all_d_actuals)

    mean_rf = statistics.mean(returner_fracs) if returner_fracs else 0.0
    median_rf = statistics.median(returner_fracs) if returner_fracs else 0.0

    return CandidateResult(
        neutral_fraction=neutral_fraction,
        max_adj_off=max_adj_off,
        max_adj_def=max_adj_def,
        n_pairs=len(per_pair),
        n_teams=len(all_d_preds),
        c_rmse=c_metrics.rmse,
        c_mae=c_metrics.mae,
        c_bias=c_metrics.bias,
        c_r2=c_metrics.r_squared,
        c_rho=c_metrics.spearman_rho,
        d_rmse=d_metrics.rmse,
        d_mae=d_metrics.mae,
        d_bias=d_metrics.bias,
        d_r2=d_metrics.r_squared,
        d_rho=d_metrics.spearman_rho,
        delta_rmse=c_metrics.rmse - d_metrics.rmse,
        delta_mae=c_metrics.mae - d_metrics.mae,
        delta_bias=d_metrics.bias - c_metrics.bias,
        delta_r2=d_metrics.r_squared - c_metrics.r_squared,
        per_pair=per_pair,
        mean_returner_frac=mean_rf,
        median_returner_frac=median_rf,
    )
