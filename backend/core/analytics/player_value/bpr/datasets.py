"""
datasets.py — Build RAPM design matrix from PlayerGameStint data.

Phase 3 of the BPR pipeline.

Key concept: "Lineup segment" is a contiguous time window where the 10-player
lineup (5 home + 5 away) does not change.  We reconstruct these by finding
all clock breakpoints in a game/period and selecting the time intervals where
exactly 5 players from each team continuously cover the full interval.

Pts and possessions per segment are estimated proportionally from the box events
of the narrowest stint that covers the segment.  When a player's stint exactly
bounds the segment (clock_start == t_start, clock_end == t_end), their values
are used directly without scaling.

Output:
  A list of dicts describing each valid RAPM observation:
    home_player_ids   list[int]   DB player PKs of home team on court
    away_player_ids   list[int]   DB player PKs of away team on court
    home_pts          float       team pts during segment
    away_pts          float       team pts during segment
    home_poss         float       estimated home offensivepossessions
    away_poss         float       estimated away offensive possessions
    is_home_neutral   bool        False when home team has a real home advantage
    secs              int         segment duration in seconds
    game_id           int         DB game PK
    season_year       int
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Possession estimator ───────────────────────────────────────────────────────
from core.analytics.player_value.bpr.constants import FTA_POSS_FACTOR, MIN_SEGMENT_POSS


def _est_poss(fga: float, fta: float, tov: float, oreb: float) -> float:
    """Kubatko possession estimate: FGA + 0.44·FTA + TOV - ORB."""
    return max(0.0, fga + FTA_POSS_FACTOR * fta + tov - oreb)


def _scale(value: float, seg_secs: int, stint_secs: int) -> float:
    """Proportionally scale a stint-level value to a sub-segment duration."""
    if stint_secs <= 0:
        return 0.0
    return value * seg_secs / stint_secs


# ── Per-game lineup segment extractor ────────────────────────────────────────

def extract_lineup_segments(
    game_id: int,
    home_team_id: int,
    away_team_id: int,
    stints: list[dict],  # [{player_id, team_id, period, clock_start_secs, clock_end_secs, secs_on,
                         #   pts_scored, pts_allowed, team_fga, team_fta, team_tov, team_oreb,
                         #   opp_fga, opp_fta, opp_tov, opp_oreb}]
    season_year: int,
    is_neutral: bool = False,
) -> list[dict]:
    """
    Return all valid 5v5 lineup segments for one game.

    A segment is valid when exactly 5 home players AND 5 away players all have
    stints whose [clock_start_secs, clock_end_secs] window completely contains
    the segment interval [t_start, t_end].  (Clock counts down, so
    clock_start_secs > clock_end_secs.)
    """
    observations: list[dict] = []

    # Group stints by period
    by_period: dict[int, list[dict]] = defaultdict(list)
    for s in stints:
        by_period[s["period"]].append(s)

    for period, period_stints in by_period.items():
        home_stints = [s for s in period_stints if s["team_id"] == home_team_id]
        away_stints = [s for s in period_stints if s["team_id"] == away_team_id]

        if not home_stints or not away_stints:
            continue

        # All clock breakpoints in this period
        breakpoints = sorted(
            {s["clock_start_secs"] for s in period_stints}
            | {s["clock_end_secs"]  for s in period_stints},
            reverse=True,  # highest clock first (earlier in game)
        )

        for i in range(len(breakpoints) - 1):
            t_start = breakpoints[i]
            t_end   = breakpoints[i + 1]
            seg_secs = t_start - t_end
            if seg_secs <= 0:
                continue

            # Players whose entirestint covers this segment:
            # clock_start_secs >= t_start (entered at or before t_start)
            # clock_end_secs <= t_end (left at or after t_end — clock is counting DOWN)
            home_covering = [
                s for s in home_stints
                if s["clock_start_secs"] >= t_start and s["clock_end_secs"] <= t_end
            ]
            away_covering = [
                s for s in away_stints
                if s["clock_start_secs"] >= t_start and s["clock_end_secs"] <= t_end
            ]

            if len(home_covering) != 5 or len(away_covering) != 5:
                continue  # imperfect segment — skip

            # ── Estimate pts and possessions ──────────────────────────────────
            # Use the narrowest (shortest) stint from each side for attribution.
            # If a player's stint exactly matches [t_start, t_end], no scaling needed.
            home_ref = min(home_covering, key=lambda s: s["clock_start_secs"] - s["clock_end_secs"])
            away_ref = min(away_covering, key=lambda s: s["clock_start_secs"] - s["clock_end_secs"])

            h_secs = home_ref["clock_start_secs"] - home_ref["clock_end_secs"]
            a_secs = away_ref["clock_start_secs"] - away_ref["clock_end_secs"]

            if h_secs <= 0 or a_secs <= 0:
                continue

            home_pts  = _scale(home_ref["pts_scored"],  seg_secs, h_secs)
            # Use away_ref for away-side attribution (native perspective, smaller scaling error)
            away_pts  = _scale(away_ref["pts_scored"],  seg_secs, a_secs)

            home_poss = _est_poss(
                _scale(home_ref["team_fga"],  seg_secs, h_secs),
                _scale(home_ref["team_fta"],  seg_secs, h_secs),
                _scale(home_ref["team_tov"],  seg_secs, h_secs),
                _scale(home_ref["team_oreb"], seg_secs, h_secs),
            )
            away_poss = _est_poss(
                _scale(away_ref["team_fga"],  seg_secs, a_secs),
                _scale(away_ref["team_fta"],  seg_secs, a_secs),
                _scale(away_ref["team_tov"],  seg_secs, a_secs),
                _scale(away_ref["team_oreb"], seg_secs, a_secs),
            )

            if home_poss < MIN_SEGMENT_POSS and away_poss < MIN_SEGMENT_POSS:
                continue  # no meaningful possession data for this segment

            observations.append({
                "game_id":         game_id,
                "season_year":     season_year,
                "period":          period,
                "secs":            seg_secs,
                "home_player_ids": [s["player_id"] for s in home_covering],
                "away_player_ids": [s["player_id"] for s in away_covering],
                "home_pts":        home_pts,
                "away_pts":        away_pts,
                "home_poss":       home_poss,
                "away_poss":       away_poss,
                "is_neutral":      is_neutral,
            })

    return observations


# ── Full-season design matrix builder ────────────────────────────────────────

def build_rapm_dataset(season_year: int, verbose: bool = True) -> dict:
    """
    Build the complete RAPM dataset for a single season.

    Returns:
        {
          "observations":  list[dict]   (all lineup segment observations)
          "player_index":  dict[int, int]  (player_id → matrix column index)
          "n_players":     int
          "n_observations": int
          "possession_totals": dict[int, {off, def}]  (player_id → poss counts)
        }
    """
    from django.db.models import Prefetch
    from core.models import Game, PlayerGameStint

    games_qs = (
        Game.objects
        .filter(season_year=season_year)
        .values("id", "home_team_id", "away_team_id", "neutral_site")
    )
    game_list = list(games_qs)
    n_games = len(game_list)

    if verbose:
        logger.info(f"BPR dataset: loading stints for {n_games} games (season {season_year})")

    # Load all stints for the season at once (one DB round-trip)
    stints_qs = (
        PlayerGameStint.objects
        .filter(game__season_year=season_year)
        .values(
            "game_id", "player_id", "team_id", "period",
            "clock_start_secs", "clock_end_secs", "secs_on",
            "pts_scored", "pts_allowed",
            "team_fga", "team_fta", "team_tov", "team_oreb",
            "opp_fga", "opp_fta", "opp_tov", "opp_oreb",
        )
    )

    # Group stints by game_id (dict of lists)
    stints_by_game: dict[int, list[dict]] = defaultdict(list)
    for s in stints_qs.iterator(chunk_size=10000):
        stints_by_game[s["game_id"]].append(s)

    # Build a game lookup for team IDs
    game_lookup = {g["id"]: g for g in game_list}

    all_observations: list[dict] = []
    games_with_data = 0
    games_skipped = 0

    for gid, game_stints in stints_by_game.items():
        game_meta = game_lookup.get(gid)
        if game_meta is None:
            games_skipped += 1
            continue

        obs = extract_lineup_segments(
            game_id=gid,
            home_team_id=game_meta["home_team_id"],
            away_team_id=game_meta["away_team_id"],
            stints=game_stints,
            season_year=season_year,
            is_neutral=bool(game_meta.get("neutral_site", False)),
        )
        if obs:
            all_observations.extend(obs)
            games_with_data += 1
        else:
            games_skipped += 1

    if verbose:
        logger.info(
            f"BPR dataset: {len(all_observations)} lineup segments from {games_with_data} games "
            f"({games_skipped} games had no clean stints)"
        )

    # Build player index (sorted for reproducibility)
    all_player_ids = sorted({
        pid
        for obs in all_observations
        for pid in obs["home_player_ids"] + obs["away_player_ids"]
    })
    player_index = {pid: i for i, pid in enumerate(all_player_ids)}

    # Accumulate per-player possession totals
    possession_totals: dict[int, dict] = {pid: {"off": 0.0, "def": 0.0} for pid in all_player_ids}
    for obs in all_observations:
        for pid in obs["home_player_ids"]:
            possession_totals[pid]["off"] += obs["home_poss"]
            possession_totals[pid]["def"] += obs["away_poss"]
        for pid in obs["away_player_ids"]:
            possession_totals[pid]["off"] += obs["away_poss"]
            possession_totals[pid]["def"] += obs["home_poss"]

    return {
        "observations":     all_observations,
        "player_index":     player_index,
        "player_ids":       all_player_ids,
        "n_players":        len(all_player_ids),
        "n_observations":   len(all_observations),
        "possession_totals": possession_totals,
    }
