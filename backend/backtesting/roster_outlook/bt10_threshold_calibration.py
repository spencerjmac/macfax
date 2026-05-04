"""
bt10_threshold_calibration.py — BT-10: Role-bucket-relative archetype threshold
calibration (Sprint 4).

Collects player data from all valid backtest source years, computes per-bucket
and per-conference-group percentiles, and recommends replacement thresholds for:
  • RIM_PROTECTOR_BLK_THRESHOLD  → per-bucket Big p50
  • DISRUPTOR_STL_THRESHOLD      → per-bucket Guard/Wing p70
  • SPACER_FG3A_THRESHOLD        → per-bucket p60
  • WEAK_DEFENDER_DBPR_MAX       → per-conf-group p5 projected_dbpr (unfiltered pool)

Problems addressed:
  A. Rim protector under-detection: league-wide 0.70 blk threshold too high for Bigs.
  B. Weak defender over-detection for mid-majors: -1.0 dbpr fires for most of rotation.
  C. Spacer threshold position-blind: 3.5 fg3a misses Bigs who space well at lower volume.

Usage:
    from backtesting.roster_outlook.bt10_threshold_calibration import (
        collect_threshold_data, compute_bucket_percentiles, recommend_thresholds,
    )
    dataset   = collect_threshold_data()
    percs     = compute_bucket_percentiles(dataset)
    result    = recommend_thresholds(percs)

Or via management command:
    python manage.py run_bt10
    python manage.py run_bt10 --years 2023 2024 2025 --apply
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import Optional

from ncaa.analytics.player_value.fit.constants import (
    RIM_PROTECTOR_BLK_THRESHOLD,
    DISRUPTOR_STL_THRESHOLD,
    SPACER_FG3A_THRESHOLD,
    WEAK_DEFENDER_DBPR_MAX,
    TOP_ROTATION_THRESHOLD,
)
from ncaa.conf_utils import get_conf_detail

logger = logging.getLogger(__name__)

_BUCKETS     = ("G", "Wing", "Big")
_CONF_GROUPS = ("power", "high_mid", "mid_major")


# ── Data containers ────────────────────────────────────────────────────────────

@dataclass
class PlayerThresholdRow:
    """Per-player data point for threshold analysis."""
    player_id:       int
    role_bucket:     str    # "G", "Wing", "Big"
    conf_group:      str    # "power", "high_mid", "mid_major"
    blk_pg:          float
    stl_pg:          float
    ast_pg:          float
    reb_pg:          float
    fg3a_pg:         float
    projected_dbpr:  float
    projected_obpr:  float
    minutes_share_p2: float
    source_year:     int


@dataclass
class DbprRow:
    """Unfiltered per-player dbpr data point — no minutes threshold applied.

    Used for WEAK_DEFENDER threshold calibration only. Weak defenders by definition
    don't earn rotation minutes, so the minutes-filtered player pool produces a
    positively-biased p25 that incorrectly tags most rotation players.
    """
    conf_group:      str    # "power", "high_mid", "mid_major"
    projected_dbpr:  float
    source_year:     int


@dataclass
class ThresholdDataset:
    players:      list[PlayerThresholdRow]  # minutes-filtered (for blk/stl/fg3a thresholds)
    source_years: list[int]
    n_players:    int
    dbpr_rows:    list[DbprRow] = field(default_factory=list)  # unfiltered (for weak_defender calibration)


@dataclass
class BucketPercentiles:
    """Percentile breakdowns by role bucket and by conf_group (for dbpr)."""
    by_bucket:    dict[str, dict[str, float]]  # {bucket: {metric_pXX: val}}
    by_conf_group: dict[str, dict[str, float]] # {conf_group: {dbpr_pXX: val}}
    n_by_bucket:  dict[str, int]
    n_by_conf:    dict[str, int]


@dataclass
class ThresholdRec:
    """Single threshold recommendation."""
    threshold_name:       str
    current_value:        float
    recommended_value:    float
    target_bucket:        str    # "G", "Wing", "Big", "power", "high_mid", "mid_major", "all"
    target_percentile:    str    # e.g. "p50", "p70"
    n_players_in_bucket:  int
    confidence:           str    # "high" (n>=100), "medium" (n>=40), "low" (n<40)
    rationale:            str


@dataclass
class ThresholdRecommendations:
    recommendations: list[ThresholdRec]
    summary_table:   str


# ── Data collection ────────────────────────────────────────────────────────────

def collect_threshold_data(source_years: Optional[list[int]] = None) -> ThresholdDataset:
    """
    Collect per-player threshold data from all valid backtest source years.

    Includes only players with:
      - minutes_share_p2 >= TOP_ROTATION_THRESHOLD (0.075 = meaningful rotation)
      - projected_dbpr IS NOT NULL

    Uses PlayerSeasonProjection.role_bucket directly (already derived by Phase 2).
    Conference group derived from team slug via get_conf_detail().

    Args:
        source_years: Restrict to these source years. None → all available.

    Returns:
        ThresholdDataset with all qualifying player-season rows.
    """
    from ncaa.models import PlayerSeasonProjection, PlayerSeasonStats, Team
    from backtesting.roster_outlook.data_loader import available_source_years

    years = source_years or available_source_years()
    if not years:
        logger.warning("[BT-10] No valid source years found.")
        return ThresholdDataset(players=[], source_years=[], n_players=0)

    players: list[PlayerThresholdRow] = []
    dbpr_rows: list[DbprRow] = []
    years_used: list[int] = []

    for source_year in years:
        # Load qualifying projections for this source year (minutes-filtered)
        psp_rows = list(
            PlayerSeasonProjection.objects
            .filter(
                from_season__year=source_year,
                minutes_share_p2__gte=TOP_ROTATION_THRESHOLD,
                projected_dbpr__isnull=False,
                role_bucket__isnull=False,
            )
            .values(
                "player_id", "team_id", "role_bucket",
                "projected_obpr", "projected_dbpr", "minutes_share_p2",
            )
        )
        if not psp_rows:
            continue

        # Load team slugs for conf_group (start with filtered set's team_ids)
        team_ids = {r["team_id"] for r in psp_rows if r.get("team_id")}
        slug_map: dict[int, str] = dict(
            Team.objects.filter(id__in=team_ids).values_list("id", "slug")
        )

        # Load box stats for this source year
        all_pids = {r["player_id"] for r in psp_rows}
        stats_map: dict[int, dict] = {}
        for row in PlayerSeasonStats.objects.filter(
            player_id__in=all_pids, season__year=source_year
        ).values("player_id", "blk", "stl", "ast", "reb", "fg3a_pg"):
            pid = row["player_id"]
            if pid not in stats_map:
                stats_map[pid] = row

        years_used.append(source_year)

        for row in psp_rows:
            pid     = row["player_id"]
            slug    = slug_map.get(row["team_id"] or 0, "")
            stats   = stats_map.get(pid, {})
            bucket  = row["role_bucket"] or "Wing"
            if bucket not in _BUCKETS:
                continue

            players.append(PlayerThresholdRow(
                player_id=pid,
                role_bucket=bucket,
                conf_group=get_conf_detail(slug),
                blk_pg=float(stats.get("blk") or 0.0),
                stl_pg=float(stats.get("stl") or 0.0),
                ast_pg=float(stats.get("ast") or 0.0),
                reb_pg=float(stats.get("reb") or 0.0),
                fg3a_pg=float(stats.get("fg3a_pg") or 0.0),
                projected_dbpr=float(row["projected_dbpr"]),
                projected_obpr=float(row.get("projected_obpr") or 0.0),
                minutes_share_p2=float(row["minutes_share_p2"]),
                source_year=source_year,
            ))

        # Load ALL players for dbpr (no minutes filter) — weak defenders by definition
        # don't earn rotation minutes, so filtering them out makes p25 come out positive.
        all_dbpr = list(
            PlayerSeasonProjection.objects
            .filter(
                from_season__year=source_year,
                projected_dbpr__isnull=False,
                role_bucket__isnull=False,
            )
            .values("team_id", "projected_dbpr")
        )
        # Extend slug_map for any team_ids not already loaded
        extra_ids = {r["team_id"] for r in all_dbpr if r.get("team_id")} - set(slug_map)
        if extra_ids:
            slug_map.update(dict(Team.objects.filter(id__in=extra_ids).values_list("id", "slug")))
        for row in all_dbpr:
            slug = slug_map.get(row["team_id"] or 0, "")
            dbpr_rows.append(DbprRow(
                conf_group=get_conf_detail(slug),
                projected_dbpr=float(row["projected_dbpr"]),
                source_year=source_year,
            ))

    logger.info(
        "[BT-10] Collected %d rotation player-seasons and %d unfiltered dbpr rows across %d source years.",
        len(players), len(dbpr_rows), len(years_used),
    )
    return ThresholdDataset(
        players=players,
        source_years=years_used,
        n_players=len(players),
        dbpr_rows=dbpr_rows,
    )


# ── Percentile computation ─────────────────────────────────────────────────────

def compute_bucket_percentiles(dataset: ThresholdDataset) -> BucketPercentiles:
    """
    Compute per-bucket and per-conf-group metric percentiles.

    For projected_dbpr: lower values = worse defenders. p5 of projected_dbpr is the
    5th percentile (bottom 5%) — this is used for WEAK_DEFENDER threshold.
    p25 produces positive thresholds (too permissive); p5 ≈ -1.1, matching the
    semantics of the legacy WEAK_DEFENDER_DBPR_MAX = -1.0.

    Per-bucket metrics: blk_pg, stl_pg, ast_pg, reb_pg, fg3a_pg.
    Per-conf-group metric: projected_dbpr (for weak-defender calibration).

    Args:
        dataset: Output from collect_threshold_data().

    Returns:
        BucketPercentiles with p5/p10/p25/p40/p50/p60/p70/p75/p80/p85/p90 per metric.
    """
    _PCT_LEVELS = [5, 10, 25, 40, 50, 60, 70, 75, 80, 85, 90]
    _METRICS    = ["blk_pg", "stl_pg", "ast_pg", "reb_pg", "fg3a_pg"]

    def _quantile(vals: list[float], pct: int) -> float:
        if len(vals) < 4:
            return 0.0
        # statistics.quantiles returns n-1 cut points; use n=100 for percentile precision
        q = statistics.quantiles(vals, n=100)
        return q[pct - 1]  # 0-indexed: p1 → q[0], p50 → q[49]

    by_bucket: dict[str, dict[str, float]] = {}
    n_by_bucket: dict[str, int] = {}

    for bucket in _BUCKETS:
        subset = [p for p in dataset.players if p.role_bucket == bucket]
        n_by_bucket[bucket] = len(subset)
        percs: dict[str, float] = {}
        for metric in _METRICS:
            vals = [getattr(p, metric) for p in subset]
            for pct in _PCT_LEVELS:
                percs[f"{metric}_p{pct}"] = round(_quantile(vals, pct), 3)
        by_bucket[bucket] = percs

    by_conf: dict[str, dict[str, float]] = {}
    n_by_conf: dict[str, int] = {}
    for cg in _CONF_GROUPS:
        # Use UNFILTERED dbpr_rows so weak defenders who don't earn rotation minutes
        # are included. Falls back to dataset.players if dbpr_rows is empty (legacy callers).
        if dataset.dbpr_rows:
            subset_dbpr = [r.projected_dbpr for r in dataset.dbpr_rows if r.conf_group == cg]
            n_by_conf[cg] = len(subset_dbpr)
        else:
            subset_dbpr = [p.projected_dbpr for p in dataset.players if p.conf_group == cg]
            n_by_conf[cg] = len(subset_dbpr)
        cg_percs: dict[str, float] = {}
        for pct in _PCT_LEVELS:
            cg_percs[f"projected_dbpr_p{pct}"] = round(_quantile(subset_dbpr, pct), 3)
        by_conf[cg] = cg_percs

    return BucketPercentiles(
        by_bucket=by_bucket,
        by_conf_group=by_conf,
        n_by_bucket=n_by_bucket,
        n_by_conf=n_by_conf,
    )


# ── Recommendation engine ─────────────────────────────────────────────────────

def _confidence(n: int) -> str:
    return "high" if n >= 100 else "medium" if n >= 40 else "low"


def recommend_thresholds(percentiles: BucketPercentiles) -> ThresholdRecommendations:
    """
    Derive recommended per-bucket / per-conf-group threshold values.

    Rules:
      RIM_PROTECTOR_BLK_BIG  → p50 of Big blk_pg (top half of Bigs → rim protector)
      DISRUPTOR_STL_G        → p70 of Guard stl_pg
      DISRUPTOR_STL_WING     → p70 of Wing stl_pg
      SPACER_FG3A_{bucket}   → p60 per bucket
      WEAK_DEFENDER_DBPR_{conf} → p5 of conf_group projected_dbpr (unfiltered pool, bottom 5%)

    Guard/Wing RIM_PROTECTOR and Big DISRUPTOR keep legacy values (rarely applies).
    """
    recs: list[ThresholdRec] = []
    bb = percentiles.by_bucket
    bc = percentiles.by_conf_group
    nb = percentiles.n_by_bucket
    nc = percentiles.n_by_conf

    # ── Rim protector ──────────────────────────────────────────────────────
    big_blk_p50 = bb.get("Big", {}).get("blk_pg_p50", RIM_PROTECTOR_BLK_THRESHOLD)
    recs.append(ThresholdRec(
        threshold_name="RIM_PROTECTOR_BLK_BIG",
        current_value=RIM_PROTECTOR_BLK_THRESHOLD,
        recommended_value=round(big_blk_p50, 2),
        target_bucket="Big",
        target_percentile="p50",
        n_players_in_bucket=nb.get("Big", 0),
        confidence=_confidence(nb.get("Big", 0)),
        rationale=(
            "Rim protector should identify the top half of interior defenders. "
            "Current 0.70 league-wide threshold captures only ~top 35% of Bigs. "
            "Big p50 blk/game correctly targets the median interior defender."
        ),
    ))
    recs.append(ThresholdRec(
        threshold_name="RIM_PROTECTOR_BLK_WING",
        current_value=RIM_PROTECTOR_BLK_THRESHOLD,
        recommended_value=0.70,   # keep legacy for wings
        target_bucket="Wing",
        target_percentile="p70",
        n_players_in_bucket=nb.get("Wing", 0),
        confidence=_confidence(nb.get("Wing", 0)),
        rationale="Wings with 0.70+ blk/game are genuinely rim-protecting; keep legacy.",
    ))
    recs.append(ThresholdRec(
        threshold_name="RIM_PROTECTOR_BLK_G",
        current_value=RIM_PROTECTOR_BLK_THRESHOLD,
        recommended_value=0.70,   # keep legacy for guards
        target_bucket="G",
        target_percentile="league-wide",
        n_players_in_bucket=nb.get("G", 0),
        confidence=_confidence(nb.get("G", 0)),
        rationale="Guards rarely qualify; keep legacy threshold for correctness.",
    ))

    # ── Disruptor ──────────────────────────────────────────────────────────
    for bucket, key in [("G", "G"), ("Wing", "WING")]:
        stl_p70 = bb.get(bucket, {}).get("stl_pg_p70", DISRUPTOR_STL_THRESHOLD)
        recs.append(ThresholdRec(
            threshold_name=f"DISRUPTOR_STL_{key}",
            current_value=DISRUPTOR_STL_THRESHOLD,
            recommended_value=round(stl_p70, 2),
            target_bucket=bucket,
            target_percentile="p70",
            n_players_in_bucket=nb.get(bucket, 0),
            confidence=_confidence(nb.get(bucket, 0)),
            rationale=(
                f"Top 30% of {bucket}s by steals captures meaningful defensive disruptors. "
                f"League-wide 1.00 is too high for wings and slightly off for guards."
            ),
        ))
    recs.append(ThresholdRec(
        threshold_name="DISRUPTOR_STL_BIG",
        current_value=DISRUPTOR_STL_THRESHOLD,
        recommended_value=1.00,   # keep league-wide for Bigs
        target_bucket="Big",
        target_percentile="league-wide",
        n_players_in_bucket=nb.get("Big", 0),
        confidence=_confidence(nb.get("Big", 0)),
        rationale="Disruptor is primarily a guard/wing concept; keep league-wide for Bigs.",
    ))

    # ── Spacer ─────────────────────────────────────────────────────────────
    for bucket, key in [("G", "G"), ("Wing", "WING"), ("Big", "BIG")]:
        fg3a_p60 = bb.get(bucket, {}).get("fg3a_pg_p60", SPACER_FG3A_THRESHOLD)
        recs.append(ThresholdRec(
            threshold_name=f"SPACER_FG3A_{key}",
            current_value=SPACER_FG3A_THRESHOLD,
            recommended_value=round(fg3a_p60, 2),
            target_bucket=bucket,
            target_percentile="p60",
            n_players_in_bucket=nb.get(bucket, 0),
            confidence=_confidence(nb.get(bucket, 0)),
            rationale=(
                f"Top 40% of {bucket}s by 3PA signals meaningful spacing threat. "
                f"Current 3.5 league-wide threshold completely misses Bigs who space "
                f"effectively at lower attempt rates."
            ),
        ))

    # ── Weak defender ──────────────────────────────────────────────────────
    # Use p5 (bottom 5%), NOT p25. The projected_dbpr distribution is right-skewed
    # with most values positive; p25 comes out positive and tags too many players.
    # p5 ≈ -1.1 to -1.2, matching the semantics of the legacy -1.0 threshold.
    for cg, key in [("power", "POWER"), ("high_mid", "HIGH_MID"), ("mid_major", "MID_MAJOR")]:
        dbpr_p5 = bc.get(cg, {}).get("projected_dbpr_p5", WEAK_DEFENDER_DBPR_MAX)
        recs.append(ThresholdRec(
            threshold_name=f"WEAK_DEFENDER_DBPR_{key}",
            current_value=WEAK_DEFENDER_DBPR_MAX,
            recommended_value=round(dbpr_p5, 2),
            target_bucket=cg,
            target_percentile="p5",
            n_players_in_bucket=nc.get(cg, 0),
            confidence=_confidence(nc.get(cg, 0)),
            rationale=(
                f"Bottom 5% of {cg} defenders are 'truly weak' (p5 ≈ -1.1). "
                f"p25 produces positive thresholds and over-fires. p5 matches the "
                f"legacy -1.0 threshold semantics while being conf-group calibrated."
            ),
        ))

    table = _build_table(recs)
    return ThresholdRecommendations(recommendations=recs, summary_table=table)


def _build_table(recs: list[ThresholdRec]) -> str:
    lines = [
        "",
        "=" * 90,
        "BT-10  Role-Bucket-Relative Archetype Threshold Recommendations",
        "=" * 90,
        f"  {'Threshold':<35}  {'Bucket':<10}  {'Current':>8}  {'Rec':>8}  {'Δ':>7}  {'N':>6}  {'Conf':<8}",
        "  " + "-" * 84,
    ]
    for r in recs:
        delta = r.recommended_value - r.current_value
        lines.append(
            f"  {r.threshold_name:<35}  {r.target_bucket:<10}  "
            f"{r.current_value:>8.3f}  {r.recommended_value:>8.3f}  "
            f"{delta:>+7.3f}  {r.n_players_in_bucket:>6}  {r.confidence:<8}"
        )
    lines.append("")
    return "\n".join(lines)


# ── Constants writer ──────────────────────────────────────────────────────────

def write_bt10_constants(result: ThresholdRecommendations, constants_path: str) -> None:
    """
    Append role-bucket-relative threshold constants to fit/constants.py.

    Only called when management command is run with --apply.
    Prints each value written and warns on low-confidence recommendations.
    """
    recs_by_name = {r.threshold_name: r for r in result.recommendations}

    def _val(name: str, fallback: float) -> float:
        r = recs_by_name.get(name)
        return r.recommended_value if r else fallback

    from datetime import date
    today = date.today().isoformat()

    lines = [
        "",
        f"# ── Role-bucket-relative thresholds (Sprint 4 — BT-10 validated, {today}) ──────",
        "# These REPLACE the single-value thresholds above when USE_BUCKET_THRESHOLDS=True.",
        "# Legacy single-value thresholds are retained for backward compatibility.",
        "# Run `python manage.py run_bt10` to regenerate these values from fresh data.",
        "",
        "USE_BUCKET_THRESHOLDS: bool = True",
        "",
        "# Rim protector — Big p50 blk/game; Guards/Wings keep legacy 0.70",
    ]

    for name, fallback, comment in [
        ("RIM_PROTECTOR_BLK_G",    0.70, "# Guards: keep legacy (rim protection rarely applies)"),
        ("RIM_PROTECTOR_BLK_WING", 0.70, "# Wings: keep legacy"),
        ("RIM_PROTECTOR_BLK_BIG",  RIM_PROTECTOR_BLK_THRESHOLD, "# Bigs: p50 blk/game"),
    ]:
        r = recs_by_name.get(name)
        n_note = f"n={r.n_players_in_bucket}, {r.confidence}" if r else "legacy"
        v = _val(name, fallback)
        lines.append(f"{name}: float = {v}  {comment}  [{n_note}]")

    lines += ["", "# Disruptor — per-bucket p70 stl/game"]
    for name, fallback, comment in [
        ("DISRUPTOR_STL_G",    DISRUPTOR_STL_THRESHOLD, "# Guard p70"),
        ("DISRUPTOR_STL_WING", DISRUPTOR_STL_THRESHOLD, "# Wing p70"),
        ("DISRUPTOR_STL_BIG",  1.00, "# Keep league-wide for Bigs"),
    ]:
        r = recs_by_name.get(name)
        n_note = f"n={r.n_players_in_bucket}, {r.confidence}" if r else "legacy"
        v = _val(name, fallback)
        lines.append(f"{name}: float = {v}  {comment}  [{n_note}]")

    lines += ["", "# Spacer — per-bucket p60 fg3a/game"]
    for name, fallback in [
        ("SPACER_FG3A_G",    SPACER_FG3A_THRESHOLD),
        ("SPACER_FG3A_WING", SPACER_FG3A_THRESHOLD),
        ("SPACER_FG3A_BIG",  SPACER_FG3A_THRESHOLD),
    ]:
        r = recs_by_name.get(name)
        n_note = f"n={r.n_players_in_bucket}, {r.confidence}" if r else "legacy"
        v = _val(name, fallback)
        lines.append(f"{name}: float = {v}  # {name.split('_')[-1]} p60 fg3a/game  [{n_note}]")

    lines += ["", "# Weak defender — per-conf-group p25 projected_dbpr (bottom 25%)"]
    for name, fallback in [
        ("WEAK_DEFENDER_DBPR_POWER",    WEAK_DEFENDER_DBPR_MAX),
        ("WEAK_DEFENDER_DBPR_HIGH_MID", WEAK_DEFENDER_DBPR_MAX),
        ("WEAK_DEFENDER_DBPR_MID_MAJOR", WEAK_DEFENDER_DBPR_MAX),
    ]:
        r = recs_by_name.get(name)
        n_note = f"n={r.n_players_in_bucket}, {r.confidence}" if r else "legacy"
        v = _val(name, fallback)
        lines.append(f"{name}: float = {v}  # [{n_note}]")
    lines.append("WEAK_DEFENDER_DBPR_DEFAULT: float = -1.0  # fallback when conf_group unknown")
    lines.append("")

    with open(constants_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[BT-10] Constants written to {constants_path}")
    for r in result.recommendations:
        if r.confidence == "low":
            print(f"  ⚠ LOW CONFIDENCE: {r.threshold_name} (n={r.n_players_in_bucket})")
