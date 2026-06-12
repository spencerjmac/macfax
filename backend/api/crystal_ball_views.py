"""
Crystal Ball API View

Evaluates every D1 team (or tournament-only teams) against the 15-item
National Champion Checklist and returns results sorted by checklist score.

All computation is driven by TeamSeasonRatings (the live pipeline model)
plus TeamSeasonMetrics for shooting percentage fields.
"""

import numpy as np
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from ncaa.models import Season, TeamSeasonRatings, TeamSeasonMetrics
from .trapezoid_views import compute_trapezoid_boundaries, is_inside_trapezoid, trapezoid_margin
from .serializers import RankingsSerializer


# ---------------------------------------------------------------------------
# Season-context helpers
# ---------------------------------------------------------------------------

def _build_season_context(ratings_qs, metrics_map=None):
    """
    Pre-compute season-wide stats needed for the context-dependent checklist
    items (trapezoid, title-favorite delta, off/def rank, Z-score thresholds).

    Always built from ALL D1 teams regardless of any tournament filter so that
    rank thresholds stay stable when the user switches between "All" and
    "Tournament Teams Only".
    """
    ratings = list(ratings_qs)
    if not ratings:
        return {}

    metrics_map = metrics_map or {}

    tempo_arr = np.array([r.adj_tempo for r in ratings])
    em_arr    = np.array([r.adj_em    for r in ratings])

    trapezoid  = compute_trapezoid_boundaries(tempo_arr, em_arr)
    max_adj_em = float(np.max(em_arr))

    # Off rank: higher adj_o = rank 1
    off_sorted = sorted(ratings, key=lambda r: r.adj_o, reverse=True)
    off_ranks  = {r.team_id: idx + 1 for idx, r in enumerate(off_sorted)}

    # Def rank: lower adj_d = rank 1
    def_sorted = sorted(ratings, key=lambda r: r.adj_d)
    def_ranks  = {r.team_id: idx + 1 for idx, r in enumerate(def_sorted)}

    # AdjEM rank: higher = rank 1
    em_sorted  = sorted(ratings, key=lambda r: r.adj_em, reverse=True)
    em_ranks   = {r.team_id: idx + 1 for idx, r in enumerate(em_sorted)}

    # Compute means and standard deviations for dynamic thresholds
    efg_margins = np.array([r.adj_efg_margin for r in ratings if r.adj_efg_margin is not None])
    tov_edges = np.array([r.adj_tov_edge for r in ratings if r.adj_tov_edge is not None])
    reb_edges = np.array([r.adj_reb_edge for r in ratings if r.adj_reb_edge is not None])
    ftr_margins = np.array([r.adj_ftr_margin for r in ratings if r.adj_ftr_margin is not None])
    ffis = np.array([r.ffi_adj for r in ratings if r.ffi_adj is not None])
    adj_ems = np.array([r.adj_em for r in ratings if r.adj_em is not None])
    adj_os = np.array([r.adj_o for r in ratings if r.adj_o is not None])
    adj_ds = np.array([r.adj_d for r in ratings if r.adj_d is not None])
    win_pcts = np.array([r.wins / r.games_played for r in ratings if r.games_played])

    # Shooting percentages come from TeamSeasonMetrics, not TeamSeasonRatings
    fg3_pct_list = []
    ft_pct_list = []
    for r in ratings:
        m = metrics_map.get(r.team_id)
        if not m:
            continue
        if m.total_fg3a:
            fg3_pct_list.append(m.total_fg3m / m.total_fg3a)
        if m.total_fta:
            ft_pct_list.append(m.total_ftm / m.total_fta)
    fg3_pcts = np.array(fg3_pct_list)
    ft_pcts = np.array(ft_pct_list)

    stats = {
        "efg_mean": float(np.mean(efg_margins)) if len(efg_margins) else 0,
        "efg_std": float(np.std(efg_margins)) if len(efg_margins) else 1,
        "tov_mean": float(np.mean(tov_edges)) if len(tov_edges) else 0,
        "tov_std": float(np.std(tov_edges)) if len(tov_edges) else 1,
        "reb_mean": float(np.mean(reb_edges)) if len(reb_edges) else 0,
        "reb_std": float(np.std(reb_edges)) if len(reb_edges) else 1,
        "ftr_mean": float(np.mean(ftr_margins)) if len(ftr_margins) else 0,
        "ftr_std": float(np.std(ftr_margins)) if len(ftr_margins) else 1,
        "ffi_mean": float(np.mean(ffis)) if len(ffis) else 0,
        "ffi_std": float(np.std(ffis)) if len(ffis) else 1,
        "adjem_mean": float(np.mean(adj_ems)) if len(adj_ems) else 0,
        "adjem_std": float(np.std(adj_ems)) if len(adj_ems) else 1,
        "adjo_mean": float(np.mean(adj_os)) if len(adj_os) else 0,
        "adjo_std": float(np.std(adj_os)) if len(adj_os) else 1,
        "adjd_mean": float(np.mean(adj_ds)) if len(adj_ds) else 0,
        "adjd_std": float(np.std(adj_ds)) if len(adj_ds) else 1,
        "win_pct_mean": float(np.mean(win_pcts)) if len(win_pcts) else 0.5,
        "win_pct_std": float(np.std(win_pcts)) if len(win_pcts) else 0.1,
        "fg3_pct_mean": float(np.mean(fg3_pcts)) if len(fg3_pcts) else 0.33,
        "fg3_pct_std": float(np.std(fg3_pcts)) if len(fg3_pcts) else 0.03,
        "ft_pct_mean": float(np.mean(ft_pcts)) if len(ft_pcts) else 0.70,
        "ft_pct_std": float(np.std(ft_pcts)) if len(ft_pcts) else 0.03,
    }

    return {
        "trapezoid":   trapezoid,
        "max_adj_em":  max_adj_em,
        "off_ranks":   off_ranks,
        "def_ranks":   def_ranks,
        "em_ranks":    em_ranks,
        "stats":       stats,
    }


