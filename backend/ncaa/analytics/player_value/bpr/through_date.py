"""
through_date.py — date-bounded (leak-free) feature rebuilds for BPR backtesting.

The production pipeline's Phase 3 loads full-season PlayerSeasonStats and
full-season TeamSeasonRatings even when run_bpr_season() is given a
cutoff_date — that leaks post-cutoff information into any within-season
backtest (see docs/bpr_audit/03_weakness_report.md item 3.1).

This module rebuilds every input the pipeline's Phase 3 consumes using only
games with game_date <= cutoff_date:

  build_team_adj_em_through_date()   — iterative opponent-adjusted team EM
                                       (lightweight mirror of compute_adjusted_ratings)
  build_opp_quality_map_through_date() — mean opponent adj_em per team
  build_pss_features_through_date()  — PlayerSeasonStats-shaped rows with the
                                       exact keys pipeline Phase 3 selects,
                                       including on-court features rebuilt from
                                       date-bounded PlayerGameStint aggregates
                                       (on_court_adj_em replicates the Phase E
                                       formula in compute_ncaa_player_impact)

All functions are pure reads — no DB writes. Every ORM query carries a
game__game_date__lte (or game_date__lte) filter; the anti-leak unit test in
ncaa/tests/test_bpr_through_date.py enforces mid-season != full-season and
season-end == stored values.
"""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# Mirrors compute_ncaa_player_impact Phase E / TeamGameStats.site_factor
HCA_OFF = {"H": 0.9862, "A": 1.0140, "N": 1.0}
HCA_DEF = {"H": 1.0140, "A": 0.9862, "N": 1.0}
PLAYER_SHRINKAGE_K = 200.0   # possessions — Phase E player shrinkage
TEAM_SHRINKAGE_K = 100.0     # possessions — team-level shrinkage (early-season stability)
TEAM_ITERATIONS = 25
MIN_FF_FGA = 30              # mirrors compute_ncaa_player_impact.MIN_FF_FGA


def _poss(fga: float, fta: float, tov: float, oreb: float) -> float:
    return fga + 0.44 * fta + tov - oreb


def _load_team_games(season_year: int, cutoff_date) -> tuple[dict, dict]:
    """
    Aggregate PlayerGameStats into per-(game, team) box totals through cutoff.

    Returns (game_team_box, games_meta):
      game_team_box: {(game_id, team_id): {pts, fga, fta, tov, oreb, poss}}
      games_meta:    {game_id: (home_team_id, away_team_id, neutral_site)}
    """
    from django.db.models import Sum
    from ncaa.models import Game, PlayerGameStats

    games_meta = {
        g["id"]: (g["home_team_id"], g["away_team_id"], g["neutral_site"])
        for g in Game.objects.filter(
            season_year=season_year, status="final",
            game_date__lte=cutoff_date,
        ).values("id", "home_team_id", "away_team_id", "neutral_site")
    }

    game_team_box: dict[tuple, dict] = {}
    agg = (PlayerGameStats.objects
           .filter(game__season_year=season_year,
                   game__game_date__lte=cutoff_date,
                   game__status="final",
                   team__isnull=False)
           .values("game_id", "team_id")
           .annotate(pts=Sum("points"), fga=Sum("fg_attempted"),
                     fta=Sum("ft_attempted"), tov=Sum("turnovers"),
                     oreb=Sum("offensive_rebounds")))
    for r in agg:
        poss = _poss(r["fga"] or 0, r["fta"] or 0, r["tov"] or 0, r["oreb"] or 0)
        game_team_box[(r["game_id"], r["team_id"])] = {
            "pts": r["pts"] or 0, "poss": poss,
        }
    return game_team_box, games_meta


