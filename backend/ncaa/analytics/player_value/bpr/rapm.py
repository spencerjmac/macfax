"""
rapm.py — RAPM fitting for the BPR framework.

Two fitting modes:
  1. Baseline RAPM   — global prior μ=0, λ chosen by 5-fold CV
  2. Prior-informed RAPM — per-player prior means & SDs from Box BPR

Design matrix layout (sparse, CSR):
  Rows:    2 observations per lineup segment (home-offense, away-offense)
  Columns: [intercept | hca | obpr_0 … obpr_{N-1} | dbpr_0 … dbpr_{N-1}]
  Width:   2 + 2*N

  For a home-offense row:
    col 0  (intercept) = 1.0
    col 1  (hca)       = +1.0  (home team on offense)
    col 2+j (obpr_j)   = +1.0  for each home player j
    col 2+N+k (dbpr_k) = +1.0  for each away player k (note: positive weight on
                                positive output means minus sign in defensive interpretation)

  For an away-offense row:
    col 0  (intercept) = 1.0
    col 1  (hca)       = -1.0  (away team on offense)
    col 2+j (obpr_j)   = +1.0  for each away player j
    col 2+N+k (dbpr_k) = +1.0  for each home player k

  Targets (y):   offensive efficiency = (pts / poss) * 100
  Weights (w):   possessions

  **Defensive sign convention**: we report DBPR as a *positive-good* number
  (points per 100 poss PREVENTED relative to average), so internally the DBPR
  coefficient is fit with a +1 column but the opponent's scoring is the target,
  meaning the coefficient will be negative for a good defender.  We flip sign
  when writing results so that higher DBPR = better defense.

Solver:
  Augmented weighted least-squares via scipy.sparse.linalg.lsqr.
  Stack [√W · X ; √λ · I_players] and solve as unweighted LS.
  The augmentation term encodes the Gaussian prior.

CV:
  5-fold on random GAME folds (not observation folds) to avoid data leakage
  across observations from the same game.
"""

from __future__ import annotations

import logging
import random
from typing import Optional

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import lsqr

from ncaa.analytics.player_value.bpr.constants import (
    HCA_PTS_PER_100,
    RAPM_LAMBDA_CANDIDATES,
    RAPM_CV_FOLDS,
    PRIOR_SD_DEFAULT_OFF,
    PRIOR_SD_DEFAULT_DEF,
    PRIOR_SD_SCALE_CANDIDATES,
    BOX_ONLY_SD_SCALE_REF,
    MIN_OBS_POSS,
)

logger = logging.getLogger(__name__)


# ── Design matrix builder ────────────────────────────────────────────────────

