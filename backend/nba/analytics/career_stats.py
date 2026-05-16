"""
career_stats.py — Career-stabilized stat estimates for NBA box BPR.

Rate stat formula (Phase 1):
  stabilized = (career_avg * career_poss + current * current_poss)
               / (career_poss + current_poss)

Per-100 counting stat formula (Phase 2):
  effective_career_poss = career_poss * ROLE_DISCOUNT   (0.5x)
  stabilized = (career_avg * effective_career_poss + current * current_poss)
               / (effective_career_poss + current_poss)

  Lower career weight for counting stats because role changes are real
  (a player in reduced minutes legitimately has lower pts100), while
  rate stats are more stable across role changes.

Traded players (multiple team rows in one season) are deduplicated:
  - on_court_poss: MAX (duplicated across rows — do NOT sum)
  - rate stats: GP-weighted average
  - counting totals: sum(stat_pg * gp) across all team rows
    → correct denominator for per-100 across the full season
"""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# ── Tiers ──────────────────────────────────────────────────────────────────────

TIER1_STATS = [
    "ts_pct", "efg_pct", "fg3_pct", "ft_pct",
    "ast_pct", "stl_pct", "blk_pct", "oreb_pct",
]
TIER2_STATS = ["usg_pct", "tov_pct", "dreb_pct"]
ALL_STABILIZED = TIER1_STATS + TIER2_STATS

ROLE_DISCOUNT = 0.5   # career weight multiplier for per-100 counting stats

PER100_STATS = [
    "pts100", "ast100", "tov100", "oreb100",
    "fga100", "fg3a100", "fta100",
    "stl100", "blk100", "dreb100",
]

# Maps raw DB field → season total key stored in consolidated dict
# total = stat_pg * gp (sum across team rows for traded players)
PER100_RAW_TO_TOTAL: dict[str, str] = {
    "pts":    "pts_total",
    "ast":    "ast_total",
    "stl":    "stl_total",
    "blk":    "blk_total",
    "tov":    "tov_total",
    "oreb_pg": "oreb_total",
    "dreb_pg": "dreb_total",
    "fga_pg":  "fga_total",
    "fg3a_pg": "fg3a_total",
    "fta_pg":  "fta_total",
}

