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
from .trapezoid_views import compute_trapezoid_boundaries, is_inside_trapezoid
from .serializers import RankingsSerializer


# ---------------------------------------------------------------------------
# Season-context helpers
# ---------------------------------------------------------------------------

def _build_season_context(ratings_qs):
    """
    Pre-compute season-wide stats needed for the context-dependent checklist
    items (trapezoid, title-favorite delta, off/def rank).

    Always built from ALL D1 teams regardless of any tournament filter so that
    rank thresholds stay stable when the user switches between "All" and
    "Tournament Teams Only".
    """
    ratings = list(ratings_qs)
    if not ratings:
        return {}

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
    return _item("trapezoid", "Trapezoid of Excellence", inside,
                 "Inside" if inside else "Outside",
                 "Inside trapezoid",
                 f"Tempo {r.adj_tempo:.1f}, AdjEM {r.adj_em:.1f}")


def _check_kenpom_contender(r, ctx):
    c1 = r.adj_o > 113.8 and r.adj_d < 95.0
    c2 = r.adj_em > 30.0
    passed = c1 or c2
    return _item("kenpom_contender", "KenPom Contender", passed,
                 f"O {r.adj_o:.1f} / D {r.adj_d:.1f}",
                 "(O > 113.8 & D < 95.0) or EM > 30.0",
                 f"AdjO {r.adj_o:.1f}, AdjD {r.adj_d:.1f}, AdjEM {r.adj_em:.1f}")


def _check_title_favorite(r, ctx):
    max_em = ctx.get("max_adj_em")
    if max_em is None:
        return _item("title_favorite", "Title Favorite (AdjEM)", False,
                     "N/A", "Within 6.0 of max")
    threshold = max_em - 6.0
    passed = r.adj_em >= threshold
    return _item("title_favorite", "Title Favorite (AdjEM)", passed,
                 f"{r.adj_em:.1f}",
                 f"≥ {threshold:.1f} (max {max_em:.1f})",
                 f"AdjEM {r.adj_em:.1f}, needs ≥ {threshold:.1f}")


def _check_win_pct(r, ctx):
    games = r.games_played or 0
    pct   = (r.wins / games) if games else 0.0
    passed = pct > 0.74
    return _item("win_pct", "Win Percentage", passed,
                 f"{pct * 100:.1f}%", "> 74%",
                 f"{r.wins}-{r.losses} ({pct * 100:.1f}%)")


def _check_elite_ranks(r, ctx):
    off_rank = ctx.get("off_ranks", {}).get(r.team_id)
    def_rank = ctx.get("def_ranks", {}).get(r.team_id)
    if off_rank is None or def_rank is None:
        return _item("elite_ranks", "Elite Off/Def Ranks", False,
                     "N/A", "Off ≤ 21, Def ≤ 37")
    passed = off_rank <= 21 and def_rank <= 37
    return _item("elite_ranks", "Elite Off/Def Ranks", passed,
                 f"Off #{off_rank} / Def #{def_rank}",
                 "Off ≤ 21, Def ≤ 37",
                 f"Offensive rank #{off_rank}, Defensive rank #{def_rank}")


def _check_three_point_pct(r, ctx):
    metrics = ctx.get("metrics_map", {}).get(r.team_id)
    fg3_pct = None
    if metrics and metrics.total_fg3a and metrics.total_fg3a > 0:
        fg3_pct = metrics.total_fg3m / metrics.total_fg3a
    if fg3_pct is None:
        return _item("three_point_pct", "3-Point %", False,
                     "N/A", "> 32%", "3P% data unavailable")
    passed = fg3_pct > 0.32
    return _item("three_point_pct", "3-Point %", passed,
                 f"{fg3_pct * 100:.1f}%", "> 32%",
                 f"3P%: {fg3_pct * 100:.1f}% ({metrics.total_fg3m}/{metrics.total_fg3a})")