def build_design_matrix(
    observations: list[dict],
    player_season_index: dict,  # (player_id, season_year) → col  OR  player_id → col
    n_player_seasons: int,
    league_avg_off_eff: Optional[float] = None,
    player_keyed: bool = False,
) -> tuple[sparse.csr_matrix, np.ndarray, np.ndarray]:
    """
    Build the sparse design matrix X, target vector y, and weight vector w.

    player_keyed=False (default): player_season_index is {(player_id, yr): col}.
      Same player in different years gets separate columns — correct multi-year RAPM.
    player_keyed=True: player_season_index is {player_id: col}.
      Same player across all years maps to ONE column, implementing EM's "constant
      value across 4 pooled years" assumption. Used only for box training RAPM targets.

    Returns:
        X        (n_obs, 2 + 2*n_player_seasons)  CSR sparse
        y        (n_obs,)
        weights  (n_obs,)
    """
    # Two rows per observation (home-offense + away-offense)
    n_obs = len(observations) * 2
    n_features = 2 + 2 * n_player_seasons  # intercept + hca + OBPR×N_ps + DBPR×N_ps

    rows, cols, vals = [], [], []
    y = np.zeros(n_obs, dtype=np.float64)
    weights = np.zeros(n_obs, dtype=np.float64)

    for idx, obs in enumerate(observations):
        home_ids = obs["home_player_ids"]
        away_ids = obs["away_player_ids"]
        h_pts    = obs["home_pts"]
        a_pts    = obs["away_pts"]
        h_poss   = obs["home_poss"]
        a_poss   = obs["away_poss"]
        obs_year = obs["season_year"]  # used to form player-season key
        neutral  = obs.get("is_neutral", False)
        hca_sign = 0.0 if neutral else 1.0  # real home court = ±1.0

        # ── Row 2·idx: home team on offense ──────────────────────────────────
        i = idx * 2
        if h_poss >= MIN_OBS_POSS:
            y[i] = h_pts / h_poss * 100.0
            weights[i] = h_poss

            # intercept
            rows.append(i); cols.append(0); vals.append(1.0)
            # hca (home team on offense → +hca_sign)
            rows.append(i); cols.append(1); vals.append(hca_sign)
            # home players: OBPR columns (offensive)
            for pid in home_ids:
                j = player_season_index[pid] if player_keyed else player_season_index[(pid, obs_year)]
                rows.append(i); cols.append(2 + j); vals.append(1.0)
            # away players: DBPR columns (defending against home offense)
            for pid in away_ids:
                j = player_season_index[pid] if player_keyed else player_season_index[(pid, obs_year)]
                rows.append(i); cols.append(2 + n_player_seasons + j); vals.append(1.0)

        # ── Row 2·idx+1: away team on offense ────────────────────────────────
        i = idx * 2 + 1
        if a_poss >= MIN_OBS_POSS:
            y[i] = a_pts / a_poss * 100.0
            weights[i] = a_poss

            rows.append(i); cols.append(0); vals.append(1.0)
            rows.append(i); cols.append(1); vals.append(-hca_sign)
            for pid in away_ids:
                j = player_season_index[pid] if player_keyed else player_season_index[(pid, obs_year)]
                rows.append(i); cols.append(2 + j); vals.append(1.0)
            for pid in home_ids:
                j = player_season_index[pid] if player_keyed else player_season_index[(pid, obs_year)]
                rows.append(i); cols.append(2 + n_player_seasons + j); vals.append(1.0)

    X = sparse.coo_matrix(
        (vals, (rows, cols)), shape=(n_obs, n_features)
    ).tocsr()

    # Mask zero-weight rows (possessions == 0 → no information)
    mask = weights > 0
    X = X[mask]
    y = y[mask]
    weights = weights[mask]

    return X, y, weights


# ── Augmented solver ─────────────────────────────────────────────────────────

def _solve_augmented(
    X: sparse.csr_matrix,
    y: np.ndarray,
    weights: np.ndarray,
    lambda_val: float,
    prior_means: Optional[np.ndarray] = None,
    player_col_slice: Optional[tuple[int, int]] = None,
) -> np.ndarray:
    """
    Solve weighted ridge: min_β ||√W (Xβ − y)||² + λ ||β_players − μ||²

    player_col_slice: (start, end) column range for the player block being
                      regularized (intercept and hca are NOT regularized).
                      If None, regularizes all features.

    Returns β (1-D array, length = X.shape[1]).
    """
    n_features = X.shape[1]

    if prior_means is None:
        prior_means = np.zeros(n_features)

    # Weight the data rows
    sqrt_w = np.sqrt(weights)
    Xw = sparse.diags(sqrt_w) @ X
    yw = sqrt_w * y

    # Build penalty rows: √λ · I on player columns only
    if player_col_slice is not None:
        start, end = player_col_slice
        n_pen = end - start
        pen_rows = np.arange(n_pen)
        pen_cols = np.arange(start, end)
        pen_vals = np.full(n_pen, np.sqrt(lambda_val))
        I_pen = sparse.coo_matrix(
            (pen_vals, (pen_rows, pen_cols)), shape=(n_pen, n_features)
        ).tocsr()
        pen_targets = np.sqrt(lambda_val) * prior_means[start:end]
    else:
        I_pen = np.sqrt(lambda_val) * sparse.eye(n_features, format="csr")
        pen_targets = np.sqrt(lambda_val) * prior_means

    X_aug = sparse.vstack([Xw, I_pen])
    y_aug = np.concatenate([yw, pen_targets])

    result = lsqr(X_aug, y_aug, show=False)
    return result[0]  # solution vector β


# ── Cross-validation ─────────────────────────────────────────────────────────

