"""
bt1_bt4_calibration.py — BT-1 (player BPR RMSE baseline) and BT-4 (empirical
slope derivation for SLOPE_OFF / SLOPE_DEF).

BT-1
────
For each valid source year, compare each player's source-year BPR (carry-forward
baseline) against their actual next-season BPR.  Computes RMSE, MAE, bias, R²
overall and broken down by recruitment_type (returner / transfer / newcomer).
This establishes the carry-forward baseline that the Phase 1 shrinkage engine
must beat to be justified.

BT-4
────
For each valid source year, regresses actual (next_adj_o − D1_avg) against
(team base_off − league_mean_base_off) to derive empirical SLOPE_OFF and
SLOPE_DEF.  These empirical slopes are candidate replacements for the current
constants, which were calibrated from a single Duke cross-check.

Usage:
    from backtesting.roster_outlook.bt1_bt4_calibration import run_bt1, run_bt4
    bt1 = run_bt1()
    bt4 = run_bt4()

Or via management command:
    python manage.py run_bt1_bt4 [--years 2023 2024 2025]
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from typing import Optional

from scipy import stats as scipy_stats

from backtesting.roster_outlook.data_loader import (
    available_source_years,
    load_backtest_pair,
)
from backtesting.roster_outlook.metrics import PointMetrics, compute_point_metrics
from ncaa.analytics.player_value.team_projection.constants import SLOPE_OFF, SLOPE_DEF

logger = logging.getLogger(__name__)

SLOPE_WARN_THRESHOLD = 0.10  # warn if empirical slope differs from constant by more than this


# ── BT-1: Player BPR Projection RMSE ─────────────────────────────────────────

def run_bt1(source_years: Optional[list[int]] = None) -> dict:
    """
    BT-1: Compute player-level BPR projection RMSE across all valid backtest pairs.

    Uses each player's source-year BPR as a carry-forward prediction and
    compares it against their actual BPR in the target year.  This is the
    simplest possible baseline — the Phase 1 shrinkage engine must beat this.

    Args:
        source_years: Restrict to these source years. None → use all available.

    Returns:
        dict with keys:
            overall        (PointMetrics)
            by_type        (dict[str → PointMetrics]) — returner/transfer/newcomer
            by_source_year (dict[int → PointMetrics])
            n_players      (int) — total (source_year, player_id) pairs evaluated
            source_years_used (list[int])
    """
    # Django model import inside function for test-isolation
    from ncaa.models import PlayerSeasonStats

    years = source_years or available_source_years()
    if not years:
        logger.warning("[BT-1] No valid source years found.")
        return {}

    # Collect (predicted_bpr, actual_bpr, recruitment_type, source_year)
    records: list[dict] = []

    for source_year in years:
        pair = load_backtest_pair(source_year)
        target_year = pair.target_year

        # Load target-year BPR for all players we care about
        all_pids = {
            p.player_id
            for pool in pair.team_pools.values()
            for p in pool.players
        }
        actual_bpr_map: dict[int, float] = dict(
            PlayerSeasonStats.objects
            .filter(player_id__in=all_pids, season__year=target_year)
            .values_list("player_id", "bpr")
        )

        for slug in pair.evaluable_teams():
            pool = pair.team_pools[slug]
            for player in pool.players:
                actual = actual_bpr_map.get(player.player_id)
                if actual is None:
                    continue
                records.append({
                    "predicted":        player.bpr,
                    "actual":           float(actual),
                    "recruitment_type": player.recruitment_type,
                    "source_year":      source_year,
                })

    if len(records) < 2:
        logger.warning("[BT-1] Not enough player pairs to compute metrics (n=%d).", len(records))
        return {"n_players": len(records), "source_years_used": years}

    # Overall metrics
    preds   = [r["predicted"] for r in records]
    actuals = [r["actual"]    for r in records]
    overall = compute_point_metrics(preds, actuals)

    # By recruitment type
    by_type: dict[str, PointMetrics] = {}
    for rtype in ("returner", "transfer", "newcomer"):
        subset = [r for r in records if r["recruitment_type"] == rtype]
        if len(subset) >= 2:
            by_type[rtype] = compute_point_metrics(
                [r["predicted"] for r in subset],
                [r["actual"]    for r in subset],
            )

    # By source year
    by_year: dict[int, PointMetrics] = {}
    for yr in years:
        subset = [r for r in records if r["source_year"] == yr]
        if len(subset) >= 2:
            by_year[yr] = compute_point_metrics(
                [r["predicted"] for r in subset],
                [r["actual"]    for r in subset],
            )

    result = {
        "overall":         overall,
        "by_type":         by_type,
        "by_source_year":  by_year,
        "n_players":       len(records),
        "source_years_used": years,
    }

    _print_bt1_summary(result)
    return result


def _print_bt1_summary(result: dict) -> None:
    overall = result["overall"]
    print("\n" + "=" * 62)
    print("BT-1  Player BPR Carry-Forward Baseline")
    print("=" * 62)
    print(f"  Source years  : {result['source_years_used']}")
    print(f"  N players     : {result['n_players']}")
    print(f"  Overall RMSE  : {overall.rmse:.4f}")
    print(f"  Overall MAE   : {overall.mae:.4f}")
    print(f"  Bias          : {overall.bias:.4f}  (+ = over-predict)")
    print(f"  R²            : {overall.r_squared:.4f}")
    print(f"  Pearson r     : {overall.pearson_r:.4f}  (p={overall.pearson_p:.4f})")
    print(f"  Spearman ρ    : {overall.spearman_rho:.4f}  (p={overall.spearman_p:.4f})")

    if result.get("by_type"):
        print("\n  By recruitment type:")
        print(f"  {'Type':<12} {'n':>6}  {'RMSE':>7}  {'MAE':>7}  {'Bias':>7}  {'R²':>7}")
        print("  " + "-" * 54)
        for rtype, m in result["by_type"].items():
            print(f"  {rtype:<12} {m.n:>6}  {m.rmse:>7.4f}  {m.mae:>7.4f}  {m.bias:>7.4f}  {m.r_squared:>7.4f}")

    if result.get("by_source_year"):
        print("\n  By source year:")
        print(f"  {'Year':>6}  {'n':>6}  {'RMSE':>7}  {'Bias':>7}")
        print("  " + "-" * 34)
        for yr, m in sorted(result["by_source_year"].items()):
            print(f"  {yr:>6}  {m.n:>6}  {m.rmse:>7.4f}  {m.bias:>7.4f}")

    print()


# ── BT-4: Empirical slope derivation ─────────────────────────────────────────

def run_bt4(source_years: Optional[list[int]] = None) -> dict:
    """
    BT-4: Derive SLOPE_OFF and SLOPE_DEF empirically via OLS regression.

    Regresses (actual_adj_o − D1_avg_o) against (team_base_off − league_mean_base_off)
    across all valid source years to produce empirical slope candidates.

    If the empirical slope differs from the current constant by > SLOPE_WARN_THRESHOLD,
    a warning is printed recommending the constant be updated.

    Args:
        source_years: Restrict to these source years. None → use all available.

    Returns:
        dict with keys:
            empirical_slope_off (float)
            empirical_slope_def (float)
            r_squared_off       (float)
            r_squared_def       (float)
            n_teams             (int)
            current_slope_off   (float)  — SLOPE_OFF from constants
            current_slope_def   (float)  — SLOPE_DEF from constants
            recommendation      (str)    — human-readable update/keep message
            source_years_used   (list[int])
            per_year            (list[dict])  — per-source-year slope for stability check
    """
    years = source_years or available_source_years()
    if not years:
        logger.warning("[BT-4] No valid source years found.")
        return {}

    # Accumulate all (x_off, y_off) and (x_def, y_def) across years
    all_x_off: list[float] = []
    all_y_off: list[float] = []
    all_x_def: list[float] = []
    all_y_def: list[float] = []

    per_year: list[dict] = []

    for source_year in years:
        pair = load_backtest_pair(source_year)

        # Compute per-team base_off / base_def from PlayerRow minutes-weighted BPR
        team_base: dict[str, tuple[float, float]] = {}  # slug → (base_off, base_def)
        for slug in pair.evaluable_teams():
            pool = pair.team_pools[slug]
            b_off = sum(p.obpr * p.minutes_share_p2 for p in pool.players)
            b_def = sum(p.dbpr * p.minutes_share_p2 for p in pool.players)
            team_base[slug] = (b_off, b_def)

        if not team_base:
            continue

        # League means for this source year (across evaluable teams)
        league_mean_off = statistics.mean(b[0] for b in team_base.values())
        league_mean_def = statistics.mean(b[1] for b in team_base.values())

        # Build regression inputs for this year
        yr_x_off: list[float] = []
        yr_y_off: list[float] = []
        yr_x_def: list[float] = []
        yr_y_def: list[float] = []

        for slug, (b_off, b_def) in team_base.items():
            actual = pair.actual_outcomes.get(slug)
            if actual is None:
                continue

            x_off = b_off - league_mean_off
            y_off = actual.adj_o - pair.d1_avg_o

            # Defense: lower adj_d = better defense; sign consistent with engine formula:
            #   projected_adj_d = D1_avg_d - SLOPE_DEF × (base_def - league_mean_base_def)
            # So y_def = D1_avg_d - actual_adj_d
            x_def = b_def - league_mean_def
            y_def = pair.d1_avg_d - actual.adj_d

            yr_x_off.append(x_off)
            yr_y_off.append(y_off)
            yr_x_def.append(x_def)
            yr_y_def.append(y_def)

        all_x_off.extend(yr_x_off)
        all_y_off.extend(yr_y_off)
        all_x_def.extend(yr_x_def)
        all_y_def.extend(yr_y_def)

        # Per-year slope estimates (for stability inspection)
        yr_result: dict = {"source_year": source_year, "n_teams": len(yr_x_off)}
        if len(yr_x_off) >= 3:
            reg_off = scipy_stats.linregress(yr_x_off, yr_y_off)
            reg_def = scipy_stats.linregress(yr_x_def, yr_y_def)
            yr_result["slope_off"] = float(reg_off.slope)
            yr_result["slope_def"] = float(reg_def.slope)
            yr_result["r2_off"]    = float(reg_off.rvalue ** 2)
            yr_result["r2_def"]    = float(reg_def.rvalue ** 2)
        per_year.append(yr_result)

    if len(all_x_off) < 3:
        logger.warning("[BT-4] Not enough team pairs to regress (n=%d).", len(all_x_off))
        return {"n_teams": len(all_x_off), "source_years_used": years}

    # Combined OLS regression
    reg_off = scipy_stats.linregress(all_x_off, all_y_off)
    reg_def = scipy_stats.linregress(all_x_def, all_y_def)

    emp_off = float(reg_off.slope)
    emp_def = float(reg_def.slope)
    r2_off  = float(reg_off.rvalue ** 2)
    r2_def  = float(reg_def.rvalue ** 2)

    # Build recommendation string
    recs: list[str] = []
    if abs(emp_off - SLOPE_OFF) > SLOPE_WARN_THRESHOLD:
        recs.append(
            f"⚠  SLOPE_OFF: current={SLOPE_OFF:.3f}, empirical={emp_off:.3f} "
            f"(diff={emp_off - SLOPE_OFF:+.3f}) — recommend updating (R²={r2_off:.3f})"
        )
    else:
        recs.append(f"✓  SLOPE_OFF: current={SLOPE_OFF:.3f}, empirical={emp_off:.3f} — no change needed")
    if abs(emp_def - SLOPE_DEF) > SLOPE_WARN_THRESHOLD:
        recs.append(
            f"⚠  SLOPE_DEF: current={SLOPE_DEF:.3f}, empirical={emp_def:.3f} "
            f"(diff={emp_def - SLOPE_DEF:+.3f}) — recommend updating (R²={r2_def:.3f})"
        )
    else:
        recs.append(f"✓  SLOPE_DEF: current={SLOPE_DEF:.3f}, empirical={emp_def:.3f} — no change needed")

    recommendation = "\n".join(recs)

    result = {
        "empirical_slope_off": emp_off,
        "empirical_slope_def": emp_def,
        "r_squared_off":       r2_off,
        "r_squared_def":       r2_def,
        "n_teams":             len(all_x_off),
        "current_slope_off":   SLOPE_OFF,
        "current_slope_def":   SLOPE_DEF,
        "recommendation":      recommendation,
        "source_years_used":   years,
        "per_year":            per_year,
    }

    _print_bt4_summary(result)
    return result


def _print_bt4_summary(result: dict) -> None:
    print("\n" + "=" * 62)
    print("BT-4  Empirical Slope Derivation (SLOPE_OFF / SLOPE_DEF)")
    print("=" * 62)
    print(f"  Source years    : {result['source_years_used']}")
    print(f"  N team pairs    : {result['n_teams']}")
    print()
    print(f"  {'':20}  {'Empirical':>10}  {'Current':>10}  {'Delta':>8}  {'R²':>7}")
    print("  " + "-" * 56)
    print(
        f"  {'SLOPE_OFF':<20}  "
        f"{result['empirical_slope_off']:>10.4f}  "
        f"{result['current_slope_off']:>10.4f}  "
        f"{result['empirical_slope_off'] - result['current_slope_off']:>+8.4f}  "
        f"{result['r_squared_off']:>7.4f}"
    )
    print(
        f"  {'SLOPE_DEF':<20}  "
        f"{result['empirical_slope_def']:>10.4f}  "
        f"{result['current_slope_def']:>10.4f}  "
        f"{result['empirical_slope_def'] - result['current_slope_def']:>+8.4f}  "
        f"{result['r_squared_def']:>7.4f}"
    )

    if result.get("per_year"):
        print("\n  Per-year slope estimates (stability check):")
        print(f"  {'Year':>6}  {'n':>5}  {'slope_off':>10}  {'slope_def':>10}  {'r2_off':>8}  {'r2_def':>8}")
        print("  " + "-" * 58)
        for yr in result["per_year"]:
            if "slope_off" in yr:
                print(
                    f"  {yr['source_year']:>6}  {yr['n_teams']:>5}  "
                    f"{yr['slope_off']:>10.4f}  {yr['slope_def']:>10.4f}  "
                    f"{yr['r2_off']:>8.4f}  {yr['r2_def']:>8.4f}"
                )

    print()
    print("  Recommendation:")
    for line in result["recommendation"].split("\n"):
        print(f"    {line}")
    print()
