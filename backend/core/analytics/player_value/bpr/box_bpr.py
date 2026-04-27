"""
box_bpr.py — Box-score Bayesian Performance Rating model.

Trains two Ridge regression models (offensive and defensive) that map
per-100-possession box-score features to RAPM targets, then uses the
trained models to generate priors for players in seasons where we lack
on-court PBP data.

Features used (per 100 offensive possessions for OBPR,
per 100 defensive possessions for DBPR):

  Offensive (13):
    pts100       — points
    ast100       — assists
    tov100       — turnovers (negative weight expected)
    oreb100      — offensive rebounds
    fga100       — field-goal attempts
    fg3a100      — 3-point attempts
    fta100       — free-throw attempts
    efg_pct      — effective field-goal %
    ts_pct       — true shooting % (proxy for efficiency)
    min_share    — minutes share (fraction of game played = mpg/40)
    fg3_rate     — 3PA / FGA  (shot-selection profile)
    ft_rate      — FTA / FGA  (ability to draw fouls)
    ast_tov_ratio — AST / max(TOV, 0.1)  (playmaking efficiency)
    usage_rate   — (FGA + 0.44×FTA + TOV) per 100 poss  (offensive load)
    ast_rate     — AST100 / max(usage_rate, 1)  (playmaking vs scoring role)

  Defensive (8):
    stl100       — steals
    blk100       — blocks
    dreb100      — defensive rebounds
    pf100        — personal fouls (negative weight expected)
    min_share    — minutes share
    fg3a_share   — 3PA / FGA  (position/role proxy: guards vs bigs)
    oreb_share   — OREB / max(total REB, 0.01)  (rebounding-role indicator)
    pf_per_min   — PF per 40 min  (complementary foul-rate angle)

  Pruned from v1.2 (v1.3 collinearity fix):
    reb100       — removed; collinear with dreb100 + oreb_share
    stl_blk100   — removed; exact linear combination of stl100 + blk100

Leakage prevention:
  When >= MIN_PRIOR_TRAINING_SAMPLES prior-season RAPM records exist,
  Box BPR is trained on prior seasons (train_box_bpr_prior_seasons).
  When prior-season data is insufficient, out-of-fold (k-fold on players)
  predictions are generated (out_of_fold_box_bpr) so no player's prior
  is trained on that player's own RAPM target.

Assumptions documented in constants.py (Deviation #3).
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from core.analytics.player_value.bpr.constants import (
    BOX_BPR_ALPHAS_OFF,
    BOX_BPR_ALPHAS_DEF,
    BOX_BPR_CV_FOLDS,
    BOX_BPR_OOF_FOLDS,
    MIN_MPG_BOX_BPR,
    MIN_GP_BOX_BPR,
)

logger = logging.getLogger(__name__)

# Feature lists — order matters: must match extract_box_features()
OFF_FEATURES = [
    "pts100", "ast100", "tov100", "oreb100",
    "fga100", "fg3a100", "fta100",
    "efg_pct", "ts_pct", "min_share",
    "fg3_rate", "ft_rate", "ast_tov_ratio",
    "opp_quality",   # avg adj_em of opponents faced (schedule strength)
    "usage_rate",    # (FGA + 0.44*FTA + TOV) per 100 poss — offensive load signal
    "ast_rate",      # AST100 / usage_rate — playmaking vs scoring role signal
]
DEF_FEATURES = [
    "stl100", "blk100", "dreb100", "pf100", "min_share",
    "fg3a_share", "oreb_share", "pf_per_min",
    "opp_quality",   # same value, both models
]


# ── Feature extraction ────────────────────────────────────────────────────────

def extract_box_features(
    player_season_stats: list[dict],   # dicts from PlayerSeasonStats.values(...)
    off_poss_map: dict[int, float],    # player_id → total off possessions (from RAPM dataset)
    def_poss_map: dict[int, float],    # player_id → total def possessions
    opp_quality_map: "dict[int, float] | None" = None,  # team_id → mean opp adj_em
) -> dict[int, dict]:
    """
    Compute per-100-possession features for each qualified player.

    opp_quality_map: team_id → mean adj_em of opponents faced this season.
        Adjusts for schedule strength. Missing teams default to 0.0 (league avg).

    Returns: {player_id: {"off": [feature_values], "def": [feature_values]}}
    Only includes players meeting the minimum qualifier.
    """
    _opp_quality = opp_quality_map or {}
    features: dict[int, dict] = {}

    for p in player_season_stats:
        pid = p["player_id"] if "player_id" in p else p.get("id")
        if pid is None:
            continue

        gp  = p.get("gp", 0) or 0
        mpg = p.get("mpg", 0.0) or 0.0
        if gp < MIN_GP_BOX_BPR or mpg < MIN_MPG_BOX_BPR:
            continue

        off_poss = off_poss_map.get(pid, 0.0)
        def_poss = def_poss_map.get(pid, 0.0)
        if off_poss < 1.0 or def_poss < 1.0:
            continue

        def per100(stat_pg: float, gp: int, poss: float) -> float:
            """Convert per-game stat to per-100-possessions."""
            if poss <= 0:
                return 0.0
            return (stat_pg * gp) / poss * 100.0

        pts_pg   = p.get("pts", 0.0) or 0.0
        ast_pg   = p.get("ast", 0.0) or 0.0
        tov_pg   = p.get("tov", 0.0) or 0.0
        oreb_pg  = p.get("oreb_pg", 0.0) or 0.0
        dreb_pg  = p.get("dreb_pg", 0.0) or 0.0
        fga_pg   = p.get("fga_pg", 0.0) or 0.0
        fg3a_pg  = p.get("fg3a_pg", 0.0) or 0.0
        fta_pg   = p.get("fta_pg", 0.0) or 0.0
        stl_pg   = p.get("stl", 0.0) or 0.0
        blk_pg   = p.get("blk", 0.0) or 0.0
        pf_pg    = p.get("pf", 0.0) or 0.0
        efg_pct  = p.get("efg_pct", 0.0) or 0.0
        ts_pct   = p.get("ts_pct", 0.0) or 0.0
        min_share = min(mpg / 40.0, 1.0)

        # team_id from .values() as "team_id"; some legacy paths use "team"
        team_id = p.get("team_id") or p.get("team")
        opp_quality = _opp_quality.get(team_id, 0.0) if team_id else 0.0

        fga100  = per100(fga_pg,  gp, off_poss)
        fta100  = per100(fta_pg,  gp, off_poss)
        tov100  = per100(tov_pg,  gp, off_poss)
        ast100  = per100(ast_pg,  gp, off_poss)
        usage_rate = fga100 + 0.44 * fta100 + tov100
        ast_rate   = ast100 / max(usage_rate, 1.0)

        off_feat = [
            per100(pts_pg,  gp, off_poss),
            ast100,
            tov100,
            per100(oreb_pg, gp, off_poss),
            fga100,
            per100(fg3a_pg, gp, off_poss),
            fta100,
            efg_pct,
            ts_pct,
            min_share,
            fg3a_pg / max(fga_pg, 0.01),               # fg3_rate: shot-selection profile
            fta_pg  / max(fga_pg, 0.01),               # ft_rate: foul-drawing ability
            ast_pg  / max(tov_pg, 0.1),                # ast_tov_ratio: playmaking efficiency
            opp_quality,
            usage_rate,
            ast_rate,
        ]

        total_reb_pg = oreb_pg + dreb_pg
        def_feat = [
            per100(stl_pg,  gp, def_poss),
            per100(blk_pg,  gp, def_poss),
            per100(dreb_pg, gp, def_poss),
            per100(pf_pg,   gp, def_poss),
            min_share,
            # (v1.3: reb100 and stl_blk100 removed — collinear with existing features)
            fg3a_pg / max(fga_pg, 0.01),                                      # fg3a_share: position proxy
            oreb_pg / max(total_reb_pg, 0.01),                               # oreb_share: rebounding-role indicator
            pf_pg * (40.0 / max(mpg, 1.0)),                                  # pf_per_min: foul rate per 40 min
            opp_quality,
        ]

        features[pid] = {"off": off_feat, "def": def_feat}

    return features


# ── Model training ────────────────────────────────────────────────────────────

def _build_pipeline(alphas: list[float], cv_folds: int) -> Pipeline:
    """Ridge regression pipeline with standard scaling and CV alpha selection."""
    return Pipeline([
        ("scaler", StandardScaler()),
        ("ridge",  RidgeCV(alphas=alphas, cv=cv_folds, scoring="neg_mean_squared_error")),
    ])


def train_box_bpr(
    player_season_stats: list[dict],
    off_poss_map: dict[int, float],
    def_poss_map: dict[int, float],
    rapm_obpr: dict[int, float],   # player_id → baseline RAPM OBPR targets
    rapm_dbpr: dict[int, float],   # player_id → baseline RAPM DBPR targets
    opp_quality_map: "dict[int, float] | None" = None,
) -> dict:
    """
    Train offensive and defensive Box BPR models.

    Returns:
        {
          "off_pipeline": fitted sklearn Pipeline (StandardScaler + RidgeCV)
          "def_pipeline": fitted sklearn Pipeline
          "off_cv_alpha": float
          "def_cv_alpha": float
          "off_cv_mse":   float
          "def_cv_mse":   float
          "n_train":      int
          "off_features": list[str]
          "def_features": list[str]
        }
    """
    box_features = extract_box_features(
        player_season_stats, off_poss_map, def_poss_map,
        opp_quality_map=opp_quality_map,
    )

    # Build training arrays — only players who have both box features AND RAPM targets
    off_X, off_y, off_pids = [], [], []
    def_X, def_y, def_pids = [], [], []

    for pid, feats in box_features.items():
        if pid in rapm_obpr:
            off_X.append(feats["off"])
            off_y.append(rapm_obpr[pid])
            off_pids.append(pid)
        if pid in rapm_dbpr:
            def_X.append(feats["def"])
            def_y.append(rapm_dbpr[pid])
            def_pids.append(pid)

    if not off_X or not def_X:
        raise ValueError(
            f"Insufficient training data for Box BPR: "
            f"off_samples={len(off_X)}, def_samples={len(def_X)}"
        )

    logger.info(f"Training Box BPR models: {len(off_X)} off, {len(def_X)} def training samples")

    off_Xarr = np.array(off_X, dtype=np.float64)
    off_yarr = np.array(off_y, dtype=np.float64)
    def_Xarr = np.array(def_X, dtype=np.float64)
    def_yarr = np.array(def_y, dtype=np.float64)

    off_pipe = _build_pipeline(BOX_BPR_ALPHAS_OFF, BOX_BPR_CV_FOLDS)
    def_pipe = _build_pipeline(BOX_BPR_ALPHAS_DEF, BOX_BPR_CV_FOLDS)

    off_pipe.fit(off_Xarr, off_yarr)
    def_pipe.fit(def_Xarr, def_yarr)

    off_alpha = float(off_pipe.named_steps["ridge"].alpha_)
    def_alpha = float(def_pipe.named_steps["ridge"].alpha_)

    logger.info(f"Box BPR trained. Off α={off_alpha:.4f}, Def α={def_alpha:.4f}")

    return {
        "off_pipeline": off_pipe,
        "def_pipeline": def_pipe,
        "off_cv_alpha": off_alpha,
        "def_cv_alpha": def_alpha,
        "n_train":      len(off_X),
        "off_features": OFF_FEATURES,
        "def_features": DEF_FEATURES,
    }


def compute_prior_sds_from_r2(
    model_artifacts: dict,
    rapm_obpr: dict[int, float],
    rapm_dbpr: dict[int, float],
    player_season_stats: list[dict],
    off_poss_map: dict[int, float],
    def_poss_map: dict[int, float],
    opp_quality_map: "dict[int, float] | None" = None,
    precomputed_off_preds: "dict[int, float] | None" = None,
    precomputed_def_preds: "dict[int, float] | None" = None,
) -> tuple[float, float]:
    """
    Derive prior SDs from the box model's R² against RAPM targets.

    Formula (per EvanMiya's methodology):
        σ_rapm   = std(baseline_rapm_coefficients)
        R²       = fraction of σ_rapm² explained by box predictions
        prior_sd = sqrt(1 - R²) × σ_rapm

    Args:
        precomputed_off_preds / precomputed_def_preds:
            When provided (OOF path), skip re-running predict() and use
            these directly as y_hat.  Keys are player_ids, values are
            box_obpr / box_dbpr floats.

    Returns:
        (prior_sd_off, prior_sd_def) in pts/100 poss units.
    """
    from core.analytics.player_value.bpr.constants import (
        PRIOR_SD_BOX_OFF, PRIOR_SD_BOX_DEF,
    )

    off_pipe = model_artifacts["off_pipeline"]
    def_pipe = model_artifacts["def_pipeline"]

    if precomputed_off_preds is not None and precomputed_def_preds is not None:
        # OOF path — use stored out-of-fold predictions directly (truly OOS)
        off_pids = [pid for pid in precomputed_off_preds if pid in rapm_obpr]
        def_pids = [pid for pid in precomputed_def_preds if pid in rapm_dbpr]

        if len(off_pids) < 10 or len(def_pids) < 10:
            logger.warning(
                f"compute_prior_sds_from_r2 (OOF): too few players "
                f"(off={len(off_pids)}, def={len(def_pids)}). Falling back to constants."
            )
            return PRIOR_SD_BOX_OFF, PRIOR_SD_BOX_DEF

        off_y   = np.array([rapm_obpr[pid] for pid in off_pids])
        off_hat = np.array([precomputed_off_preds[pid] for pid in off_pids])
        def_y   = np.array([rapm_dbpr[pid] for pid in def_pids])
        def_hat = np.array([precomputed_def_preds[pid] for pid in def_pids])

    else:
        # Prior-season training path — extract features + predict current season
        box_features = extract_box_features(
            player_season_stats, off_poss_map, def_poss_map,
            opp_quality_map=opp_quality_map,
        )

        off_pids = [pid for pid in box_features if pid in rapm_obpr]
        def_pids = [pid for pid in box_features if pid in rapm_dbpr]

        if len(off_pids) < 10 or len(def_pids) < 10:
            logger.warning(
                f"compute_prior_sds_from_r2: too few players "
                f"(off={len(off_pids)}, def={len(def_pids)}). Falling back to constants."
            )
            return PRIOR_SD_BOX_OFF, PRIOR_SD_BOX_DEF

        off_X   = np.array([box_features[pid]["off"] for pid in off_pids])
        off_y   = np.array([rapm_obpr[pid] for pid in off_pids])
        def_X   = np.array([box_features[pid]["def"] for pid in def_pids])
        def_y   = np.array([rapm_dbpr[pid] for pid in def_pids])
        off_hat = off_pipe.predict(off_X)
        def_hat = def_pipe.predict(def_X)

    def _r2_and_sd(y: np.ndarray, y_hat: np.ndarray) -> tuple[float, float]:
        sigma = float(np.std(y, ddof=1))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        ss_res = float(np.sum((y - y_hat) ** 2))
        r2 = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
        prior_sd = float(np.sqrt(max(1.0 - r2, 0.0)) * sigma)
        prior_sd = float(np.clip(prior_sd, 0.5, 8.0))
        return r2, prior_sd

    r2_off, prior_sd_off = _r2_and_sd(off_y, off_hat)
    r2_def, prior_sd_def = _r2_and_sd(def_y, def_hat)

    sigma_off = float(np.std(off_y, ddof=1))
    sigma_def = float(np.std(def_y, ddof=1))

    logger.info(
        f"[BoxBPR] R²-derived prior SDs — "
        f"off: R²={r2_off:.3f}, σ_rapm={sigma_off:.3f}, prior_sd={prior_sd_off:.3f} | "
        f"def: R²={r2_def:.3f}, σ_rapm={sigma_def:.3f}, prior_sd={prior_sd_def:.3f}"
    )

    return prior_sd_off, prior_sd_def


# ── Inference (predict Box BPR for all players) ───────────────────────────────

def predict_box_bpr(
    player_season_stats: list[dict],
    off_poss_map: dict[int, float],
    def_poss_map: dict[int, float],
    model_artifacts: dict,
    opp_quality_map: "dict[int, float] | None" = None,
) -> dict[int, dict]:
    """
    Predict Box BPR for all qualified players using trained pipelines.

    Returns:
        {player_id: {"box_obpr": float, "box_dbpr": float}}
    """
    off_pipe = model_artifacts["off_pipeline"]
    def_pipe = model_artifacts["def_pipeline"]

    box_features = extract_box_features(
        player_season_stats, off_poss_map, def_poss_map,
        opp_quality_map=opp_quality_map,
    )

    preds: dict[int, dict] = {}
    for pid, feats in box_features.items():
        off_X = np.array([feats["off"]])
        def_X = np.array([feats["def"]])

        box_obpr = float(off_pipe.predict(off_X)[0])
        box_dbpr = float(def_pipe.predict(def_X)[0])

        preds[pid] = {"box_obpr": box_obpr, "box_dbpr": box_dbpr}

    return preds


# ── Artifact serialization (for BPRModelArtifact) ────────────────────────────

def export_model_artifacts(model_artifacts: dict, season_year: int) -> dict:
    """
    Extract serializable metadata from fitted Box BPR pipelines for storage
    in the BPRModelArtifact database record (coefficients + feature names).
    NOTE: does NOT store the full sklearn model object (no pickle in DB).
    The pipeline objects are held in memory during the pipeline run only.
    """
    off_ridge = model_artifacts["off_pipeline"].named_steps["ridge"]
    def_ridge = model_artifacts["def_pipeline"].named_steps["ridge"]
    off_scaler = model_artifacts["off_pipeline"].named_steps["scaler"]
    def_scaler = model_artifacts["def_pipeline"].named_steps["scaler"]

    def _scaler_metadata(scaler: StandardScaler, feature_names: list[str]) -> dict:
        return {
            "mean_": scaler.mean_.tolist(),
            "scale_": scaler.scale_.tolist(),
            "feature_names": feature_names,
        }

    return {
        "off": {
            "feature_names": model_artifacts["off_features"],
            "coefficients":  off_ridge.coef_.tolist(),
            "intercept":     float(off_ridge.intercept_),
            "alpha":         model_artifacts["off_cv_alpha"],
            "scaler":        _scaler_metadata(off_scaler, model_artifacts["off_features"]),
        },
        "def": {
            "feature_names": model_artifacts["def_features"],
            "coefficients":  def_ridge.coef_.tolist(),
            "intercept":     float(def_ridge.intercept_),
            "alpha":         model_artifacts["def_cv_alpha"],
            "scaler":        _scaler_metadata(def_scaler, model_artifacts["def_features"]),
        },
        "n_train":          model_artifacts["n_train"],
        "training_method":  model_artifacts.get("training_method", "in_sample"),
    }


# ── Leak-free training helpers ────────────────────────────────────────────────

def out_of_fold_box_bpr(
    player_season_stats: list[dict],
    off_poss_map: dict[int, float],
    def_poss_map: dict[int, float],
    rapm_obpr: dict[int, float],
    rapm_dbpr: dict[int, float],
    n_folds: int = BOX_BPR_OOF_FOLDS,
    seed: int = 42,
    opp_quality_map: "dict[int, float] | None" = None,
) -> tuple[dict, dict]:
    """
    Generate leak-free Box BPR predictions via out-of-fold cross-validation.

    For each RAPM-eligible player (has both box features AND a RAPM target),
    the box prediction is generated by a model trained on the other k-1 folds
    of players \u2014 so no player's prior is informed by that player's own RAPM target.

    Players without RAPM targets receive predictions from the final full model
    trained on all RAPM-eligible players.

    Returns:
        model_artifacts  dict  (final full model, for DB storage / export)
        box_bpr_preds    dict[int, {box_obpr, box_dbpr}]
    """
    import random

    box_features = extract_box_features(
        player_season_stats, off_poss_map, def_poss_map,
        opp_quality_map=opp_quality_map,
    )

    rapm_pids     = [pid for pid in box_features if pid in rapm_obpr and pid in rapm_dbpr]
    non_rapm_pids = [pid for pid in box_features if pid not in rapm_obpr or pid not in rapm_dbpr]

    if len(rapm_pids) < n_folds * 2:
        raise ValueError(
            f"OOF Box BPR: insufficient RAPM-eligible players "
            f"({len(rapm_pids)} < {n_folds * 2})"
        )

    rng = random.Random(seed)
    rng.shuffle(rapm_pids)
    fold_of = {pid: i % n_folds for i, pid in enumerate(rapm_pids)}

    oof_preds: dict[int, dict] = {}

    for fold in range(n_folds):
        train_pids = [pid for pid in rapm_pids if fold_of[pid] != fold]
        test_pids  = [pid for pid in rapm_pids if fold_of[pid] == fold]

        if not train_pids or not test_pids:
            continue

        off_X = np.array([box_features[pid]["off"] for pid in train_pids])
        off_y = np.array([rapm_obpr[pid] for pid in train_pids])
        def_X = np.array([box_features[pid]["def"] for pid in train_pids])
        def_y = np.array([rapm_dbpr[pid] for pid in train_pids])

        off_pipe = _build_pipeline(BOX_BPR_ALPHAS_OFF, BOX_BPR_CV_FOLDS)
        def_pipe = _build_pipeline(BOX_BPR_ALPHAS_DEF, BOX_BPR_CV_FOLDS)
        off_pipe.fit(off_X, off_y)
        def_pipe.fit(def_X, def_y)

        for pid in test_pids:
            if pid in box_features:
                oof_preds[pid] = {
                    "box_obpr": float(off_pipe.predict([box_features[pid]["off"]])[0]),
                    "box_dbpr": float(def_pipe.predict([box_features[pid]["def"]])[0]),
                }

    # Final full model: train on all RAPM-eligible players
    all_off_X = np.array([box_features[pid]["off"] for pid in rapm_pids])
    all_off_y = np.array([rapm_obpr[pid] for pid in rapm_pids])
    all_def_X = np.array([box_features[pid]["def"] for pid in rapm_pids])
    all_def_y = np.array([rapm_dbpr[pid] for pid in rapm_pids])

    final_off_pipe = _build_pipeline(BOX_BPR_ALPHAS_OFF, BOX_BPR_CV_FOLDS)
    final_def_pipe = _build_pipeline(BOX_BPR_ALPHAS_DEF, BOX_BPR_CV_FOLDS)
    final_off_pipe.fit(all_off_X, all_off_y)
    final_def_pipe.fit(all_def_X, all_def_y)

    # Non-RAPM players \u2192 full model predictions (no leakage issue, they have no RAPM targets)
    for pid in non_rapm_pids:
        if pid in box_features:
            oof_preds[pid] = {
                "box_obpr": float(final_off_pipe.predict([box_features[pid]["off"]])[0]),
                "box_dbpr": float(final_def_pipe.predict([box_features[pid]["def"]])[0]),
            }

    off_alpha = float(final_off_pipe.named_steps["ridge"].alpha_)
    def_alpha = float(final_def_pipe.named_steps["ridge"].alpha_)

    logger.info(
        f"OOF Box BPR: {len(oof_preds)} total predictions "
        f"({len(rapm_pids)} via OOF, {len(non_rapm_pids)} via full model) "
        f"off_\u03b1={off_alpha:.4f}, def_\u03b1={def_alpha:.4f}"
    )

    model_artifacts = {
        "off_pipeline":    final_off_pipe,
        "def_pipeline":    final_def_pipe,
        "off_cv_alpha":    off_alpha,
        "def_cv_alpha":    def_alpha,
        "n_train":         len(rapm_pids),
        "off_features":    OFF_FEATURES,
        "def_features":    DEF_FEATURES,
        "training_method": "out_of_fold",
        "n_folds":         n_folds,
    }

    return model_artifacts, oof_preds


def train_box_bpr_prior_seasons(
    train_off_X: np.ndarray,
    train_off_y: np.ndarray,
    train_def_X: np.ndarray,
    train_def_y: np.ndarray,
    current_season_stats: list[dict],
    current_off_poss_map: dict[int, float],
    current_def_poss_map: dict[int, float],
    opp_quality_map: "dict[int, float] | None" = None,
) -> tuple[dict, dict]:
    """
    Train Box BPR on prior-season data, then predict current-season players.

    Training arrays (train_off_X, train_off_y, etc.) are pre-built by
    pipeline._load_prior_season_box_data() using extract_box_features() on
    prior-season PlayerSeasonStats so the feature ordering is identical to
    what is produced for the current season.

    Returns:
        model_artifacts  dict
        box_bpr_preds    dict[int, {box_obpr, box_dbpr}]
    """
    n_train = len(train_off_y)

    off_pipe = _build_pipeline(BOX_BPR_ALPHAS_OFF, BOX_BPR_CV_FOLDS)
    def_pipe = _build_pipeline(BOX_BPR_ALPHAS_DEF, BOX_BPR_CV_FOLDS)
    off_pipe.fit(train_off_X, train_off_y)
    def_pipe.fit(train_def_X, train_def_y)

    off_alpha = float(off_pipe.named_steps["ridge"].alpha_)
    def_alpha = float(def_pipe.named_steps["ridge"].alpha_)

    logger.info(
        f"Box BPR (prior-season training): n_train={n_train}, "
        f"off_\u03b1={off_alpha:.4f}, def_\u03b1={def_alpha:.4f}"
    )

    box_preds = predict_box_bpr(
        current_season_stats, current_off_poss_map, current_def_poss_map,
        {"off_pipeline": off_pipe, "def_pipeline": def_pipe},
        opp_quality_map=opp_quality_map,
    )

    model_artifacts = {
        "off_pipeline":    off_pipe,
        "def_pipeline":    def_pipe,
        "off_cv_alpha":    off_alpha,
        "def_cv_alpha":    def_alpha,
        "n_train":         n_train,
        "off_features":    OFF_FEATURES,
        "def_features":    DEF_FEATURES,
        "training_method": "prior_seasons",
    }

    return model_artifacts, box_preds


# ── Coefficient diagnostics ───────────────────────────────────────────────────

def get_coefficient_table(model_artifacts: dict) -> dict:
    """
    Return a human-readable coefficient table for the fitted Box BPR models.

    Coefficients are in scaled space (post-StandardScaler), so they represent
    the marginal impact of a 1-SD increase in each feature on predicted BPR.
    Sorted by absolute magnitude (most influential first).

    Returns:
        {
            "off": [{"feature": str, "coef": float}, ...],   # sorted by |coef| desc
            "def": [{"feature": str, "coef": float}, ...],
            "off_alpha": float,  # chosen Ridge regularization strength
            "def_alpha": float,
        }
    """
    off_ridge = model_artifacts["off_pipeline"].named_steps["ridge"]
    def_ridge = model_artifacts["def_pipeline"].named_steps["ridge"]

    off_table = sorted(
        [
            {"feature": feat, "coef": round(float(coef), 5)}
            for feat, coef in zip(OFF_FEATURES, off_ridge.coef_)
        ],
        key=lambda x: abs(x["coef"]),
        reverse=True,
    )
    def_table = sorted(
        [
            {"feature": feat, "coef": round(float(coef), 5)}
            for feat, coef in zip(DEF_FEATURES, def_ridge.coef_)
        ],
        key=lambda x: abs(x["coef"]),
        reverse=True,
    )

    return {
        "off": off_table,
        "def": def_table,
        "off_alpha": model_artifacts.get("off_cv_alpha"),
        "def_alpha": model_artifacts.get("def_cv_alpha"),
    }
