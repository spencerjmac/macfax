"""
rapm.py — NBA RAPM fitting (Regularized Adjusted Plus-Minus).

Ported from ncaa/analytics/player_value/bpr/rapm.py with NBA-specific
observation builder (from NBAPlayerGameStint rows rather than ESPN PBP stints).

Design matrix layout (sparse, CSR) — identical to NCAA:
  Columns: [intercept (0) | hca (1) | obpr_0…obpr_{N-1} | dbpr_0…dbpr_{N-1}]
  Rows:    2 per lineup observation (home-offense + away-offense)
  Targets: offensive efficiency = (pts / poss) × 100
  Weights: possessions (not time — a 3-poss stint ≠ a 40-poss stint)

DBPR sign convention: internally fit as positive = allowed more (bad defender).
Negated in output so higher DBPR → better defense. Same as NCAA.

Lambda selection: 5-fold CV on game folds (not observation folds) to prevent
leakage across observations from the same game.

NBA-specific differences vs NCAA:
  - player_season_index keyed by (NBAPlayer.player_id, season_year)
    where player_id is the NBA.com canonical integer ID (not Django pk)
  - Observations built from NBAPlayerGameStint rows grouped by (game, stint_index)
  - pbp_quality_flag=True games excluded from RAPM training
  - Lambda candidates start at 500 as anchor; CV typically selects lower for NBA
"""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from typing import Optional

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import lsqr

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

RAPM_LAMBDA_CANDIDATES = [1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0]
RAPM_CV_FOLDS = 5
MIN_OBS_POSS  = 2.0   # minimum possession count to include a stint observation


# ── Observation builder ───────────────────────────────────────────────────────

