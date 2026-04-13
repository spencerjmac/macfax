"""
ffi/datasets.py — Build lineup segment observations enriched with box-score
factor stats for Four Factor Impact RAPM.

This mirrors core/analytics/player_value/bpr/datasets.py but:
  1. Fetches additional box fields: team_fgm, team_fg3m, team_dreb,
     opp_fgm, opp_fg3m, opp_dreb — needed for eFG% and DRB%.
  2. Scales those fields to the segment duration (same proportional
     scaling used for pts/poss in the BPR dataset).
  3. Each observation dict gains 14 new keys:
       home_fgm  home_fga  home_fg3m  home_fta  home_tov  home_oreb  home_dreb
       away_fgm  away_fga  away_fg3m  away_fta  away_tov  away_oreb  away_dreb

The existing BPR dataset is NOT modified to avoid breaking the live BPR
pipeline.  Factor RAPM uses this parallel build path.
"""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


# ── Possession/factor helpers ─────────────────────────────────────────────────

FTA_POSS_FACTOR = 0.44
MIN_SEGMENT_POSS = 0.5
MIN_OBS_WEIGHT = 1.0  # minimum opportunity count for a factor observation row


def _est_poss(fga: float, fta: float, tov: float, oreb: float) -> float:
    return max(0.0, fga + FTA_POSS_FACTOR * fta + tov - oreb)


def _scale(value: float, seg_secs: int, stint_secs: int) -> float:
    if stint_secs <= 0:
        return 0.0
    return value * seg_secs / stint_secs


# ── Extended lineup segment extractor ────────────────────────────────────────

def extract_ffi_segments(
    game_id: int,
    home_team_id: int,
    away_team_id: int,
    stints: list[dict],
    season_year: int,
    is_neutral: bool = False,
) -> list[dict]:
    """
    Return all valid 5v5 lineup segments for one game, extended with
    per-segment box-score factor stats scaled to segment duration.

    Stints must include the full box fields:
      team_fgm, team_fga, team_fg3m, team_fta, team_tov, team_oreb, team_dreb
      opp_fgm,  opp_fga,  opp_fg3m,  opp_fta,  opp_tov,  opp_oreb,  opp_dreb
    """
    observations: list[dict] = []

    by_period: dict[int, list[dict]] = defaultdict(list)
    for s in stints:
        by_period[s["period"]].append(s)

    for period, period_stints in by_period.items():
        home_stints = [s for s in period_stints if s["team_id"] == home_team_id]
        away_stints = [s for s in period_stints if s["team_id"] == away_team_id]

        if not home_stints or not away_stints:
            continue

        breakpoints = sorted(
            {s["clock_start_secs"] for s in period_stints}
            | {s["clock_end_secs"]  for s in period_stints},
            reverse=True,
        )

        for i in range(len(breakpoints) - 1):
            t_start = breakpoints[i]
            t_end   = breakpoints[i + 1]
            seg_secs = t_start - t_end
            if seg_secs <= 0:
                continue

            home_covering = [
                s for s in home_stints
                if s["clock_start_secs"] >= t_start and s["clock_end_secs"] <= t_end
            ]
            away_covering = [
                s for s in away_stints
                if s["clock_start_secs"] >= t_start and s["clock_end_secs"] <= t_end
            ]

            if len(home_covering) != 5 or len(away_covering) != 5:
                continue

            home_ref = min(home_covering, key=lambda s: s["clock_start_secs"] - s["clock_end_secs"])
            away_ref = min(away_covering, key=lambda s: s["clock_start_secs"] - s["clock_end_secs"])

            h_secs = home_ref["clock_start_secs"] - home_ref["clock_end_secs"]
            a_secs = away_ref["clock_start_secs"] - away_ref["clock_end_secs"]

            if h_secs <= 0 or a_secs <= 0:
                continue

            def hs(field: str) -> float:  # scale from home_ref
                return _scale(home_ref[field], seg_secs, h_secs)

            def as_(field: str) -> float:  # scale from away_ref
                return _scale(away_ref[field], seg_secs, a_secs)

            home_poss = _est_poss(hs("team_fga"), hs("team_fta"), hs("team_tov"), hs("team_oreb"))
            away_poss = _est_poss(as_("team_fga"), as_("team_fta"), as_("team_tov"), as_("team_oreb"))

            if home_poss < MIN_SEGMENT_POSS and away_poss < MIN_SEGMENT_POSS:
                continue

            observations.append({
                # Metadata
                "game_id":         game_id,
                "season_year":     season_year,
                "period":          period,
                "secs":            seg_secs,
                "is_neutral":      is_neutral,
                # Lineup ids
                "home_player_ids": [s["player_id"] for s in home_covering],
                "away_player_ids": [s["player_id"] for s in away_covering],
                # Pts and poss (same as BPR; kept for compat / future use)
                "home_pts":  hs("pts_scored"),
                "away_pts":  as_("pts_scored"),
                "home_poss": home_poss,
                "away_poss": away_poss,
                # ── home-team box stats (home team on offense) ──────────────
                "home_fgm":  hs("team_fgm"),
                "home_fga":  hs("team_fga"),
                "home_fg3m": hs("team_fg3m"),
                "home_fta":  hs("team_fta"),
                "home_tov":  hs("team_tov"),
                "home_oreb": hs("team_oreb"),
                "home_dreb": hs("team_dreb"),   # home DREB (limits away ORB)
                # ── away-team box stats (away team on offense) ──────────────
                "away_fgm":  as_("team_fgm"),
                "away_fga":  as_("team_fga"),
                "away_fg3m": as_("team_fg3m"),
                "away_fta":  as_("team_fta"),
                "away_tov":  as_("team_tov"),
                "away_oreb": as_("team_oreb"),
                "away_dreb": as_("team_dreb"),  # away DREB (limits home ORB)
            })

    return observations


