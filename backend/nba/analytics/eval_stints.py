"""
eval_stints.py — score player ratings by how well they predict a season's stints.

Rows are built exactly as rapm.py builds them: two per lineup observation from
build_nba_observations (quality-flagged games are already excluded there), a
home-offense row and an away-offense row, target points per 100 possessions,
weight possessions, rows under MIN_OBS_POSS possessions dropped.

Prediction for a row, with rapm.py's signs (DBPR is stored negated, so a
defender's D rating enters with a minus):

    league_mean + hca_sign * hca + sum(O of the offense) - sum(D of the defense)

hca_sign is +1 on home-offense rows and -1 on away-offense rows. league_mean
and hca are fitted once per season from the rows alone (possession-weighted
least squares on the intercept and HCA columns), so every candidate is scored
against the same baseline. Players missing from the ratings count as 0.

score() returns the possession-weighted MSE, and the same MSE with every
rating at 0 (the baseline alone).
"""

from __future__ import annotations

import numpy as np

from nba.analytics.rapm import MIN_OBS_POSS, build_nba_observations


def stint_rows(observations: list[dict]) -> list[tuple[float, float, float, list[int], list[int]]]:
    """(target, weight, hca_sign, offense ids, defense ids) per row, as build_design_matrix."""
    rows = []
    for obs in observations:
        home, away = obs["home_player_ids"], obs["away_player_ids"]
        if obs["home_poss"] >= MIN_OBS_POSS:
            rows.append((obs["home_pts"] / obs["home_poss"] * 100.0, obs["home_poss"], 1.0, home, away))
        if obs["away_poss"] >= MIN_OBS_POSS:
            rows.append((obs["away_pts"] / obs["away_poss"] * 100.0, obs["away_poss"], -1.0, away, home))
    return rows


def _baseline(y: np.ndarray, w: np.ndarray, s: np.ndarray) -> tuple[float, float]:
    """Possession-weighted least squares of y on [1, hca_sign]: (league_mean, hca)."""
    X = np.column_stack([np.ones_like(s), s])
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    return float(beta[0]), float(beta[1])


def score(
    ratings_o: dict[int, float],
    ratings_d: dict[int, float],
    season_year: int,
    observations: list[dict] | None = None,
) -> dict:
    """
    Score {nba_id: O} / {nba_id: D} ratings on season_year's stints.

    observations: build_nba_observations(season_year) output, to reuse a load
    (or for tests); loaded when None.

    Returns {"mse", "mse_zero", "n_rows", "poss", "league_mean", "hca"};
    mse values are None when the season has no rows.
    """
    if observations is None:
        observations = build_nba_observations(season_year)
    rows = stint_rows(observations)
    if not rows:
        return {"mse": None, "mse_zero": None, "n_rows": 0, "poss": 0.0,
                "league_mean": None, "hca": None}

    y = np.array([r[0] for r in rows])
    w = np.array([r[1] for r in rows])
    s = np.array([r[2] for r in rows])
    league_mean, hca = _baseline(y, w, s)

    players = np.array([
        sum(ratings_o.get(p, 0.0) for p in off) - sum(ratings_d.get(p, 0.0) for p in dfn)
        for _, _, _, off, dfn in rows
    ])
    base = league_mean + hca * s
    total = float(w.sum())
    return {
        "mse": float((w * (y - base - players) ** 2).sum() / total),
        "mse_zero": float((w * (y - base) ** 2).sum() / total),
        "n_rows": len(rows),
        "poss": total,
        "league_mean": league_mean,
        "hca": hca,
    }