# ---------------------------------------------------------------------------
# Checklist – each item returns {"key", "label", "pass", "value", "threshold"}
# ---------------------------------------------------------------------------

def _item(key, label, passed, value, threshold, details=""):
    return {
        "key":       key,
        "label":     label,
        "pass":      passed,
        "value":     value,
        "threshold": threshold,
        "details":   details,
    }


def _check_trapezoid(r, ctx):
    trap = ctx.get("trapezoid")
    if trap is None:
        return _item("trapezoid", "Trapezoid of Excellence", False, "N/A",
                     "Inside trapezoid", "Trapezoid unavailable")
    inside = is_inside_trapezoid(r.adj_tempo, r.adj_em, trap)
    margin = trapezoid_margin(r.adj_tempo, r.adj_em, trap)
    margin_str = f"{margin:+.2f}" if margin is not None else "N/A"
    return _item("trapezoid", "Trapezoid of Excellence", inside,
                 "Inside" if inside else "Outside",
                 "Inside trapezoid",
                 f"Tempo {r.adj_tempo:.1f}, AdjEM {r.adj_em:.1f}, Margin {margin_str}")


def _check_balanced_dominance(r, ctx):
    stats = ctx.get("stats", {})
    # Z-scores from historical champions
    MIN_Z_ADJO = 1.66
    MAX_Z_ADJD = -1.24
    MIN_Z_ADJEM = 2.50 # High AdjEM threshold proxy for 30.0
    
    adjo_mean = stats.get("adjo_mean", 0)
    adjo_std = stats.get("adjo_std", 1)
    adjd_mean = stats.get("adjd_mean", 0)
    adjd_std = stats.get("adjd_std", 1)
    adjem_mean = stats.get("adjem_mean", 0)
    adjem_std = stats.get("adjem_std", 1)
    
    thresh_adjo = adjo_mean + (MIN_Z_ADJO * adjo_std)
    thresh_adjd = adjd_mean + (MAX_Z_ADJD * adjd_std)
    thresh_adjem = adjem_mean + (MIN_Z_ADJEM * adjem_std)
    
    adjo_z = (r.adj_o - adjo_mean) / adjo_std if r.adj_o else 0
    adjd_z = (r.adj_d - adjd_mean) / adjd_std if r.adj_d else 0
    adjem_z = (r.adj_em - adjem_mean) / adjem_std if r.adj_em else 0
    
    c1 = (adjo_z >= MIN_Z_ADJO) and (adjd_z <= MAX_Z_ADJD)
    c2 = (adjem_z >= MIN_Z_ADJEM)
    passed = c1 or c2
    return _item("balanced_dominance", "Balanced Dominance", passed,
                 f"O: {r.adj_o:.1f} / D: {r.adj_d:.1f}",
                 f"(O ≥ {thresh_adjo:.1f} & D ≤ {thresh_adjd:.1f}) or EM ≥ {thresh_adjem:.1f}",
                 f"AdjO {r.adj_o:.1f} (Threshold: {thresh_adjo:.1f}), AdjD {r.adj_d:.1f} (Threshold: {thresh_adjd:.1f}), AdjEM {r.adj_em:.1f} (Threshold: {thresh_adjem:.1f})")