def _check_adj_em_rank(r, ctx):
    """AdjEM rank ≤ 17 — proxy for T-Rank contender status."""
    em_rank = ctx.get("em_ranks", {}).get(r.team_id)
    if em_rank is None:
        return _item("adj_em_rank", "AdjEM Top 17", False,
                     "N/A", "AdjEM Rank ≤ 17")
    passed = em_rank <= 17
    return _item("adj_em_rank", "AdjEM Top 17", passed,
                 f"#{em_rank}", "Rank ≤ 17",
                 f"AdjEM rank: #{em_rank}")


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
    MIN_Z_EFG = 1.39  # 1.3936
    
    threshold = stats.get("efg_mean", 0) + (MIN_Z_EFG * stats.get("efg_std", 1))
    passed = margin >= threshold if margin is not None else False
    return _item("efg_margin", "eFG Margin", passed,
                 f"{margin:.2f}" if margin is not None else "N/A", f"≥ {threshold:.2f}",
                 f"Adjusted eFG margin: {margin:.2f}" if margin is not None else "Unavailable")


def _check_ftr_margin(r, ctx):
    margin = r.adj_ftr_margin
    stats = ctx.get("stats", {})
    
    MIN_Z_FTR = -0.47  # -0.4703
    
    threshold = stats.get("ftr_mean", 0) + (MIN_Z_FTR * stats.get("ftr_std", 1))
    passed = margin >= threshold if margin is not None else False
    return _item("ftr_margin", "FTR Margin", passed,
                 f"{margin:.2f}" if margin is not None else "N/A", f"≥ {threshold:.2f}",
                 f"Adjusted FTR margin: {margin:.2f}" if margin is not None else "Unavailable")


def _check_reb_edge(r, ctx):
    edge = r.adj_reb_edge
    stats = ctx.get("stats", {})
    
    MIN_Z_REB = 0.15  # 0.1491
    
    threshold = stats.get("reb_mean", 0) + (MIN_Z_REB * stats.get("reb_std", 1))
    passed = edge >= threshold if edge is not None else False
    return _item("rebounding_edge", "Rebounding Edge", passed,
                 f"{edge:.2f}" if edge is not None else "N/A", f"≥ {threshold:.2f}",
                 f"Adjusted rebounding edge: {edge:.2f}" if edge is not None else "Unavailable")


def _check_tov_edge(r, ctx):
    edge = r.adj_tov_edge
    stats = ctx.get("stats", {})
    
    MIN_Z_TOV = -0.10  # -0.1009
    
    threshold = stats.get("tov_mean", 0) + (MIN_Z_TOV * stats.get("tov_std", 1))
    passed = edge >= threshold if edge is not None else False
    return _item("turnover_edge", "Turnover Edge", passed,
                 f"{edge:.2f}" if edge is not None else "N/A", f"≥ {threshold:.2f}",
                 f"Adjusted turnover edge: {edge:.2f}" if edge is not None else "Unavailable")


def _check_ffi(r, ctx):
    ffi = r.ffi_adj
    stats = ctx.get("stats", {})
    
    MIN_Z_FFI = 1.64  # 1.6378
    
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
    if wab is None:
        return _item("wab", "WAB (Wins Above Bubble)", False,
                     "N/A", "> 5", "WAB unavailable")
    passed = wab > 5.0
    return _item("wab", "WAB (Wins Above Bubble)", passed,
                 f"{wab:.1f}", "> 5",
                 f"WAB: {wab:.1f}")


def _check_ft_pct(r, ctx):
    metrics = ctx.get("metrics_map", {}).get(r.team_id)
    ft_pct  = None
    if metrics and metrics.total_fta and metrics.total_fta > 0:
        ft_pct = metrics.total_ftm / metrics.total_fta
    if ft_pct is None:
        return _item("ft_pct", "Free Throw %", False,
                     "N/A", "> 70%", "FT% data unavailable")
    passed = ft_pct > 0.70
    return _item("ft_pct", "Free Throw %", passed,
                 f"{ft_pct * 100:.1f}%", "> 70%",
                 f"FT%: {ft_pct * 100:.1f}% ({metrics.total_ftm}/{metrics.total_fta})")


# Ordered list of check functions
CHECKS = [
    _check_trapezoid,
    _check_kenpom_contender,
    _check_title_favorite,
    _check_win_pct,
    _check_elite_ranks,
    _check_three_point_pct,
    _check_adj_em_rank,
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
            TeamSeasonRatings.objects
            .filter(season=season, team__is_d1=True, games_played__gt=0)
            .select_related("team")
        )

        ctx = _build_season_context(all_qs)

        # Build metrics lookup for shooting pct checks
        metrics_qs = TeamSeasonMetrics.objects.filter(season=season)
        ctx["metrics_map"] = {m.team_id: m for m in metrics_qs}

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