def build_nba_observations(
    season_year: int,
    rapm_years: list[int] | None = None,
) -> list[dict]:
    """
    Load NBAPlayerGameStint rows and construct RAPM observation dicts.

    Each observation covers one full 5v5 stint (game_id + game-level stint_index).
    Games with pbp_quality_flag=True are excluded.

    Multi-year RAPM: pass rapm_years=[2024, 2025, 2026] to pool stints across
    seasons. Each player-season gets its own OBPR/DBPR column, enabling correct
    multi-year regularization. Only target-season coefficients are written to DB.

    Returns list of dicts:
      {
        "game_id":         str,
        "season_year":     int,
        "home_player_ids": list[int],   # NBAPlayer.player_id (NBA.com ID)
        "away_player_ids": list[int],
        "home_pts":        int,
        "away_pts":        int,
        "home_poss":       float,
        "away_poss":       float,
      }
    """
    from nba.models import NBAGame, NBAPlayerGameStint

    years = sorted(set(rapm_years or [season_year]))

    all_observations: list[dict] = []

    for year in years:
        # Load all stints for this season (exclude quality-flagged games)
        stints = list(
            NBAPlayerGameStint.objects.filter(
                game__season__year=year,
                game__pbp_quality_flag=False,
                game__counts_toward_regular_season=True,
            ).select_related(
                "player", "game", "game__home_team", "game__away_team", "team"
            ).only(
                "player__player_id",
                "game__game_id",
                "game__home_team__nba_team_id",
                "game__away_team__nba_team_id",
                "team__nba_team_id",
                "stint_index",
                "pts_scored", "pts_allowed",
                "team_fgm", "team_fga", "team_fg3m", "team_fta", "team_tov", "team_oreb", "team_dreb",
                "opp_fgm", "opp_fga", "opp_fg3m", "opp_fta", "opp_tov", "opp_oreb", "opp_dreb",
            )
        )

        if not stints:
            logger.warning("No stints found for season %s (check nba_sync_play_by_play)", year)
            continue

        # Group by (game_id, game-level stint_index)
        # game-level stint_index = stint_index within this player (per-player counter)
        # We reconstruct game-level lineups by grouping player stints that share
        # the same (game_id, period, clock_start_secs, clock_end_secs) window.
        # Using (game_id, period, clock_start, clock_end) as the lineup key.

        Stint = type(stints[0])  # model class

        # Build lookup: game_pk → NBAGame attributes
        game_meta: dict[int, dict] = {}
        for s in stints:
            g = s.game
            if g.pk not in game_meta:
                game_meta[g.pk] = {
                    "game_id": g.game_id,
                    "home_team_id": g.home_team.nba_team_id,
                    "away_team_id": g.away_team.nba_team_id,
                }

        # Group stints by (game_pk, period, clock_start, clock_end)
        lineup_groups: dict[tuple, list] = defaultdict(list)
        for s in stints:
            key = (s.game_id, s.period, s.clock_start_secs, s.clock_end_secs)
            lineup_groups[key].append(s)

        year_obs = 0
        for key, group in lineup_groups.items():
            game_pk_int = key[0]   # s.game_id is the NBAGame Django pk (int), not game_id string
            g_meta = game_meta.get(game_pk_int)
            if g_meta is None:
                continue

            home_team_id = g_meta["home_team_id"]
            away_team_id = g_meta["away_team_id"]

            home_players: list[int] = []
            away_players: list[int] = []
            home_pts = 0
            away_pts = 0
            home_fga = home_oreb = home_tov = home_fta = 0
            away_fga = away_oreb = away_tov = away_fta = 0

            for s in group:
                pid = s.player.player_id   # NBA.com canonical ID
                team_nba_id = s.team.nba_team_id if s.team else None
                if team_nba_id == home_team_id:
                    home_players.append(pid)
                    home_pts = s.pts_scored    # all players in same stint have same value
                    away_pts = s.pts_allowed
                    home_fga  += s.team_fga    # sum across players would double-count;
                    home_oreb += s.team_oreb   # these are per-player duplicates of team counts
                    home_tov  += s.team_tov    # → use just the first home player's values
                    home_fta  += s.team_fta
                elif team_nba_id == away_team_id:
                    away_players.append(pid)
                    away_fga  += s.team_fga
                    away_oreb += s.team_oreb
                    away_tov  += s.team_tov
                    away_fta  += s.team_fta

            if len(home_players) != 5 or len(away_players) != 5:
                continue  # already filtered by 10-player check; paranoia guard

            # Use first player's team counts (all players have same team totals per stint)
            # The per-player rows duplicate team box counts — take from one representative
            rep_home = next((s for s in group if s.team and s.team.nba_team_id == home_team_id), None)
            rep_away = next((s for s in group if s.team and s.team.nba_team_id == away_team_id), None)
            if rep_home is None or rep_away is None:
                continue

            home_poss = (
                rep_home.team_fga - rep_home.team_oreb + rep_home.team_tov + 0.44 * rep_home.team_fta
            )
            away_poss = (
                rep_away.team_fga - rep_away.team_oreb + rep_away.team_tov + 0.44 * rep_away.team_fta
            )

            if home_poss < MIN_OBS_POSS and away_poss < MIN_OBS_POSS:
                continue

            all_observations.append({
                "game_id":         g_meta["game_id"],
                "season_year":     year,
                "home_player_ids": home_players,
                "away_player_ids": away_players,
                "home_pts":        rep_home.pts_scored,
                "away_pts":        rep_home.pts_allowed,
                "home_poss":       max(0.0, home_poss),
                "away_poss":       max(0.0, away_poss),
            })
            year_obs += 1

        logger.info("Season %s: %d lineup observations from %d stints", year, year_obs, len(stints))

    logger.info("Total observations across %s seasons: %d", years, len(all_observations))
    return all_observations


# ── Design matrix ─────────────────────────────────────────────────────────────

def build_design_matrix(
    observations: list[dict],
    player_season_index: dict,   # (player_id, season_year) → col index (0-based)
    n_player_seasons: int,
) -> tuple[sparse.csr_matrix, np.ndarray, np.ndarray]:
    """
    Build sparse CSR design matrix X, target vector y, weights vector w.

    Two rows per observation: home-offense (idx*2) and away-offense (idx*2+1).
    """
    n_obs = len(observations) * 2
    n_features = 2 + 2 * n_player_seasons

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
        obs_year = obs["season_year"]
        hca_sign = 1.0   # NBA always has a designated home team

        # ── Home-offense row ─────────────────────────────────────────────────
        i = idx * 2
        if h_poss >= MIN_OBS_POSS:
            y[i] = h_pts / h_poss * 100.0
            weights[i] = h_poss
            rows.append(i); cols.append(0); vals.append(1.0)           # intercept
            rows.append(i); cols.append(1); vals.append(hca_sign)      # hca
            for pid in home_ids:
                j = player_season_index.get((pid, obs_year))
                if j is not None:
                    rows.append(i); cols.append(2 + j); vals.append(1.0)
            for pid in away_ids:
                j = player_season_index.get((pid, obs_year))
                if j is not None:
                    rows.append(i); cols.append(2 + n_player_seasons + j); vals.append(1.0)

        # ── Away-offense row ─────────────────────────────────────────────────
        i = idx * 2 + 1
        if a_poss >= MIN_OBS_POSS:
            y[i] = a_pts / a_poss * 100.0
            weights[i] = a_poss
            rows.append(i); cols.append(0); vals.append(1.0)
            rows.append(i); cols.append(1); vals.append(-hca_sign)
            for pid in away_ids:
                j = player_season_index.get((pid, obs_year))
                if j is not None:
                    rows.append(i); cols.append(2 + j); vals.append(1.0)
            for pid in home_ids:
                j = player_season_index.get((pid, obs_year))
                if j is not None:
                    rows.append(i); cols.append(2 + n_player_seasons + j); vals.append(1.0)

    X = sparse.coo_matrix(
        (vals, (rows, cols)), shape=(n_obs, n_features)
    ).tocsr()

    mask = weights > 0
    return X[mask], y[mask], weights[mask]