# ── Full-season dataset builder ───────────────────────────────────────────────

def build_ffi_dataset(season_years: "int | list[int]", verbose: bool = True) -> dict:
    """
    Build the FFI RAPM dataset for one or more seasons.

    Returns the same structure as bpr.datasets.build_rapm_dataset plus
    the extended box stats fields in every observation dict.
    """
    from django.db.models import Q
    from core.models import Game, PlayerGameStint

    if isinstance(season_years, int):
        years: list[int] = [season_years]
    else:
        years = sorted(set(season_years))

    game_list = list(
        Game.objects
        .filter(season_year__in=years, status="final")
        .values("id", "home_team_id", "away_team_id", "neutral_site", "season_year")
    )
    n_games = len(game_list)

    if verbose:
        logger.info(f"FFI dataset: loading stints for {n_games} games (seasons {years})")

    # Fetch all box fields (superset of BPR stints_qs)
    stints_qs = (
        PlayerGameStint.objects
        .filter(game__season_year__in=years)
        .values(
            "game_id", "player_id", "team_id", "period",
            "clock_start_secs", "clock_end_secs", "secs_on",
            "pts_scored", "pts_allowed",
            # All box stats — superset of BPR query
            "team_fgm", "team_fga", "team_fg3m",
            "team_fta", "team_tov", "team_oreb", "team_dreb",
            "opp_fgm", "opp_fga", "opp_fg3m",
            "opp_fta", "opp_tov", "opp_oreb", "opp_dreb",
        )
    )

    stints_by_game: dict[int, list[dict]] = defaultdict(list)
    for s in stints_qs.iterator(chunk_size=10000):
        stints_by_game[s["game_id"]].append(s)

    game_lookup = {g["id"]: g for g in game_list}

    all_observations: list[dict] = []
    games_with_data = 0
    games_skipped = 0

    for gid, game_stints in stints_by_game.items():
        game_meta = game_lookup.get(gid)
        if game_meta is None:
            games_skipped += 1
            continue

        obs = extract_ffi_segments(
            game_id=gid,
            home_team_id=game_meta["home_team_id"],
            away_team_id=game_meta["away_team_id"],
            stints=game_stints,
            season_year=game_meta["season_year"],
            is_neutral=bool(game_meta.get("neutral_site", False)),
        )
        if obs:
            all_observations.extend(obs)
            games_with_data += 1
        else:
            games_skipped += 1

    if verbose:
        logger.info(
            f"FFI dataset: {len(all_observations)} segments from {games_with_data} games "
            f"({games_skipped} skipped)"
        )

    # Player-season index (same approach as BPR datasets.py v1.3.1)
    target_year = max(years)
    all_player_season_pairs: list[tuple[int, int]] = sorted({
        (pid, obs["season_year"])
        for obs in all_observations
        for pid in obs["home_player_ids"] + obs["away_player_ids"]
    })
    player_season_index: dict[tuple[int, int], int] = {
        ps: i for i, ps in enumerate(all_player_season_pairs)
    }
    n_player_seasons = len(all_player_season_pairs)

    # Possession totals per player-season (for minimum threshold checks)
    possession_totals_all: dict[tuple[int, int], dict] = {
        ps: {"off": 0.0, "def": 0.0} for ps in all_player_season_pairs
    }
    for obs in all_observations:
        yr = obs["season_year"]
        for pid in obs["home_player_ids"]:
            possession_totals_all[(pid, yr)]["off"] += obs["home_poss"]
            possession_totals_all[(pid, yr)]["def"] += obs["away_poss"]
        for pid in obs["away_player_ids"]:
            possession_totals_all[(pid, yr)]["off"] += obs["away_poss"]
            possession_totals_all[(pid, yr)]["def"] += obs["home_poss"]

    possession_totals_target: dict[int, dict] = {
        pid: possession_totals_all[(pid, target_year)]
        for (pid, yr) in all_player_season_pairs
        if yr == target_year
    }
    target_season_player_ids: list[int] = [
        pid for (pid, yr) in all_player_season_pairs if yr == target_year
    ]

    return {
        "observations":             all_observations,
        "n_observations":           len(all_observations),
        "player_season_index":      player_season_index,
        "player_season_keys":       all_player_season_pairs,
        "n_player_seasons":         n_player_seasons,
        "possession_totals_all":    possession_totals_all,
        "possession_totals_target": possession_totals_target,
        "target_season_player_ids": target_season_player_ids,
        "season_years":             years,
        "target_year":              target_year,
        # Backward-compat aliases
        "player_index":    {pid: i for i, pid in enumerate(target_season_player_ids)},
        "player_ids":      target_season_player_ids,
        "n_players":       len(target_season_player_ids),
        "possession_totals": possession_totals_target,
    }
