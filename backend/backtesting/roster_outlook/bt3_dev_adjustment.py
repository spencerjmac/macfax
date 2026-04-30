"""
bt3_dev_adjustment.py — BT-3: Development Adjustment Stratified by Role Bucket.

Measures actual year-over-year BPR deltas for players grouped by role bucket
(Guard/Wing/Big) and experience stage (newcomer/second_year/third_year/senior_plus).

Current constants (DEV_OFF_NEWCOMER etc.) apply the same adjustment regardless of
position. Bigs tend to contribute earlier; guards tend to develop slower. This
analysis produces position-stratified recommended constants.

Usage:
    from backtesting.roster_outlook.bt3_dev_adjustment import run_bt3
    result = run_bt3()

Or via management command:
    python manage.py run_bt3
    python manage.py run_bt3 --apply
    python manage.py run_bt3 --years 2023 2024 2025
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from typing import Optional

from backtesting.roster_outlook.data_loader import (
    available_source_years,
    load_backtest_pair,
)
from ncaa.analytics.player_value.minutes.role_buckets import (
    GUARD, WING, BIG,
    classify_role_bucket,
)
from ncaa.analytics.player_value.projection.constants import (
    DEV_OFF_NEWCOMER,    DEV_DEF_NEWCOMER,
    DEV_OFF_SECOND_YEAR, DEV_DEF_SECOND_YEAR,
    DEV_OFF_SENIOR,      DEV_DEF_SENIOR,
    SENIOR_SEASON_THRESHOLD,
)

logger = logging.getLogger(__name__)

# Experience stage labels
STAGE_NEWCOMER    = "newcomer"
STAGE_SECOND_YEAR = "second_year"
STAGE_THIRD_YEAR  = "third_year"
STAGE_SENIOR_PLUS = "senior_plus"

ALL_STAGES = (STAGE_NEWCOMER, STAGE_SECOND_YEAR, STAGE_THIRD_YEAR, STAGE_SENIOR_PLUS)
ALL_BUCKETS = (GUARD, WING, BIG)

# Confidence thresholds
HIGH_CONFIDENCE_N   = 50
MEDIUM_CONFIDENCE_N = 20

# Clamping ranges per stage (off and def share the same range in each stage)
_CLAMP: dict[str, tuple[float, float]] = {
    STAGE_NEWCOMER:    (-0.10, +0.60),
    STAGE_SECOND_YEAR: (-0.10, +0.40),
    STAGE_THIRD_YEAR:  (-0.15, +0.20),
    STAGE_SENIOR_PLUS: (-0.30, +0.10),
}

# Current flat constants used as fallback for low-confidence cells
_CURRENT_OFF: dict[str, float] = {
    STAGE_NEWCOMER:    DEV_OFF_NEWCOMER,
    STAGE_SECOND_YEAR: DEV_OFF_SECOND_YEAR,
    STAGE_THIRD_YEAR:  0.0,
    STAGE_SENIOR_PLUS: DEV_OFF_SENIOR,
}
_CURRENT_DEF: dict[str, float] = {
    STAGE_NEWCOMER:    DEV_DEF_NEWCOMER,
    STAGE_SECOND_YEAR: DEV_DEF_SECOND_YEAR,
    STAGE_THIRD_YEAR:  0.0,
    STAGE_SENIOR_PLUS: DEV_DEF_SENIOR,
}


# ── Data containers ────────────────────────────────────────────────────────────

@dataclass
class DevStats:
    """Development statistics for one (bucket, stage) cell."""
    bucket: str
    stage: str
    n: int
    mean_actual_delta: float
    std_actual_delta: float
    current_dev_adj: float     # current flat constant for this stage
    recommended_adj: float     # data-derived recommendation (or current if n<20)

    @property
    def confidence(self) -> str:
        if self.n >= HIGH_CONFIDENCE_N:
            return "high"
        if self.n >= MEDIUM_CONFIDENCE_N:
            return "medium"
        return "low"


@dataclass
class BT3Result:
    """Full BT-3 analysis result."""
    by_bucket_by_stage: dict[str, dict[str, DevStats]]  # {bucket: {stage: DevStats}}
    recommended_constants: dict[str, float]   # {constant_name: value}
    current_constants: dict[str, float]       # snapshot before any change
    n_observations: int
    source_years_used: list[int]
    summary_table: str


# ── Analysis function ─────────────────────────────────────────────────────────

def run_bt3(source_years: Optional[list[int]] = None) -> BT3Result:
    """
    BT-3: Compute actual year-over-year BPR deltas by role bucket and experience stage.

    For each player in each evaluable team across valid source years:
      - Derives role bucket via classify_role_bucket()
      - Determines experience stage from prior season count
      - Computes delta = actual_bpr_next_year - source_year_bpr
      - Groups into (bucket, stage) cells

    Returns BT3Result with per-cell stats and recommended constants.
    Cells with n < MEDIUM_CONFIDENCE_N (20) retain the current flat constant.

    Args:
        source_years: Restrict to these source years. None → all available.

    Returns:
        BT3Result dataclass.
    """
    from ncaa.models import PlayerSeasonStats, Player
    from django.db.models import Count

    years = source_years or available_source_years()
    if not years:
        logger.warning("[BT-3] No valid source years found.")
        return _empty_result(years)

    # Accumulate deltas: {(bucket, stage): [delta, ...]}
    deltas: dict[tuple[str, str], list[float]] = {
        (b, s): [] for b in ALL_BUCKETS for s in ALL_STAGES
    }
    years_used: list[int] = []

    for source_year in years:
        pair = load_backtest_pair(source_year)
        if not pair.prior_year_has_data:
            continue

        years_used.append(source_year)

        # All player IDs across evaluable teams
        all_pids = {
            p.player_id
            for slug in pair.evaluable_teams()
            for p in pair.team_pools[slug].players
        }
        if not all_pids:
            continue

        # Load box stats for source_year (one query for all players)
        box_map: dict[int, dict] = {}
        for row in PlayerSeasonStats.objects.filter(
            player_id__in=all_pids, season__year=source_year
        ).values("player_id", "blk", "reb", "ast", "fg3a_pg"):
            box_map[row["player_id"]] = row

        # Load player positions (one query)
        position_map: dict[int, str] = dict(
            Player.objects.filter(id__in=all_pids).values_list("id", "position")
        )

        # Load actual next-year BPR (one query)
        actual_bpr_map: dict[int, float] = dict(
            PlayerSeasonStats.objects
            .filter(player_id__in=all_pids, season__year=pair.target_year)
            .values_list("player_id", "bpr")
        )

        # Count prior seasons per player for stage determination (one query)
        prior_count_map: dict[int, int] = dict(
            PlayerSeasonStats.objects
            .filter(player_id__in=all_pids, season__year__lt=source_year)
            .values("player_id")
            .annotate(n=Count("season__year", distinct=True))
            .values_list("player_id", "n")
        )

        for slug in pair.evaluable_teams():
            pool = pair.team_pools[slug]
            for player in pool.players:
                pid = player.player_id
                actual_bpr = actual_bpr_map.get(pid)
                if actual_bpr is None:
                    continue  # left D1

                box = box_map.get(pid, {})
                bucket = classify_role_bucket(
                    position=position_map.get(pid, "") or "",
                    blk_pg=float(box.get("blk") or 0.0),
                    reb_pg=float(box.get("reb") or 0.0),
                    ast_pg=float(box.get("ast") or 0.0),
                    fg3a_pg=float(box.get("fg3a_pg") or 0.0),
                )

                n_prior = prior_count_map.get(pid, 0)
                stage = _stage_from_prior_count(n_prior)

                delta = float(actual_bpr) - player.bpr
                deltas[(bucket, stage)].append(delta)

    if not years_used:
        logger.warning("[BT-3] No valid source years with prior data found.")
        return _empty_result(years)

    # Build DevStats for each (bucket, stage) cell
    by_bucket: dict[str, dict[str, DevStats]] = {b: {} for b in ALL_BUCKETS}
    recommended: dict[str, float] = {}
    current_snap: dict[str, float] = {}
    total_obs = 0

    for bucket in ALL_BUCKETS:
        for stage in ALL_STAGES:
            cell_deltas = deltas[(bucket, stage)]
            n = len(cell_deltas)
            total_obs += n

            cur_off = _CURRENT_OFF[stage]
            cur_def = _CURRENT_DEF[stage]

            if n >= MEDIUM_CONFIDENCE_N:
                mean_d = statistics.mean(cell_deltas)
                lo, hi = _CLAMP[stage]
                rec_adj = max(lo, min(hi, round(mean_d, 2)))
            else:
                mean_d = statistics.mean(cell_deltas) if n >= 2 else 0.0
                rec_adj = cur_off  # fallback to current

            std_d = statistics.stdev(cell_deltas) if n >= 2 else 0.0

            ds = DevStats(
                bucket=bucket,
                stage=stage,
                n=n,
                mean_actual_delta=round(mean_d, 4),
                std_actual_delta=round(std_d, 4),
                current_dev_adj=cur_off,
                recommended_adj=rec_adj,
            )
            by_bucket[bucket][stage] = ds

            # Build constant names → values
            b_suffix = bucket.upper() if bucket == GUARD else bucket.capitalize()
            b_suffix = bucket.replace("G", "G").replace("Wing", "WING").replace("Big", "BIG")

            if stage == STAGE_NEWCOMER:
                recommended[f"DEV_OFF_NEWCOMER_{b_suffix}"]    = rec_adj
                recommended[f"DEV_DEF_NEWCOMER_{b_suffix}"]    = max(lo, min(hi, round(mean_d * 0.5, 2))) if n >= MEDIUM_CONFIDENCE_N else cur_def
                current_snap[f"DEV_OFF_NEWCOMER_{b_suffix}"]   = cur_off
                current_snap[f"DEV_DEF_NEWCOMER_{b_suffix}"]   = cur_def
            elif stage == STAGE_SECOND_YEAR:
                recommended[f"DEV_OFF_SECOND_YEAR_{b_suffix}"] = rec_adj
                recommended[f"DEV_DEF_SECOND_YEAR_{b_suffix}"] = max(lo, min(hi, round(mean_d * 0.5, 2))) if n >= MEDIUM_CONFIDENCE_N else cur_def
                current_snap[f"DEV_OFF_SECOND_YEAR_{b_suffix}"] = cur_off
                current_snap[f"DEV_DEF_SECOND_YEAR_{b_suffix}"] = cur_def
            elif stage == STAGE_SENIOR_PLUS:
                recommended[f"DEV_OFF_SENIOR_{b_suffix}"]      = rec_adj
                recommended[f"DEV_DEF_SENIOR_{b_suffix}"]      = max(lo, min(hi, round(mean_d * 0.5, 2))) if n >= MEDIUM_CONFIDENCE_N else cur_def
                current_snap[f"DEV_OFF_SENIOR_{b_suffix}"]     = cur_off
                current_snap[f"DEV_DEF_SENIOR_{b_suffix}"]     = cur_def

    table = _build_table(by_bucket)
    result = BT3Result(
        by_bucket_by_stage=by_bucket,
        recommended_constants=recommended,
        current_constants=current_snap,
        n_observations=total_obs,
        source_years_used=years_used,
        summary_table=table,
    )
    print(table)
    return result


def _stage_from_prior_count(n_prior: int) -> str:
    """Map count of prior college seasons to experience stage label."""
    if n_prior == 0:
        return STAGE_NEWCOMER
    if n_prior == 1:
        return STAGE_SECOND_YEAR
    if n_prior == 2:
        return STAGE_THIRD_YEAR
    return STAGE_SENIOR_PLUS  # n_prior >= 3


def _empty_result(years: list[int]) -> BT3Result:
    return BT3Result(
        by_bucket_by_stage={b: {} for b in ALL_BUCKETS},
        recommended_constants={},
        current_constants={},
        n_observations=0,
        source_years_used=years,
        summary_table="(no data)",
    )


def _build_table(by_bucket: dict[str, dict[str, DevStats]]) -> str:
    lines = [
        "",
        "=" * 82,
        "BT-3  Development Delta by Role Bucket × Experience Stage",
        "=" * 82,
        f"  {'':>10}  {'newcomer':>18}  {'second_year':>18}  {'third_year':>18}  {'senior_plus':>18}",
        f"  {'':>10}  {'mean/n/cur/rec':>18}  {'mean/n/cur/rec':>18}  {'mean/n/cur/rec':>18}  {'mean/n/cur/rec':>18}",
        "  " + "-" * 78,
    ]
    for bucket in ALL_BUCKETS:
        parts = [f"  {bucket:<10}"]
        for stage in ALL_STAGES:
            ds = by_bucket.get(bucket, {}).get(stage)
            if ds is None:
                parts.append(f"  {'—':>18}")
                continue
            warn = "⚠ " if ds.confidence == "low" else "  "
            cell = f"{warn}{ds.mean_actual_delta:+.2f} n={ds.n:<4} → {ds.recommended_adj:+.2f}"
            parts.append(f"  {cell:>18}")
        lines.append("".join(parts))
    lines.append("")
    lines.append("  Legend: mean delta (actual_next - source_bpr) | n | recommended constant")
    lines.append("  ⚠ = low confidence (n < 20); current constant retained")
    lines.append("")
    return "\n".join(lines)


# ── Constants writer ──────────────────────────────────────────────────────────

def write_stratified_constants(result: BT3Result, constants_path: str) -> None:
    """
    Append position-stratified development constants to projection/constants.py.

    Writes a clearly-labeled new section at the end of the file.
    Only call when --apply flag is passed to the management command.

    Args:
        result:          BT3Result from run_bt3().
        constants_path:  Absolute path to projection/constants.py.
    """
    by = result.by_bucket_by_stage

    def _cell(bucket: str, stage: str, off_or_def: str) -> str:
        ds = by.get(bucket, {}).get(stage)
        if ds is None:
            return "0.0  # no data"
        base = ds.recommended_adj if off_or_def == "off" else max(
            _CLAMP[stage][0],
            min(_CLAMP[stage][1], round(ds.mean_actual_delta * 0.5, 2))
        ) if ds.n >= MEDIUM_CONFIDENCE_N else (
            _CURRENT_DEF[stage]
        )
        conf_flag = "⚠ low conf — current constant" if ds.confidence == "low" else f"n={ds.n}, {ds.confidence}"
        return f"{base}  # {conf_flag}"

    lines = [
        "",
        "# ── Position-stratified development adjustments (Phase 1.2 — BT-3 validated) ──",
        f"# Source years: {result.source_years_used}, N observations: {result.n_observations}",
        "# Low-confidence cells (n < 20) retain the current flat constant value.",
        "# Set USE_STRATIFIED_DEV_ADJUSTMENTS = False to revert to flat constants.",
        "",
        "USE_STRATIFIED_DEV_ADJUSTMENTS: bool = True",
        "",
    ]

    for stage, label in [
        (STAGE_NEWCOMER,    "Newcomer"),
        (STAGE_SECOND_YEAR, "Second year"),
        (STAGE_SENIOR_PLUS, "Senior+"),
    ]:
        lines.append(f"# {label} development adjustments (offense)")
        for bucket in ALL_BUCKETS:
            ds = by.get(bucket, {}).get(stage)
            n_note = f"n={ds.n}, {ds.confidence}" if ds else "no data"
            rec = ds.recommended_adj if ds and ds.n >= MEDIUM_CONFIDENCE_N else _CURRENT_OFF[stage]
            warn = "  # ⚠ low conf — current flat constant" if (ds and ds.confidence == "low") else f"  # {n_note}"
            suffix = "G" if bucket == GUARD else bucket.upper()
            const_name = f"DEV_OFF_{stage.upper().replace('_', '_')}_{suffix}"
            # Normalize stage name for constant
            if stage == STAGE_NEWCOMER:
                const_name = f"DEV_OFF_NEWCOMER_{suffix}"
            elif stage == STAGE_SECOND_YEAR:
                const_name = f"DEV_OFF_SECOND_YEAR_{suffix}"
            elif stage == STAGE_SENIOR_PLUS:
                const_name = f"DEV_OFF_SENIOR_{suffix}"
            lines.append(f"{const_name}: float = {rec}{warn}")

        lines.append(f"# {label} development adjustments (defense)")
        for bucket in ALL_BUCKETS:
            ds = by.get(bucket, {}).get(stage)
            rec_def = _CURRENT_DEF[stage]
            if ds and ds.n >= MEDIUM_CONFIDENCE_N:
                lo, hi = _CLAMP[stage]
                rec_def = max(lo, min(hi, round(ds.mean_actual_delta * 0.5, 2)))
            warn = "  # ⚠ low conf — current flat constant" if (ds and ds.confidence == "low") else f"  # n={ds.n if ds else 0}"
            suffix = "G" if bucket == GUARD else bucket.upper()
            if stage == STAGE_NEWCOMER:
                const_name = f"DEV_DEF_NEWCOMER_{suffix}"
            elif stage == STAGE_SECOND_YEAR:
                const_name = f"DEV_DEF_SECOND_YEAR_{suffix}"
            elif stage == STAGE_SENIOR_PLUS:
                const_name = f"DEV_DEF_SENIOR_{suffix}"
            lines.append(f"{const_name}: float = {rec_def}{warn}")
        lines.append("")

    with open(constants_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[BT-3] Stratified development constants written to {constants_path}")