# ── Augmented solver ──────────────────────────────────────────────────────────

def _solve_augmented(
    X: sparse.csr_matrix,
    y: np.ndarray,
    weights: np.ndarray,
    lambda_val: float,
    prior_means: Optional[np.ndarray] = None,
    player_col_slice: Optional[tuple[int, int]] = None,
) -> np.ndarray:
    """
    Weighted ridge regression via augmented least squares.

    Solves: min_β ||√W (Xβ − y)||² + λ ||β_players − μ||²

    Intercept and HCA columns are NOT regularized (player_col_slice excludes them).
    """
    n_features = X.shape[1]
    if prior_means is None:
        prior_means = np.zeros(n_features)

    sqrt_w = np.sqrt(weights)
    Xw = sparse.diags(sqrt_w) @ X
    yw = sqrt_w * y

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
    return lsqr(X_aug, y_aug, show=False)[0]


# ── Cross-validation ──────────────────────────────────────────────────────────

def cross_validate_lambda(
    observations: list[dict],
    X: sparse.csr_matrix,
    y: np.ndarray,
    weights: np.ndarray,
    n_player_seasons: int,
    seed: int = 42,
) -> tuple[float, dict]:
    """
    5-fold CV on game folds to select λ. Criterion: weighted MSE of offensive efficiency.
    """
    game_ids = sorted({obs["game_id"] for obs in observations})
    rng = random.Random(seed)
    rng.shuffle(game_ids)
    game_fold = {gid: i % RAPM_CV_FOLDS for i, gid in enumerate(game_ids)}

    all_weights_full = np.array([
        v for obs in observations for v in [obs["home_poss"], obs["away_poss"]]
    ])
    nonzero_mask = all_weights_full >= MIN_OBS_POSS

    obs_fold_full = []
    for obs in observations:
        fold = game_fold[obs["game_id"]]
        obs_fold_full.extend([fold, fold])
    obs_fold_arr = np.array([f for f, m in zip(obs_fold_full, nonzero_mask) if m])

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
            beta  = _solve_augmented(X_train, y_train, w_train, lam, player_col_slice=player_col_slice)
            y_hat = X_test @ beta
            wmse  = float(np.average((y_test - y_hat) ** 2, weights=w_test))
            cv_errors[lam].append(wmse)

    mean_errors = {lam: float(np.mean(errs)) for lam, errs in cv_errors.items() if errs}
    best_lambda = min(mean_errors, key=mean_errors.get)

    logger.info("RAPM CV done. Best λ=%.1f (WMSE=%.4f)", best_lambda, mean_errors[best_lambda])
    return best_lambda, {
        "lambda_candidates": RAPM_LAMBDA_CANDIDATES,
        "mean_wmse": mean_errors,
        "best_lambda": best_lambda,
        "n_folds": RAPM_CV_FOLDS,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def fit_baseline_rapm(
    observations: list[dict],
    player_season_index: dict,   # (player_id, season_year) → col index
    n_player_seasons: int,
    run_cv: bool = True,
    lambda_override: Optional[float] = None,
) -> dict:
    """
    Fit baseline RAPM with global prior μ=0, λ selected by 5-fold game CV.

    Returns:
      {
        "obpr":       dict[(player_id, season_year), float],
        "dbpr":       dict[(player_id, season_year), float],
        "intercept":  float,
        "hca":        float,
        "lambda":     float,
        "cv_metrics": dict | None,
      }
    """
    logger.info("Building RAPM design matrix for %d observations...", len(observations))
    X, y, weights = build_design_matrix(observations, player_season_index, n_player_seasons)
    logger.info("  Matrix: %s × %s (%d non-zeros)", X.shape[0], X.shape[1], X.nnz)

    player_col_slice = (2, 2 + 2 * n_player_seasons)
    cv_metrics = None

    if lambda_override is not None:
        best_lambda = lambda_override
        logger.info("Using lambda_override=%.1f", best_lambda)
    elif run_cv:
        best_lambda, cv_metrics = cross_validate_lambda(
            observations, X, y, weights, n_player_seasons
        )
    else:
        best_lambda = 500.0

    logger.info("Fitting baseline RAPM with λ=%.1f ...", best_lambda)
    beta = _solve_augmented(X, y, weights, best_lambda, player_col_slice=player_col_slice)

    intercept = float(beta[0])
    hca       = float(beta[1])
    obpr_block = beta[2 : 2 + n_player_seasons]
    dbpr_block = beta[2 + n_player_seasons : 2 + 2 * n_player_seasons]

    player_season_keys = sorted(player_season_index, key=player_season_index.get)

    # DBPR sign flip: positive raw = allowed more (bad defender) → negate
    obpr = {ps: float(obpr_block[i]) for i, ps in enumerate(player_season_keys)}
    dbpr = {ps: float(-dbpr_block[i]) for i, ps in enumerate(player_season_keys)}

    logger.info(
        "RAPM done. HCA=%.2f intercept=%.2f. "
        "OBPR range [%.2f, %.2f], DBPR range [%.2f, %.2f]",
        hca, intercept,
        min(obpr.values()), max(obpr.values()),
        min(dbpr.values()), max(dbpr.values()),
    )

    return {
        "obpr":       obpr,
        "dbpr":       dbpr,
        "intercept":  intercept,
        "hca":        hca,
        "lambda":     best_lambda,
        "cv_metrics": cv_metrics,
    }


def fit_prior_informed_rapm(
    observations: list[dict],
    player_season_index: dict,
    n_player_seasons: int,
    prior_obpr: dict[int, float],   # {nba_player_id: box_obpr prior mean}
    prior_dbpr: dict[int, float],   # {nba_player_id: box_dbpr prior mean}
    lambda_val: float,
) -> dict:
    """
    LEBRON-style regularized on-off: RAPM regularized toward per-player box-score priors.

    Instead of shrinking toward zero (baseline RAPM), each player's coefficient is
    pulled toward their box_obpr / box_dbpr prior. This reduces team-quality bias
    by grounding the estimate in a team-adjusted prior while updating with lineup data.

    prior_obpr / prior_dbpr are keyed by NBA.com player_id (same as player_season_index).
    """
    X, y, weights = build_design_matrix(observations, player_season_index, n_player_seasons)

    player_season_keys = sorted(player_season_index, key=player_season_index.get)
    n_features = X.shape[1]
    prior_means = np.zeros(n_features)

    for i, (pid, _yr) in enumerate(player_season_keys):
        prior_means[2 + i] = prior_obpr.get(pid, 0.0)
        # DBPR internal sign: positive = allowed more (bad defense). Negate the prior.
        prior_means[2 + n_player_seasons + i] = -prior_dbpr.get(pid, 0.0)

    player_col_slice = (2, 2 + 2 * n_player_seasons)
    beta = _solve_augmented(X, y, weights, lambda_val, prior_means=prior_means,
                            player_col_slice=player_col_slice)

    intercept  = float(beta[0])
    hca        = float(beta[1])
    obpr_block = beta[2 : 2 + n_player_seasons]
    dbpr_block = beta[2 + n_player_seasons : 2 + 2 * n_player_seasons]

    obpr = {ps: float(obpr_block[i]) for i, ps in enumerate(player_season_keys)}
    dbpr = {ps: float(-dbpr_block[i]) for i, ps in enumerate(player_season_keys)}

    logger.info(
        "Prior-informed RAPM done (λ=%.1f). "
        "OBPR range [%.2f, %.2f], DBPR range [%.2f, %.2f]",
        lambda_val,
        min(obpr.values()), max(obpr.values()),
        min(dbpr.values()), max(dbpr.values()),
    )

    return {
        "obpr":      obpr,
        "dbpr":      dbpr,
        "intercept": intercept,
        "hca":       hca,
        "lambda":    lambda_val,
    }