def cross_validate_lambda(
    observations: list[dict],
    X: sparse.csr_matrix,
    y: np.ndarray,
    weights: np.ndarray,
    n_player_seasons: int,
    seed: int = 42,
) -> tuple[float, dict]:
    """
    5-fold CV on game splits to select the RAPM regularization parameter λ.

    Criterion: weighted mean squared error of held-out offensive efficiency.

    Returns:
        best_lambda   float
        cv_results    dict with per-lambda mean/std CV errors
    """
    # Assign each observation pair to a fold by game_id
    game_ids = sorted({obs["game_id"] for obs in observations})
    rng = random.Random(seed)
    rng.shuffle(game_ids)
    game_fold = {gid: i % RAPM_CV_FOLDS for i, gid in enumerate(game_ids)}

    # Map observation index to fold (two rows per obs)
    obs_fold = []
    for obs in observations:
        fold = game_fold[obs["game_id"]]
        obs_fold.extend([fold, fold])

    # Mask rows matching build_design_matrix threshold (h_poss >= MIN_OBS_POSS)
    all_weights = np.array([
        v
        for obs in observations
        for v in [obs["home_poss"], obs["away_poss"]]
    ])
    nonzero_mask = all_weights >= MIN_OBS_POSS
    obs_fold_filtered = [f for f, m in zip(obs_fold, nonzero_mask) if m]
    obs_fold_arr = np.array(obs_fold_filtered)

    player_col_slice = (2, 2 + 2 * n_player_seasons)

    cv_errors: dict[float, list[float]] = {lam: [] for lam in RAPM_LAMBDA_CANDIDATES}

    for fold in range(RAPM_CV_FOLDS):
        train_mask = obs_fold_arr != fold
        test_mask  = obs_fold_arr == fold

        X_train, y_train, w_train = X[train_mask], y[train_mask], weights[train_mask]
        X_test,  y_test,  w_test  = X[test_mask],  y[test_mask],  weights[test_mask]

        if w_test.sum() == 0:
            continue

        for lam in RAPM_LAMBDA_CANDIDATES:
            beta = _solve_augmented(X_train, y_train, w_train, lam, player_col_slice=player_col_slice)
            y_hat = X_test @ beta
            residuals = y_test - y_hat
            wmse = np.average(residuals ** 2, weights=w_test)
            cv_errors[lam].append(wmse)

    mean_errors = {lam: float(np.mean(errs)) for lam, errs in cv_errors.items() if errs}
    best_lambda = min(mean_errors, key=mean_errors.get)

    logger.info(f"RAPM CV finished. Best λ={best_lambda:.4f}  (mean WMSE={mean_errors[best_lambda]:.4f})")

    return best_lambda, {
        "lambda_candidates": RAPM_LAMBDA_CANDIDATES,
        "mean_wmse": mean_errors,
        "best_lambda": best_lambda,
        "n_folds": RAPM_CV_FOLDS,
    }


# ── Public API ───────────────────────────────────────────────────────────────

def fit_baseline_rapm(
    observations: list[dict],
    player_season_index: dict,
    n_player_seasons: int,
    run_cv: bool = True,
    lambda_override: Optional[float] = None,
    player_keyed: bool = False,
) -> dict:
    """
    Fit baseline RAPM with global prior μ=0.

    player_keyed=False (default): returns obpr/dbpr keyed by (player_id, season_year).
    player_keyed=True: single coefficient per player across all years.
      Returns obpr/dbpr keyed by player_id directly — no extract_target_season needed.

    Returns:
        {
          obpr:        dict[(player_id, season_year), float]  OR  dict[player_id, float]
          dbpr:        dict[(player_id, season_year), float]  OR  dict[player_id, float]
          intercept:   float
          hca:         float
          lambda:      float
          cv_metrics:  dict | None
          player_keyed: bool
        }
    """
    logger.info(f"Building RAPM design matrix for {len(observations)} lineup segments …")
    X, y, weights = build_design_matrix(
        observations, player_season_index, n_player_seasons, player_keyed=player_keyed
    )
    logger.info(f"  Design matrix: {X.shape[0]} observations × {X.shape[1]} features  "
                f"({X.nnz} non-zeros)")

    player_col_slice = (2, 2 + 2 * n_player_seasons)
    cv_metrics = None

    if lambda_override is not None:
        best_lambda = lambda_override
    elif run_cv:
        best_lambda, cv_metrics = cross_validate_lambda(
            observations, X, y, weights, n_player_seasons
        )
    else:
        best_lambda = 1.0  # conservative default

    logger.info(f"Fitting baseline RAPM with λ={best_lambda} …")
    beta = _solve_augmented(X, y, weights, best_lambda, player_col_slice=player_col_slice)

    intercept = float(beta[0])
    hca       = float(beta[1])
    obpr_block = beta[2 : 2 + n_player_seasons]
    dbpr_block = beta[2 + n_player_seasons : 2 + 2 * n_player_seasons]

    player_season_keys = sorted(player_season_index, key=player_season_index.get)

    # DBPR sign flip: positive DBPR_raw = allowed more than avg (bad defender).
    # Negate so higher DBPR → better defender.
    obpr = {ps: float(obpr_block[i]) for i, ps in enumerate(player_season_keys)}
    dbpr = {ps: float(-dbpr_block[i]) for i, ps in enumerate(player_season_keys)}

    return {
        "obpr":         obpr,
        "dbpr":         dbpr,
        "intercept":    intercept,
        "hca":          hca,
        "lambda":       best_lambda,
        "cv_metrics":   cv_metrics,
        "player_keyed": player_keyed,
    }


