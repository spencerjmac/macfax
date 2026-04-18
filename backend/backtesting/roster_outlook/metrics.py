"""
metrics.py — Evaluation metrics for roster-outlook backtesting.

All metrics operate on paired (predicted, actual) arrays of adj_em values
(or adj_o / adj_d if requested).

Main public interface:

    compute_point_metrics(preds, actuals)       → PointMetrics
    compute_rank_metrics(pred_ranks, act_ranks) → RankMetrics
    compute_coverage(low, high, actuals)        → CoverageMetrics
    paired_comparison(errors_a, errors_b)       → PairedComparison
    subgroup_metrics(records, subgroup_key)     → dict[group → PointMetrics]

Dependencies: scipy (already in requirements), numpy, statistics (stdlib).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Optional

# scipy is already a dependency (used by backtest_shrinkage.py)
from scipy import stats as scipy_stats


# ── Output containers ─────────────────────────────────────────────────────────

@dataclass
class PointMetrics:
    """Point-prediction accuracy on adj_em (or adj_o / adj_d)."""
    n: int
    rmse: float
    mae: float
    bias: float               # mean(pred − actual); positive = systematic over-prediction
    r_squared: float          # coefficient of determination (may be negative if worse than mean)
    pearson_r: float          # linear correlation
    pearson_p: float          # two-tailed p-value for Pearson correlation
    spearman_rho: float       # rank correlation (robustness to outliers)
    spearman_p: float         # two-tailed p-value for Spearman rho

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "rmse": round(self.rmse, 4),
            "mae": round(self.mae, 4),
            "bias": round(self.bias, 4),
            "r_squared": round(self.r_squared, 4),
            "pearson_r": round(self.pearson_r, 4),
            "pearson_p": round(self.pearson_p, 6),
            "spearman_rho": round(self.spearman_rho, 4),
            "spearman_p": round(self.spearman_p, 6),
        }


@dataclass
class RankMetrics:
    """Rank-order accuracy (for national rank predictions)."""
    n: int
    mean_abs_rank_error: float    # avg |pred_rank − actual_rank|
    median_abs_rank_error: float  # median |pred_rank − actual_rank|
    top_10_hit_rate: float        # fraction of actual top-10 teams predicted in top-10
    top_25_hit_rate: float
    top_50_hit_rate: float

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "mean_abs_rank_error": round(self.mean_abs_rank_error, 2),
            "median_abs_rank_error": round(self.median_abs_rank_error, 2),
            "top_10_hit_rate": round(self.top_10_hit_rate, 4),
            "top_25_hit_rate": round(self.top_25_hit_rate, 4),
            "top_50_hit_rate": round(self.top_50_hit_rate, 4),
        }


@dataclass
class CoverageMetrics:
    """Calibration of uncertainty bands (predicted adj_em_low / high vs actual)."""
    n: int
    coverage_rate: float       # fraction of actuals inside [low, high] band
    mean_band_width: float     # average (high − low) in pts/100 poss
    median_band_width: float

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "coverage_rate": round(self.coverage_rate, 4),
            "mean_band_width": round(self.mean_band_width, 4),
            "median_band_width": round(self.median_band_width, 4),
        }


@dataclass
class PairedComparison:
    """
    Statistical comparison of two models on the same set of teams.

    Uses absolute errors (|pred − actual|) for the paired comparison,
    so a negative delta_mae means model_b is BETTER (lower error).
    """
    model_a: str
    model_b: str
    n: int
    delta_rmse: float       # rmse_b − rmse_a (negative = B better)
    delta_mae: float        # mae_b − mae_a (negative = B better)
    mae_pct_change: float   # (mae_b − mae_a) / mae_a × 100 (negative = improvement)
    wilcoxon_statistic: float
    wilcoxon_p: float       # two-tailed Wilcoxon signed-rank test (H0: no diff)
    b_better_fraction: float  # fraction of teams where |err_b| < |err_a|

    def as_dict(self) -> dict:
        return {
            "model_a": self.model_a,
            "model_b": self.model_b,
            "n": self.n,
            "delta_rmse": round(self.delta_rmse, 4),
            "delta_mae": round(self.delta_mae, 4),
            "mae_pct_change": round(self.mae_pct_change, 2),
            "wilcoxon_statistic": round(self.wilcoxon_statistic, 4),
            "wilcoxon_p": round(self.wilcoxon_p, 6),
            "b_better_fraction": round(self.b_better_fraction, 4),
        }


# ── Public functions ──────────────────────────────────────────────────────────

def compute_point_metrics(
    preds: list[float],
    actuals: list[float],
) -> PointMetrics:
    """
    Compute RMSE, MAE, bias, R², Pearson, Spearman from paired lists.

    Args:
        preds:   Model predictions (adj_em or adj_o/d).
        actuals: Corresponding ground-truth values.

    Returns:
        PointMetrics dataclass.

    Raises:
        ValueError: If lists are empty or have different lengths.
    """
    if len(preds) != len(actuals):
        raise ValueError(
            f"predictions ({len(preds)}) and actuals ({len(actuals)}) must have the same length"
        )
    n = len(preds)
    if n < 2:
        raise ValueError("Need at least 2 observations for metrics.")

    errors = [p - a for p, a in zip(preds, actuals)]
    abs_errors = [abs(e) for e in errors]

    rmse = math.sqrt(sum(e ** 2 for e in errors) / n)
    mae = statistics.mean(abs_errors)
    bias = statistics.mean(errors)

    # R²  — same formula as sklearn but dependency-free
    actual_mean = statistics.mean(actuals)
    ss_tot = sum((a - actual_mean) ** 2 for a in actuals)
    ss_res = sum(e ** 2 for e in errors)
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    pearson_r, pearson_p = scipy_stats.pearsonr(preds, actuals)
    spearman_rho, spearman_p = scipy_stats.spearmanr(preds, actuals)

    return PointMetrics(
        n=n,
        rmse=rmse,
        mae=mae,
        bias=bias,
        r_squared=r_squared,
        pearson_r=float(pearson_r),
        pearson_p=float(pearson_p),
        spearman_rho=float(spearman_rho),
        spearman_p=float(spearman_p),
    )


def compute_rank_metrics(
    pred_ranks: list[int],
    actual_ranks: list[int],
) -> RankMetrics:
    """
    Compare rank lists for national-rank prediction quality.

    Args:
        pred_ranks:   Predicted national rank (1 = best).
        actual_ranks: Actual national rank (from TeamSeasonRatings.rank_adj_em).

    Returns:
        RankMetrics dataclass.
    """
    if len(pred_ranks) != len(actual_ranks):
        raise ValueError("pred_ranks and actual_ranks must have the same length.")
    n = len(pred_ranks)
    if n < 2:
        raise ValueError("Need at least 2 observations.")

    abs_errs = [abs(p - a) for p, a in zip(pred_ranks, actual_ranks)]
    mean_err = statistics.mean(abs_errs)
    median_err = statistics.median(abs_errs)

    def _hit_rate(threshold: int) -> float:
        actual_top = {a for a in actual_ranks if a <= threshold}
        hits = sum(1 for p, a in zip(pred_ranks, actual_ranks) if a <= threshold and p <= threshold)
        return hits / len(actual_top) if actual_top else 0.0

    return RankMetrics(
        n=n,
        mean_abs_rank_error=mean_err,
        median_abs_rank_error=median_err,
        top_10_hit_rate=_hit_rate(10),
        top_25_hit_rate=_hit_rate(25),
        top_50_hit_rate=_hit_rate(50),
    )


def compute_coverage(
    pred_low: list[float],
    pred_high: list[float],
    actuals: list[float],
) -> CoverageMetrics:
    """
    Measure calibration of predicted uncertainty bands.

    Args:
        pred_low:  Lower bound of predicted adj_em confidence band.
        pred_high: Upper bound of predicted adj_em confidence band.
        actuals:   Actual realized adj_em values.

    Returns:
        CoverageMetrics dataclass.
    """
    if not (len(pred_low) == len(pred_high) == len(actuals)):
        raise ValueError("All lists must have the same length.")
    n = len(actuals)
    if n < 1:
        raise ValueError("Need at least 1 observation.")

    covered = sum(1 for lo, hi, a in zip(pred_low, pred_high, actuals) if lo <= a <= hi)
    widths = [hi - lo for lo, hi in zip(pred_low, pred_high)]

    return CoverageMetrics(
        n=n,
        coverage_rate=covered / n,
        mean_band_width=statistics.mean(widths),
        median_band_width=statistics.median(widths),
    )


def paired_comparison(
    errors_a: list[float],
    errors_b: list[float],
    model_a: str = "A",
    model_b: str = "B",
) -> Optional[PairedComparison]:
    """
    Paired statistical comparison of two models' error distributions.

    Args:
        errors_a: Signed errors (pred_a − actual) for model A.
        errors_b: Signed errors (pred_b − actual) for model B.
        model_a:  Name label for model A.
        model_b:  Name label for model B.

    Returns:
        PairedComparison, or None if sample is too small for the Wilcoxon test.
    """
    if len(errors_a) != len(errors_b):
        raise ValueError("Error lists must have the same length.")
    n = len(errors_a)
    if n < 6:
        # Wilcoxon requires minimum sample; return None rather than invalid p-value
        return None

    abs_a = [abs(e) for e in errors_a]
    abs_b = [abs(e) for e in errors_b]

    rmse_a = math.sqrt(sum(e ** 2 for e in errors_a) / n)
    rmse_b = math.sqrt(sum(e ** 2 for e in errors_b) / n)
    mae_a = statistics.mean(abs_a)
    mae_b = statistics.mean(abs_b)

    diffs = [b - a for a, b in zip(abs_a, abs_b)]
    # Guard: if all diffs are 0, Wilcoxon raises
    if all(d == 0 for d in diffs):
        w_stat, w_p = 0.0, 1.0
    else:
        res = scipy_stats.wilcoxon(diffs, alternative="two-sided")
        w_stat = float(res.statistic)
        w_p = float(res.pvalue)

    b_better_frac = sum(1 for a, b in zip(abs_a, abs_b) if b < a) / n

    mae_pct = ((mae_b - mae_a) / mae_a * 100) if mae_a != 0 else 0.0

    return PairedComparison(
        model_a=model_a,
        model_b=model_b,
        n=n,
        delta_rmse=rmse_b - rmse_a,
        delta_mae=mae_b - mae_a,
        mae_pct_change=mae_pct,
        wilcoxon_statistic=w_stat,
        wilcoxon_p=w_p,
        b_better_fraction=b_better_frac,
    )


def subgroup_metrics(
    records: list[dict],
    subgroup_key: str,
) -> dict[str, PointMetrics]:
    """
    Compute per-subgroup PointMetrics from a list of row dicts.

    Each dict must contain 'pred_adj_em' and 'actual_adj_em' keys, plus
    the `subgroup_key` field (e.g. 'conf_group', 'strength_bucket').

    Args:
        records:       List of per-team row dicts.
        subgroup_key:  Field to group by.

    Returns:
        dict mapping subgroup value → PointMetrics for that subgroup.
    """
    from collections import defaultdict
    groups: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for rec in records:
        group = str(rec.get(subgroup_key, "unknown"))
        pred = rec.get("pred_adj_em")
        actual = rec.get("actual_adj_em")
        if pred is not None and actual is not None:
            groups[group].append((float(pred), float(actual)))

    result: dict[str, PointMetrics] = {}
    for group, pairs in groups.items():
        if len(pairs) >= 2:
            preds = [p for p, _ in pairs]
            actuals = [a for _, a in pairs]
            result[group] = compute_point_metrics(preds, actuals)
    return result