def build_team_adj_em_through_date(
    season_year: int, cutoff_date,
) -> tuple[dict[int, float], dict[int, float], dict[int, float], float]:
    """
    Iterative opponent-adjusted team ratings using games <= cutoff_date only.

    Lightweight mirror of compute_adjusted_ratings: multiplicative opponent
    adjustment with site factors, possession-weighted, shrunk toward the
    through-date national average (k=TEAM_SHRINKAGE_K), TEAM_ITERATIONS rounds.
    Omits: elevation adjustment, recency weighting, importance weighting,
    BPR-prior anchoring — acceptable divergences for backtest arms (validated
    r >= 0.97 vs stored TeamSeasonRatings at season-end cutoff).

    Returns (adj_em_map, adj_o_map, adj_d_map, nat_avg_ortg).
    """
    game_team_box, games_meta = _load_team_games(season_year, cutoff_date)
    if not game_team_box:
        return {}, {}, {}, 100.0

    # Per-team game efficiency rows
    team_games: dict[int, list] = defaultdict(list)
    total_pts = 0.0
    total_poss = 0.0
    for gid, (home, away, neutral) in games_meta.items():
        hb = game_team_box.get((gid, home))
        ab = game_team_box.get((gid, away))
        if not hb or not ab or hb["poss"] < 10 or ab["poss"] < 10:
            continue
        for tid, own, opp, site in ((home, hb, ab, "N" if neutral else "H"),
                                    (away, ab, hb, "N" if neutral else "A")):
            oe = 100.0 * own["pts"] / own["poss"]
            de = 100.0 * opp["pts"] / opp["poss"]
            team_games[tid].append({
                "opp": home if tid == away else away,
                "oe": oe, "de": de,
                "off_poss": own["poss"], "def_poss": opp["poss"],
                "site": site,
            })
            total_pts += own["pts"]
            total_poss += own["poss"]

    nat_avg = 100.0 * total_pts / total_poss if total_poss else 100.0

    adj_o = {tid: nat_avg for tid in team_games}
    adj_d = {tid: nat_avg for tid in team_games}

    for _ in range(TEAM_ITERATIONS):
        new_o, new_d = {}, {}
        for tid, rows in team_games.items():
            sum_ao = sum_ad = w_off = w_def = 0.0
            for r in rows:
                opp_ad = adj_d.get(r["opp"], nat_avg)
                opp_ao = adj_o.get(r["opp"], nat_avg)
                ao = r["oe"] * (nat_avg / opp_ad) * HCA_OFF[r["site"]] if opp_ad > 0 else r["oe"]
                ad = r["de"] * (nat_avg / opp_ao) * HCA_DEF[r["site"]] if opp_ao > 0 else r["de"]
                sum_ao += ao * r["off_poss"]
                sum_ad += ad * r["def_poss"]
                w_off += r["off_poss"]
                w_def += r["def_poss"]
            new_o[tid] = ((sum_ao + TEAM_SHRINKAGE_K * nat_avg)
                          / (w_off + TEAM_SHRINKAGE_K)) if w_off else nat_avg
            new_d[tid] = ((sum_ad + TEAM_SHRINKAGE_K * nat_avg)
                          / (w_def + TEAM_SHRINKAGE_K)) if w_def else nat_avg
        adj_o, adj_d = new_o, new_d

    adj_em = {tid: adj_o[tid] - adj_d[tid] for tid in adj_o}
    return adj_em, adj_o, adj_d, nat_avg


def build_opp_quality_map_through_date(
    season_year: int, cutoff_date,
    adj_em_map: dict[int, float] | None = None,
) -> dict[int, float]:
    """
    team_id -> mean adj_em of opponents faced through cutoff_date.
    Mirrors pipeline._build_opponent_quality_map with date bounding.
    """
    from ncaa.models import Game

    if adj_em_map is None:
        adj_em_map, _, _, _ = build_team_adj_em_through_date(season_year, cutoff_date)
    if not adj_em_map:
        return {}

    opp_lists: dict[int, list[float]] = defaultdict(list)
    for g in Game.objects.filter(
        season_year=season_year, status="final",
        game_date__lte=cutoff_date,
    ).values("home_team_id", "away_team_id"):
        home, away = g["home_team_id"], g["away_team_id"]
        if home and away:
            if away in adj_em_map:
                opp_lists[home].append(adj_em_map[away])
            if home in adj_em_map:
                opp_lists[away].append(adj_em_map[home])
    return {tid: sum(v) / len(v) for tid, v in opp_lists.items()}