def tune_prior_sd_scale(
    observations: list[dict],
    player_season_index: dict,
    n_player_seasons: int,
    prior_mean_obpr: dict[tuple[int, int], float],
    prior_mean_dbpr: dict[tuple[int, int], float],
    prior_sd_obpr: dict[tuple[int, int], float],
    prior_sd_dbpr: dict[tuple[int, int], float],
    baseline_lambda: float,
    sd_scale_candidates: Optional[list[float]] = None,
    seed: int = 42,
) -> tuple[float, dict]:
    """
    Tune a global prior SD scale factor by 5-fold game-split CV.

    Prior maps are keyed by (player_id, season_year).  Target-season rows
    receive their computed box-BPR prior; non-target-season rows receive
    neutral priors (mean=0, default SD) so data dominates for them.

    Also evaluates the BOX_ONLY_SD_SCALE_REF (0.01) as a diagnostic reference
    to capture near-box-only held-out WMSE without making it selectable.

    Returns:
        best_sd_scale   float
        cv_results      dict with per-candidate mean WMSE and box_only_reference_wmse
    """
    if sd_scale_candidates is None:
        sd_scale_candidates = PRIOR_SD_SCALE_CANDIDATES

    X, y, weights = build_design_matrix(observations, player_season_index, n_player_seasons)

    # Build game-fold assignment (same approach as lambda CV)
    game_ids = sorted({obs["game_id"] for obs in observations})
    rng = random.Random(seed)
    rng.shuffle(game_ids)
    game_fold = {gid: i % RAPM_CV_FOLDS for i, gid in enumerate(game_ids)}

    obs_fold = []
    for obs in observations:
        fold = game_fold[obs["game_id"]]
        obs_fold.extend([fold, fold])

    all_weights = np.array([
        v for obs in observations for v in [obs["home_poss"], obs["away_poss"]]
    ])
    nonzero_mask = all_weights >= MIN_OBS_POSS
    obs_fold_filtered = [f for f, m in zip(obs_fold, nonzero_mask) if m]
    obs_fold_arr = np.array(obs_fold_filtered)

    player_season_keys_ordered = sorted(player_season_index, key=player_season_index.get)
    n_features = X.shape[1]

    # Evaluate selectable candidates + box-only reference
    all_scales_to_eval = list(sd_scale_candidates) + [BOX_ONLY_SD_SCALE_REF]
    cv_errors: dict[float, list[float]] = {s: [] for s in all_scales_to_eval}

    for fold in range(RAPM_CV_FOLDS):
        train_mask = obs_fold_arr != fold
        test_mask  = obs_fold_arr == fold
        X_train, y_train, w_train = X[train_mask], y[train_mask], weights[train_mask]
        X_test,  y_test,  w_test  = X[test_mask],  y[test_mask],  weights[test_mask]

        if w_test.sum() == 0:
            continue

        for s in all_scales_to_eval:
            prior_means_full  = np.zeros(n_features)
            prior_lambda_diag = np.ones(n_features) * 1e-8

            for i, (pid, yr) in enumerate(player_season_keys_ordered):
                ps_key = (pid, yr)
                mu_o = prior_mean_obpr.get(ps_key, 0.0)
                sd_o = prior_sd_obpr.get(ps_key, PRIOR_SD_DEFAULT_OFF) * s
                prior_means_full[2 + i] = mu_o
                prior_lambda_diag[2 + i] = baseline_lambda / max(sd_o, 0.5) ** 2

                mu_d = prior_mean_dbpr.get(ps_key, 0.0)
                sd_d = prior_sd_dbpr.get(ps_key, PRIOR_SD_DEFAULT_DEF) * s
                prior_means_full[2 + n_player_seasons + i] = -mu_d
                prior_lambda_diag[2 + n_player_seasons + i] = baseline_lambda / max(sd_d, 0.5) ** 2

            sqrt_w  = np.sqrt(w_train)
            Xw      = sparse.diags(sqrt_w) @ X_train
            yw      = sqrt_w * y_train
            sqrt_lam = np.sqrt(prior_lambda_diag)
            I_pen   = sparse.diags(sqrt_lam, format="csr")
            pen_tgt = sqrt_lam * prior_means_full

            X_aug = sparse.vstack([Xw, I_pen])
            y_aug = np.concatenate([yw, pen_tgt])

            beta  = lsqr(X_aug, y_aug, show=False)[0]
            y_hat = X_test @ beta
            wmse  = float(np.average((y_test - y_hat) ** 2, weights=w_test))
            cv_errors[s].append(wmse)

    # Separate selectable vs reference
    selectable_errors = {s: cv_errors[s] for s in sd_scale_candidates if cv_errors[s]}
    mean_errors = {s: float(np.mean(errs)) for s, errs in selectable_errors.items()}
    best_sd_scale = min(mean_errors, key=mean_errors.get)

    # Box-only reference WMSE
    box_only_errs = cv_errors.get(BOX_ONLY_SD_SCALE_REF, [])
    box_only_wmse = float(np.mean(box_only_errs)) if box_only_errs else None

    logger.info(
        f"Prior SD scale CV finished. Best s={best_sd_scale:.3f}  "
        f"(mean WMSE={mean_errors[best_sd_scale]:.4f})  "
        f"box-only ref WMSE={f'{box_only_wmse:.4f}' if box_only_wmse is not None else 'N/A'}"
    )

    return best_sd_scale, {
        "sd_scale_candidates": sd_scale_candidates,
        "mean_wmse":           mean_errors,
        "best_sd_scale":       best_sd_scale,
        "n_folds":             RAPM_CV_FOLDS,
        "box_only_reference_wmse": box_only_wmse,
        "tuning_mode":         "joint",
    }


