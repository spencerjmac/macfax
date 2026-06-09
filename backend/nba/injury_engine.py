"""
nba/injury_engine.py

Computes a game-specific injury adjustment for the NBA matchup model.

NEVER writes to NBATeamSeasonRatings — all deltas are in-memory, matchup-only.

Formula
-------
  minute_share  = min(player.mpg / 48.0, 0.85)
  off_adj_i     = player.obpr × minute_share × status_weight
  def_adj_i     = player.dbpr × minute_share × status_weight

  team_off_delta = -sum(off_adj_i)   (negative = team is weaker offensively)
  team_def_delta = -sum(def_adj_i)   (negative = team is weaker defensively)

BPR is in pts/100 possessions relative to league average. Minute share converts
it to a per-game impact. Status weight (0–1) reflects expected unavailability.
Replacement value = 0 BPR (league average), so no offset is needed.

Adjustments are capped at ±MAX_ADJ_PTS to guard against bad data.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nba.models import NBAPlayerAvailability, NBATeam, NBASeason

_log = logging.getLogger(__name__)

# Hard cap: no team adjustment can exceed this magnitude (in pts/100 poss)
MAX_ADJ_PTS = 10.0

# Only pull records with status weights > 0 (skip "available")
_IMPACTFUL_STATUSES = [
    "probable",
    "day_to_day",
    "questionable",
    "game_time_decision",
    "doubtful",
    "out",
    "out_for_season",
]


def compute_nba_injury_adjustment(
    team: "NBATeam",
    season: "NBASeason",
    game_date: date,
) -> dict:
    """
    Return injury-based adj_off/adj_def deltas for one team on a given date.

    Returns
    -------
    {
        "adj_off_delta": float,   # add to ratings_x.adj_off before forecast_game()
        "adj_def_delta": float,   # add to ratings_x.adj_def before forecast_game()
        "players": [
            {
                "name": str,
                "status": str,
                "obpr": float | None,
                "dbpr": float | None,
                "mpg": float | None,
                "off_adj": float,
                "def_adj": float,
            },
            ...
        ],
    }
    """
    from nba.models import NBAPlayerAvailability, NBAPlayerSeasonStats

    reports = (
        NBAPlayerAvailability.objects
        .filter(
            team=team,
            game_date=game_date,
            status__in=_IMPACTFUL_STATUSES,
        )
        .select_related("player")
    )

    if not reports.exists():
        return {"adj_off_delta": 0.0, "adj_def_delta": 0.0, "players": []}

    # Build player-stats lookup (current-season BPR + mpg).
    # Sort nulls first so that if a player has two entries (e.g. traded mid-season),
    # the non-null BPR row overwrites the null one in the dict comprehension.
    from django.db.models import F
    player_ids = [r.player_id for r in reports]
    stats_qs = NBAPlayerSeasonStats.objects.filter(
        player_id__in=player_ids,
        team=team,
        season=season,
    ).order_by(F("obpr").asc(nulls_first=True)).values("player_id", "obpr", "dbpr", "mpg")
    stats_map = {s["player_id"]: s for s in stats_qs}

    total_off = 0.0
    total_def = 0.0
    players_detail = []

    for report in reports:
        stats = stats_map.get(report.player_id)
        if stats is None:
            _log.debug(
                "[injury_engine] No season stats for %s (player_id=%d) — skipping",
                report.player.name, report.player_id,
            )
            continue

        obpr = stats["obpr"]
        dbpr = stats["dbpr"]
        mpg  = stats["mpg"]

        if obpr is None or dbpr is None or mpg is None or mpg <= 0:
            _log.debug(
                "[injury_engine] Incomplete BPR/mpg for %s — skipping",
                report.player.name,
            )
            continue

        # Use expected_minutes_pct override if set (e.g. "limited, ~20 min")
        if report.expected_minutes_pct is not None:
            minute_share = min(float(report.expected_minutes_pct), 1.0)
        else:
            minute_share = min(float(mpg) / 48.0, 0.85)

        w = report.weight  # STATUS_WEIGHTS lookup on model

        off_adj = float(obpr) * minute_share * w
        def_adj = float(dbpr) * minute_share * w

        total_off += off_adj
        total_def += def_adj

        players_detail.append(
            {
                "name":    report.player.name,
                "status":  report.status,
                "obpr":    round(float(obpr), 2),
                "dbpr":    round(float(dbpr), 2),
                "mpg":     round(float(mpg), 1),
                "off_adj": round(off_adj, 2),
                "def_adj": round(def_adj, 2),
            }
        )

    # Sort by absolute net impact descending for readability in API response
    players_detail.sort(key=lambda p: abs(p["off_adj"] + p["def_adj"]), reverse=True)

    # Apply cap
    # adj_off: decreases (negative) when good offensive players are out
    # adj_def: increases (positive) when good defensive players are out
    #   (adj_def = points-per-100-allowed; higher = worse defense)
    off_delta = max(-MAX_ADJ_PTS, min(MAX_ADJ_PTS, -total_off))
    def_delta = max(-MAX_ADJ_PTS, min(MAX_ADJ_PTS, +total_def))

    _log.debug(
        "[injury_engine] %s on %s: off_delta=%.2f def_delta=%.2f (%d players affected)",
        team.abbreviation, game_date, off_delta, def_delta, len(players_detail),
    )

    return {
        "adj_off_delta": round(off_delta, 3),
        "adj_def_delta": round(def_delta, 3),
        "players": players_detail,
    }
