"""
nba_team_ratings_recency_backtest.py

Backtest recency weighting on NBA Adjusted Team Ratings.

Methodology:
  - Within-season split: train first half, predict second-half game outcomes
  - Full-season retrodiction: adj_net vs actual win totals (R²/RMSE)
  - Grid: baseline (no decay) + half-lives of 30, 60, 90 days
  - Evaluated on 2 full seasons (2024 and 2025), averaged

Zero changes to the live pipeline — solver is copied inline with recency added.

Usage:
    backend/.venv/bin/python nba_team_ratings_recency_backtest.py
    backend/.venv/bin/python nba_team_ratings_recency_backtest.py --seasons 2024 2025
    backend/.venv/bin/python nba_team_ratings_recency_backtest.py --half-lives None,30,60,90
    backend/.venv/bin/python nba_team_ratings_recency_backtest.py --seasons 2025 --half-lives None,45,60
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import scipy.stats

SCRIPT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(SCRIPT_DIR / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402
django.setup()

OUTPUT_DIR = SCRIPT_DIR / "metrics_output"
OUTPUT_DIR.mkdir(exist_ok=True)
RESULTS_CSV = OUTPUT_DIR / "team_ratings_recency_results.csv"

# Production config values (from nba/ratings_config.py)
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


# ── CLI ─────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NBA team ratings recency weighting backtest")
    p.add_argument("--seasons", type=int, nargs="+", default=[2024, 2025],
                   help="Season years to evaluate (default: 2024 2025)")
    p.add_argument("--half-lives", default="None,30,60,90",
                   help="Comma-separated half-lives in days. 'None' = baseline. (default: None,30,60,90)")
    return p.parse_args()


def _parse_half_lives(s: str) -> list[Optional[float]]:
    out: list[Optional[float]] = []
    for part in s.split(","):
        part = part.strip()
        out.append(None if part.lower() == "none" else float(part))
    return out


# ── Data structures ─────────────────────────────────────────────────────────────

@dataclass
class _GameRec:
    """Minimal game record for the inline solver."""
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


# ── Data loading ────────────────────────────────────────────────────────────────

def _load_season_data(season_year: int) -> tuple[list[_GameRec], pd.DataFrame, dict[int, int]]:
    """
    Returns:
        game_recs   — list of _GameRec for all qualifying regular-season games
        games_df    — DataFrame (game_id, date, home_team_id, away_team_id, margin)
        actual_wins — dict {team_id -> win count}
    """
    from nba.models import NBAGame, NBATeamGameStats

    stats_qs = (
        NBATeamGameStats.objects
        .filter(
            game__season__year=season_year,
            game__counts_toward_regular_season=True,
            game__status="Final",
            poss__isnull=False,
            poss__gt=0,
            raw_ortg__isnull=False,
            raw_drtg__isnull=False,
        )
        .select_related("game", "team")
    )
    stats_list = list(stats_qs)

    # Build per-game pair lookup
    game_pair: dict[str, dict[int, NBATeamGameStats]] = {}
    for s in stats_list:
        gid = s.game_id
        if gid not in game_pair:
            game_pair[gid] = {}
        game_pair[gid][s.team_id] = s

    game_recs: list[_GameRec] = []
    for s in stats_list:
        pair = game_pair.get(s.game_id, {})
        opp = next((x for tid, x in pair.items() if tid != s.team_id), None)
        if opp is None:
            continue
        game_recs.append(_GameRec(
            team_id=s.team_id,
            opp_id=opp.team_id,
            game_id=s.game.game_id,
            raw_ortg=s.raw_ortg,
            raw_drtg=s.raw_drtg,
            poss=s.poss,
            is_home=s.is_home,
            rest_days=s.game.rest_days_home if s.is_home else s.game.rest_days_away,
            is_b2b=s.game.home_b2b if s.is_home else s.game.away_b2b,
            game_date=s.game.date,
        ))

    # Build games_df (unique games, home perspective)
    seen: set[str] = set()
    game_rows = []
    for s in stats_list:
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
    for row in game_rows:
        # home_team_id / away_team_id are PKs from the game's FK fields
        pass
    # Re-derive from stats_list for accuracy
    for s in stats_list:
        if s.game.home_score is None or s.game.away_score is None:
            continue
        home_win = s.game.home_score > s.game.away_score
        if s.is_home and home_win:
            actual_wins[s.team_id] += 1
        elif not s.is_home and not home_win:
            actual_wins[s.team_id] += 1

    return game_recs, games_df, dict(actual_wins)


# ── Recency weight computation ──────────────────────────────────────────────────

def _compute_recency_weights(
    game_recs: list[_GameRec],
    half_life_days: Optional[float],
    ref_date: date,
) -> tuple[dict[str, float], dict[int, float]]:
    """
    Returns (w_time, team_rescale):
      w_time[game_id]       = exponential decay weight for that game
      team_rescale[team_id] = calibration factor to preserve shrinkage denominator

    When half_life_days is None, returns all 1.0 (baseline).
    """
    if half_life_days is None:
        return {}, {}

    lam = math.log(2) / half_life_days

    w_time: dict[str, float] = {}
    for rec in game_recs:
        days_ago = max(0, (ref_date - rec.game_date).days)
        w_time[rec.game_id] = math.exp(-lam * days_ago)

    # Per-team rescale: keeps Σ(poss * w_time * scale) == Σ(poss)
    # so Bayesian shrinkage denominator is unchanged
    team_poss_sum: dict[int, float] = defaultdict(float)
    team_poss_w_sum: dict[int, float] = defaultdict(float)
    for rec in game_recs:
        w = w_time[rec.game_id]
        team_poss_sum[rec.team_id] += rec.poss
        team_poss_w_sum[rec.team_id] += rec.poss * w

    team_rescale: dict[int, float] = {}
    for tid, total in team_poss_sum.items():
        denom = team_poss_w_sum[tid]
        scale = total / denom if denom > 0 else 1.0
        team_rescale[tid] = max(0.80, min(1.25, scale))

    return w_time, team_rescale


# ── Inline solver (no changes to live ratings_engine.py) ───────────────────────

def _solve(
    game_recs: list[_GameRec],
    w_time: dict[str, float],
    team_rescale: dict[int, float],
) -> dict[int, dict]:
    """
    Iterative opponent-adjustment, identical to services/ratings_engine.iterative_adjust
    but multiplies possession weight by recency_weight * team_rescale.
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

    team_ctx_ortg: dict[int, list[float]] = defaultdict(list)
    team_ctx_drtg: dict[int, list[float]] = defaultdict(list)
    team_poss: dict[int, list[float]] = defaultdict(list)
    team_opps: dict[int, list[int]] = defaultdict(list)
    team_game_ids: dict[int, list[str]] = defaultdict(list)

    for g in game_recs:
        ctx = 0.0
        if g.is_home is not None and home_court_adj:
            ctx += home_court_adj if g.is_home else -home_court_adj
        if g.is_b2b and b2b_penalty:
            ctx -= b2b_penalty
        elif g.rest_days is not None and rest_adj_per_day:
            extra_rest = min(max(g.rest_days - 1, 0), 3)
            ctx += extra_rest * rest_adj_per_day

        team_ctx_ortg[g.team_id].append(g.raw_ortg - ctx)
        team_ctx_drtg[g.team_id].append(g.raw_drtg + ctx)
        team_poss[g.team_id].append(g.poss)
        team_opps[g.team_id].append(g.opp_id)
        team_game_ids[g.team_id].append(g.game_id)

    all_ctx_ortg = [v for vals in team_ctx_ortg.values() for v in vals]
    all_ctx_drtg = [v for vals in team_ctx_drtg.values() for v in vals]
    lg_avg_off = sum(all_ctx_ortg) / len(all_ctx_ortg) if all_ctx_ortg else prior_ortg
    lg_avg_def = sum(all_ctx_drtg) / len(all_ctx_drtg) if all_ctx_drtg else prior_drtg

    for _ in range(_CFG["iterations"]):
        new_adj_off: dict[int, float] = {}
        new_adj_def: dict[int, float] = {}
        max_delta = 0.0

        for tid in team_ids:
            ortg_vals = team_ctx_ortg.get(tid, [])
            drtg_vals = team_ctx_drtg.get(tid, [])
            opp_ids = team_opps.get(tid, [])
            poss_vals = team_poss.get(tid, [])
            gids = team_game_ids.get(tid, [])

            off_weighted_sum = lg_avg_off * prior_games
            def_weighted_sum = lg_avg_def * prior_games
            total_weight = prior_games

            for ortg, drtg, opp_id, poss, gid in zip(
                ortg_vals, drtg_vals, opp_ids, poss_vals, gids
            ):
                w = max(poss / 100.0, 0.5)
                # Apply recency weighting when active
                if w_time:
                    w *= w_time.get(gid, 1.0) * team_rescale.get(tid, 1.0)

                opp_adj_def = adj_def.get(opp_id, prior_drtg)
                opp_adj_off = adj_off.get(opp_id, prior_ortg)
                off_weighted_sum += (ortg + (lg_avg_off - opp_adj_def)) * w
                def_weighted_sum += (drtg + (lg_avg_def - opp_adj_off)) * w
                total_weight += w

            new_off = off_weighted_sum / total_weight
            new_def = def_weighted_sum / total_weight
            max_delta = max(
                max_delta,
                abs(new_off - adj_off.get(tid, prior_ortg)),
                abs(new_def - adj_def.get(tid, prior_drtg)),
            )
            new_adj_off[tid] = new_off
            new_adj_def[tid] = new_def

        adj_off = new_adj_off
        adj_def = new_adj_def
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