def build_pss_features_through_date(
    season_year: int, cutoff_date,
    team_maps: tuple | None = None,
) -> list[dict]:
    """
    Rebuild the PlayerSeasonStats rows pipeline Phase 3 consumes, using only
    games with game_date <= cutoff_date.

    Returns a list of dicts with exactly the keys of the pipeline's
    PlayerSeasonStats.values(...) query (pipeline.py Phase 3), so the result
    can be passed to run_bpr_season(player_season_stats_override=...).

    team_maps: optional (adj_em_map, adj_o_map, adj_d_map, nat_avg) from
    build_team_adj_em_through_date to avoid recomputation.
    """
    from ncaa.models import PlayerGameStats, PlayerGameStint, Game

    if team_maps is None:
        team_maps = build_team_adj_em_through_date(season_year, cutoff_date)
    adj_em_map, adj_o_map, adj_d_map, nat_avg = team_maps

    games_meta = {
        g["id"]: (g["home_team_id"], g["away_team_id"], g["neutral_site"])
        for g in Game.objects.filter(
            season_year=season_year, status="final",
            game_date__lte=cutoff_date,
        ).values("id", "home_team_id", "away_team_id", "neutral_site")
    }

    # ── Box-score aggregation per (player, team) ──────────────────────────────
    box: dict[tuple, dict] = defaultdict(lambda: {
        "gp": 0, "min": 0.0, "pts": 0, "ast": 0, "tov": 0, "stl": 0,
        "blk": 0, "pf": 0, "reb": 0, "oreb": 0, "dreb": 0,
        "fga": 0, "fg3a": 0, "fgm": 0, "fg3m": 0, "fta": 0, "ftm": 0,
    })
    for r in (PlayerGameStats.objects
              .filter(game__season_year=season_year,
                      game__game_date__lte=cutoff_date,
                      game__status="final",
                      did_not_play=False,
                      team__isnull=False)
              .values("player_id", "team_id", "minutes", "points",
                      "assists", "turnovers", "steals", "blocks", "fouls",
                      "rebounds", "offensive_rebounds", "defensive_rebounds",
                      "fg_attempted", "fg3_attempted", "fg_made", "fg3_made",
                      "ft_attempted", "ft_made")
              .iterator(chunk_size=50000)):
        b = box[(r["player_id"], r["team_id"])]
        b["gp"] += 1
        b["min"] += r["minutes"] or 0.0
        b["pts"] += r["points"] or 0
        b["ast"] += r["assists"] or 0
        b["tov"] += r["turnovers"] or 0
        b["stl"] += r["steals"] or 0
        b["blk"] += r["blocks"] or 0
        b["pf"] += r["fouls"] or 0
        b["reb"] += r["rebounds"] or 0
        b["oreb"] += r["offensive_rebounds"] or 0
        b["dreb"] += r["defensive_rebounds"] or 0
        b["fga"] += r["fg_attempted"] or 0
        b["fg3a"] += r["fg3_attempted"] or 0
        b["fgm"] += r["fg_made"] or 0
        b["fg3m"] += r["fg3_made"] or 0
        b["fta"] += r["ft_attempted"] or 0
        b["ftm"] += r["ft_made"] or 0

    # ── On-court aggregation per (player, team) from stints ──────────────────
    oc: dict[tuple, dict] = defaultdict(lambda: {
        "secs": 0, "game_ids": set(),
        "team_fga": 0, "team_fta": 0, "team_tov": 0,
        "team_oreb": 0, "team_dreb": 0,
        "opp_fga": 0, "opp_fta": 0, "opp_tov": 0,
        "opp_oreb": 0, "opp_dreb": 0,
        # per-game accumulators for Phase E adjusted EM
        "per_game": defaultdict(lambda: {
            "pts": 0, "def_pts": 0,
            "team_fga": 0, "team_fta": 0, "team_tov": 0, "team_oreb": 0,
            "opp_fga": 0, "opp_fta": 0, "opp_tov": 0, "opp_oreb": 0,
        }),
    })
    for r in (PlayerGameStint.objects
              .filter(game__season_year=season_year,
                      game__game_date__lte=cutoff_date,
                      team__isnull=False)
              .values("player_id", "team_id", "game_id", "secs_on",
                      "pts_scored", "pts_allowed",
                      "team_fga", "team_fta", "team_tov", "team_oreb", "team_dreb",
                      "opp_fga", "opp_fta", "opp_tov", "opp_oreb", "opp_dreb")
              .iterator(chunk_size=50000)):
        o = oc[(r["player_id"], r["team_id"])]
        o["secs"] += r["secs_on"]
        o["game_ids"].add(r["game_id"])
        for k in ("team_fga", "team_fta", "team_tov", "team_oreb", "team_dreb",
                  "opp_fga", "opp_fta", "opp_tov", "opp_oreb", "opp_dreb"):
            o[k] += r[k]
        g = o["per_game"][r["game_id"]]
        g["pts"] += r["pts_scored"]
        g["def_pts"] += r["pts_allowed"]
        for k in ("team_fga", "team_fta", "team_tov", "team_oreb",
                  "opp_fga", "opp_fta", "opp_tov", "opp_oreb"):
            g[k] += r[k]

    # ── Assemble rows ─────────────────────────────────────────────────────────
    rows: list[dict] = []
    for (pid, tid), b in box.items():
        gp = b["gp"]
        if gp == 0:
            continue
        efg = ((b["fgm"] + 0.5 * b["fg3m"]) / b["fga"]) if b["fga"] > 0 else None
        ts_denom = 2.0 * (b["fga"] + 0.44 * b["fta"])
        ts = (b["pts"] / ts_denom) if ts_denom > 0 else None

        row = {
            "player_id": pid, "team_id": tid,
            "gp": gp, "mpg": b["min"] / gp,
            "pts": b["pts"] / gp, "ast": b["ast"] / gp, "tov": b["tov"] / gp,
            "stl": b["stl"] / gp, "blk": b["blk"] / gp, "pf": b["pf"] / gp,
            "reb": b["reb"] / gp,
            "oreb_pg": b["oreb"] / gp, "dreb_pg": b["dreb"] / gp,
            "fga_pg": b["fga"] / gp, "fg3a_pg": b["fg3a"] / gp,
            "fta_pg": b["fta"] / gp, "ftm_pg": b["ftm"] / gp,
            "efg_pct": efg, "ts_pct": ts,
            "on_court_secs_pg": None,
            "on_court_adj_em": None,
            "on_court_tov_edge": None,
            "on_court_reb_edge": None,
        }

        o = oc.get((pid, tid))
        if o and o["secs"] >= 120 and o["game_ids"]:
            oc_gp = len(o["game_ids"])
            row["on_court_secs_pg"] = round(o["secs"] / oc_gp, 2)

            # Four-factor margins (mirrors _compute_four_factors)
            if o["team_fga"] >= MIN_FF_FGA:
                tov_denom = o["team_fga"] + 0.44 * o["team_fta"] + o["team_tov"]
                opp_tov_denom = o["opp_fga"] + 0.44 * o["opp_fta"] + o["opp_tov"]
                tov_pct = 100.0 * o["team_tov"] / tov_denom if tov_denom > 0 else None
                opp_tov_pct = 100.0 * o["opp_tov"] / opp_tov_denom if opp_tov_denom > 0 else None
                orb_denom = o["team_oreb"] + o["opp_dreb"]
                opp_orb_denom = o["opp_oreb"] + o["team_dreb"]
                orb_pct = 100.0 * o["team_oreb"] / orb_denom if orb_denom > 0 else None
                opp_orb_pct = 100.0 * o["opp_oreb"] / opp_orb_denom if opp_orb_denom > 0 else None
                if tov_pct is not None and opp_tov_pct is not None:
                    row["on_court_tov_edge"] = round(opp_tov_pct - tov_pct, 2)
                if orb_pct is not None and opp_orb_pct is not None:
                    row["on_court_reb_edge"] = round(orb_pct - opp_orb_pct, 2)

            # Phase E adjusted on-court EM (possession-weighted, shrunk k=200)
            sum_ao = sum_ad = w_off = w_def = 0.0
            for gid, g in o["per_game"].items():
                meta = games_meta.get(gid)
                if meta is None:
                    continue
                home, away, neutral = meta
                site = "N" if neutral else ("H" if home == tid else "A")
                opp_id = away if home == tid else home
                off_poss = _poss(g["team_fga"], g["team_fta"], g["team_tov"], g["team_oreb"])
                def_poss = _poss(g["opp_fga"], g["opp_fta"], g["opp_tov"], g["opp_oreb"])
                if off_poss < 1.0 or def_poss < 1.0:
                    continue
                raw_oe = 100.0 * g["pts"] / off_poss
                raw_de = 100.0 * g["def_pts"] / def_poss
                opp_ao = adj_o_map.get(opp_id, nat_avg)
                opp_ad = adj_d_map.get(opp_id, nat_avg)
                ao = raw_oe * (nat_avg / opp_ad) * HCA_OFF[site] if opp_ad > 0 else raw_oe
                ad = raw_de * (nat_avg / opp_ao) * HCA_DEF[site] if opp_ao > 0 else raw_de
                sum_ao += ao * off_poss
                sum_ad += ad * def_poss
                w_off += off_poss
                w_def += def_poss
            if w_off >= 1.0 and w_def >= 1.0:
                adj_o_p = (sum_ao + nat_avg * PLAYER_SHRINKAGE_K) / (w_off + PLAYER_SHRINKAGE_K)
                adj_d_p = (sum_ad + nat_avg * PLAYER_SHRINKAGE_K) / (w_def + PLAYER_SHRINKAGE_K)
                row["on_court_adj_em"] = round(adj_o_p - adj_d_p, 2)

        rows.append(row)

    logger.info(
        "[through_date] season=%s cutoff=%s: %d player rows, %d with on-court adj_em",
        season_year, cutoff_date, len(rows),
        sum(1 for r in rows if r["on_court_adj_em"] is not None),
    )
    return rows


def build_rosters_through_date(
    season_year: int, cutoff_date,
) -> dict[int, list[dict]]:
    """
    team_id -> [{player_id, mpg}] using only games <= cutoff_date.
    For leak-free team-strength aggregation in the backtest suite
    (replaces full-season PlayerSeasonStats.mpg rosters).
    """
    from django.db.models import Count, Sum
    from ncaa.models import PlayerGameStats

    rosters: dict[int, list[dict]] = defaultdict(list)
    agg = (PlayerGameStats.objects
           .filter(game__season_year=season_year,
                   game__game_date__lte=cutoff_date,
                   game__status="final",
                   did_not_play=False,
                   team__isnull=False)
           .values("player_id", "team_id")
           .annotate(gp=Count("id"), total_min=Sum("minutes")))
    for r in agg:
        if r["gp"]:
            rosters[r["team_id"]].append({
                "player_id": r["player_id"],
                "mpg": (r["total_min"] or 0.0) / r["gp"],
            })
    return rosters
