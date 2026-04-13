"""
ffi/rapm.py — Factor-specific RAPM for the Four Factor Impact Index.

Fits 4 independent lineup-adjusted regressions (one per Four Factor):
  efg  — effective FG% (eFG = (FGM + 0.5·FG3M) / FGA × 100)
  tov  — turnover rate  (TOV / (FGA + 0.44·FTA + TOV) × 100)
  orb  — offensive rebound rate (OREB / (OREB + opp_DREB) × 100)
  ftr  — free-throw rate (FTA / FGA × 100)

Design matrix structure (identical to bpr/rapm.py):
  cols: [intercept | HCA | off_0 … off_{N-1} | def_0 … def_{N-1}]

  home-offense row: target = home_factor_rate, weight = home_opportunity_count
    intercept = 1.0,  HCA = +1.0 (or 0 neutral)
    home players in off columns, away players in def columns

  away-offense row: target = away_factor_rate, weight = away_opportunity_count
    intercept = 1.0,  HCA = -1.0 (or 0 neutral)
    away players in off columns, home players in def columns

Sign conventions for stored values (all positive-good):
  off_efg_impact = +off_coeff          (higher = player boosts team eFG)
  def_efg_impact = -def_coeff          (higher = player cuts opp eFG)

  off_tov_impact = -off_coeff          (higher = fewer turnovers)
  def_tov_impact = +def_coeff          (higher = more forced turnovers)

  off_orb_impact = +off_coeff          (higher = better offensive rebounding)
  def_reb_impact = -def_coeff          (higher = limits opp offensive rebounding)

  off_ftr_impact = +off_coeff          (higher = draws more fouls)
  def_ftr_impact = -def_coeff          (higher = limits opp free throws)

Solver: same augmented weighted LS as bpr/rapm.py (_solve_augmented reused).
"""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import lsqr

logger = logging.getLogger(__name__)

MIN_OBS_WEIGHT = 1.0   # rows below this weight are dropped from the design matrix
FFI_RAPM_LAMBDA_DEFAULT = 500.0  # regularization; tunable via CLI


# ── Factor target / weight extractors ────────────────────────────────────────
# Each returns (y_home, w_home, y_away, w_away) for one observation.
# A weight of 0.0 means that side's row is excluded from the fit.

def _efg_targets(obs: dict) -> tuple[float, float, float, float]:
    h_fga = obs["home_fga"]
    a_fga = obs["away_fga"]
    y_h = (obs["home_fgm"] + 0.5 * obs["home_fg3m"]) / h_fga * 100.0 if h_fga >= MIN_OBS_WEIGHT else 0.0
    y_a = (obs["away_fgm"] + 0.5 * obs["away_fg3m"]) / a_fga * 100.0 if a_fga >= MIN_OBS_WEIGHT else 0.0
    return y_h, h_fga if h_fga >= MIN_OBS_WEIGHT else 0.0, \
           y_a, a_fga if a_fga >= MIN_OBS_WEIGHT else 0.0


def _tov_targets(obs: dict) -> tuple[float, float, float, float]:
    h_opps = obs["home_fga"] + 0.44 * obs["home_fta"] + obs["home_tov"]
    a_opps = obs["away_fga"] + 0.44 * obs["away_fta"] + obs["away_tov"]
    y_h = obs["home_tov"] / h_opps * 100.0 if h_opps >= MIN_OBS_WEIGHT else 0.0
    y_a = obs["away_tov"] / a_opps * 100.0 if a_opps >= MIN_OBS_WEIGHT else 0.0
    return y_h, h_opps if h_opps >= MIN_OBS_WEIGHT else 0.0, \
           y_a, a_opps if a_opps >= MIN_OBS_WEIGHT else 0.0


def _orb_targets(obs: dict) -> tuple[float, float, float, float]:
    # Home ORB% uses home_oreb and away's defensive rebound
    h_denom = obs["home_oreb"] + obs["away_dreb"]
    # Away ORB% uses away_oreb and home's defensive rebound
    a_denom = obs["away_oreb"] + obs["home_dreb"]
    y_h = obs["home_oreb"] / h_denom * 100.0 if h_denom >= MIN_OBS_WEIGHT else 0.0
    y_a = obs["away_oreb"] / a_denom * 100.0 if a_denom >= MIN_OBS_WEIGHT else 0.0
    return y_h, h_denom if h_denom >= MIN_OBS_WEIGHT else 0.0, \
           y_a, a_denom if a_denom >= MIN_OBS_WEIGHT else 0.0


