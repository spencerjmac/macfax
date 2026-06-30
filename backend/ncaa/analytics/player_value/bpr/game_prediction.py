"""
game_prediction.py — Shared helpers for BPR game-margin prediction.

Used by:
  - backtest_bpr_margin.py  (cross-season BPR backtest)
  - backtest_bpr_walkforward.py  (within-season walk-forward backtest)

Do not add imports or state — these are pure functions.
"""

from __future__ import annotations

import math

import numpy as np


def _team_strength(
    team_id: int,
    rating_year: int,
    roster_year: int,
    predictor: str,
    player_ratings: dict,
    team_roster: dict,
    adj_em_map: dict,
    min_poss: int,
) -> tuple[float, float]:
    """
    Returns (strength, coverage).

    rating_year: which season's ratings to use.
    roster_year: which season's roster / mpg weights to use.
    coverage = Σ minshare(players WITH prior rating) / Σ minshare(all rostered).
    """
    if predictor == "home_only":
        return 0.0, 1.0

    if predictor == "adj_em":
        val = adj_em_map.get((team_id, rating_year))
        return (float(val) if val is not None else 0.0), (1.0 if val is not None else 0.0)

    # Player-level: bpr, box_bpr, baseline
    roster = team_roster.get((team_id, roster_year), [])
    if not roster:
        return 0.0, 0.0

    total_w = 0.0
    covered_w = 0.0
    wt_sum = 0.0

    for p in roster:
        w = min(p["mpg"] / 40.0, 1.0)
        total_w += w
        pr = player_ratings.get((p["player_id"], rating_year))
        if pr and pr["off_poss"] >= min_poss:
            if predictor == "baseline":
                val = (pr.get("baseline_obpr") or 0.0) + (pr.get("baseline_dbpr") or 0.0)
            elif predictor == "box_bpr":
                val = pr.get("box_bpr") or 0.0
            else:  # bpr
                val = pr.get("bpr") or 0.0
            wt_sum += val * w
            covered_w += w
        # else: league average = 0; player counted in total_w (lowers coverage)

    if total_w == 0.0:
        return 0.0, 0.0

    # Scale by minute-share so team_strength ≈ Σ(per-player contribution)
    scale = min(total_w, 5.0)
    return (wt_sum / total_w) * scale, covered_w / total_w


def _fit_ols(
    train_games: list[dict],
    predictor: str,
    train_year: int,
    player_ratings: dict,
    team_roster: dict,
    adj_em_map: dict,
    min_poss: int,
) -> tuple[float, float, float, float]:
    """
    Fit actual_margin = β0 + β1·strength_diff + β2·home_indicator on TRAIN games.
    Returns (beta0, beta1, beta2, sigma).
    """
    diffs = []
    hinds = []
    margins = []

    for g in train_games:
        h_str, _ = _team_strength(
            g["home_team_id"], train_year, train_year,
            predictor, player_ratings, team_roster, adj_em_map, min_poss,
        )
        a_str, _ = _team_strength(
            g["away_team_id"], train_year, train_year,
            predictor, player_ratings, team_roster, adj_em_map, min_poss,
        )
        diffs.append(h_str - a_str)
        hinds.append(0.0 if g["neutral_site"] else 1.0)
        margins.append(float(g["home_score"] - g["away_score"]))

    if not margins:
        return 0.0, 1.0, 3.0, 11.0  # safe fallback

    y = np.array(margins)
    X = np.column_stack([np.ones(len(margins)), diffs, hinds])
    coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    beta0, beta1, beta2 = float(coeffs[0]), float(coeffs[1]), float(coeffs[2])
    sigma = float(np.std(y - X @ coeffs))
    if sigma < 0.5:
        sigma = 11.0
    return beta0, beta1, beta2, sigma


def _auc(scores: np.ndarray, labels: np.ndarray) -> float:
    wins   = scores[labels == 1]
    losses = scores[labels == 0]
    if not len(wins) or not len(losses):
        return float("nan")
    concordant = float(np.sum(wins[:, None] > losses[None, :]))
    tied       = float(np.sum(wins[:, None] == losses[None, :])) * 0.5
    return (concordant + tied) / (len(wins) * len(losses))


def _metrics(results: list[dict]) -> dict:
    if not results:
        return {}
    preds     = np.array([r["pred"]     for r in results])
    actuals   = np.array([r["actual"]   for r in results])
    p_homes   = np.array([r["p_home"]   for r in results])
    home_wons = np.array([r["home_won"] for r in results])

    rmse    = float(np.sqrt(np.mean((preds - actuals) ** 2)))
    mae     = float(np.mean(np.abs(preds - actuals)))
    win_acc = float(np.mean((preds > 0) == (actuals > 0)))
    brier   = float(np.mean((p_homes - home_wons) ** 2))
    auc     = _auc(preds, home_wons)
    mean_cov = float(np.mean([r["coverage"] for r in results]))

    return dict(n=len(results), rmse=rmse, mae=mae,
                win_acc=win_acc, brier=brier, auc=auc, mean_cov=mean_cov)


def predict_margin_and_prob(
    home_str: float,
    away_str: float,
    is_neutral: bool,
    beta0: float,
    beta1: float,
    beta2: float,
    sigma: float,
) -> tuple[float, float]:
    """Returns (predicted_margin, p_home_win)."""
    home_ind = 0.0 if is_neutral else 1.0
    pred = beta0 + beta1 * (home_str - away_str) + beta2 * home_ind
    p_home = 0.5 * (1.0 + math.erf(pred / (sigma * math.sqrt(2))))
    return pred, p_home
