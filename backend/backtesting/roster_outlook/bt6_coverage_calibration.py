"""
bt6_coverage_calibration.py — BT-6: Uncertainty band coverage calibration (Sprint 5).

Measures how well the team projection confidence bands (projected_adj_em_low /
projected_adj_em_high) cover actual outcomes.  For a well-calibrated ±1σ band,
~68% of actuals should fall inside.  Target range: 0.60–0.75.

Requires: TeamSeasonProjection rows with projected_adj_em_low/high already computed
by Phase 5.  Unlike BT-1/BT-4 which work from raw PSP data, BT-6 can only evaluate
seasons that have been through the full pipeline.

Usage:
    from backtesting.roster_outlook.bt6_coverage_calibration import run_bt6
    result = run_bt6()               # all available years
    result = run_bt6([2023, 2024])   # specific years
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional

from ncaa.analytics.player_value.team_projection.constants import (
    UNCERTAINTY_SIGMA_SCALE,
    UNCERTAINTY_SIGMA_MAX,
)
from backtesting.roster_outlook.metrics import compute_coverage, CoverageMetrics


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class BT6Result:
    overall_coverage_rate: float
    mean_band_width: float
    median_band_width: float
    n_teams: int
    n_pairs: int
    source_years_used: list[int]
    current_sigma_scale: float
    current_sigma_max: float
    recommended_sigma_scale: float
    recommended_sigma_max: float
    recommendation: str           # "increase" | "decrease" | "no_change"
    recommendation_detail: str
    by_source_year: list[dict]
    by_uncertainty_bucket: list[dict]
    coverage_metrics: CoverageMetrics


# ── Pure recommendation logic (extracted for testability) ─────────────────────

def _compute_sigma_recommendation(
    coverage_rate: float,
    sigma_scale: float = UNCERTAINTY_SIGMA_SCALE,
    sigma_max: float = UNCERTAINTY_SIGMA_MAX,
) -> tuple[float, float, str]:
    """
    Given observed coverage_rate, return (recommended_scale, recommended_max, recommendation).

    Target coverage: 0.60–0.75 (±1σ theoretical is 0.68).
    """
    if coverage_rate < 0.55:
        scale_factor = 0.68 / max(coverage_rate, 0.10)
        rec_scale = min(
            round(sigma_scale * scale_factor, 1),
            sigma_max - 0.5,
        )
        rec_max = min(rec_scale + 2.5, 8.0)
        return rec_scale, rec_max, "increase"

    elif coverage_rate > 0.80:
        scale_factor = 0.68 / coverage_rate
        rec_scale = max(round(sigma_scale * scale_factor, 1), 1.5)
        rec_max = rec_scale + 2.5
        return rec_scale, rec_max, "decrease"

    else:
        return sigma_scale, sigma_max, "no_change"


# ── Main BT-6 runner ──────────────────────────────────────────────────────────

def run_bt6(source_years: Optional[list[int]] = None) -> BT6Result:
    """
    Collect projected_adj_em_low/high vs actual adj_em from TeamSeasonProjection,
    compute coverage metrics, and recommend UNCERTAINTY_SIGMA_SCALE adjustments.

    NOTE: requires TeamSeasonProjection rows to have been computed by Phase 5.
    Seasons where no TeamSeasonProjection rows exist are silently skipped.
    """
    from backtesting.roster_outlook.data_loader import available_source_years, load_backtest_pair
    from ncaa.models import Team, TeamSeasonProjection

    years_to_try = source_years or available_source_years()

    pred_lows:   list[float] = []
    pred_highs:  list[float] = []
    actuals:     list[float] = []
    uncertainties: list[float] = []
    years_used:  list[int] = []
    by_year: list[dict] = []

    for source_year in years_to_try:
        try:
            pair = load_backtest_pair(source_year)
        except Exception:
            continue

        if not pair.prior_year_has_data:
            continue

        # Build slug → team_id map once per year
        slug_to_id: dict[str, int] = dict(
            Team.objects.filter(slug__in=list(pair.actual_outcomes.keys()))
            .values_list("slug", "id")
        )

        year_lows:   list[float] = []
        year_highs:  list[float] = []
        year_actuals: list[float] = []

        for slug in pair.evaluable_teams():
            team_id = slug_to_id.get(slug)
            if team_id is None:
                continue

            tsp = (
                TeamSeasonProjection.objects
                .filter(from_season__year=source_year, team_id=team_id)
                .values(
                    "projected_adj_em",
                    "projected_adj_em_low",
                    "projected_adj_em_high",
                    "team_projection_uncertainty",
                )
                .first()
            )
            if tsp is None:
                continue
            if tsp["projected_adj_em_low"] is None or tsp["projected_adj_em_high"] is None:
                continue

            actual_em = pair.actual_outcomes[slug].adj_em
            year_lows.append(float(tsp["projected_adj_em_low"]))
            year_highs.append(float(tsp["projected_adj_em_high"]))
            year_actuals.append(actual_em)
            uncertainties.append(float(tsp["team_projection_uncertainty"] or 0.5))

        if not year_actuals:
            continue

        years_used.append(source_year)
        pred_lows.extend(year_lows)
        pred_highs.extend(year_highs)
        actuals.extend(year_actuals)

        yr_cov = compute_coverage(year_lows, year_highs, year_actuals)
        by_year.append({
            "source_year": source_year,
            "target_year": source_year + 1,
            "coverage_rate": round(yr_cov.coverage_rate, 4),
            "mean_band_width": round(yr_cov.mean_band_width, 4),
            "n": yr_cov.n,
        })

    if not actuals:
        # No data — return no_change result with zeroed metrics
        return BT6Result(
            overall_coverage_rate=0.0,
            mean_band_width=0.0,
            median_band_width=0.0,
            n_teams=0,
            n_pairs=0,
            source_years_used=[],
            current_sigma_scale=UNCERTAINTY_SIGMA_SCALE,
            current_sigma_max=UNCERTAINTY_SIGMA_MAX,
            recommended_sigma_scale=UNCERTAINTY_SIGMA_SCALE,
            recommended_sigma_max=UNCERTAINTY_SIGMA_MAX,
            recommendation="no_change",
            recommendation_detail="No TeamSeasonProjection data found for the requested years.",
            by_source_year=[],
            by_uncertainty_bucket=[],
            coverage_metrics=CoverageMetrics(n=0, coverage_rate=0.0, mean_band_width=0.0, median_band_width=0.0),
        )

    coverage_metrics = compute_coverage(pred_lows, pred_highs, actuals)

    # ── By uncertainty quartile ───────────────────────────────────────────────
    quartiles = _quartile_breakdown(pred_lows, pred_highs, actuals, uncertainties)

    # ── Recommendation ────────────────────────────────────────────────────────
    rec_scale, rec_max, recommendation = _compute_sigma_recommendation(
        coverage_metrics.coverage_rate
    )
    recommendation_detail = _build_recommendation_detail(
        coverage_metrics.coverage_rate, recommendation, rec_scale, rec_max
    )

    return BT6Result(
        overall_coverage_rate=round(coverage_metrics.coverage_rate, 4),
        mean_band_width=round(coverage_metrics.mean_band_width, 4),
        median_band_width=round(coverage_metrics.median_band_width, 4),
        n_teams=len(actuals),
        n_pairs=len(years_used),
        source_years_used=years_used,
        current_sigma_scale=UNCERTAINTY_SIGMA_SCALE,
        current_sigma_max=UNCERTAINTY_SIGMA_MAX,
        recommended_sigma_scale=rec_scale,
        recommended_sigma_max=rec_max,
        recommendation=recommendation,
        recommendation_detail=recommendation_detail,
        by_source_year=by_year,
        by_uncertainty_bucket=quartiles,
        coverage_metrics=coverage_metrics,
    )


def _quartile_breakdown(
    pred_lows: list[float],
    pred_highs: list[float],
    actuals: list[float],
    uncertainties: list[float],
) -> list[dict]:
    """Split teams into 4 quartiles by uncertainty and compute coverage per quartile."""
    n = len(actuals)
    if n < 4:
        return []

    # Sort by uncertainty
    combined = sorted(zip(uncertainties, pred_lows, pred_highs, actuals))
    q_size = n // 4

    result = []
    for q_idx in range(4):
        start = q_idx * q_size
        end   = start + q_size if q_idx < 3 else n
        chunk = combined[start:end]
        q_unc  = [row[0] for row in chunk]
        q_low  = [row[1] for row in chunk]
        q_high = [row[2] for row in chunk]
        q_act  = [row[3] for row in chunk]
        cov = compute_coverage(q_low, q_high, q_act)
        result.append({
            "quartile": q_idx + 1,
            "label": f"Q{q_idx + 1} ({'low' if q_idx == 0 else 'high' if q_idx == 3 else 'mid'} uncertainty)",
            "n": len(chunk),
            "mean_uncertainty": round(statistics.mean(q_unc), 4),
            "coverage_rate": round(cov.coverage_rate, 4),
            "mean_band_width": round(cov.mean_band_width, 4),
        })
    return result


def _build_recommendation_detail(
    coverage_rate: float,
    recommendation: str,
    rec_scale: float,
    rec_max: float,
) -> str:
    pct = f"{coverage_rate:.1%}"
    if recommendation == "no_change":
        return (
            f"Coverage {pct} is within the 60–75% target range. "
            f"No change to UNCERTAINTY_SIGMA_SCALE ({UNCERTAINTY_SIGMA_SCALE}) recommended."
        )
    elif recommendation == "increase":
        return (
            f"Coverage {pct} is below the 60% floor — bands are too narrow. "
            f"Recommend increasing UNCERTAINTY_SIGMA_SCALE: {UNCERTAINTY_SIGMA_SCALE} → {rec_scale}, "
            f"UNCERTAINTY_SIGMA_MAX: {UNCERTAINTY_SIGMA_MAX} → {rec_max}."
        )
    else:
        return (
            f"Coverage {pct} is above the 75% ceiling — bands are too wide. "
            f"Recommend decreasing UNCERTAINTY_SIGMA_SCALE: {UNCERTAINTY_SIGMA_SCALE} → {rec_scale}, "
            f"UNCERTAINTY_SIGMA_MAX: {UNCERTAINTY_SIGMA_MAX} → {rec_max}."
        )