def tune_prior_sd_scales_separate(
    observations: list[dict],
    player_season_index: dict,
    n_player_seasons: int,
    prior_mean_obpr: dict[tuple[int, int], float],
    prior_mean_dbpr: dict[tuple[int, int], float],
    prior_sd_obpr: dict[tuple[int, int], float],
    prior_sd_dbpr: dict[tuple[int, int], float],
    baseline_lambda: float,
    sd_scale_candidates: Optional[list[float]] = None,
    seed: int = 42,
) -> tuple[float, float, float, dict]:
    """
    Tune separate sd_scale_off and sd_scale_def via 1D coordinate descent.

    Step 1: Find best sd_scale_off with sd_scale_def fixed at 1.0.
    Step 2: Find best sd_scale_def with sd_scale_off fixed at result of step 1.
    Step 3: Evaluate combined WMSE at (best_off, best_def).

    Returns:
        best_off    float  — best offensive SD scale
        best_def    float  — best defensive SD scale
        best_wmse   float  — held-out WMSE at (best_off, best_def)
        cv_results  dict
    """
    if sd_scale_candidates is None:
        sd_scale_candidates = PRIOR_SD_SCALE_CANDIDATES

    X, y, weights = build_design_matrix(observations, player_season_index, n_player_seasons)

    game_ids = sorted({obs["game_id"] for obs in observations})
    rng = random.Random(seed)
    rng.shuffle(game_ids)
    game_fold = {gid: i % RAPM_CV_FOLDS for i, gid in enumerate(game_ids)}

    obs_fold = []
    for obs in observations:
        fold = game_fold[obs["game_id"]]
        obs_fold.extend([fold, fold])

    all_weights = np.array([
        v for obs in observations for v in [obs["home_poss"], obs["away_poss"]]
    ])
    nonzero_mask = all_weights >= MIN_OBS_POSS
    obs_fold_arr = np.array([f for f, m in zip(obs_fold, nonzero_mask) if m])

    player_season_keys_ordered = sorted(player_season_index, key=player_season_index.get)
    n_features = X.shape[1]

    def _cv_wmse_separate(s_off: float, s_def: float) -> float:
        """5-fold CV WMSE for a given (sd_scale_off, sd_scale_def) pair."""
        fold_errors = []
        for fold in range(RAPM_CV_FOLDS):
            train_mask = obs_fold_arr != fold
            test_mask  = obs_fold_arr == fold
            X_train, y_train, w_train = X[train_mask], y[train_mask], weights[train_mask]
            X_test,  y_test,  w_test  = X[test_mask],  y[test_mask],  weights[test_mask]
            if w_test.sum() == 0:
                continue

            prior_means_full  = np.zeros(n_features)
            prior_lambda_diag = np.ones(n_features) * 1e-8
            for i, (pid, yr) in enumerate(player_season_keys_ordered):
                ps_key = (pid, yr)
                mu_o = prior_mean_obpr.get(ps_key, 0.0)
                sd_o = prior_sd_obpr.get(ps_key, PRIOR_SD_DEFAULT_OFF) * s_off
                prior_means_full[2 + i] = mu_o
                prior_lambda_diag[2 + i] = baseline_lambda / max(sd_o, 0.5) ** 2

                mu_d = prior_mean_dbpr.get(ps_key, 0.0)
                sd_d = prior_sd_dbpr.get(ps_key, PRIOR_SD_DEFAULT_DEF) * s_def
                prior_means_full[2 + n_player_seasons + i] = -mu_d
                prior_lambda_diag[2 + n_player_seasons + i] = baseline_lambda / max(sd_d, 0.5) ** 2

            sqrt_lam = np.sqrt(prior_lambda_diag)
            X_aug = sparse.vstack([
                sparse.diags(np.sqrt(w_train)) @ X_train,
                sparse.diags(sqrt_lam, format="csr"),
            ])
            y_aug = np.concatenate([
                np.sqrt(w_train) * y_train,
                sqrt_lam * prior_means_full,
            ])
            beta  = lsqr(X_aug, y_aug, show=False)[0]
            y_hat = X_test @ beta
            fold_errors.append(float(np.average((y_test - y_hat) ** 2, weights=w_test)))

        return float(np.mean(fold_errors)) if fold_errors else float("inf")

    # Step 1: find best sd_scale_off (fix def=1.0)
    off_wmses = {s: _cv_wmse_separate(s, 1.0) for s in sd_scale_candidates}
    best_off = min(off_wmses, key=off_wmses.get)

    # Step 2: find best sd_scale_def (fix off=best_off)
    def_wmses = {s: _cv_wmse_separate(best_off, s) for s in sd_scale_candidates}
    best_def = min(def_wmses, key=def_wmses.get)

    # Step 3: combined WMSE at (best_off, best_def)
    combined_wmse = _cv_wmse_separate(best_off, best_def)

    logger.info(
        f"Separate SD scale CV finished. "
        f"best_off={best_off:.3f}, best_def={best_def:.3f}, "
        f"combined WMSE={combined_wmse:.4f}"
    )

    return best_off, best_def, combined_wmse, {
        "sd_scale_candidates": sd_scale_candidates,
        "off_wmse_by_scale":   {s: round(v, 4) for s, v in off_wmses.items()},
        "def_wmse_by_scale":   {s: round(v, 4) for s, v in def_wmses.items()},
        "best_sd_scale_off":   best_off,
        "best_sd_scale_def":   best_def,
        "combined_wmse":       round(combined_wmse, 4),
        "n_folds":             RAPM_CV_FOLDS,
        "tuning_mode":         "separate",
    }


