"""
nba_team_ratings_importance_backtest.py

Backtest importance weighting variants on NBA Adjusted Team Ratings.

Variants tested:
  baseline   — equal weights (current pipeline)
  b2b_075    — B2B games downweighted 0.75x
  close8_15  — games with |margin| ≤ 8 pts boosted 1.5x
  late20_15  — last 20 games per team boosted 1.5x  [retrodiction only]
  late30_15  — last 30 games per team boosted 1.5x  [retrodiction only]
  po_15      — prior-season playoff games included at 1.5x
  po_20      — prior-season playoff games included at 2.0x
  combined   — B2B 0.75x + last-20 1.5x + close-game 1.5x
  lorentzian — NCAA-style iterative Lorentzian (IMP_C=6, NBA-scaled)

NOTE: late-season variants only affect retrodiction metrics, not holdout predictive
metrics, because the last ~20–30 games fall in the test set (after median cutoff).

Zero changes to the live pipeline.

Usage:
    backend/.venv/bin/python nba_team_ratings_importance_backtest.py
    backend/.venv/bin/python nba_team_ratings_importance_backtest.py --seasons 2024 2025
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import scipy.stats

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402
django.setup()

OUTPUT_DIR = SCRIPT_DIR / "metrics_output"
OUTPUT_DIR.mkdir(exist_ok=True)
RESULTS_CSV = OUTPUT_DIR / "team_ratings_importance_results.csv"

# Production config (from nba/ratings_config.py)
_CFG = {
    "iterations": 8,
    "convergence_threshold": 0.001,
    "prior_games": 5.0,
    "prior_ortg": 115.0,
    "prior_drtg": 115.0,
    "home_court_adj": 2.1,
    "rest_adj_per_day": 0.4,
    "b2b_penalty": 2.1,
}

# Sentinel: game_number=0 means prior-season playoff game (out-of-season)
_PLAYOFF_SENTINEL = 0


# ── CLI ─────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NBA team ratings importance weighting backtest")
    p.add_argument("--seasons", type=int, nargs="+", default=[2022, 2023, 2024, 2025, 2026],
                   help="Season years to evaluate (default: 2022 2023 2024 2025 2026)")
    p.add_argument("--skip-lorentzian", action="store_true",
                   help="Skip the iterative Lorentzian variant (slower)")
    return p.parse_args()


# ── Data structures ─────────────────────────────────────────────────────────────

@dataclass
class _GameRec:
    """Per-team game record for the inline solver."""
    team_id: int
    opp_id: int
    game_id: str
    raw_ortg: float
    raw_drtg: float
    poss: float
    is_home: Optional[bool]
    rest_days: Optional[int]
    is_b2b: bool
    game_date: date
    actual_margin: float   # team's margin from their perspective (positive = win)
    game_number: int       # Nth game in team's season (1-indexed); 0 = prior playoff sentinel
    season_games: int      # total games team played this season (82 typical)


# ── Data loading ────────────────────────────────────────────────────────────────

def _build_game_recs(stats_list, is_playoff_sentinel: bool = False) -> list[_GameRec]:
    """Convert a queryset result list into _GameRec objects."""
    # Build per-game pair lookup: game_id → {team_id: stat}
    game_pair: dict[str, dict] = {}
    for s in stats_list:
        gid = s.game.game_id
        if gid not in game_pair:
            game_pair[gid] = {}
        game_pair[gid][s.team_id] = s

    recs: list[_GameRec] = []
    for s in stats_list:
        gid = s.game.game_id
        pair = game_pair.get(gid, {})
        opp = next((x for tid, x in pair.items() if tid != s.team_id), None)
        if opp is None:
            continue
        hs = s.game.home_score
        aws = s.game.away_score
        if hs is None or aws is None:
            continue
        raw_margin = (hs - aws) * (1 if s.is_home else -1)
        recs.append(_GameRec(
            team_id=s.team_id,
            opp_id=opp.team_id,
            game_id=gid,
            raw_ortg=s.raw_ortg,
            raw_drtg=s.raw_drtg,
            poss=s.poss,
            is_home=s.is_home,
            rest_days=s.game.rest_days_home if s.is_home else s.game.rest_days_away,
            is_b2b=s.game.home_b2b if s.is_home else s.game.away_b2b,
            game_date=s.game.date,
            actual_margin=float(raw_margin),
            game_number=_PLAYOFF_SENTINEL if is_playoff_sentinel else -1,  # -1 = fill later
            season_games=0,
        ))
    return recs


def _assign_game_numbers(recs: list[_GameRec]) -> None:
    """In-place: assign game_number (1..N) per team, sorted by date. Skips sentinels."""
    team_games: dict[int, list[tuple[date, str]]] = defaultdict(list)
    for r in recs:
        if r.game_number == _PLAYOFF_SENTINEL:
            continue
        team_games[r.team_id].append((r.game_date, r.game_id))

    # Sort per team by date, build lookup {(team_id, game_id) → game_number}
    team_gid_num: dict[tuple[int, str], int] = {}
    for tid, dated_games in team_games.items():
        dated_games.sort(key=lambda x: x[0])
        for i, (_, gid) in enumerate(dated_games, start=1):
            team_gid_num[(tid, gid)] = i

    # Assign season_games (total per team)
    team_total: dict[int, int] = {tid: len(g) for tid, g in team_games.items()}

    for r in recs:
        if r.game_number == _PLAYOFF_SENTINEL:
            r.season_games = 0
            continue
        r.game_number = team_gid_num.get((r.team_id, r.game_id), -1)
        r.season_games = team_total.get(r.team_id, 0)


def _load_season_data(
    season_year: int,
    include_prior_playoffs: bool = True,
) -> tuple[list[_GameRec], list[_GameRec], pd.DataFrame, dict[int, int]]:
    """
    Returns:
        reg_recs       — regular-season game records
        playoff_recs   — prior-season playoff records (empty if not available)
        games_df       — DataFrame for prediction evaluation
        actual_wins    — dict {team_id → win count}
    """
    from nba.models import NBATeamGameStats

    # Regular season
    reg_stats = list(
        NBATeamGameStats.objects.select_related("game", "team").filter(
            game__season__year=season_year,
            game__counts_toward_regular_season=True,
            game__status="Final",
            poss__isnull=False, poss__gt=0,
            raw_ortg__isnull=False, raw_drtg__isnull=False,
        )
    )
    reg_recs = _build_game_recs(reg_stats, is_playoff_sentinel=False)
    _assign_game_numbers(reg_recs)

    # Prior-season playoffs
    playoff_recs: list[_GameRec] = []
    if include_prior_playoffs:
        po_stats = list(
            NBATeamGameStats.objects.select_related("game", "team").filter(
                game__season__year=season_year - 1,
                game__season_type="playoffs",
                game__status="Final",
                poss__isnull=False, poss__gt=0,
                raw_ortg__isnull=False, raw_drtg__isnull=False,
            )
        )
        playoff_recs = _build_game_recs(po_stats, is_playoff_sentinel=True)

    # Games DataFrame for evaluation
    seen: set[str] = set()
    game_rows = []
    for s in reg_stats:
        g = s.game
        if g.game_id in seen:
            continue
        if g.home_score is None or g.away_score is None:
            continue
        seen.add(g.game_id)
        game_rows.append({
            "game_id":      g.game_id,
            "date":         g.date,
            "home_team_id": g.home_team_id,
            "away_team_id": g.away_team_id,
            "margin":       g.home_score - g.away_score,
        })
    games_df = pd.DataFrame(game_rows)
    if not games_df.empty:
        games_df["date"] = pd.to_datetime(games_df["date"])
        games_df = games_df.sort_values("date").reset_index(drop=True)

    # Win totals
    actual_wins: dict[int, int] = defaultdict(int)
    for s in reg_stats:
        g = s.game
        if g.home_score is None or g.away_score is None:
            continue
        home_win = g.home_score > g.away_score
        if s.is_home and home_win:
            actual_wins[s.team_id] += 1
        elif not s.is_home and not home_win:
            actual_wins[s.team_id] += 1

    return reg_recs, playoff_recs, games_df, dict(actual_wins)


# ── Team rescale (preserves shrinkage denominator) ──────────────────────────────

def _team_rescale(recs: list[_GameRec], imp_weights: dict[str, float]) -> dict[int, float]:
    """
    Compute per-team rescale so importance weighting doesn't silently tighten
    the Bayesian shrinkage. Mirrors NCAA compute_adjusted_ratings.py:463-503.
    """
    sum_poss: dict[int, float] = defaultdict(float)
    sum_poss_w: dict[int, float] = defaultdict(float)
    for r in recs:
        w = imp_weights.get(r.game_id, 1.0)
        sum_poss[r.team_id] += r.poss
        sum_poss_w[r.team_id] += r.poss * w
    rescale = {}
    for tid, total in sum_poss.items():
        denom = sum_poss_w[tid]
        scale = total / denom if denom > 0 else 1.0
        rescale[tid] = max(0.85, min(1.30, scale))
    return rescale


# ── Importance weight functions ──────────────────────────────────────────────────

def _w_baseline(_recs):
    return {}, {}


def _w_b2b(recs: list[_GameRec], factor: float = 0.75):
    w = {r.game_id: factor for r in recs if r.is_b2b}
    return w, _team_rescale(recs, w)


def _w_close_game(recs: list[_GameRec], threshold: float = 8.0, boost: float = 1.5):
    w = {r.game_id: boost for r in recs if abs(r.actual_margin) <= threshold}
    return w, _team_rescale(recs, w)


def _w_late_season(recs: list[_GameRec], last_n: int = 20, boost: float = 1.5):
    w = {}
    for r in recs:
        if r.game_number == _PLAYOFF_SENTINEL or r.season_games == 0:
            continue
        if r.game_number >= (r.season_games - last_n + 1):
            w[r.game_id] = boost
    return w, _team_rescale(recs, w)


def _w_prior_playoff(recs: list[_GameRec], multiplier: float = 1.5):
    w = {r.game_id: multiplier for r in recs if r.game_number == _PLAYOFF_SENTINEL}
    return w, _team_rescale(recs, w)


def _w_combined(
    recs: list[_GameRec],
    b2b_factor: float = 0.75,
    late_n: int = 20,
    late_boost: float = 1.5,
    close_thresh: float = 8.0,
    close_boost: float = 1.5,
):
    w: dict[str, float] = {}
    for r in recs:
        val = 1.0
        if r.is_b2b:
            val *= b2b_factor
        if r.season_games > 0 and r.game_number != _PLAYOFF_SENTINEL:
            if r.game_number >= (r.season_games - late_n + 1):
                val *= late_boost
        if abs(r.actual_margin) <= close_thresh:
            val *= close_boost
        if val != 1.0:
            w[r.game_id] = val
    return w, _team_rescale(recs, w)


# ── Inline solver (no changes to live ratings_engine.py) ────────────────────────

def _solve(
    game_recs: list[_GameRec],
    imp_weights: dict[str, float],
    team_rescale_map: dict[int, float],
) -> dict[int, dict]:
    """
    Iterative opponent-adjustment. Identical to services/ratings_engine.iterative_adjust
    but multiplies possession weight by imp_weights * team_rescale.
    """
    if not game_recs:
        return {}

    team_ids: set[int] = set()
    for g in game_recs:
        team_ids.add(g.team_id)
        team_ids.add(g.opp_id)

    prior_ortg = _CFG["prior_ortg"]
    prior_drtg = _CFG["prior_drtg"]
    prior_games = _CFG["prior_games"]
    home_court_adj = _CFG["home_court_adj"]
    b2b_penalty = _CFG["b2b_penalty"]
    rest_adj_per_day = _CFG["rest_adj_per_day"]

    adj_off: dict[int, float] = {tid: prior_ortg for tid in team_ids}
    adj_def: dict[int, float] = {tid: prior_drtg for tid in team_ids}

    team_ctx_ortg: dict[int, list] = defaultdict(list)
    team_ctx_drtg: dict[int, list] = defaultdict(list)
    team_poss: dict[int, list] = defaultdict(list)
    team_opps: dict[int, list] = defaultdict(list)
    team_gids: dict[int, list] = defaultdict(list)

    for g in game_recs:
        ctx = 0.0
        if g.is_home is not None and home_court_adj:
            ctx += home_court_adj if g.is_home else -home_court_adj
        if g.is_b2b and b2b_penalty:
            ctx -= b2b_penalty
        elif g.rest_days is not None and rest_adj_per_day:
            ctx += min(max(g.rest_days - 1, 0), 3) * rest_adj_per_day
        team_ctx_ortg[g.team_id].append(g.raw_ortg - ctx)
        team_ctx_drtg[g.team_id].append(g.raw_drtg + ctx)
        team_poss[g.team_id].append(g.poss)
        team_opps[g.team_id].append(g.opp_id)
        team_gids[g.team_id].append(g.game_id)

    all_ortg = [v for vals in team_ctx_ortg.values() for v in vals]
    all_drtg = [v for vals in team_ctx_drtg.values() for v in vals]
    lg_avg_off = sum(all_ortg) / len(all_ortg) if all_ortg else prior_ortg
    lg_avg_def = sum(all_drtg) / len(all_drtg) if all_drtg else prior_drtg

    for _ in range(_CFG["iterations"]):
        new_off: dict[int, float] = {}
        new_def: dict[int, float] = {}
        max_delta = 0.0

        for tid in team_ids:
            ortg_vals = team_ctx_ortg.get(tid, [])
            drtg_vals = team_ctx_drtg.get(tid, [])
            opp_ids = team_opps.get(tid, [])
            poss_vals = team_poss.get(tid, [])
            gids = team_gids.get(tid, [])

            off_sum = lg_avg_off * prior_games
            def_sum = lg_avg_def * prior_games
            total_w = prior_games

            for ortg, drtg, opp_id, poss, gid in zip(
                ortg_vals, drtg_vals, opp_ids, poss_vals, gids
            ):
                w = max(poss / 100.0, 0.5)
                if imp_weights:
                    w *= imp_weights.get(gid, 1.0) * team_rescale_map.get(tid, 1.0)
                opp_adj_def = adj_def.get(opp_id, prior_drtg)
                opp_adj_off = adj_off.get(opp_id, prior_ortg)
                off_sum += (ortg + (lg_avg_off - opp_adj_def)) * w
                def_sum += (drtg + (lg_avg_def - opp_adj_off)) * w
                total_w += w

            no = off_sum / total_w
            nd = def_sum / total_w
            max_delta = max(max_delta,
                            abs(no - adj_off.get(tid, prior_ortg)),
                            abs(nd - adj_def.get(tid, prior_drtg)))
            new_off[tid] = no
            new_def[tid] = nd

        adj_off = new_off
        adj_def = new_def
        if max_delta < _CFG["convergence_threshold"]:
            break

    return {
        tid: {
            "adj_off": adj_off[tid],
            "adj_def": adj_def[tid],
            "adj_net": adj_off[tid] - adj_def[tid],
            "game_count": len(team_ctx_ortg.get(tid, [])),
        }
        for tid in team_ids
    }


def _solve_lorentzian(
    game_recs: list[_GameRec],
    imp_c: float = 6.0,
    imp_floor: float = 0.35,
    close_m: float = 8.0,
    boost_max: float = 1.40,
    freeze_iter: int = 6,
) -> dict[int, dict]:
    """
    NCAA-style iterative importance weighting. Adapted to NBA scale (IMP_C=6 vs NCAA's 40).

    For each iteration up to freeze_iter:
      gap = |adj_net_team - adj_net_opp|
      base = max(imp_floor, 1 / (1 + (gap/imp_c)²))
      closer_than_expected = max(0, |exp_margin| - |actual_margin|)
      closeness_factor = 1 - exp(-closer_than_expected / close_m)
      boost = 1 + (boost_max - 1) * closeness_factor
      w_imp = min(1.0, base * boost)

    After freeze_iter: weights frozen, team_rescale computed once, solver continues.
    """
    if not game_recs:
        return {}

    team_ids: set[int] = set()
    for g in game_recs:
        team_ids.add(g.team_id)
        team_ids.add(g.opp_id)

    prior_ortg = _CFG["prior_ortg"]
    prior_drtg = _CFG["prior_drtg"]
    prior_games = _CFG["prior_games"]
    home_court_adj = _CFG["home_court_adj"]
    b2b_penalty = _CFG["b2b_penalty"]
    rest_adj_per_day = _CFG["rest_adj_per_day"]

    adj_off: dict[int, float] = {tid: prior_ortg for tid in team_ids}
    adj_def: dict[int, float] = {tid: prior_drtg for tid in team_ids}

    # Pre-compute context adjustments (same as _solve)
    team_ctx_ortg: dict[int, list] = defaultdict(list)
    team_ctx_drtg: dict[int, list] = defaultdict(list)
    team_poss: dict[int, list] = defaultdict(list)
    team_opps: dict[int, list] = defaultdict(list)
    team_gids: dict[int, list] = defaultdict(list)
    team_actual_margins: dict[int, list] = defaultdict(list)

    for g in game_recs:
        ctx = 0.0
        if g.is_home is not None and home_court_adj:
            ctx += home_court_adj if g.is_home else -home_court_adj
        if g.is_b2b and b2b_penalty:
            ctx -= b2b_penalty
        elif g.rest_days is not None and rest_adj_per_day:
            ctx += min(max(g.rest_days - 1, 0), 3) * rest_adj_per_day
        team_ctx_ortg[g.team_id].append(g.raw_ortg - ctx)
        team_ctx_drtg[g.team_id].append(g.raw_drtg + ctx)
        team_poss[g.team_id].append(g.poss)
        team_opps[g.team_id].append(g.opp_id)
        team_gids[g.team_id].append(g.game_id)
        team_actual_margins[g.team_id].append(g.actual_margin)

    all_ortg = [v for vals in team_ctx_ortg.values() for v in vals]
    all_drtg = [v for vals in team_ctx_drtg.values() for v in vals]
    lg_avg_off = sum(all_ortg) / len(all_ortg) if all_ortg else prior_ortg
    lg_avg_def = sum(all_drtg) / len(all_drtg) if all_drtg else prior_drtg

    frozen_imp: dict[tuple, float] = {}
    frozen = False
    team_rescale_map: dict[int, float] = {}

    for iteration in range(_CFG["iterations"]):
        new_off: dict[int, float] = {}
        new_def: dict[int, float] = {}
        max_delta = 0.0
        current_imp: dict[tuple, float] = {}

        for tid in team_ids:
            ortg_vals = team_ctx_ortg.get(tid, [])
            drtg_vals = team_ctx_drtg.get(tid, [])
            opp_ids = team_opps.get(tid, [])
            poss_vals = team_poss.get(tid, [])
            gids = team_gids.get(tid, [])
            margins = team_actual_margins.get(tid, [])

            off_sum = lg_avg_off * prior_games
            def_sum = lg_avg_def * prior_games
            total_w = prior_games

            for ortg, drtg, opp_id, poss, gid, actual_margin in zip(
                ortg_vals, drtg_vals, opp_ids, poss_vals, gids, margins
            ):
                # Compute or look up importance weight
                imp_key = (tid, gid)
                if frozen:
                    w_imp = frozen_imp.get(imp_key, 1.0)
                else:
                    gap = abs(
                        (adj_off.get(tid, prior_ortg) - adj_def.get(tid, prior_drtg))
                        - (adj_off.get(opp_id, prior_ortg) - adj_def.get(opp_id, prior_drtg))
                    )
                    base = max(imp_floor, 1.0 / (1.0 + (gap / imp_c) ** 2))
                    exp_margin = (adj_off.get(tid, prior_ortg) - adj_def.get(tid, prior_drtg)
                                  - (adj_off.get(opp_id, prior_ortg) - adj_def.get(opp_id, prior_drtg)))
                    closer = max(0.0, abs(exp_margin) - abs(actual_margin))
                    closeness_factor = 1.0 - math.exp(-closer / close_m) if close_m > 0 else 0.0
                    boost = 1.0 + (boost_max - 1.0) * closeness_factor
                    w_imp = min(1.0, base * boost)
                    current_imp[imp_key] = w_imp

                w = max(poss / 100.0, 0.5) * w_imp
                if frozen and team_rescale_map:
                    w *= team_rescale_map.get(tid, 1.0)

                opp_adj_def = adj_def.get(opp_id, prior_drtg)
                opp_adj_off = adj_off.get(opp_id, prior_ortg)
                off_sum += (ortg + (lg_avg_off - opp_adj_def)) * w
                def_sum += (drtg + (lg_avg_def - opp_adj_off)) * w
                total_w += w

            no = off_sum / total_w
            nd = def_sum / total_w
            max_delta = max(max_delta,
                            abs(no - adj_off.get(tid, prior_ortg)),
                            abs(nd - adj_def.get(tid, prior_drtg)))
            new_off[tid] = no
            new_def[tid] = nd

        adj_off = new_off
        adj_def = new_def

        # Freeze after freeze_iter — compute rescale once
        if not frozen and iteration + 1 == freeze_iter:
            frozen_imp = dict(current_imp)
            frozen = True
            # Build rescale: keyed by team_id using frozen weights
            flat_w = {gid: w for (tid_key, gid), w in frozen_imp.items()}
            sum_poss: dict[int, float] = defaultdict(float)
            sum_poss_w: dict[int, float] = defaultdict(float)
            for g in game_recs:
                w = flat_w.get(g.game_id, 1.0)
                sum_poss[g.team_id] += g.poss
                sum_poss_w[g.team_id] += g.poss * w
            for tid in sum_poss:
                denom = sum_poss_w[tid]
                scale = sum_poss[tid] / denom if denom > 0 else 1.0
                team_rescale_map[tid] = max(0.85, min(1.30, scale))

        if max_delta < _CFG["convergence_threshold"]:
            break

    return {
        tid: {
            "adj_off": adj_off[tid],
            "adj_def": adj_def[tid],
            "adj_net": adj_off[tid] - adj_def[tid],
            "game_count": len(team_ctx_ortg.get(tid, [])),
        }
        for tid in team_ids
    }


# ── Evaluation helpers (identical to recency backtest) ──────────────────────────

def _predict_margins(
    ratings: dict[int, dict],
    games_df: pd.DataFrame,
    hca: float,
) -> tuple[np.ndarray, np.ndarray]:
    predicted, actual = [], []
    for _, row in games_df.iterrows():
        h, a = int(row["home_team_id"]), int(row["away_team_id"])
        if h not in ratings or a not in ratings:
            continue
        predicted.append(ratings[h]["adj_net"] - ratings[a]["adj_net"] + hca)
        actual.append(row["margin"])
    return np.array(predicted), np.array(actual)


def _game_metrics(pred: np.ndarray, actual: np.ndarray, sigma: float) -> dict:
    if len(pred) < 5:
        return {k: float("nan") for k in ["n", "brier", "logloss", "win_acc", "margin_mae"]}
    p_home = np.clip(scipy.stats.norm.cdf(pred / sigma), 1e-7, 1 - 1e-7)
    y = (actual > 0).astype(float)
    return {
        "n":          len(pred),
        "brier":      float(np.mean((p_home - y) ** 2)),
        "logloss":    float(-np.mean(y * np.log(p_home) + (1 - y) * np.log(1 - p_home))),
        "win_acc":    float(np.mean((pred > 0) == (actual > 0))),
        "margin_mae": float(np.mean(np.abs(pred - actual))),
    }


def _actual_net_ratings(games_df: pd.DataFrame) -> dict[int, float]:
    margins: dict[int, list] = defaultdict(list)
    for _, row in games_df.iterrows():
        margins[int(row["home_team_id"])].append(row["margin"])
        margins[int(row["away_team_id"])].append(-row["margin"])
    return {tid: float(np.mean(ms)) for tid, ms in margins.items() if ms}


def _retrodiction_metrics(
    ratings: dict[int, dict],
    actual_wins: dict[int, int],
    actual_net: dict[int, float],
) -> dict:
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_squared_error, r2_score

    pairs_wins = [(ratings[tid]["adj_net"], w) for tid, w in actual_wins.items() if tid in ratings]
    pairs_net = [(ratings[tid]["adj_net"], actual_net[tid]) for tid in actual_net if tid in ratings]

    result: dict = {}

    if len(pairs_wins) >= 5:
        X = np.array([x for x, _ in pairs_wins]).reshape(-1, 1)
        y = np.array([w for _, w in pairs_wins])
        reg = LinearRegression().fit(X, y)
        result["retro_r2"] = float(reg.score(X, y))
        result["retro_rmse_wins"] = float(np.sqrt(mean_squared_error(y, reg.predict(X))))
        result["retro_n"] = len(pairs_wins)
    else:
        result.update({"retro_r2": float("nan"), "retro_rmse_wins": float("nan"), "retro_n": 0})

    if len(pairs_net) >= 5:
        pred_net = np.array([p for p, _ in pairs_net])
        true_net = np.array([t for _, t in pairs_net])
        result["team_rmse"] = float(np.sqrt(np.mean((pred_net - true_net) ** 2)))
        result["team_r2"] = float(r2_score(true_net, pred_net))
    else:
        result.update({"team_rmse": float("nan"), "team_r2": float("nan")})

    return result


# ── Variant definitions ──────────────────────────────────────────────────────────

def _build_variants(
    train_recs: list[_GameRec],
    po_recs: list[_GameRec],
    skip_lorentzian: bool,
) -> list[dict]:
    """
    Each variant dict: {label, note, use_playoff, weight_fn_or_none, lorentzian}
    weight_fn: callable(recs) → (imp_weights, team_rescale) or None for baseline
    lorentzian: bool
    """
    train_with_po = train_recs + po_recs  # for playoff variants

    def _run(recs, weight_fn):
        if weight_fn is None:
            return {}, {}
        return weight_fn(recs)

    variants = [
        {
            "label": "baseline",
            "note": "",
            "recs_fn": lambda: train_recs,
            "weight_fn": None,
            "lorentzian": False,
        },
        {
            "label": "b2b_075",
            "note": "B2B games → 0.75x",
            "recs_fn": lambda: train_recs,
            "weight_fn": lambda r: _w_b2b(r, factor=0.75),
            "lorentzian": False,
        },
        {
            "label": "close8_15",
            "note": "|margin| ≤ 8 → 1.5x",
            "recs_fn": lambda: train_recs,
            "weight_fn": lambda r: _w_close_game(r, threshold=8.0, boost=1.5),
            "lorentzian": False,
        },
        {
            "label": "late20_15",
            "note": "Last 20 games → 1.5x  [retrodiction only]",
            "recs_fn": lambda: train_recs,
            "weight_fn": lambda r: _w_late_season(r, last_n=20, boost=1.5),
            "lorentzian": False,
        },
        {
            "label": "late30_15",
            "note": "Last 30 games → 1.5x  [retrodiction only]",
            "recs_fn": lambda: train_recs,
            "weight_fn": lambda r: _w_late_season(r, last_n=30, boost=1.5),
            "lorentzian": False,
        },
        {
            "label": "po_15",
            "note": "Prior playoff games at 1.5x",
            "recs_fn": lambda: train_with_po,
            "weight_fn": lambda r: _w_prior_playoff(r, multiplier=1.5),
            "lorentzian": False,
        },
        {
            "label": "po_20",
            "note": "Prior playoff games at 2.0x",
            "recs_fn": lambda: train_with_po,
            "weight_fn": lambda r: _w_prior_playoff(r, multiplier=2.0),
            "lorentzian": False,
        },
        {
            "label": "combined",
            "note": "B2B 0.75x + last-20 1.5x + close 1.5x",
            "recs_fn": lambda: train_recs,
            "weight_fn": lambda r: _w_combined(r),
            "lorentzian": False,
        },
    ]

    if not skip_lorentzian:
        variants.append({
            "label": "lorentzian",
            "note": "NCAA-style iterative (IMP_C=6, freeze iter 6)",
            "recs_fn": lambda: train_recs,
            "weight_fn": None,
            "lorentzian": True,
        })

    return variants


# ── Per-season evaluation ───────────────────────────────────────────────────────

def _eval_season(
    season_year: int,
    skip_lorentzian: bool,
) -> list[dict]:
    print(f"\n  Loading {season_year} data...")
    reg_recs, po_recs, games_df, actual_wins = _load_season_data(season_year)
    if games_df.empty:
        print(f"  WARNING: No games for {season_year}, skipping.")
        return []
    print(f"    {len(games_df)} reg games  |  {len(po_recs)} prior playoff recs  |  {len(actual_wins)} teams")

    cutoff = games_df["date"].median().date()
    train_ids = set(games_df[games_df["date"].dt.date <= cutoff]["game_id"])
    test_df = games_df[games_df["date"].dt.date > cutoff].copy()
    train_recs = [r for r in reg_recs if r.game_id in train_ids]
    print(f"    Cutoff {cutoff}: {len(train_ids)} train / {len(test_df)} test games")

    actual_net = _actual_net_ratings(games_df)

    # Baseline sigma (locked for fair comparison)
    base_w, base_r = {}, {}
    base_ratings = _solve(train_recs, base_w, base_r)
    base_pred, base_actual = _predict_margins(base_ratings, test_df, _CFG["home_court_adj"])
    sigma = float(np.std(base_pred - base_actual)) if len(base_pred) >= 5 else 12.0
    print(f"    Sigma: {sigma:.2f}")

    # Full-season baseline for retrodiction
    base_full = _solve(reg_recs, {}, {})

    variants = _build_variants(train_recs, po_recs, skip_lorentzian)

    # For retrodiction with playoff variants, need full reg + po recs
    full_recs_with_po = reg_recs + po_recs

    results = []
    for v in variants:
        label = v["label"]
        t0 = time.time()

        # ── Within-season holdout ─────────────────────────────────────────────
        train_set = v["recs_fn"]()
        # For holdout, filter to training game IDs (po_recs are always pre-cutoff)
        holdout_train = [r for r in train_set if r.game_id in train_ids or r.game_number == _PLAYOFF_SENTINEL]

        if v["lorentzian"]:
            train_ratings = _solve_lorentzian(holdout_train)
        else:
            if v["weight_fn"] is not None:
                iw, tr = v["weight_fn"](holdout_train)
            else:
                iw, tr = {}, {}
            train_ratings = _solve(holdout_train, iw, tr)

        pred, actual = _predict_margins(train_ratings, test_df, _CFG["home_court_adj"])
        game_m = _game_metrics(pred, actual, sigma)

        # ── Full-season retrodiction ───────────────────────────────────────────
        if v["lorentzian"]:
            full_set = reg_recs
            full_ratings = _solve_lorentzian(full_set)
        else:
            if v["weight_fn"] is not None:
                full_set = v["recs_fn"]()
                # Replace train_recs with reg_recs for full-season sets
                if full_set is train_recs:
                    full_set = reg_recs
                else:
                    full_set = full_recs_with_po
                iw_f, tr_f = v["weight_fn"](full_set)
            else:
                full_set = reg_recs
                iw_f, tr_f = {}, {}
            full_ratings = _solve(full_set, iw_f, tr_f)

        retro = _retrodiction_metrics(full_ratings, actual_wins, actual_net)

        elapsed = time.time() - t0
        row = {
            "season": season_year,
            "label": label,
            "note": v["note"],
            "is_baseline": label == "baseline",
            **game_m,
            **retro,
            "elapsed_s": round(elapsed, 2),
        }
        results.append(row)

        late_flag = "  [retrodiction only]" if "late" in label else ""
        print(
            f"    {label:<14}  Brier={game_m['brier']:.4f}  LL={game_m['logloss']:.4f}"
            f"  WinAcc={game_m['win_acc']*100:.1f}%  MAE={game_m['margin_mae']:.2f}"
            f"  TeamRMSE={retro['team_rmse']:.2f}  RetroR²={retro['retro_r2']:.3f}"
            f"  ({elapsed:.1f}s){late_flag}"
        )

    return results


# ── Summary (identical structure to recency backtest) ────────────────────────────

_METRIC_COLS = ["brier", "logloss", "win_acc", "margin_mae", "team_rmse", "retro_r2"]
_HDR = f"  {'Variant':<16} {'Brier':>8} {'LogLoss':>8} {'WinAcc%':>8} {'MrgMAE':>8} {'TeamRMSE':>10} {'RetroR²':>8}"


def _fmt_row(label, row, note=""):
    line = (
        f"  {label:<16}"
        f" {row['brier']:>8.4f}"
        f" {row['logloss']:>8.4f}"
        f" {row['win_acc']*100:>8.1f}"
        f" {row['margin_mae']:>8.2f}"
        f" {row['team_rmse']:>10.3f}"
        f" {row['retro_r2']:>8.3f}"
    )
    if note:
        line += f"  {note}"
    return line


def _print_summary(all_results: list[dict], seasons: list[int]) -> None:
    df = pd.DataFrame(all_results)

    label_order = df[df["season"] == seasons[0]]["label"].tolist()

    def _make_avg(frame):
        avg = frame.groupby("label")[_METRIC_COLS].mean().reset_index()
        avg["is_baseline"] = avg["label"] == "baseline"
        # Keep label order
        avg = avg.set_index("label").reindex(label_order).reset_index()
        return avg

    avg = _make_avg(df)
    base_row = avg[avg["is_baseline"]]

    print(f"\n{'='*96}")
    print(f"AGGREGATE — averaged over {len(seasons)} seasons {seasons}")
    print(f"{'='*96}")
    print(_HDR)
    print("  " + "-" * 92)
    for _, row in avg.iterrows():
        note = "← BASELINE" if row["is_baseline"] else ""
        print(_fmt_row(row["label"], row, note=note))

    print()
    def _best(col, ascending, arrow):
        sub = avg.dropna(subset=[col])
        if sub.empty:
            return
        idx = sub[col].idxmin() if ascending else sub[col].idxmax()
        winner = sub.loc[idx]
        delta = ""
        if not base_row.empty:
            b = base_row.iloc[0][col]
            diff = b - winner[col] if ascending else winner[col] - b
            pct = diff / abs(b) * 100 if b else 0
            delta = f"  (Δ={diff:+.4f}, {pct:+.1f}% vs baseline)"
        print(f"  Best {col} {arrow}: {winner['label']}{delta}")

    _best("brier",      True,  "↓")
    _best("logloss",    True,  "↓")
    _best("win_acc",    False, "↑")
    _best("margin_mae", True,  "↓")
    _best("team_rmse",  True,  "↓")
    _best("retro_r2",   False, "↑")

    # Joint rank
    valid = avg.copy()
    rank_cols = []
    for col, asc in [("brier", True), ("logloss", True), ("win_acc", False),
                     ("margin_mae", True), ("team_rmse", True), ("retro_r2", False)]:
        if col in valid.columns and not valid[col].isna().all():
            valid[f"_r_{col}"] = valid[col].rank(ascending=asc)
            rank_cols.append(f"_r_{col}")
    if rank_cols:
        valid["_joint"] = valid[rank_cols].sum(axis=1)
        best = valid.loc[valid["_joint"].idxmin()]
        print(f"\n  Best combined (joint rank, {len(rank_cols)} metrics): {best['label']}")

    # Per-season breakdown
    print(f"\n{'='*96}")
    print("PER-SEASON BREAKDOWN")
    print(f"{'='*96}")
    for season in seasons:
        s_df = df[df["season"] == season]
        if s_df.empty:
            continue
        s_avg = _make_avg(s_df)
        s_base = s_avg[s_avg["is_baseline"]]
        print(f"\n  Season {season}")
        print(_HDR)
        print("  " + "-" * 92)
        for _, row in s_avg.iterrows():
            beats = []
            if not s_base.empty and not row["is_baseline"]:
                b = s_base.iloc[0]
                if row["brier"] < b["brier"]:        beats.append("Brier")
                if row["logloss"] < b["logloss"]:    beats.append("LL")
                if row["win_acc"] > b["win_acc"]:    beats.append("WinAcc")
                if row["margin_mae"] < b["margin_mae"]: beats.append("MAE")
                if row["team_rmse"] < b["team_rmse"]: beats.append("TeamRMSE")
                if row["retro_r2"] > b["retro_r2"]:  beats.append("R²")
            note = ("← BASELINE" if row["is_baseline"]
                    else (f"beats baseline: {', '.join(beats)}" if beats else ""))
            print(_fmt_row(row["label"], row, note=note))

    # Win summary
    predictive_cols = {"brier", "logloss", "win_acc", "margin_mae"}
    wins: list[tuple] = []
    for season in seasons:
        s_df = df[df["season"] == season]
        if s_df.empty:
            continue
        s_avg = _make_avg(s_df)
        s_base = s_avg[s_avg["is_baseline"]]
        if s_base.empty:
            continue
        b = s_base.iloc[0]
        for _, row in s_avg[~s_avg["is_baseline"]].iterrows():
            beats = []
            if row["brier"] < b["brier"]:        beats.append("Brier")
            if row["logloss"] < b["logloss"]:    beats.append("LL")
            if row["win_acc"] > b["win_acc"]:    beats.append("WinAcc")
            if row["margin_mae"] < b["margin_mae"]: beats.append("MAE")
            if beats:
                wins.append((season, row["label"], beats))

    print(f"\n{'='*96}")
    print("IMPORTANCE WIN SUMMARY (predictive metrics only: Brier, LL, WinAcc, MAE)")
    print(f"{'='*96}")
    if wins:
        for season, label, cols in wins:
            print(f"  Season {season}  {label:<14}  beats baseline on: {', '.join(cols)}")
    else:
        print("  Baseline wins all predictive metrics in every season.")

    print(f"\n{'='*96}")
    print(f"Full results: {RESULTS_CSV}")
    print(f"{'='*96}\n")


# ── Main ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    seasons = args.seasons

    print(f"\n{'='*96}")
    print("NBA TEAM RATINGS — IMPORTANCE WEIGHTING BACKTEST")
    print(f"  Seasons       : {seasons}")
    print(f"  Variants      : baseline, b2b_075, close8_15, late20_15, late30_15, po_15, po_20, combined"
          + ("" if args.skip_lorentzian else ", lorentzian"))
    print(f"  Solver        : inline copy of iterative_adjust (no live pipeline changes)")
    print(f"  Holdout       : within-season median split + full-season retrodiction")
    print(f"  Late-season   : NOTE — last-N game variants only affect retrodiction (test set games)")
    print(f"{'='*96}")

    all_results: list[dict] = []
    for season in seasons:
        rows = _eval_season(season, args.skip_lorentzian)
        all_results.extend(rows)

    if not all_results:
        print("No results generated.")
        return

    df = pd.DataFrame(all_results)
    df.to_csv(RESULTS_CSV, index=False)
    print(f"\n[SAVED] {RESULTS_CSV}")

    _print_summary(all_results, seasons)


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    main()
