"""
NBA Crystal Ball API View

Evaluates every team in an NBA season against a 10-item Championship
Checklist and returns results sorted by checklist score.

All computation is driven by NBATeamSeasonRatings (a single model — no
multi-model join needed, unlike the NCAA version) plus NBAPlayerSeasonStats
for the star-player check (2022+ only).

Thresholds come from backend/api/nba_crystal_ball_config.py, derived in
backend/backtesting/management/commands/backtest_nba_checklist.py from 10
seasons (2016-2025, 300 team-seasons) of our own data.
"""

import numpy as np
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from nba.analytics.standings import compute_standings
from nba.models import NBASeason, NBATeamSeasonRatings, NBAPlayerSeasonStats

from .checklist_utils import _item
from . import nba_crystal_ball_config as cfg


# ---------------------------------------------------------------------------
# Season-context helper
# ---------------------------------------------------------------------------

# Every Z-score check's metric MUST appear here. This is the explicit fix for
# the NCAA Z-score bug (commit 75b5a44), where metrics missing from the stats
# dict silently fell back to mean=0/std=1.
Z_METRICS = ["adj_net", "ffi", "efg_margin", "tov_edge"]

# Four-factor edge fields ranked (desc — higher margin/edge = better) for the
# "No Glaring Weakness" check.
FACTOR_FIELDS = ["efg_margin", "tov_edge", "oreb_edge", "fta_margin"]


def _build_nba_season_context(ratings_qs, season_year, player_stats_qs=None):
    """
    Pre-compute season-wide rank maps, factor ranks, and Z-score stats for
    one NBA season's 30 teams.
    """
    ratings = list(ratings_qs)
    if not ratings:
        return {}

    # Net/Off/Def rank maps (1 = best). Only rank_adj_net is stored on the
    # model; recompute all three in-memory for consistency within this view.
    net_ranks = {r.team_id: i + 1 for i, r in enumerate(
        sorted(ratings, key=lambda r: r.adj_net, reverse=True))}
    off_ranks = {r.team_id: i + 1 for i, r in enumerate(
        sorted(ratings, key=lambda r: r.adj_off, reverse=True))}
    def_ranks = {r.team_id: i + 1 for i, r in enumerate(
        sorted(ratings, key=lambda r: r.adj_def))}

    # Per-team four-factor-edge ranks (1 = best/highest margin)
    factor_ranks = {r.team_id: {} for r in ratings}
    for field in FACTOR_FIELDS:
        sorted_teams = sorted(
            ratings,
            key=lambda r: getattr(r, field) if getattr(r, field) is not None else -999,
            reverse=True,
        )
        for idx, r in enumerate(sorted_teams):
            factor_ranks[r.team_id][field] = idx + 1

    # Mean/std for every Z-score metric — single explicit loop, guaranteed
    # to populate every entry in Z_METRICS.
    stats = {}
    for metric in Z_METRICS:
        values = [getattr(r, metric) for r in ratings if getattr(r, metric) is not None]
        if len(values):
            stats[f"{metric}_mean"] = float(np.mean(values))
            stats[f"{metric}_std"] = float(np.std(values))
        else:
            stats[f"{metric}_mean"] = 0.0
            stats[f"{metric}_std"] = 1.0

    conf_seeds = {r.team_id: r.conference_seed for r in ratings}

    # Best roster BPR per team — only available 2022+
    team_max_bpr = {}
    if season_year >= 2022 and player_stats_qs is not None:
        for ps in player_stats_qs:
            if ps.bpr is None or ps.team_id is None:
                continue
            cur = team_max_bpr.get(ps.team_id)
            if cur is None or ps.bpr > cur:
                team_max_bpr[ps.team_id] = ps.bpr

    return {
        "season_year":  season_year,
        "net_ranks":    net_ranks,
        "off_ranks":    off_ranks,
        "def_ranks":    def_ranks,
        "factor_ranks": factor_ranks,
        "stats":        stats,
        "conf_seeds":   conf_seeds,
        "team_max_bpr": team_max_bpr,
    }


# ---------------------------------------------------------------------------
# Checklist – each item returns {"key", "label", "pass", "value", "threshold"}
# ---------------------------------------------------------------------------

def _check_net_rating_rank(r, ctx):
    rank = ctx.get("net_ranks", {}).get(r.team_id)
    if rank is None:
        return _item("net_rating_rank", "Net Rating Top-N", False,
                     "N/A", f"Rank ≤ {cfg.NET_RATING_RANK}")
    passed = rank <= cfg.NET_RATING_RANK
    return _item("net_rating_rank", "Net Rating Top-N", passed,
                 f"#{rank}", f"Rank ≤ {cfg.NET_RATING_RANK}",
                 f"Adj Net rank #{rank}")


