"""
backtest_lib.py — shared utilities for the leak-free BPR backtest suite.

Consolidates the helpers duplicated between backtest_bpr_margin and
backtest_bpr_walkforward, adds log loss / calibration / split tagging, and
provides the ratings/roster loaders used by backtest_bpr_suite.

Pure reads and pure functions — no DB writes.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

# Re-exported so the suite imports everything from one place
from ncaa.analytics.player_value.bpr.game_prediction import (  # noqa: F401
    _team_strength,
    _fit_ols,
    _auc,
    predict_margin_and_prob,
)

CALIB_EDGES = [-15.0, -10.0, -5.0, -2.0, 0.0, 2.0, 5.0, 10.0, 15.0]
CALIB_LABELS = [
    "<-15", "-15:-10", "-10:-5", "-5:-2", "-2:0",
    "0:2", "2:5", "5:10", "10:15", ">15",
]

# Power-conference set for the high-major split (current alignment era)
HIGH_MAJOR_CONFERENCES = {
    "Atlantic Coast Conference", "Big 12", "Big East", "Big Ten",
    "Southeastern Conference",
}


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_metrics(results: list[dict]) -> dict:
    """
    results rows need: pred, actual, p_home, home_won, coverage.
    Returns n, rmse, mae, win_acc, brier, log_loss, auc, mean_cov.
    """
    if not results:
        return {}
    preds = np.array([r["pred"] for r in results])
    actuals = np.array([r["actual"] for r in results])
    p = np.clip(np.array([r["p_home"] for r in results]), 1e-6, 1 - 1e-6)
    won = np.array([r["home_won"] for r in results]).astype(float)

    return dict(
        n=len(results),
        rmse=float(np.sqrt(np.mean((preds - actuals) ** 2))),
        mae=float(np.mean(np.abs(preds - actuals))),
        win_acc=float(np.mean((preds > 0) == (actuals > 0))),
        brier=float(np.mean((p - won) ** 2)),
        log_loss=float(-np.mean(won * np.log(p) + (1 - won) * np.log(1 - p))),
        auc=_auc(preds, won),
        mean_cov=float(np.mean([r.get("coverage", 1.0) for r in results])),
    )


def calibration_table(results: list[dict], n_buckets: int = 10) -> list[dict]:
    """Probability-bucket calibration: predicted p_home vs realized rate."""
    if not results:
        return []
    rows = []
    edges = np.linspace(0.0, 1.0, n_buckets + 1)
    p = np.array([r["p_home"] for r in results])
    won = np.array([r["home_won"] for r in results]).astype(float)
    for i in range(n_buckets):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi if i < n_buckets - 1 else p <= hi)
        if mask.sum() == 0:
            continue
        rows.append({
            "bucket": f"{lo:.1f}-{hi:.1f}",
            "n": int(mask.sum()),
            "mean_p": float(p[mask].mean()),
            "realized": float(won[mask].mean()),
        })
    return rows


# ── Split tagging ─────────────────────────────────────────────────────────────

def load_conference_maps(season_year: int) -> tuple[dict[int, str], set[int]]:
    """
    Returns (conf_by_team, high_major_team_ids) for one season,
    from TeamSeasonStats.conference.
    """
    from ncaa.models import TeamSeasonStats

    conf_by_team: dict[int, str] = {}
    for r in (TeamSeasonStats.objects
              .filter(season__year=season_year, conference__isnull=False)
              .values("team_id", "conference__name")):
        conf_by_team[r["team_id"]] = r["conference__name"]
    high = {tid for tid, c in conf_by_team.items() if c in HIGH_MAJOR_CONFERENCES}
    return conf_by_team, high


def tag_game_splits(game: dict, conf_by_team: dict[int, str],
                    high_major: set[int]) -> dict[str, str]:
    """Split labels for one game dict (home_team_id/away_team_id/neutral_site)."""
    h, a = game["home_team_id"], game["away_team_id"]
    conf_h, conf_a = conf_by_team.get(h), conf_by_team.get(a)
    return {
        "site": "neutral" if game["neutral_site"] else "home_away",
        "conf": ("conference" if conf_h is not None and conf_h == conf_a
                 else "non_conference"),
        "tier": ("high_major" if (h in high_major and a in high_major)
                 else "mid_major" if (h not in high_major and a not in high_major)
                 else "cross_tier"),
    }


# ── Loaders (stored-ratings mode, cross-season) ───────────────────────────────

def load_stored_player_ratings(seasons: list[int]) -> tuple[dict, dict]:
    """
    player_ratings[(pid, yr)] -> {bpr, box_bpr, baseline_obpr, baseline_dbpr, off_poss}
    team_roster[(tid, yr)]    -> [{player_id, mpg}]
    """
    from ncaa.models import PlayerSeasonStats

    player_ratings: dict = {}
    team_roster: dict = defaultdict(list)
    for row in PlayerSeasonStats.objects.filter(
        season__year__in=seasons,
    ).values("player_id", "team_id", "season__year",
             "bpr", "box_bpr", "baseline_obpr", "baseline_dbpr",
             "mpg", "off_poss"):
        yr, pid = row["season__year"], row["player_id"]
        player_ratings[(pid, yr)] = {
            "bpr": row["bpr"], "box_bpr": row["box_bpr"],
            "baseline_obpr": row["baseline_obpr"],
            "baseline_dbpr": row["baseline_dbpr"],
            "off_poss": row["off_poss"] or 0.0,
        }
        team_roster[(row["team_id"], yr)].append(
            {"player_id": pid, "mpg": row["mpg"] or 0.0})
    return player_ratings, dict(team_roster)


def load_stored_adj_em(seasons: list[int]) -> dict:
    from ncaa.models import TeamSeasonRatings

    out: dict = {}
    for row in TeamSeasonRatings.objects.filter(
        season__year__in=seasons, adj_em__isnull=False,
    ).values("team_id", "season__year", "adj_em"):
        out[(row["team_id"], row["season__year"])] = float(row["adj_em"])
    return out


def load_games(seasons: list[int]) -> dict[int, list[dict]]:
    """games_by_year, D1-vs-D1 finals with scores, sorted by date."""
    from ncaa.models import Game

    games_by_year: dict[int, list] = defaultdict(list)
    for g in Game.objects.filter(
        season_year__in=seasons, status="final",
        home_team__is_d1=True, away_team__is_d1=True,
        home_score__isnull=False, away_score__isnull=False,
    ).values("id", "season_year", "game_date", "home_team_id", "away_team_id",
             "home_score", "away_score", "neutral_site"):
        games_by_year[g["season_year"]].append(g)
    for yr in games_by_year:
        games_by_year[yr].sort(key=lambda g: (g["game_date"], g["id"]))
    return dict(games_by_year)


# ── Combined team+player arm ─────────────────────────────────────────────────
# margin ~ β0 + β1·adj_em_diff + β2·bpr_diff + β3·home. Answers the mission
# question "does player BPR add anything over the team rating?" directly:
# if β2 ≈ 0 out-of-sample, BPR carries no incremental signal.

def fit_ols_combo(
    train_games: list[dict],
    rating_year: int,
    player_ratings: dict,
    team_roster: dict,
    adj_em_map: dict,
    min_poss: int,
) -> tuple[float, float, float, float, float]:
    """Returns (beta0, beta_em, beta_bpr, beta_home, sigma)."""
    rows, margins = [], []
    for g in train_games:
        em_h, _ = _team_strength(g["home_team_id"], rating_year, rating_year,
                                 "adj_em", player_ratings, team_roster,
                                 adj_em_map, min_poss)
        em_a, _ = _team_strength(g["away_team_id"], rating_year, rating_year,
                                 "adj_em", player_ratings, team_roster,
                                 adj_em_map, min_poss)
        b_h, _ = _team_strength(g["home_team_id"], rating_year, rating_year,
                                "bpr", player_ratings, team_roster,
                                adj_em_map, min_poss)
        b_a, _ = _team_strength(g["away_team_id"], rating_year, rating_year,
                                "bpr", player_ratings, team_roster,
                                adj_em_map, min_poss)
        rows.append([1.0, em_h - em_a, b_h - b_a,
                     0.0 if g["neutral_site"] else 1.0])
        margins.append(float(g["home_score"] - g["away_score"]))
    if not margins:
        return 0.0, 1.0, 0.0, 3.0, 11.0
    X = np.array(rows)
    y = np.array(margins)
    coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    sigma = float(np.std(y - X @ coeffs))
    if sigma < 0.5:
        sigma = 11.0
    return (float(coeffs[0]), float(coeffs[1]), float(coeffs[2]),
            float(coeffs[3]), sigma)


def evaluate_combo_arm(
    test_games: list[dict],
    rating_year: int,
    roster_year: int,
    player_ratings: dict,
    team_roster: dict,
    adj_em_map: dict,
    min_poss: int,
    betas: tuple[float, float, float, float, float],
) -> list[dict]:
    import math as _math

    b0, b_em, b_bpr, b_home, sigma = betas
    out = []
    for g in test_games:
        em_h, _ = _team_strength(g["home_team_id"], rating_year, roster_year,
                                 "adj_em", player_ratings, team_roster,
                                 adj_em_map, min_poss)
        em_a, _ = _team_strength(g["away_team_id"], rating_year, roster_year,
                                 "adj_em", player_ratings, team_roster,
                                 adj_em_map, min_poss)
        b_h, cov_h = _team_strength(g["home_team_id"], rating_year, roster_year,
                                    "bpr", player_ratings, team_roster,
                                    adj_em_map, min_poss)
        b_a, cov_a = _team_strength(g["away_team_id"], rating_year, roster_year,
                                    "bpr", player_ratings, team_roster,
                                    adj_em_map, min_poss)
        home_ind = 0.0 if g["neutral_site"] else 1.0
        pred = b0 + b_em * (em_h - em_a) + b_bpr * (b_h - b_a) + b_home * home_ind
        p_home = 0.5 * (1.0 + _math.erf(pred / (sigma * _math.sqrt(2))))
        out.append({
            "game_id": g["id"], "pred": pred, "p_home": p_home,
            "actual": float(g["home_score"] - g["away_score"]),
            "home_won": 1 if g["home_score"] > g["away_score"] else 0,
            "coverage": min(cov_h, cov_a),
        })
    return out


# ── Evaluation core ───────────────────────────────────────────────────────────

def evaluate_arm(
    test_games: list[dict],
    predictor: str,
    rating_year: int,
    roster_year: int,
    player_ratings: dict,
    team_roster: dict,
    adj_em_map: dict,
    min_poss: int,
    betas: tuple[float, float, float, float],
) -> list[dict]:
    """Predict each test game with a fitted (beta0, beta1, beta2, sigma)."""
    beta0, beta1, beta2, sigma = betas
    out = []
    for g in test_games:
        h_str, h_cov = _team_strength(
            g["home_team_id"], rating_year, roster_year,
            predictor, player_ratings, team_roster, adj_em_map, min_poss)
        a_str, a_cov = _team_strength(
            g["away_team_id"], rating_year, roster_year,
            predictor, player_ratings, team_roster, adj_em_map, min_poss)
        pred, p_home = predict_margin_and_prob(
            h_str, a_str, bool(g["neutral_site"]), beta0, beta1, beta2, sigma)
        out.append({
            "game_id": g["id"],
            "pred": pred,
            "p_home": p_home,
            "actual": float(g["home_score"] - g["away_score"]),
            "home_won": 1 if g["home_score"] > g["away_score"] else 0,
            "coverage": min(h_cov, a_cov),
        })
    return out
