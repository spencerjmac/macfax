"""
fit_calibration.py — Phase 9e fit recalibration sweep.

Tests shrinkage, offense/defense independence, recentering, and Phase-3-only
variants of the fit adjustment layer to diagnose why Model E is slightly worse
than Model D on the fit-capable window (source years 2023–2025).

Root cause (diagnosed): ``adjusted_off_fit`` is systematically ~4.3 pts below
the nominal neutral of 50 (empirical mean ≈ 45.7), so the production formula:

    fit_adj_off = FIT_TO_RATING_OFF × (adjusted_off_fit − 50) / 50

applies a mean negative adjustment of ≈ −0.21 pts to every team's adj_o, and
77.5 % of teams receive a below-neutral offensive fit score.  The defensive
dimension is approximately centered (mean ≈ 49.1 ≈ 50).

Scaling formula used in this module (applied before feeding to the engine):

    scaled_off = 50 + shrink_off × (source_score_off − neutral_off)
    scaled_def = 50 + shrink_def × (source_score_def − neutral_def)

The engine then applies its unchanged production formula to the scaled scores:

    fit_adj_off = FIT_TO_RATING_OFF × (scaled_off − 50) / 50
               = FIT_TO_RATING_OFF × shrink_off × (source_score_off − neutral_off) / 50

Key special cases:
  neutral_off=50,   shrink=1.0  → scaled = source_score (current production / E_current)
  neutral_off=50,   shrink=0.0  → scaled = 50 → fit_adj = 0 (equivalent to D)
  neutral_off=45.7, shrink=1.0  → scaled = 50 at mean score → mean fit_adj = 0 (recentered)

Usage (from management command or shell):

    from backtesting.roster_outlook.fit_calibration import (
        run_fit_calibration_sweep,
        compute_fit_diagnostics,
        STANDARD_FIT_CONFIGS,
    )
    results = run_fit_calibration_sweep(all_pairs, STANDARD_FIT_CONFIGS)
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Default fit-capable source years (where TeamRosterFit rows exist in the DB).
DEFAULT_FIT_CAPABLE_SOURCE_YEARS: set[int] = {2023, 2024, 2025}

# Empirical neutral centers derived from DB across all fit-capable seasons.
# Mean adjusted_off_fit across 2023/2024/2025 ≈ 45.7 (vs. nominal 50.0).
# Mean adjusted_def_fit across those seasons  ≈ 49.1 (approximately neutral).
EMPIRICAL_NEUTRAL_OFF: float = 45.7
EMPIRICAL_NEUTRAL_DEF: float = 49.1


# ── Configuration dataclass ───────────────────────────────────────────────────

@dataclass
class FitCalibConfig:
    """
    Configuration for a single fit recalibration variant.

    Scaling formula (applied to each axis independently):

        scaled = 50 + shrink × (source_score − neutral)

    The engine's unchanged formula is then applied to ``scaled``:

        fit_adj = FIT_TO_RATING × (scaled − 50) / 50
                = FIT_TO_RATING × shrink × (source_score − neutral) / 50

    Attributes:
        label:       Human-readable identifier used in reports / CSV.
        shrink_off:  Multiplicative scale for offensive fit deviation from neutral.
                     0.0 = zero adjustment (same as D on offense);
                     1.0 = full production scale.
        shrink_def:  Same for defensive fit.
        neutral_off: Score value that maps to zero fit_adj_off.
                     50.0 = production default; 45.7 = empirical mean (recentered).
        neutral_def: Score value that maps to zero fit_adj_def.
                     50.0 = production default; 49.1 = empirical mean (recentered).
        use_phase4:  If True (default), source_score = Phase 4 adjusted_off/def_fit.
                     If False, source_score = Phase 3 offensive/defensive_fit_score.
    """

    label: str
    shrink_off: float = 1.0
    shrink_def: float = 1.0
    neutral_off: float = 50.0
    neutral_def: float = 50.0
    use_phase4: bool = True


# ── Standard sweep configurations (15 variants) ───────────────────────────────

STANDARD_FIT_CONFIGS: list[FitCalibConfig] = [
    # ── Group 1: Global shrinkage (neutral=50, both axes) ─────────────────
    # Tests whether the raw scale of the fit layer is too large.
    FitCalibConfig("E_current",    shrink_off=1.00, shrink_def=1.00),
    FitCalibConfig("shrink_75pct", shrink_off=0.75, shrink_def=0.75),
    FitCalibConfig("shrink_50pct", shrink_off=0.50, shrink_def=0.50),
    FitCalibConfig("shrink_35pct", shrink_off=0.35, shrink_def=0.35),
    FitCalibConfig("shrink_25pct", shrink_off=0.25, shrink_def=0.25),
    FitCalibConfig("shrink_10pct", shrink_off=0.10, shrink_def=0.10),
    FitCalibConfig("zero_fit",     shrink_off=0.00, shrink_def=0.00),  # ≡ D

    # ── Group 2: Offense / defense independence ────────────────────────────
    # Tests whether fit signal is concentrated on one axis.
    FitCalibConfig("off_only",       shrink_off=1.00, shrink_def=0.00),
    FitCalibConfig("def_only",       shrink_off=0.00, shrink_def=1.00),
    FitCalibConfig("off_50pct_only", shrink_off=0.50, shrink_def=0.00),
    FitCalibConfig("def_50pct_only", shrink_off=0.00, shrink_def=0.50),

    # ── Group 3: Recentering (empirical neutral centers) ──────────────────
    # Corrects the systematic negative bias by setting the effective neutral
    # to the empirical mean score (45.7 for off, 49.1 for def).
    FitCalibConfig(
        "recentered",
        shrink_off=1.00, shrink_def=1.00,
        neutral_off=EMPIRICAL_NEUTRAL_OFF, neutral_def=EMPIRICAL_NEUTRAL_DEF,
    ),
    FitCalibConfig(
        "recentered_50pct",
        shrink_off=0.50, shrink_def=0.50,
        neutral_off=EMPIRICAL_NEUTRAL_OFF, neutral_def=EMPIRICAL_NEUTRAL_DEF,
    ),

    # ── Group 4: Phase 3 vs Phase 4 scores ────────────────────────────────
    # Tests whether Phase 4 contextual adjustments (which have their own
    # neutral assumption) are adding or removing signal vs Phase 3 raw scores.
    FitCalibConfig("phase3_full",  shrink_off=1.00, shrink_def=1.00, use_phase4=False),
    FitCalibConfig("phase3_50pct", shrink_off=0.50, shrink_def=0.50, use_phase4=False),
]


# ── Scaling helper ────────────────────────────────────────────────────────────

def _scale_roster_fit(roster_fit, config: FitCalibConfig):
    """
    Return a new ``RosterFitInput`` with scores scaled per ``FitCalibConfig``.

    The scaling formula maps ``neutral`` → 50 (the engine's reference):

        scaled = 50 + shrink × (source_score − neutral)

    With shrink=1.0, neutral=50: scaled = source_score (production, current E).
    With shrink=0.0: scaled = 50 → zero fit_adj from the engine (≡ D on both axes).
    With neutral=45.7, shrink=1.0: mean score 45.7 maps to 50 → zero adj at mean.

    The returned object feeds directly into the engine's ``_compute_fit_adjustments()``,
    which applies ``FIT_TO_RATING × (scaled − 50) / 50``.  Raw Phase 3 fields
    (``offensive_fit_score``, ``defensive_fit_score``) are always preserved unchanged
    so that callers can still inspect the original values.
    """
    from ncaa.analytics.player_value.team_projection.engine import RosterFitInput

    # Pick source scores based on phase flag
    if config.use_phase4:
        off_score = roster_fit.adjusted_off_fit
        def_score = roster_fit.adjusted_def_fit
    else:
        off_score = roster_fit.offensive_fit_score
        def_score = roster_fit.defensive_fit_score

    # Scale: map neutral → 50 (engine's zero-adjustment reference)
    scaled_off = 50.0 + config.shrink_off * (off_score - config.neutral_off)
    scaled_def = 50.0 + config.shrink_def * (def_score - config.neutral_def)

    return RosterFitInput(
        offensive_fit_score=roster_fit.offensive_fit_score,
        defensive_fit_score=roster_fit.defensive_fit_score,
        adjusted_off_fit=scaled_off,
        adjusted_def_fit=scaled_def,
        has_team_style_data=roster_fit.has_team_style_data,
    )


# ── Diagnostics ───────────────────────────────────────────────────────────────

def compute_fit_diagnostics(
    fit_capable_source_years: Optional[set[int]] = None,
) -> dict:
    """
    Compute distribution statistics for current production fit adjustments.

    Queries TeamRosterFit directly from the DB for the specified fit-capable
    seasons and returns aggregate statistics.

    Returns a dict with:
        n_teams             Total observations in fit-capable window
        mean_adj_off_fit    Mean Phase 4 adjusted_off_fit (nominal neutral: 50)
        mean_adj_def_fit    Mean Phase 4 adjusted_def_fit
        mean_fit_adj_off    Mean actual fit_adj_off (pts/100 poss) applied to adj_o
        mean_fit_adj_def    Mean actual fit_adj_def applied to adj_d
        mean_net_adj_em     Mean net adj_em impact of fit (off + def)
        pct_negative_off    Fraction of teams with negative fit_adj_off
        pct_negative_def    Fraction of teams with negative fit_adj_def
        std_fit_adj_off     Std dev of fit_adj_off
        std_fit_adj_def     Std dev of fit_adj_def
    """
    from ncaa.models import TeamRosterFit
    from ncaa.analytics.player_value.team_projection.constants import (
        FIT_TO_RATING_OFF,
        FIT_TO_RATING_DEF,
    )

    if fit_capable_source_years is None:
        fit_capable_source_years = DEFAULT_FIT_CAPABLE_SOURCE_YEARS

    rows = list(
        TeamRosterFit.objects.filter(
            from_season__year__in=list(fit_capable_source_years),
            adjusted_off_fit__isnull=False,
            adjusted_def_fit__isnull=False,
        ).values("adjusted_off_fit", "adjusted_def_fit")
    )

    if not rows:
        return {"n_teams": 0}

    adj_offs = [r["adjusted_off_fit"] for r in rows]
    adj_defs = [r["adjusted_def_fit"] for r in rows]

    fit_adj_offs = [FIT_TO_RATING_OFF * (x - 50.0) / 50.0 for x in adj_offs]
    fit_adj_defs = [FIT_TO_RATING_DEF * (x - 50.0) / 50.0 for x in adj_defs]
    net_adj_ems = [o + d for o, d in zip(fit_adj_offs, fit_adj_defs)]

    return {
        "n_teams": len(rows),
        "mean_adj_off_fit": statistics.mean(adj_offs),
        "mean_adj_def_fit": statistics.mean(adj_defs),
        "mean_fit_adj_off": statistics.mean(fit_adj_offs),
        "mean_fit_adj_def": statistics.mean(fit_adj_defs),
        "mean_net_adj_em": statistics.mean(net_adj_ems),
        "pct_negative_off": sum(1 for x in fit_adj_offs if x < 0) / len(fit_adj_offs),
        "pct_negative_def": sum(1 for x in fit_adj_defs if x < 0) / len(fit_adj_defs),
        "std_fit_adj_off": statistics.stdev(fit_adj_offs),
        "std_fit_adj_def": statistics.stdev(fit_adj_defs),
    }


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class FitCalibResult:
    """Metrics for one fit calibration variant."""

    config: FitCalibConfig
    label: str
    n: int
    rmse: float
    mae: float
    bias: float
    r_squared: float
    spearman_rho: float
    # Deltas vs D baseline (both axes negative = better than D)
    delta_mae_vs_d: float
    delta_rmse_vs_d: float

    @property
    def beats_d_mae(self) -> bool:
        return self.delta_mae_vs_d < 0

    @property
    def beats_d_rmse(self) -> bool:
        return self.delta_rmse_vs_d < 0


# ── Main sweep ────────────────────────────────────────────────────────────────

def run_fit_calibration_sweep(
    all_pairs: list,
    configs: Optional[list[FitCalibConfig]] = None,
    fit_capable_source_years: Optional[set[int]] = None,
) -> list[FitCalibResult]:
    """
    Sweep fit calibration variants and return evaluation metrics for each.

    For each config in ``configs``, all fit-capable backtest pairs are re-evaluated
    with the scaled roster fit applied per ``_scale_roster_fit()``.  A Model-D
    baseline (zero fit, roster_fit=None) is computed from the same pairs and used
    as the delta reference.

    Args:
        all_pairs:
            List of ``(AblationResult, BacktestPair)`` tuples from a prior
            backtest run (e.g. from ``run_all_models()``).  The AblationResult
            is not used directly — only the associated BacktestPair is needed.
        configs:
            List of FitCalibConfig variants to evaluate.  Defaults to
            ``STANDARD_FIT_CONFIGS`` (15 preset variants).
        fit_capable_source_years:
            Source years that have TeamRosterFit rows.  Only pairs whose
            ``source_year`` is in this set (and whose ``prior_year_has_data``
            is True) are included in the evaluation.
            Defaults to ``DEFAULT_FIT_CAPABLE_SOURCE_YEARS`` ({2023, 2024, 2025}).

    Returns:
        List of FitCalibResult, ordered to match ``configs``.  Configs that
        produce insufficient data (< 2 observations) are silently omitted.
    """
    from backtesting.roster_outlook.ablation import (
        _compute_league_means,
        _run_engine,
        _load_roster_fit,
        MIN_PLAYERS_FOR_ENGINE,
    )
    from backtesting.roster_outlook.metrics import compute_point_metrics

    if configs is None:
        configs = STANDARD_FIT_CONFIGS
    if fit_capable_source_years is None:
        fit_capable_source_years = DEFAULT_FIT_CAPABLE_SOURCE_YEARS

    # Identify fit-capable pairs: source year has fit data AND recruitment types are valid
    fit_pairs = [
        (ab_result, pair)
        for ab_result, pair in all_pairs
        if pair.source_year in fit_capable_source_years
        and pair.prior_year_has_data
    ]

    if not fit_pairs:
        logger.warning("[FitCalib] No fit-capable pairs found — sweep skipped.")
        return []

    logger.info("[FitCalib] Pre-loading roster fit cache for %d pair(s)...", len(fit_pairs))

    # Pre-load roster fit data from DB once (avoids N_configs × N_teams DB queries)
    roster_fit_cache: dict[tuple[str, int], object] = {}
    for _, pair in fit_pairs:
        for team_slug in pair.evaluable_teams():
            key = (team_slug, pair.source_year)
            if key not in roster_fit_cache:
                roster_fit_cache[key] = _load_roster_fit(team_slug, pair.source_year)

    # ── Build D baseline (zero fit) ────────────────────────────────────────
    d_preds: list[float] = []
    d_actuals: list[float] = []

    for _, pair in fit_pairs:
        evaluable = pair.evaluable_teams()
        league_means = _compute_league_means(pair, evaluable)
        for team_slug in evaluable:
            pool = pair.team_pools.get(team_slug)
            if pool is None or len(pool.players) < MIN_PLAYERS_FOR_ENGINE:
                continue
            actual = pair.actual_outcomes.get(team_slug)
            if actual is None:
                continue
            result = _run_engine(pool.players, pair, league_means, roster_fit=None)
            d_preds.append(result.projected_adj_em)
            d_actuals.append(actual.adj_em)

    if len(d_preds) < 2:
        logger.warning("[FitCalib] Insufficient D baseline data — sweep skipped.")
        return []

    d_metrics = compute_point_metrics(d_preds, d_actuals)
    logger.info(
        "[FitCalib] D baseline: N=%d RMSE=%.4f MAE=%.4f bias=%+.4f",
        d_metrics.n, d_metrics.rmse, d_metrics.mae, d_metrics.bias,
    )

    # ── Sweep configs ─────────────────────────────────────────────────────
    results: list[FitCalibResult] = []

    for config in configs:
        preds: list[float] = []
        actuals: list[float] = []

        for _, pair in fit_pairs:
            evaluable = pair.evaluable_teams()
            league_means = _compute_league_means(pair, evaluable)
            for team_slug in evaluable:
                pool = pair.team_pools.get(team_slug)
                if pool is None or len(pool.players) < MIN_PLAYERS_FOR_ENGINE:
                    continue
                actual = pair.actual_outcomes.get(team_slug)
                if actual is None:
                    continue

                raw_fit = roster_fit_cache.get((team_slug, pair.source_year))

                if raw_fit is not None and (config.shrink_off != 0.0 or config.shrink_def != 0.0):
                    # Apply the calibrated scaling transform
                    scaled_fit = _scale_roster_fit(raw_fit, config)
                else:
                    # shrink=0 on both axes, or no fit data → zero adjustment (= D)
                    scaled_fit = None

                result = _run_engine(pool.players, pair, league_means, roster_fit=scaled_fit)
                preds.append(result.projected_adj_em)
                actuals.append(actual.adj_em)

        if len(preds) < 2:
            logger.warning(
                "[FitCalib] Config '%s': insufficient data (N=%d) — skipped.",
                config.label, len(preds),
            )
            continue

        metrics = compute_point_metrics(preds, actuals)
        calib_result = FitCalibResult(
            config=config,
            label=config.label,
            n=metrics.n,
            rmse=metrics.rmse,
            mae=metrics.mae,
            bias=metrics.bias,
            r_squared=metrics.r_squared,
            spearman_rho=metrics.spearman_rho,
            delta_mae_vs_d=metrics.mae - d_metrics.mae,
            delta_rmse_vs_d=metrics.rmse - d_metrics.rmse,
        )
        results.append(calib_result)
        logger.info(
            "[FitCalib] %-22s N=%d RMSE=%.4f MAE=%.4f bias=%+.4f ΔMAE=%+.4f",
            config.label, metrics.n, metrics.rmse, metrics.mae,
            metrics.bias, calib_result.delta_mae_vs_d,
        )

    return results