def _ftr_targets(obs: dict) -> tuple[float, float, float, float]:
    h_fga = obs["home_fga"]
    a_fga = obs["away_fga"]
    y_h = obs["home_fta"] / h_fga * 100.0 if h_fga >= MIN_OBS_WEIGHT else 0.0
    y_a = obs["away_fta"] / a_fga * 100.0 if a_fga >= MIN_OBS_WEIGHT else 0.0
    return y_h, h_fga if h_fga >= MIN_OBS_WEIGHT else 0.0, \
           y_a, a_fga if a_fga >= MIN_OBS_WEIGHT else 0.0


_FACTOR_FNS: dict[str, Callable] = {
    "efg": _efg_targets,
    "tov": _tov_targets,
    "orb": _orb_targets,
    "ftr": _ftr_targets,
}


# ── Design matrix builder ─────────────────────────────────────────────────────

def build_factor_design_matrix(
    observations: list[dict],
    factor: str,
    player_season_index: dict[tuple[int, int], int],
    n_player_seasons: int,
) -> tuple[sparse.csr_matrix, np.ndarray, np.ndarray]:
    """
    Build the sparse design matrix X, target vector y, and weight vector w
    for one factor and one or more seasons.

    Column layout: [intercept | HCA | off_0..off_N-1 | def_0..def_N-1]
    """
    target_fn = _FACTOR_FNS[factor]
    n_features = 2 + 2 * n_player_seasons

    rows, cols, vals = [], [], []
    y_list: list[float] = []
    w_list: list[float] = []

    row_idx = 0
    for obs in observations:
        home_ids = obs["home_player_ids"]
        away_ids = obs["away_player_ids"]
        yr = obs["season_year"]
        hca_sign = 0.0 if obs.get("is_neutral", False) else 1.0

        y_h, w_h, y_a, w_a = target_fn(obs)

        # ── home-offense row ──────────────────────────────────────────────────
        if w_h >= MIN_OBS_WEIGHT:
            y_list.append(y_h)
            w_list.append(w_h)
            rows.append(row_idx); cols.append(0); vals.append(1.0)        # intercept
            rows.append(row_idx); cols.append(1); vals.append(hca_sign)   # HCA
            for pid in home_ids:
                j = player_season_index[(pid, yr)]
                rows.append(row_idx); cols.append(2 + j); vals.append(1.0)
            for pid in away_ids:
                j = player_season_index[(pid, yr)]
                rows.append(row_idx); cols.append(2 + n_player_seasons + j); vals.append(1.0)
            row_idx += 1

        # ── away-offense row ──────────────────────────────────────────────────
        if w_a >= MIN_OBS_WEIGHT:
            y_list.append(y_a)
            w_list.append(w_a)
            rows.append(row_idx); cols.append(0); vals.append(1.0)
            rows.append(row_idx); cols.append(1); vals.append(-hca_sign)
            for pid in away_ids:
                j = player_season_index[(pid, yr)]
                rows.append(row_idx); cols.append(2 + j); vals.append(1.0)
            for pid in home_ids:
                j = player_season_index[(pid, yr)]
                rows.append(row_idx); cols.append(2 + n_player_seasons + j); vals.append(1.0)
            row_idx += 1

    n_rows = row_idx
    if n_rows == 0:
        raise ValueError(f"No valid rows for factor={factor}")

    X = sparse.coo_matrix(
        (vals, (rows, cols)), shape=(n_rows, n_features)
    ).tocsr()
    y = np.array(y_list, dtype=np.float64)
    w = np.array(w_list, dtype=np.float64)
    return X, y, w


# ── Augmented solver (mirrors bpr/rapm.py) ───────────────────────────────────

def _solve_augmented(
    X: sparse.csr_matrix,
    y: np.ndarray,
    weights: np.ndarray,
    lambda_val: float,
    player_col_slice: tuple[int, int],
) -> np.ndarray:
    n_features = X.shape[1]
    start, end = player_col_slice
    n_pen = end - start

    sqrt_w = np.sqrt(weights)
    Xw = sparse.diags(sqrt_w) @ X
    yw = sqrt_w * y

    pen_rows = np.arange(n_pen)
    pen_cols = np.arange(start, end)
    pen_vals = np.full(n_pen, np.sqrt(lambda_val))
    I_pen = sparse.coo_matrix(
        (pen_vals, (pen_rows, pen_cols)), shape=(n_pen, n_features)
    ).tocsr()
    pen_targets = np.zeros(n_pen)  # prior mean = 0 for all factor impacts

    X_aug = sparse.vstack([Xw, I_pen])
    y_aug = np.concatenate([yw, pen_targets])

    result = lsqr(X_aug, y_aug, show=False)
    return result[0]