# ── Evaluation helpers ──────────────────────────────────────────────────────────

def _predict_margins(
    ratings: dict[int, dict],
    games_df: pd.DataFrame,
    hca: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (predicted_margins, actual_margins) for games where both teams rated."""
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
    p_home = scipy.stats.norm.cdf(pred / sigma)
    p_home = np.clip(p_home, 1e-7, 1 - 1e-7)
    y = (actual > 0).astype(float)
    brier = float(np.mean((p_home - y) ** 2))
    logloss = float(-np.mean(y * np.log(p_home) + (1 - y) * np.log(1 - p_home)))
    win_acc = float(np.mean((pred > 0) == (actual > 0)))
    margin_mae = float(np.mean(np.abs(pred - actual)))
    return {"n": len(pred), "brier": brier, "logloss": logloss,
            "win_acc": win_acc, "margin_mae": margin_mae}


def _retrodiction_metrics(
    ratings: dict[int, dict],
    actual_wins: dict[int, int],
    actual_net: dict[int, float],
) -> dict:
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_squared_error, r2_score

    # R²: adj_net → wins
    pairs_wins = [
        (ratings[tid]["adj_net"], w)
        for tid, w in actual_wins.items() if tid in ratings
    ]
    # RMSE: adj_net vs actual net rating
    pairs_net = [
        (ratings[tid]["adj_net"], actual_net[tid])
        for tid in actual_net if tid in ratings
    ]

    result = {}

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


def _actual_net_ratings(games_df: pd.DataFrame) -> dict[int, float]:
    """Simple actual net rating: average margin (home perspective) per team."""
    margins: dict[int, list[float]] = defaultdict(list)
    for _, row in games_df.iterrows():
        margins[int(row["home_team_id"])].append(row["margin"])
        margins[int(row["away_team_id"])].append(-row["margin"])
    return {tid: float(np.mean(ms)) for tid, ms in margins.items() if ms}


# ── Per-season evaluation ───────────────────────────────────────────────────────

def _eval_season(
    season_year: int,
    half_lives: list[Optional[float]],
) -> list[dict]:
    print(f"\n  Loading {season_year} data...")
    game_recs, games_df, actual_wins = _load_season_data(season_year)
    if games_df.empty:
        print(f"  WARNING: No games found for {season_year}, skipping.")
        return []
    print(f"    {len(games_df)} games  |  {len(actual_wins)} teams with wins")

    # Within-season split at median date
    cutoff = games_df["date"].median().date()
    train_ids = set(games_df[games_df["date"].dt.date <= cutoff]["game_id"])
    test_df = games_df[games_df["date"].dt.date > cutoff].copy()
    train_recs = [r for r in game_recs if r.game_id in train_ids]
    print(f"    Train cutoff {cutoff}: {len(train_ids)} train / {len(test_df)} test games")

    # Reference date for recency weights = last game date in season
    ref_date = max(r.game_date for r in game_recs)

    # Actual net ratings (full season, for RMSE)
    actual_net = _actual_net_ratings(games_df)

    # Compute baseline sigma from baseline predictions on test set
    baseline_w_time, baseline_rescale = _compute_recency_weights(train_recs, None, ref_date)
    baseline_ratings = _solve(train_recs, baseline_w_time, baseline_rescale)
    base_pred, base_actual = _predict_margins(baseline_ratings, test_df, _CFG["home_court_adj"])
    if len(base_pred) >= 5:
        sigma = float(np.std(base_pred - base_actual))
    else:
        sigma = 12.0  # fallback
    print(f"    Baseline prediction sigma: {sigma:.2f}")

    results = []
    for hl in half_lives:
        label = f"hl={'None' if hl is None else f'{int(hl)}d'}"
        t0 = time.time()

        # ── Within-season split ────────────────────────────────────────────────
        w_time, team_rescale = _compute_recency_weights(train_recs, hl, ref_date)
        train_ratings = _solve(train_recs, w_time, team_rescale)
        pred, actual = _predict_margins(train_ratings, test_df, _CFG["home_court_adj"])
        game_m = _game_metrics(pred, actual, sigma)

        # ── Full-season retrodiction ───────────────────────────────────────────
        w_time_full, rescale_full = _compute_recency_weights(game_recs, hl, ref_date)
        full_ratings = _solve(game_recs, w_time_full, rescale_full)
        retro = _retrodiction_metrics(full_ratings, actual_wins, actual_net)

        elapsed = time.time() - t0
        row = {
            "season": season_year,
            "half_life": hl,
            "label": label,
            "is_baseline": hl is None,
            **game_m,
            **retro,
            "elapsed_s": round(elapsed, 2),
        }
        results.append(row)

        print(
            f"    {label:<10}  Brier={game_m['brier']:.4f}  LL={game_m['logloss']:.4f}"
            f"  WinAcc={game_m['win_acc']*100:.1f}%  MAE={game_m['margin_mae']:.2f}"
            f"  TeamRMSE={retro['team_rmse']:.2f}  RetroR²={retro['retro_r2']:.3f}"
            f"  ({elapsed:.1f}s)"
        )

    return results


# ── Summary table ───────────────────────────────────────────────────────────────

_METRIC_COLS = ["brier", "logloss", "win_acc", "margin_mae", "team_rmse", "retro_r2"]
_HDR = f"  {'Variant':<12} {'Brier':>8} {'LogLoss':>8} {'WinAcc%':>8} {'MrgMAE':>8} {'TeamRMSE':>10} {'RetroR²':>8}"


def _fmt_row(label: str, row, baseline_row=None, note: str = "") -> str:
    line = (
        f"  {label:<12}"
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


def _best_flags(avg: pd.DataFrame, base_row: pd.DataFrame) -> None:
    """Print best-per-metric lines with delta vs baseline."""
    def _best(col: str, ascending: bool, arrow: str) -> None:
        sub = avg.dropna(subset=[col])
        if sub.empty:
            return
        idx = sub[col].idxmin() if ascending else sub[col].idxmax()
        winner = sub.loc[idx]
        label = winner["label"]
        delta = ""
        if not base_row.empty:
            b_val = base_row.iloc[0][col]
            diff = b_val - winner[col] if ascending else winner[col] - b_val
            pct = diff / abs(b_val) * 100 if b_val else 0
            delta = f"  (Δ={diff:+.4f}, {pct:+.1f}% vs baseline)"
        print(f"  Best {col} {arrow}: {label}{delta}")

    _best("brier",      ascending=True,  arrow="↓")
    _best("logloss",    ascending=True,  arrow="↓")
    _best("win_acc",    ascending=False, arrow="↑")
    _best("margin_mae", ascending=True,  arrow="↓")
    _best("team_rmse",  ascending=True,  arrow="↓")
    _best("retro_r2",   ascending=False, arrow="↑")


def _joint_rank(avg: pd.DataFrame) -> str:
    valid = avg.copy()
    rank_cols = []
    for col, asc in [("brier", True), ("logloss", True), ("win_acc", False),
                     ("margin_mae", True), ("team_rmse", True), ("retro_r2", False)]:
        if col in valid.columns and not valid[col].isna().all():
            valid[f"_r_{col}"] = valid[col].rank(ascending=asc)
            rank_cols.append(f"_r_{col}")
    if not rank_cols:
        return "n/a"
    valid["_joint"] = valid[rank_cols].sum(axis=1)
    return valid.loc[valid["_joint"].idxmin(), "label"]


def _print_summary(all_results: list[dict], seasons: list[int]) -> None:
    df = pd.DataFrame(all_results)

    def _make_avg(frame: pd.DataFrame) -> pd.DataFrame:
        avg = (
            frame.groupby("half_life", dropna=False)[_METRIC_COLS]
            .mean()
            .reset_index()
        )
        avg["label"] = avg["half_life"].apply(
            lambda x: f"hl={'None' if pd.isna(x) else f'{int(x)}d'}"
        )
        avg["is_baseline"] = avg["half_life"].isna()
        return avg

    # ── Aggregate table ───────────────────────────────────────────────────────
    avg = _make_avg(df)
    base_row = avg[avg["is_baseline"]]

    print(f"\n{'='*92}")
    print(f"AGGREGATE — averaged over {len(seasons)} seasons {seasons}")
    print(f"{'='*92}")
    print(_HDR)
    print("  " + "-" * 88)
    for _, row in avg.iterrows():
        note = "← BASELINE" if row["is_baseline"] else ""
        print(_fmt_row(row["label"], row, note=note))

    print()
    _best_flags(avg, base_row)
    print(f"\n  Best combined (joint rank, 6 metrics): {_joint_rank(avg)}")

    # ── Per-season tables ─────────────────────────────────────────────────────
    # Build label order from first season so output is consistent
    label_order = avg["label"].tolist()

    print(f"\n{'='*92}")
    print("PER-SEASON BREAKDOWN")
    print(f"{'='*92}")

    for season in seasons:
        s_df = df[df["season"] == season]
        if s_df.empty:
            continue
        s_avg = _make_avg(s_df)
        s_base = s_avg[s_avg["is_baseline"]]

        # Reorder rows to match label_order
        s_avg = s_avg.set_index("label").reindex(label_order).reset_index()

        print(f"\n  Season {season}")
        print(_HDR)
        print("  " + "-" * 88)
        for _, row in s_avg.iterrows():
            # Flag any recency variant that beats baseline on a metric
            beats = []
            if not s_base.empty:
                b = s_base.iloc[0]
                if not row["is_baseline"]:
                    if row["brier"] < b["brier"]:        beats.append("Brier")
                    if row["logloss"] < b["logloss"]:    beats.append("LL")
                    if row["win_acc"] > b["win_acc"]:    beats.append("WinAcc")
                    if row["margin_mae"] < b["margin_mae"]: beats.append("MAE")
                    if row["team_rmse"] < b["team_rmse"]: beats.append("TeamRMSE")
                    if row["retro_r2"] > b["retro_r2"]:  beats.append("R²")
            note = ("← BASELINE" if row["is_baseline"]
                    else (f"beats baseline: {', '.join(beats)}" if beats else ""))
            print(_fmt_row(row["label"], row, note=note))

    # ── Seasons where any recency variant won on predictive metrics ───────────
    predictive_cols = {"brier", "logloss", "win_acc", "margin_mae"}
    wins_by_season: list[tuple[int, str, list[str]]] = []
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
                wins_by_season.append((season, row["label"], beats))

    print(f"\n{'='*92}")
    print("RECENCY WIN SUMMARY (predictive metrics only: Brier, LL, WinAcc, MAE)")
    print(f"{'='*92}")
    if wins_by_season:
        for season, label, cols in wins_by_season:
            print(f"  Season {season}  {label}  beats baseline on: {', '.join(cols)}")
    else:
        print("  Baseline wins all predictive metrics in every season.")

    print(f"\n{'='*92}")
    print(f"Full results: {RESULTS_CSV}")
    print(f"{'='*92}\n")


# ── Main ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    seasons = args.seasons
    half_lives = _parse_half_lives(args.half_lives)

    print(f"\n{'='*90}")
    print("NBA TEAM RATINGS — RECENCY WEIGHTING BACKTEST")
    print(f"  Seasons     : {seasons}")
    print(f"  Half-lives  : {[str(h) if h else 'None' for h in half_lives]}")
    print(f"  Solver      : inline copy of iterative_adjust (no live pipeline changes)")
    print(f"  Holdout     : within-season split (median date cutoff) + full-season retrodiction")
    print(f"{'='*90}")

    all_results: list[dict] = []
    for season in seasons:
        rows = _eval_season(season, half_lives)
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