def _check_title_favorite(r, ctx):
    rank = ctx.get("em_ranks", {}).get(r.team_id)
    if rank is None:
        return _item("title_favorite", "Title Favorite (AdjEM Top-22)", False,
                     "N/A", "Rank ≤ 22")
    passed = rank <= 22
    return _item("title_favorite", "Title Favorite (AdjEM Top-22)", passed,
                 f"#{rank}", "Rank ≤ 22",
                 f"AdjEM rank #{rank}")


def _check_win_pct(r, ctx):
    stats = ctx.get("stats", {})
    MIN_Z_WIN = 1.31
    
    games = r.games_played or 0
    pct = (r.wins / games) if games else 0.0
    
    win_mean = stats.get("win_pct_mean", 0.5)
    win_std = stats.get("win_pct_std", 0.1)
    win_z = (pct - win_mean) / win_std if win_std else 0
    
    threshold = win_mean + (MIN_Z_WIN * win_std)
    passed = win_z >= MIN_Z_WIN
    return _item("win_pct", "Win Percentage", passed,
                 f"{pct * 100:.1f}%", f"≥ {threshold * 100:.1f}% (Z ≥ {MIN_Z_WIN})",
                 f"{r.wins}-{r.losses} ({pct * 100:.1f}%) | Z-Score: {win_z:.2f}")


def _check_elite_efficiency(r, ctx):
    off_rank = ctx.get("off_ranks", {}).get(r.team_id)
    def_rank = ctx.get("def_ranks", {}).get(r.team_id)
    if off_rank is None or def_rank is None:
        return _item("elite_efficiency", "Elite Efficiency", False,
                     "N/A", "Off ≤ 16, Def ≤ 45")
    passed = off_rank <= 16 and def_rank <= 45
    return _item("elite_efficiency", "Elite Efficiency", passed,
                 f"Off: #{off_rank} / Def: #{def_rank}",
                 "Off Rank ≤ 16, Def Rank ≤ 45",
                 f"Offensive rank #{off_rank}, Defensive rank #{def_rank}")


def _check_three_point_pct(r, ctx):
    stats = ctx.get("stats", {})
    metrics = ctx.get("metrics_map", {}).get(r.team_id)
    MIN_Z_3P = -0.52
    
    fg3_mean = stats.get("fg3_pct_mean", 0.33)
    fg3_std = stats.get("fg3_pct_std", 0.03)
    threshold = fg3_mean + (MIN_Z_3P * fg3_std)
    
    fg3_pct = None
    if metrics and metrics.total_fg3a and metrics.total_fg3a > 0:
        fg3_pct = metrics.total_fg3m / metrics.total_fg3a
        
    if fg3_pct is None:
        return _item("three_point_pct", "3-Point %", False,
                     "N/A", f"≥ {threshold * 100:.1f}%", "3P% data unavailable")
                     
    fg3_z = (fg3_pct - fg3_mean) / fg3_std if fg3_std else 0
    passed = fg3_z >= MIN_Z_3P
    return _item("three_point_pct", "3-Point %", passed,
                 f"{fg3_pct * 100:.1f}%", f"≥ {threshold * 100:.1f}%",
                 f"3P%: {fg3_pct * 100:.1f}% (Z: {fg3_z:.2f})")


def _check_elite_adjem(r, ctx):
    stats = ctx.get("stats", {})
    MIN_Z_ADJEM = 1.76
    
    adjem_mean = stats.get("adjem_mean", 0)
    adjem_std = stats.get("adjem_std", 1)
    threshold = adjem_mean + (MIN_Z_ADJEM * adjem_std)
    
    if r.adj_em is None:
        return _item("elite_adjem", "Elite AdjEM", False,
                     "N/A", f"≥ {threshold:.1f}")
                     
    adjem_z = (r.adj_em - adjem_mean) / adjem_std if adjem_std else 0
    passed = adjem_z >= MIN_Z_ADJEM
    return _item("elite_adjem", "Elite AdjEM", passed,
                 f"Z: {adjem_z:.2f}", f"Z ≥ {MIN_Z_ADJEM}",
                 f"AdjEM: {r.adj_em:.1f} (Z: {adjem_z:.2f}), threshold: {threshold:.1f}")