def _check_net_rating_z(r, ctx):
    stats = ctx.get("stats", {})
    mean = stats.get("adj_net_mean", 0.0)
    std = stats.get("adj_net_std", 1.0)
    threshold = mean + cfg.MIN_Z_NET * std
    if r.adj_net is None:
        return _item("net_rating_z", "Elite Net Rating", False,
                     "N/A", f"≥ {threshold:+.1f}")
    z = (r.adj_net - mean) / std if std else 0
    passed = z >= cfg.MIN_Z_NET
    return _item("net_rating_z", "Elite Net Rating", passed,
                 f"{r.adj_net:+.1f}", f"≥ {threshold:+.1f} (Z ≥ {cfg.MIN_Z_NET})",
                 f"Adj Net {r.adj_net:+.1f} (Z {z:.2f})")


def _check_top_conference_seed(r, ctx):
    seed = ctx.get("conf_seeds", {}).get(r.team_id)
    if seed is None:
        return _item("top_conference_seed", "Top Conference Seed", False,
                     "N/A", f"Seed ≤ {cfg.TOP_CONFERENCE_SEED}", "Seed unavailable")
    passed = seed <= cfg.TOP_CONFERENCE_SEED
    return _item("top_conference_seed", "Top Conference Seed", passed,
                 f"#{seed}", f"Seed ≤ {cfg.TOP_CONFERENCE_SEED}",
                 f"Conference seed #{seed}")


def _check_elite_offense(r, ctx):
    rank = ctx.get("off_ranks", {}).get(r.team_id)
    if rank is None:
        return _item("elite_offense", "Elite Offense", False,
                     "N/A", f"Rank ≤ {cfg.ELITE_OFFENSE_RANK}")
    passed = rank <= cfg.ELITE_OFFENSE_RANK
    return _item("elite_offense", "Elite Offense", passed,
                 f"#{rank}", f"Rank ≤ {cfg.ELITE_OFFENSE_RANK}",
                 f"Adj Off rank #{rank}")


def _check_elite_defense(r, ctx):
    rank = ctx.get("def_ranks", {}).get(r.team_id)
    if rank is None:
        return _item("elite_defense", "Elite Defense", False,
                     "N/A", f"Rank ≤ {cfg.ELITE_DEFENSE_RANK}")
    passed = rank <= cfg.ELITE_DEFENSE_RANK
    return _item("elite_defense", "Elite Defense", passed,
                 f"#{rank}", f"Rank ≤ {cfg.ELITE_DEFENSE_RANK}",
                 f"Adj Def rank #{rank}")


def _check_ffi_z(r, ctx):
    stats = ctx.get("stats", {})
    mean = stats.get("ffi_mean", 0.0)
    std = stats.get("ffi_std", 1.0)
    threshold = mean + cfg.MIN_Z_FFI * std
    if r.ffi is None:
        return _item("ffi_z", "Four Factor Index", False,
                     "N/A", f"≥ {threshold:.1f}", "FFI unavailable")
    z = (r.ffi - mean) / std if std else 0
    passed = z >= cfg.MIN_Z_FFI
    return _item("ffi_z", "Four Factor Index", passed,
                 f"{r.ffi:.1f}", f"≥ {threshold:.1f} (Z ≥ {cfg.MIN_Z_FFI})",
                 f"FFI {r.ffi:.1f} (Z {z:.2f})")


def _check_efg_margin_z(r, ctx):
    stats = ctx.get("stats", {})
    mean = stats.get("efg_margin_mean", 0.0)
    std = stats.get("efg_margin_std", 1.0)
    threshold = mean + cfg.MIN_Z_EFG * std
    if r.efg_margin is None:
        return _item("efg_margin_z", "eFG Margin", False,
                     "N/A", f"≥ {threshold * 100:+.1f}%", "eFG margin unavailable")
    z = (r.efg_margin - mean) / std if std else 0
    passed = z >= cfg.MIN_Z_EFG
    return _item("efg_margin_z", "eFG Margin", passed,
                 f"{r.efg_margin * 100:+.1f}%",
                 f"≥ {threshold * 100:+.1f}% (Z ≥ {cfg.MIN_Z_EFG})",
                 f"eFG margin {r.efg_margin * 100:+.1f}% (Z {z:.2f})")


def _check_tov_edge_z(r, ctx):
    stats = ctx.get("stats", {})
    mean = stats.get("tov_edge_mean", 0.0)
    std = stats.get("tov_edge_std", 1.0)
    threshold = mean + cfg.MIN_Z_TOV * std
    if r.tov_edge is None:
        return _item("tov_edge_z", "Turnover Edge", False,
                     "N/A", f"≥ {threshold * 100:+.1f}%", "Turnover edge unavailable")
    z = (r.tov_edge - mean) / std if std else 0
    passed = z >= cfg.MIN_Z_TOV
    return _item("tov_edge_z", "Turnover Edge", passed,
                 f"{r.tov_edge * 100:+.1f}%",
                 f"≥ {threshold * 100:+.1f}% (Z ≥ {cfg.MIN_Z_TOV})",
                 f"Turnover edge {r.tov_edge * 100:+.1f}% (Z {z:.2f})")