def fit_prior_informed_rapm(
    observations: list[dict],
    player_season_index: dict,
    n_player_seasons: int,
    prior_mean_obpr: dict[tuple[int, int], float],  # (player_id, season_year) → prior mean offensive
    prior_mean_dbpr: dict[tuple[int, int], float],  # (player_id, season_year) → prior mean defensive
    prior_sd_obpr: dict[tuple[int, int], float],    # (player_id, season_year) → prior SD offensive (base)
    prior_sd_dbpr: dict[tuple[int, int], float],    # (player_id, season_year) → prior SD defensive (base)
    baseline_lambda: float,
    sd_scale: float = 1.0,                # legacy joint scale (used when separate scales not set)
    sd_scale_off: Optional[float] = None,  # CV-tuned offensive SD multiplier (overrides sd_scale)
    sd_scale_def: Optional[float] = None,  # CV-tuned defensive SD multiplier (overrides sd_scale)
) -> dict:
    """
    Fit BPR with player-specific Gaussian priors (from Box BPR).

    Prior means/SDs are keyed by (player_id, season_year).  In multi-year mode,
    non-target-season rows carry neutral priors (mean=0, default SD) set upstream
    in pipeline.py — the RAPM data dominates for those rows, which is correct.
    Target-season rows carry the box-BPR-derived prior for the player.

    Returns obpr/dbpr keyed by (player_id, season_year).
    Use extract_target_season() to get {player_id: val} for writes.
    """
    # Separate scales override joint scale when provided
    eff_off = sd_scale_off if sd_scale_off is not None else sd_scale
    eff_def = sd_scale_def if sd_scale_def is not None else sd_scale

    player_season_keys = sorted(player_season_index, key=player_season_index.get)

    # Build per-feature prior vectors
    n_features = 2 + 2 * n_player_seasons
    prior_means_full = np.zeros(n_features)
    prior_lambda_diag = np.ones(n_features) * 1e-8  # nearly no reg on intercept/hca

    for i, (pid, yr) in enumerate(player_season_keys):
        ps_key = (pid, yr)
        # OBPR prior (offensive scale) — looked up by player-season to prevent
        # cross-season prior bleed in multi-year mode
        mu_o  = prior_mean_obpr.get(ps_key, 0.0)
        sd_o  = prior_sd_obpr.get(ps_key, PRIOR_SD_DEFAULT_OFF) * eff_off
        prior_means_full[2 + i] = mu_o
        prior_lambda_diag[2 + i] = baseline_lambda / max(sd_o, 0.5) ** 2

        # DBPR prior (defensive scale); internal sign convention: negate mean
        mu_d  = prior_mean_dbpr.get(ps_key, 0.0)
        sd_d  = prior_sd_dbpr.get(ps_key, PRIOR_SD_DEFAULT_DEF) * eff_def
        prior_means_full[2 + n_player_seasons + i] = -mu_d
        prior_lambda_diag[2 + n_player_seasons + i] = baseline_lambda / max(sd_d, 0.5) ** 2

    # Build design matrix
    X, y, weights = build_design_matrix(observations, player_season_index, n_player_seasons)

    # Weighted data terms
    sqrt_w = np.sqrt(weights)
    Xw = sparse.diags(sqrt_w) @ X
    yw = sqrt_w * y

    # Penalty rows: √(λ_j) for each feature
    sqrt_lambda = np.sqrt(prior_lambda_diag)
    I_pen = sparse.diags(sqrt_lambda, format="csr")
    pen_targets = sqrt_lambda * prior_means_full

    X_aug = sparse.vstack([Xw, I_pen])
    y_aug = np.concatenate([yw, pen_targets])

    logger.info(
        f"Fitting prior-informed RAPM ({X.shape[0]} obs, {n_player_seasons} player-seasons) "
        f"sd_off={eff_off:.3f}, sd_def={eff_def:.3f} …"
    )
    result = lsqr(X_aug, y_aug, show=False)
    beta = result[0]

    intercept = float(beta[0])
    hca       = float(beta[1])
    obpr_block = beta[2 : 2 + n_player_seasons]
    dbpr_block = beta[2 + n_player_seasons : 2 + 2 * n_player_seasons]

    obpr = {ps: float(obpr_block[i]) for i, ps in enumerate(player_season_keys)}
    dbpr = {ps: float(-dbpr_block[i]) for i, ps in enumerate(player_season_keys)}  # flip sign

    return {
        "obpr":         obpr,
        "dbpr":         dbpr,
        "intercept":    intercept,
        "hca":          hca,
        "sd_scale_off": eff_off,
        "sd_scale_def": eff_def,
    }


# ── Target-season extraction helper ─────────────────────────────────────────

def extract_target_season(
    rapm_map: dict,
    target_year: int,
) -> dict[int, float]:
    """
    Slice a player-season-keyed RAPM result dict down to the target season.

    Takes:  {(player_id, season_year): float, ...}
    Returns: {player_id: float}  for entries where season_year == target_year.

    In single-season mode (all entries share the same year) this is equivalent
    to the old {player_id: float} dict.  In multi-year mode it extracts only
    the coefficients for the season being written to PlayerSeasonStats.
    """
    return {
        pid: val
        for (pid, yr), val in rapm_map.items()
        if yr == target_year
    }