def _check_ap_poll(r, ctx):
    rank = r.ap_poll_week6
    if rank is None:
        return _item("ap_poll_week6", "AP Poll Week 6", False,
                     "Unranked", "≤ 12", "Not in AP Poll Week 6")
    passed = rank <= 12
    return _item("ap_poll_week6", "AP Poll Week 6", passed,
                 f"#{rank}", "≤ 12",
                 f"AP Poll Week 6: #{rank}")


def _check_efg_margin(r, ctx):
    margin = r.adj_efg_margin
    stats = ctx.get("stats", {})
    
    # Z-scores based on historical champion minimums
    MIN_Z_EFG = 1.36  # 1.3629
    
    threshold = stats.get("efg_mean", 0) + (MIN_Z_EFG * stats.get("efg_std", 1))
    passed = margin >= threshold if margin is not None else False
    return _item("efg_margin", "eFG Margin", passed,
                 f"{margin:.2f}" if margin is not None else "N/A", f"≥ {threshold:.2f}",
                 f"Adjusted eFG margin: {margin:.2f}" if margin is not None else "Unavailable")


def _check_ftr_margin(r, ctx):
    margin = r.adj_ftr_margin
    stats = ctx.get("stats", {})
    
    MIN_Z_FTR = -0.58  # -0.5757
    
    threshold = stats.get("ftr_mean", 0) + (MIN_Z_FTR * stats.get("ftr_std", 1))
    passed = margin >= threshold if margin is not None else False
    return _item("ftr_margin", "FTR Margin", passed,
                 f"{margin:.2f}" if margin is not None else "N/A", f"≥ {threshold:.2f}",
                 f"Adjusted FTR margin: {margin:.2f}" if margin is not None else "Unavailable")


def _check_reb_edge(r, ctx):
    edge = r.adj_reb_edge
    stats = ctx.get("stats", {})
    
    MIN_Z_REB = 0.20  # 0.1987
    
    threshold = stats.get("reb_mean", 0) + (MIN_Z_REB * stats.get("reb_std", 1))
    passed = edge >= threshold if edge is not None else False
    return _item("rebounding_edge", "Rebounding Edge", passed,
                 f"{edge:.2f}" if edge is not None else "N/A", f"≥ {threshold:.2f}",
                 f"Adjusted rebounding edge: {edge:.2f}" if edge is not None else "Unavailable")


def _check_tov_edge(r, ctx):
    edge = r.adj_tov_edge
    stats = ctx.get("stats", {})
    
    MIN_Z_TOV = 0.12  # 0.1225
    
    threshold = stats.get("tov_mean", 0) + (MIN_Z_TOV * stats.get("tov_std", 1))
    passed = edge >= threshold if edge is not None else False
    return _item("turnover_edge", "Turnover Edge", passed,
                 f"{edge:.2f}" if edge is not None else "N/A", f"≥ {threshold:.2f}",
                 f"Adjusted turnover edge: {edge:.2f}" if edge is not None else "Unavailable")


def _check_ffi(r, ctx):
    ffi = r.ffi_adj
    stats = ctx.get("stats", {})
    
    MIN_Z_FFI = 2.01  # 2.0141
    
    threshold = stats.get("ffi_mean", 0) + (MIN_Z_FFI * stats.get("ffi_std", 1))
    if ffi is None:
        return _item("four_factor_index", "Four Factor Index", False,
                     "N/A", f"≥ {threshold:.1f}", "FFI unavailable")
    passed = ffi >= threshold
    return _item("four_factor_index", "Four Factor Index", passed,
                 f"{ffi:.1f}", f"≥ {threshold:.1f}",
                 f"Adjusted FFI: {ffi:.1f}")


def _check_wab(r, ctx):
    wab = r.wab
    games = r.games_played or 0

    # Short/anomalous seasons (e.g. 2021 COVID-truncated schedules) make a
    # fixed WAB > 5.0 bar nearly unreachable, so exempt them.
    if games < 27:
        return _item("wab", "WAB (Wins Above Bubble)", True,
                     f"{wab:.1f}" if wab is not None else "N/A",
                     "> 5 (or <27-game season exception)",
                     f"Short season ({games} games) - exempted, WAB={wab}")

    if wab is None:
        return _item("wab", "WAB (Wins Above Bubble)", False,
                     "N/A", "> 5", "WAB unavailable")
    passed = wab > 5.0
    return _item("wab", "WAB (Wins Above Bubble)", passed,
                 f"{wab:.1f}", "> 5",
                 f"WAB: {wab:.1f}")