def _check_no_glaring_weakness(r, ctx):
    factors = ctx.get("factor_ranks", {}).get(r.team_id)
    if not factors:
        return _item("no_glaring_weakness", "No Glaring Weakness", False,
                     "N/A", f"Worst factor rank ≤ {cfg.NO_GLARING_WEAKNESS_RANK}")
    worst_field, worst_rank = max(factors.items(), key=lambda kv: kv[1])
    passed = worst_rank <= cfg.NO_GLARING_WEAKNESS_RANK
    return _item("no_glaring_weakness", "No Glaring Weakness", passed,
                 f"#{worst_rank}", f"Worst factor rank ≤ {cfg.NO_GLARING_WEAKNESS_RANK}",
                 f"Worst factor: {worst_field} (rank #{worst_rank})")


def _check_star_player(r, ctx):
    season_year = ctx.get("season_year")
    if season_year is not None and season_year < cfg.STAR_BPR_EXEMPT_BEFORE_YEAR:
        return _item("star_player", "Star Player Impact", True,
                     "N/A", f"≥ {cfg.MIN_STAR_BPR} (exempt before {cfg.STAR_BPR_EXEMPT_BEFORE_YEAR})",
                     "No player BPR data before 2022 — exempted")
    best_bpr = ctx.get("team_max_bpr", {}).get(r.team_id)
    if best_bpr is None:
        return _item("star_player", "Star Player Impact", False,
                     "N/A", f"≥ {cfg.MIN_STAR_BPR}", "No player BPR data")
    passed = best_bpr >= cfg.MIN_STAR_BPR
    return _item("star_player", "Star Player Impact", passed,
                 f"{best_bpr:.1f}", f"≥ {cfg.MIN_STAR_BPR}",
                 f"Best roster BPR {best_bpr:.1f}")


# Ordered list of check functions
CHECKS = [
    _check_net_rating_rank,
    _check_net_rating_z,
    _check_top_conference_seed,
    _check_elite_offense,
    _check_elite_defense,
    _check_ffi_z,
    _check_efg_margin_z,
    _check_tov_edge_z,
    _check_no_glaring_weakness,
    _check_star_player,
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

class NBACrystalBallView(APIView):
    """
    GET /api/viz/nba-crystal-ball/?season=2026

    Response:
    {
        "season": 2026, "season_display": "2025-26", "total_teams": 30,
        "teams": [
            { "team_name": "...", "team_slug": "...", "team_logo": "...",
              "conference": "West", "record": "12-3", "rank": 1,
              "adj_net": 9.3, "adj_off": 118.4, "adj_def": 109.1,
              "conference_seed": 1, "playoff_finish": null,
              "checklist": { "passedCount": 8, "totalCount": 10, "score": 80.0, "items": [...] } },
            ...
        ]
    }
    """

    def get(self, request):
        season_year = request.query_params.get("season")

        if season_year:
            season = get_object_or_404(NBASeason, year=season_year)
        else:
            season = NBASeason.objects.filter(is_current=True).first()
            if not season:
                return Response(
                    {"error": "No current season found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        ratings = list(
            NBATeamSeasonRatings.objects.filter(
                season=season,
                season_type="regular",
                adj_net__isnull=False,
            )
            .select_related("team")
        )

        if not ratings:
            return Response(
                {"error": "No teams found with computed ratings for this season"},
                status=status.HTTP_404_NOT_FOUND,
            )

        player_stats_qs = None
        if season.year >= cfg.STAR_BPR_EXEMPT_BEFORE_YEAR:
            player_stats_qs = NBAPlayerSeasonStats.objects.filter(
                season=season, season_type="regular", bpr__isnull=False,
            )

        ctx = _build_nba_season_context(ratings, season.year, player_stats_qs)

        standings_by_team = {
            row["team_id"]: row for row in compute_standings(season.year, season_type="regular")
        }

        teams_list = []
        for r in ratings:
            record = standings_by_team.get(r.team_id)
            record_str = f"{record['wins']}-{record['losses']}" if record else "0-0"
            teams_list.append({
                "team_name":        r.team.name,
                "team_slug":        r.team.slug,
                "team_logo":        r.team.logo_url,
                "conference":       r.team.conference,
                "record":           record_str,
                "rank":             ctx["net_ranks"].get(r.team_id),
                "adj_net":          round(r.adj_net, 1),
                "adj_off":          round(r.adj_off, 1),
                "adj_def":          round(r.adj_def, 1),
                "conference_seed":  r.conference_seed,
                "playoff_finish":   r.playoff_finish,
                "checklist":        run_checklist(r, ctx),
            })

        teams_list.sort(key=lambda t: (-t["checklist"]["passedCount"], -t["adj_net"]))

        return Response({
            "season":         season.year,
            "season_display": season.display_name,
            "total_teams":    len(teams_list),
            "teams":          teams_list,
        })