# ── Single-factor RAPM fit ────────────────────────────────────────────────────

def fit_factor_rapm(
    dataset: dict,
    factor: str,
    lambda_val: float = FFI_RAPM_LAMBDA_DEFAULT,
) -> dict[str, dict]:
    """
    Fit the RAPM for one factor.  Returns per-player (target-season) dicts:
      {player_id: {"off": float, "def": float}}
    where off/def are the raw regression coefficients (before sign flip).
    Sign conventions are applied by the pipeline layer.
    """
    observations = dataset["observations"]
    psi = dataset["player_season_index"]
    n_ps = dataset["n_player_seasons"]
    target_year = dataset["target_year"]

    X, y, w = build_factor_design_matrix(observations, factor, psi, n_ps)
    player_col_slice = (2, 2 + 2 * n_ps)

    beta = _solve_augmented(X, y, w, lambda_val, player_col_slice)

    n_off = n_ps
    # Extract coefficients for target-season players only
    result: dict[int, dict] = {}
    for (pid, yr), col_idx in psi.items():
        if yr != target_year:
            continue
        off_coeff = float(beta[2 + col_idx])
        def_coeff = float(beta[2 + n_off + col_idx])
        result[pid] = {"off": off_coeff, "def": def_coeff}

    logger.info(
        f"FFI RAPM [{factor}]: λ={lambda_val:.0f}, "
        f"n_rows={X.shape[0]}, n_players={len(result)}"
    )
    return result


# ── All-factor RAPM ───────────────────────────────────────────────────────────

# Sign-flip applied before storage (all values stored positive-good).
# (off_sign, def_sign): multiply raw coefficient by this to get impact value.
FACTOR_SIGNS: dict[str, tuple[int, int]] = {
    "efg": (+1, -1),   # more eFG = good offense; less opp eFG = good defense
    "tov": (-1, +1),   # less TOV% = good offense; more forced opp TOV = good defense
    "orb": (+1, -1),   # more ORB% = good offense; less allowed opp ORB = good defense
    "ftr": (+1, -1),   # more FTR = good offense; less opp FTR = good defense
}


def run_all_factors(
    dataset: dict,
    lambda_val: float = FFI_RAPM_LAMBDA_DEFAULT,
) -> dict[int, dict]:
    """
    Fit all 4 factor RAPMs.

    Returns {player_id: {
        "off_efg_impact": ..., "def_efg_impact": ...,
        "off_tov_impact": ..., "def_tov_impact": ...,
        "off_orb_impact": ..., "def_reb_impact": ...,
        "off_ftr_impact": ..., "def_ftr_impact": ...,
    }}
    """
    factor_results: dict[str, dict[int, dict]] = {}
    for factor in ("efg", "tov", "orb", "ftr"):
        factor_results[factor] = fit_factor_rapm(dataset, factor, lambda_val)

    all_pids = set()
    for r in factor_results.values():
        all_pids.update(r.keys())

    combined: dict[int, dict] = {}
    for pid in all_pids:
        d: dict[str, float | None] = {}
        for factor, (osign, dsign) in FACTOR_SIGNS.items():
            coeffs = factor_results[factor].get(pid)
            if coeffs is None:
                continue
            off_raw = coeffs["off"]
            def_raw = coeffs["def"]
            if factor == "efg":
                d["off_efg_impact"] = round(osign * off_raw, 4)
                d["def_efg_impact"] = round(dsign * def_raw, 4)
            elif factor == "tov":
                d["off_tov_impact"] = round(osign * off_raw, 4)
                d["def_tov_impact"] = round(dsign * def_raw, 4)
            elif factor == "orb":
                d["off_orb_impact"] = round(osign * off_raw, 4)
                d["def_reb_impact"] = round(dsign * def_raw, 4)
            elif factor == "ftr":
                d["off_ftr_impact"] = round(osign * off_raw, 4)
                d["def_ftr_impact"] = round(dsign * def_raw, 4)
        combined[pid] = d

    return combined