def _check_ft_pct(r, ctx):
    stats = ctx.get("stats", {})
    metrics = ctx.get("metrics_map", {}).get(r.team_id)
    MIN_Z_FT = -0.50
    
    ft_mean = stats.get("ft_pct_mean", 0.70)
    ft_std = stats.get("ft_pct_std", 0.03)
    threshold = ft_mean + (MIN_Z_FT * ft_std)
    
    ft_pct = None
    if metrics and metrics.total_fta and metrics.total_fta > 0:
        ft_pct = metrics.total_ftm / metrics.total_fta
        
    if ft_pct is None:
        return _item("ft_pct", "Free Throw %", False,
                     "N/A", f"≥ {threshold * 100:.1f}%", "FT% data unavailable")
                     
    ft_z = (ft_pct - ft_mean) / ft_std if ft_std else 0
    passed = ft_z >= MIN_Z_FT
    return _item("ft_pct", "Free Throw %", passed,
                 f"{ft_pct * 100:.1f}%", f"≥ {threshold * 100:.1f}%",
                 f"FT%: {ft_pct * 100:.1f}% (Z: {ft_z:.2f})")


# Ordered list of check functions
CHECKS = [
    _check_trapezoid,
    _check_balanced_dominance,
    _check_title_favorite,
    _check_win_pct,
    _check_elite_efficiency,
    _check_three_point_pct,
    _check_elite_adjem,
    _check_ap_poll,
    _check_efg_margin,
    _check_ftr_margin,
    _check_reb_edge,
    _check_tov_edge,
    _check_ffi,
    _check_wab,
    _check_ft_pct,
]


def run_checklist(rating, ctx):
    items = [fn(rating, ctx) for fn in CHECKS]
    passed = sum(1 for i in items if i["pass"])
    return {
        "passedCount": passed,
        "totalCount":  len(items),
        "score":       round(passed / len(items) * 100, 1),
        "items":       items,
    }


# ---------------------------------------------------------------------------
# API View
# ---------------------------------------------------------------------------

class CrystalBallView(APIView):
    """
    GET /api/viz/crystal-ball/?season=2026&filter=all

    Query params:
      season  – year (default: current)
      filter  – "all" (default) | "tournament"
    """

    def get(self, request):
        season_year   = request.query_params.get("season")
        team_filter   = request.query_params.get("filter", "all").lower()

        # Resolve season
        if season_year:
            season = get_object_or_404(Season, year=season_year)
        else:
            season = Season.objects.filter(is_current=True).first()
            if not season:
                return Response(
                    {"error": "No current season found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # All D1 rated teams — used for stable season context
        all_qs = (
            TeamSeasonRatings.all_objects
            .filter(season=season, team__is_d1=True, games_played__gt=0, is_pre_tournament=True)
            .select_related("team")
        )

        # Build metrics lookup for shooting pct checks (needed by _build_season_context
        # for fg3_pct/ft_pct means+stds, and by individual checks below)
        metrics_qs = TeamSeasonMetrics.all_objects.filter(season=season, is_pre_tournament=True)
        metrics_map = {m.team_id: m for m in metrics_qs}

        ctx = _build_season_context(all_qs, metrics_map)
        ctx["metrics_map"] = metrics_map

        # Also attach conference lookup from serializer
        conf_serializer = RankingsSerializer()

        # Decide which teams to score
        if team_filter == "tournament":
            scored_qs = all_qs.filter(tournament_seed__isnull=False)
        else:
            scored_qs = all_qs

        # Compute checklist for each team
        results = []
        for r in scored_qs:
            checklist = run_checklist(r, ctx)
            conf = conf_serializer.get_conference(r)
            results.append({
                "team_name":        r.team.name,
                "team_slug":        r.team.slug,
                "team_logo":        r.team.logo_url,
                "conference":       conf,
                "record":           f"{r.wins}-{r.losses}",
                "rank":             ctx["em_ranks"].get(r.team_id),
                "adj_em":           round(r.adj_em, 1),
                "adj_o":            round(r.adj_o, 1),
                "adj_d":            round(r.adj_d, 1),
                "tournament_seed":  r.tournament_seed,
                "tournament_region": r.tournament_region,
                "tournament_finish": r.tournament_finish,
                "checklist":        checklist,
            })

        # Sort by checklist score descending, then AdjEM descending as tiebreak
        results.sort(key=lambda x: (-x["checklist"]["passedCount"], -x["adj_em"]))

        return Response({
            "season":       season.year,
            "season_display": season.display_name,
            "filter":       team_filter,
            "total_teams":  len(results),
            "teams":        results,
        })