# Maps per-100 key → total key (used when reading current season per-100)
PER100_STAT_TO_TOTAL: dict[str, str] = {
    "pts100":  "pts_total",
    "ast100":  "ast_total",
    "tov100":  "tov_total",
    "oreb100": "oreb_total",
    "fga100":  "fga_total",
    "fg3a100": "fg3a_total",
    "fta100":  "fta_total",
    "stl100":  "stl_total",
    "blk100":  "blk_total",
    "dreb100": "dreb_total",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def stabilize_stat(
    career_avg: float | None,
    career_poss: float,
    current_val: float | None,
    current_poss: float,
    default: float = 0.0,
) -> float:
    """Posterior estimate weighted by possession volume."""
    if current_val is None:
        return default
    if career_avg is None or career_poss <= 0:
        return current_val   # rookie — use current season only
    total = career_poss + current_poss
    if total <= 0:
        return default
    return (career_avg * career_poss + current_val * current_poss) / total


def _consolidate_traded_rows(rows: list[dict]) -> dict:
    """
    Merge multiple per-team rows for one player-season into a single dict.

    poss: duplicated across team rows → MAX not SUM.
    Rate stats: GP-weighted average.
    Counting totals: sum(stat_pg * gp) — correct numerator for per-100.
    """
    gp_total  = sum(r["gp"] or 0 for r in rows)
    min_total = sum((r["mpg"] or 0.0) * (r["gp"] or 0) for r in rows)
    poss      = max((r["on_court_poss"] or 0.0) for r in rows)

    result = dict(rows[0])
    result["gp"]            = gp_total
    result["mpg"]           = min_total / gp_total if gp_total > 0 else 0.0
    result["on_court_poss"] = poss

    # Rate stats: GP-weighted average across team rows
    for stat in ALL_STABILIZED:
        vals = [
            (r[stat], r["gp"] or 0)
            for r in rows
            if r.get(stat) is not None
        ]
        if vals:
            total_gp = sum(v[1] for v in vals)
            result[stat] = sum(v[0] * v[1] for v in vals) / total_gp if total_gp > 0 else None
        else:
            result[stat] = None

    # Counting totals: sum(stat_pg * gp) — whole-season production
    for raw_field, total_field in PER100_RAW_TO_TOTAL.items():
        result[total_field] = sum(
            (r.get(raw_field) or 0.0) * (r.get("gp") or 0) for r in rows
        )

    return result


# ── Main API ───────────────────────────────────────────────────────────────────

def build_career_stats_map(
    target_season_year: int,
    min_season_year: int = 2016,
) -> dict[int, dict[str, float]]:
    """
    Build career-stabilized stats for all players with DB data.

    Returns: {nba_player_pk: {stat_name: stabilized_value}}

    Includes ALL_STABILIZED (rate stats, full career weight) and
    PER100_STATS (counting stats, 0.5x role-discounted career weight).
    Tier 3 stats (role/context) should be read directly from current season.
    """
    from nba.models import NBAPlayerSeasonStats

    all_rows = list(
        NBAPlayerSeasonStats.objects.filter(
            season__year__gte=min_season_year,
            season__year__lte=target_season_year,
            season_type="regular",
        ).values(
            "player_id",          # Django FK = NBAPlayer.pk
            "season__year",
            "gp", "mpg", "on_court_poss",
            # Rate stats (Tier 1 + 2)
            "ts_pct", "efg_pct", "fg3_pct", "ft_pct",
            "ast_pct", "stl_pct", "blk_pct", "oreb_pct",
            "usg_pct", "tov_pct", "dreb_pct",
            # Raw counting fields for per-100 computation (Phase 2)
            "pts", "ast", "stl", "blk", "tov",
            "oreb_pg", "dreb_pg", "fga_pg", "fg3a_pg", "fta_pg",
        )
    )

    # Group by (player_pk, season_year)
    grouped: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in all_rows:
        pid  = row["player_id"]
        year = row["season__year"]
        if pid:
            grouped[(pid, year)].append(row)

    # Consolidate traded players → one dict per player-season
    consolidated: dict[tuple[int, int], dict] = {}
    for (pid, year), rows in grouped.items():
        consolidated[(pid, year)] = _consolidate_traded_rows(rows)

    # Separate historical vs current per player
    player_hist: dict[int, list[dict]] = defaultdict(list)
    player_curr: dict[int, dict]       = {}

    for (pid, year), row in consolidated.items():
        if year < target_season_year:
            player_hist[pid].append(row)
        elif year == target_season_year:
            player_curr[pid] = row

    # Build career map for players with current season data
    career_map: dict[int, dict[str, float]] = {}

    for pid, curr in player_curr.items():
        hist_rows   = player_hist.get(pid, [])
        current_poss = curr.get("on_court_poss") or 0.0

        # ── Rate stat career averages (full weight) ───────────────────────────
        career_poss: float = 0.0
        stat_num: dict[str, float] = {s: 0.0 for s in ALL_STABILIZED}
        stat_den: dict[str, float] = {s: 0.0 for s in ALL_STABILIZED}

        # ── Per-100 career averages (role-discounted) ─────────────────────────
        per100_num: dict[str, float] = {s: 0.0 for s in PER100_STATS}
        per100_den: dict[str, float] = {s: 0.0 for s in PER100_STATS}

        for h in hist_rows:
            h_poss = h.get("on_court_poss") or 0.0
            if h_poss <= 0:
                continue
            career_poss += h_poss

            # Rate stats
            for stat in ALL_STABILIZED:
                val = h.get(stat)
                if val is not None:
                    stat_num[stat] += val * h_poss
                    stat_den[stat] += h_poss

            # Per-100: season total / poss * 100, weighted by poss
            season_per100 = {
                "pts100":  (h.get("pts_total")  or 0.0) / h_poss * 100,
                "ast100":  (h.get("ast_total")  or 0.0) / h_poss * 100,
                "tov100":  (h.get("tov_total")  or 0.0) / h_poss * 100,
                "oreb100": (h.get("oreb_total") or 0.0) / h_poss * 100,
                "fga100":  (h.get("fga_total")  or 0.0) / h_poss * 100,
                "fg3a100": (h.get("fg3a_total") or 0.0) / h_poss * 100,
                "fta100":  (h.get("fta_total")  or 0.0) / h_poss * 100,
                "stl100":  (h.get("stl_total")  or 0.0) / h_poss * 100,
                "blk100":  (h.get("blk_total")  or 0.0) / h_poss * 100,
                "dreb100": (h.get("dreb_total") or 0.0) / h_poss * 100,
            }
            for stat in PER100_STATS:
                per100_num[stat] += season_per100[stat] * h_poss
                per100_den[stat] += h_poss

        # Career averages
        career_avgs: dict[str, float | None] = {
            s: stat_num[s] / stat_den[s] if stat_den[s] > 0 else None
            for s in ALL_STABILIZED
        }
        career_per100_avgs: dict[str, float | None] = {
            s: per100_num[s] / per100_den[s] if per100_den[s] > 0 else None
            for s in PER100_STATS
        }

        stabilized: dict[str, float] = {}

        # Rate stats: full career weight
        for stat in ALL_STABILIZED:
            stabilized[stat] = stabilize_stat(
                career_avg=career_avgs[stat],
                career_poss=career_poss,
                current_val=curr.get(stat),
                current_poss=current_poss,
            )

        # Per-100 counting stats: 0.5x role-discounted career weight
        effective_career_poss = career_poss * ROLE_DISCOUNT
        for stat in PER100_STATS:
            total_field = PER100_STAT_TO_TOTAL[stat]
            curr_total  = curr.get(total_field) or 0.0
            curr_val    = curr_total / current_poss * 100 if current_poss > 0 else None
            stabilized[stat] = stabilize_stat(
                career_avg=career_per100_avgs[stat],
                career_poss=effective_career_poss,
                current_val=curr_val,
                current_poss=current_poss,
            )

        career_map[pid] = stabilized

    # ── Diagnostics ───────────────────────────────────────────────────────────
    n_rookie = sum(1 for p in player_curr if not player_hist.get(p))
    n_hist   = [len(player_hist.get(p, [])) for p in player_curr]
    n_1_2    = sum(1 for h in n_hist if 1 <= h <= 2)
    n_3_5    = sum(1 for h in n_hist if 3 <= h <= 5)
    n_6plus  = sum(1 for h in n_hist if h >= 6)

    logger.info(
        "Career stats map built: %d players  |  rookies=%d  1-2yr=%d  3-5yr=%d  6+yr=%d",
        len(career_map), n_rookie, n_1_2, n_3_5, n_6plus,
    )

    _print_diagnostics(career_map, player_curr, player_hist)

    return career_map


def _print_diagnostics(
    career_map: dict,
    player_curr: dict,
    player_hist: dict,
) -> None:
    """Print stabilization details for a handful of named players."""
    from nba.models import NBAPlayer

    spotlight_names = ["Nikola Jokic", "LeBron James", "Luka Doncic", "Nikola Jokić", "Luka Dončić"]
    name_to_pk: dict[str, int] = {}
    for p in NBAPlayer.objects.filter(name__in=spotlight_names).values("pk", "name"):
        name_to_pk[p["name"]] = p["pk"]

    second_yr_pk = next(
        (pk for pk in player_curr if len(player_hist.get(pk, [])) == 1), None
    )
    if second_yr_pk:
        try:
            p2 = NBAPlayer.objects.get(pk=second_yr_pk)
            name_to_pk[p2.name] = second_yr_pk
        except Exception:
            pass

    logger.info("  %-22s %-10s %8s %8s %11s %9s", "Player", "Stat", "Career", "Current", "Stabilized", "Car_poss")
    logger.info("  " + "-" * 72)

    for name, pk in name_to_pk.items():
        pid = pk
        if pid not in career_map or pid not in player_curr:
            continue
        curr      = player_curr[pid]
        hist_rows = player_hist.get(pid, [])
        car_poss  = sum((h.get("on_court_poss") or 0.0) for h in hist_rows)

        show_stats = ["ts_pct", "pts100"] if "Jokic" in name or "Jokić" in name else ["ts_pct", "usg_pct"]
        for stat in show_stats:
            is_per100 = stat in PER100_STATS
            if is_per100:
                total_field = PER100_STAT_TO_TOTAL[stat]
                curr_poss   = curr.get("on_court_poss") or 0.0
                cur_val     = (curr.get(total_field) or 0.0) / curr_poss * 100 if curr_poss > 0 else None
                # Career avg from accumulator
                career_num = sum(
                    (h.get(total_field) or 0.0) / (h.get("on_court_poss") or 1.0) * 100
                    * (h.get("on_court_poss") or 0.0)
                    for h in hist_rows if (h.get("on_court_poss") or 0.0) > 0
                )
                career_den = sum((h.get("on_court_poss") or 0.0) for h in hist_rows if (h.get("on_court_poss") or 0.0) > 0)
                car_avg = career_num / career_den if career_den > 0 else None
            else:
                cur_val = curr.get(stat)
                career_num = sum(
                    (h.get(stat) or 0.0) * (h.get("on_court_poss") or 0.0)
                    for h in hist_rows if h.get(stat) is not None
                )
                career_den = sum(
                    (h.get("on_court_poss") or 0.0)
                    for h in hist_rows if h.get(stat) is not None
                )
                car_avg = career_num / career_den if career_den > 0 else None

            stab = career_map[pid].get(stat, 0.0)
            logger.info(
                "  %-22s %-10s %8s %8s %11.3f %9.0f",
                name, stat,
                f"{car_avg:.3f}" if car_avg is not None else "rookie",
                f"{cur_val:.3f}" if cur_val is not None else "null",
                stab, car_poss,
            )
