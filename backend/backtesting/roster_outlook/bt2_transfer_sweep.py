"""
bt2_transfer_sweep.py — BT-2: Transfer Competition Weight Sweep.

Sweeps TRANSFER_COMP_WEIGHT_OFF/DEF candidates to find the value that minimises
player-level BPR prediction RMSE for transfers specifically.

The adjustment under test is:
  adjusted_bpr = player.bpr + candidate_weight * (prior_team_adj_em − current_team_adj_em)

The baseline (weight=0.03) is included in the sweep so every candidate can be
compared against the current production constant.

Usage:
    from backtesting.roster_outlook.bt2_transfer_sweep import run_bt2
    result = run_bt2()

Or via management command:
    python manage.py run_bt2
    python manage.py run_bt2 --years 2023 2024 2025
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import Optional

from backtesting.roster_outlook.data_loader import (
    available_source_years,
    load_backtest_pair,
)
from backtesting.roster_outlook.metrics import PointMetrics, compute_point_metrics
from ncaa.analytics.player_value.projection.constants import (
    TRANSFER_COMP_WEIGHT_OFF,
    TRANSFER_COMP_WEIGHT_DEF,
)

logger = logging.getLogger(__name__)

# Candidate weights to sweep
WEIGHT_CANDIDATES: list[float] = [
    0.01, 0.02, 0.03, 0.04, 0.05, 0.06,
    0.07, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20,
]

_CURRENT_WEIGHT = 0.03  # baseline comparison point


# ── Data containers ────────────────────────────────────────────────────────────

@dataclass
class TransferSweepResult:
    """Metrics for a single candidate weight across all evaluated pairs."""
    weight_off: float
    weight_def: float
    n_transfers: int
    n_pairs: int
    rmse: float
    mae: float
    bias: float
    r_squared: float
    delta_rmse_vs_baseline: float   # negative = this weight is better (lower RMSE)
    per_year: list[dict] = field(default_factory=list)


@dataclass
class BT2Result:
    """Full sweep result with recommendation."""
    candidates: list[TransferSweepResult]
    winning_weight_off: float
    winning_weight_def: float
    winner: TransferSweepResult
    baseline: TransferSweepResult   # result at weight=0.03
    winner_reason: str
    recommendation: str             # human-readable action


# ── DB helpers (Django imported inside to allow pure-Python import) ────────────

def load_team_adj_em(season_year: int) -> dict[str, float]:
    """
    Return {team_slug: adj_em} for a given season year.

    Args:
        season_year: Season year to look up.

    Returns:
        Dict mapping team slug → adj_em. Teams with no slug are excluded.
    """
    from ncaa.models import TeamSeasonRatings
    return dict(
        TeamSeasonRatings.objects
        .filter(season__year=season_year, team__slug__isnull=False)
        .values_list("team__slug", "adj_em")
    )


def load_prior_team_map(source_year: int) -> dict[int, str]:
    """
    Return {player_id: team_slug} from the season immediately before source_year.

    Mirrors data_loader._build_player_rows() logic: first row per player wins.
    This is the team the player was on BEFORE arriving at their source-year team —
    i.e., the team whose adj_em was the competition context they transferred FROM.

    Args:
        source_year: Source season year. Prior year = source_year - 1.

    Returns:
        Dict mapping player_id → prior team slug (empty string for non-D1 prior teams).
    """
    from ncaa.models import PlayerSeasonStats
    result: dict[int, str] = {}
    for row in PlayerSeasonStats.objects.filter(
        season__year=source_year - 1
    ).values("player_id", "team__slug"):
        pid = row["player_id"]
        if pid not in result:
            result[pid] = row["team__slug"] or ""
    return result


# ── Main sweep function ────────────────────────────────────────────────────────

def run_bt2(
    source_years: Optional[list[int]] = None,
    weight_candidates: Optional[list[float]] = None,
) -> BT2Result:
    """
    BT-2: Sweep transfer competition weight candidates.

    For each candidate weight, applies:
        adjusted_bpr = player.bpr + weight * (prior_team_adj_em - current_team_adj_em)

    Evaluates only transfers where both adj_em values are available and
    adj_delta != 0. Picks the winner by minimum RMSE, tie-breaking on |bias|.

    Args:
        source_years:      Restrict to these source years. None → all available,
                           filtered to prior_year_has_data=True.
        weight_candidates: Weights to evaluate. None → use WEIGHT_CANDIDATES constant.

    Returns:
        BT2Result with all candidate results and recommendation.
    """
    from ncaa.models import PlayerSeasonStats

    candidates_to_test = weight_candidates or WEIGHT_CANDIDATES
    years = source_years or available_source_years()
    if not years:
        logger.warning("[BT-2] No valid source years found.")
        _empty = TransferSweepResult(
            weight_off=_CURRENT_WEIGHT, weight_def=_CURRENT_WEIGHT,
            n_transfers=0, n_pairs=0, rmse=0.0, mae=0.0, bias=0.0,
            r_squared=0.0, delta_rmse_vs_baseline=0.0,
        )
        return BT2Result(
            candidates=[], winning_weight_off=_CURRENT_WEIGHT,
            winning_weight_def=_CURRENT_WEIGHT, winner=_empty, baseline=_empty,
            winner_reason="No data", recommendation="No data available",
        )

    # Per-weight accumulator: {weight: [(adjusted_bpr, actual_bpr)]}
    pairs_by_weight: dict[float, list[tuple[float, float]]] = {
        w: [] for w in candidates_to_test
    }
    n_skipped_missing_em = 0
    n_skipped_zero_delta = 0
    valid_pairs_count = 0
    per_year_raw: list[dict] = []

    for source_year in years:
        pair = load_backtest_pair(source_year)
        if not pair.prior_year_has_data:
            logger.info("[BT-2] Source year %d: prior_year_has_data=False, skipping.", source_year)
            continue

        source_adj_em = load_team_adj_em(source_year)
        prior_adj_em  = load_team_adj_em(source_year - 1)
        prior_team_map = load_prior_team_map(source_year)

        # Actual next-year BPR for all player IDs in evaluable teams
        all_pids = {
            p.player_id
            for slug in pair.evaluable_teams()
            for p in pair.team_pools[slug].players
        }
        actual_bpr_map: dict[int, float] = dict(
            PlayerSeasonStats.objects
            .filter(player_id__in=all_pids, season__year=pair.target_year)
            .values_list("player_id", "bpr")
        )

        yr_pairs_by_weight: dict[float, list[tuple[float, float]]] = {
            w: [] for w in candidates_to_test
        }
        yr_skipped_missing = 0
        yr_skipped_zero = 0

        for slug in pair.evaluable_teams():
            pool = pair.team_pools[slug]
            for player in pool.players:
                if player.recruitment_type != "transfer":
                    continue
                actual_bpr = actual_bpr_map.get(player.player_id)
                if actual_bpr is None:
                    continue  # player left D1 next year

                prior_slug = prior_team_map.get(player.player_id, "")
                if not prior_slug:
                    yr_skipped_missing += 1
                    continue

                prior_em   = prior_adj_em.get(prior_slug)
                current_em = source_adj_em.get(player.team_slug)
                if prior_em is None or current_em is None:
                    yr_skipped_missing += 1
                    continue

                adj_delta = prior_em - current_em
                if adj_delta == 0.0:
                    yr_skipped_zero += 1
                    continue

                actual_bpr_f = float(actual_bpr)
                for w in candidates_to_test:
                    adjusted = player.bpr + w * adj_delta
                    yr_pairs_by_weight[w].append((adjusted, actual_bpr_f))
                    pairs_by_weight[w].append((adjusted, actual_bpr_f))

        n_skipped_missing_em += yr_skipped_missing
        n_skipped_zero_delta += yr_skipped_zero

        # Per-year metrics at baseline weight for reporting
        yr_base_pairs = yr_pairs_by_weight.get(_CURRENT_WEIGHT, [])
        yr_entry: dict = {"source_year": source_year, "n_transfers": len(yr_base_pairs)}
        if len(yr_base_pairs) >= 2:
            m = compute_point_metrics(
                [p[0] for p in yr_base_pairs],
                [p[1] for p in yr_base_pairs],
            )
            yr_entry.update({"rmse": m.rmse, "bias": m.bias, "r_squared": m.r_squared})
            valid_pairs_count += 1
        per_year_raw.append(yr_entry)

    if n_skipped_missing_em > 0:
        logger.info("[BT-2] Skipped %d transfers: missing adj_em.", n_skipped_missing_em)
    if n_skipped_zero_delta > 0:
        logger.info("[BT-2] Skipped %d transfers: adj_delta == 0.", n_skipped_zero_delta)

    # Build per-candidate metrics
    candidate_results: list[TransferSweepResult] = []
    baseline_result: Optional[TransferSweepResult] = None

    for w in candidates_to_test:
        pairs = pairs_by_weight[w]
        if len(pairs) < 2:
            continue
        preds   = [p[0] for p in pairs]
        actuals = [p[1] for p in pairs]
        m = compute_point_metrics(preds, actuals)
        sr = TransferSweepResult(
            weight_off=w, weight_def=w,
            n_transfers=len(pairs),
            n_pairs=valid_pairs_count,
            rmse=m.rmse, mae=m.mae, bias=m.bias, r_squared=m.r_squared,
            delta_rmse_vs_baseline=0.0,  # filled below
            per_year=per_year_raw,
        )
        candidate_results.append(sr)
        if abs(w - _CURRENT_WEIGHT) < 1e-9:
            baseline_result = sr

    if not candidate_results:
        logger.warning("[BT-2] No valid transfer pairs found.")
        _empty = TransferSweepResult(
            weight_off=_CURRENT_WEIGHT, weight_def=_CURRENT_WEIGHT,
            n_transfers=0, n_pairs=0, rmse=0.0, mae=0.0, bias=0.0,
            r_squared=0.0, delta_rmse_vs_baseline=0.0,
        )
        return BT2Result(
            candidates=[], winning_weight_off=_CURRENT_WEIGHT,
            winning_weight_def=_CURRENT_WEIGHT, winner=_empty, baseline=_empty,
            winner_reason="No transfer pairs", recommendation="No data available",
        )

    baseline = baseline_result or candidate_results[0]

    # Fill delta_rmse_vs_baseline (negative = better than baseline)
    for sr in candidate_results:
        sr.delta_rmse_vs_baseline = sr.rmse - baseline.rmse

    # Pick winner: minimum RMSE, tie-break by |bias|
    winner = min(
        candidate_results,
        key=lambda r: (round(r.rmse, 6), abs(r.bias)),
    )

    # Build recommendation
    diff = abs(winner.weight_off - _CURRENT_WEIGHT)
    improved = winner.delta_rmse_vs_baseline < 0
    if diff > 0.01 and improved:
        recommendation = (
            f"Update TRANSFER_COMP_WEIGHT_OFF and TRANSFER_COMP_WEIGHT_DEF "
            f"from {_CURRENT_WEIGHT:.2f} to {winner.weight_off:.2f}"
        )
        winner_reason = (
            f"weight={winner.weight_off:.2f} wins: "
            f"RMSE={winner.rmse:.4f} (Δ{winner.delta_rmse_vs_baseline:+.4f} vs baseline)"
        )
    else:
        recommendation = (
            f"Current weight {_CURRENT_WEIGHT:.2f} is within acceptable range "
            f"— no update needed"
        )
        winner_reason = (
            f"weight={winner.weight_off:.2f} best but Δ={winner.delta_rmse_vs_baseline:+.4f} "
            f"or diff={diff:.3f} below threshold"
        )

    result = BT2Result(
        candidates=candidate_results,
        winning_weight_off=winner.weight_off,
        winning_weight_def=winner.weight_def,
        winner=winner,
        baseline=baseline,
        winner_reason=winner_reason,
        recommendation=recommendation,
    )

    _print_bt2_summary(result)
    return result


def _print_bt2_summary(result: BT2Result) -> None:
    baseline = result.baseline
    print("\n" + "=" * 74)
    print("BT-2  Transfer Competition Weight Sweep")
    print("=" * 74)
    print(f"  Baseline weight (current): {_CURRENT_WEIGHT:.2f}")
    print(f"  Baseline RMSE:             {baseline.rmse:.4f}")
    print(f"  N transfers evaluated:     {baseline.n_transfers}")
    print(f"  N source→target pairs:     {baseline.n_pairs}")
    print()
    print(
        f"  {'weight':>7}  {'n_xfr':>7}  {'RMSE':>8}  {'MAE':>8}  "
        f"{'bias':>8}  {'R²':>7}  {'ΔRMSE':>8}  {'':>6}"
    )
    print("  " + "-" * 70)
    for sr in result.candidates:
        winner_flag = "← WIN" if abs(sr.weight_off - result.winning_weight_off) < 1e-9 else ""
        baseline_flag = "(base)" if abs(sr.weight_off - _CURRENT_WEIGHT) < 1e-9 else ""
        print(
            f"  {sr.weight_off:>7.2f}  {sr.n_transfers:>7d}  "
            f"{sr.rmse:>8.4f}  {sr.mae:>8.4f}  "
            f"{sr.bias:>8.4f}  {sr.r_squared:>7.4f}  "
            f"{sr.delta_rmse_vs_baseline:>+8.4f}  "
            f"{winner_flag or baseline_flag:<6}"
        )
    print()
    print(f"  Winner:         {result.winner_reason}")
    print(f"  Recommendation: {result.recommendation}")
    print()
