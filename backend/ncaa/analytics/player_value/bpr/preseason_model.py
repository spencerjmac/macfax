"""
preseason_model.py — Learned preseason prior means for BPR.

Replaces the hard-coded `(0.8 × box_bpr + 0.2 × prior_baseline)` blend with
Ridge regression sub-models trained on historical player-season data.

Two sub-models:
  returner — same team year-over-year. Features include on-court adj_em.
  transfer  — changed team. Drops on-court splits (context-dependent);
              adds competition-level delta between origin and destination teams.

Training scheme:
  For each year T in {prior years of season_year}: load features from T-1,
  load current-season box_bpr from T, predict T baseline_obpr/dbpr.
  This trains on historical (T-1 history + T box) → T baseline pairs.

Freshmen (n_prior_seasons=0, no prior PSS) always fall through to the
star-tier recruiting lookup in preseason.py — they are NOT handled here.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.model_selection import cross_val_predict
from sklearn.preprocessing import StandardScaler

from ncaa.analytics.player_value.bpr.constants import (
    MIN_OFF_POSS_BPR,
    PRESEASON_ALPHAS,
    PRESEASON_MIN_PAIRS,
    PRESEASON_LOW_POSS_THRESHOLD,
    PRESEASON_LOW_POSS_SD_BONUS,
    PRESEASON_FALLBACK_SD_RETURNER_OFF,
    PRESEASON_FALLBACK_SD_RETURNER_DEF,
    PRESEASON_FALLBACK_SD_TRANSFER_OFF,
    PRESEASON_FALLBACK_SD_TRANSFER_DEF,
)

logger = logging.getLogger(__name__)

# Position one-hot index
_ROLE_BUCKETS = ("G", "Wing", "Big")


def _role_onehot(role_bucket: str | None) -> list[float]:
    return [1.0 if role_bucket == rb else 0.0 for rb in _ROLE_BUCKETS]


def _n_prior_seasons_capped(n: int) -> float:
    """Cap at 4 (senior+) and normalise to [0, 1]."""
    return min(n, 4) / 4.0


# ── Training data builders ────────────────────────────────────────────────────

def _build_returner_training_data(prior_years: list[int]) -> dict | None:
    """
    For each year T in prior_years, load same-team players with:
      features  = T-1 PSS (baseline RAPM, box, on_court_adj_em, mpg, off_poss)
                + T   PSS (box_obpr/dbpr — current-season box signal)
                + T   PSP (n_prior_seasons, role_bucket)
      targets   = T baseline_obpr / baseline_dbpr

    Only players whose team did NOT change from T-1 to T.
    """
    from ncaa.models import PlayerSeasonStats, PlayerSeasonProjection

    off_X, off_y, def_X, def_y, player_ids = [], [], [], [], []

    for yr in prior_years:
        # --- year T-1 features ---
        prev_qs = {
            r["player_id"]: r
            for r in PlayerSeasonStats.objects.filter(
                season__year=yr - 1,
                baseline_obpr__isnull=False,
                baseline_dbpr__isnull=False,
                box_obpr__isnull=False,
                box_dbpr__isnull=False,
                on_court_adj_em__isnull=False,
                off_poss__gte=MIN_OFF_POSS_BPR,
            ).values(
                "player_id", "team_id",
                "baseline_obpr", "baseline_dbpr",
                "box_obpr", "box_dbpr",
                "on_court_adj_em",
                "mpg", "off_poss",
            )
        }

        # --- year T features + targets ---
        curr_qs = {
            r["player_id"]: r
            for r in PlayerSeasonStats.objects.filter(
                season__year=yr,
                baseline_obpr__isnull=False,
                baseline_dbpr__isnull=False,
                box_obpr__isnull=False,
                box_dbpr__isnull=False,
                off_poss__gte=MIN_OFF_POSS_BPR,
            ).values(
                "player_id", "team_id",
                "baseline_obpr", "baseline_dbpr",
                "box_obpr", "box_dbpr",
                "off_poss",
            )
        }

        # PSP metadata for year T
        psp_meta = {
            r["player_id"]: r
            for r in PlayerSeasonProjection.objects.filter(
                from_season__year=yr,
            ).values("player_id", "n_prior_seasons", "role_bucket")
        }

        for pid, curr in curr_qs.items():
            prev = prev_qs.get(pid)
            if prev is None:
                continue
            # Returner = same team
            if prev["team_id"] != curr["team_id"]:
                continue

            meta = psp_meta.get(pid, {})
            n_prior = meta.get("n_prior_seasons") or 1
            role = meta.get("role_bucket")

            feats = [
                float(prev["baseline_obpr"]),
                float(prev["baseline_dbpr"]),
                float(prev["box_obpr"]),
                float(prev["box_dbpr"]),
                float(prev["on_court_adj_em"]),
                float(prev["mpg"]) / 40.0,
                float(np.log1p(prev["off_poss"])),
                _n_prior_seasons_capped(n_prior),
                *_role_onehot(role),
                float(curr["box_obpr"]),   # current-season box signal
                float(curr["box_dbpr"]),
            ]

            off_X.append(feats)
            off_y.append(float(curr["baseline_obpr"]))
            def_X.append(feats)
            def_y.append(float(curr["baseline_dbpr"]))
            player_ids.append(pid)

    if len(off_X) < PRESEASON_MIN_PAIRS:
        return None

    logger.info(
        f"[Preseason] Returner training: {len(off_X)} pairs from years "
        f"{[y - 1 for y in prior_years]}→{prior_years}"
    )
    return {
        "off_X":      np.array(off_X, dtype=np.float64),
        "off_y":      np.array(off_y, dtype=np.float64),
        "def_X":      np.array(def_X, dtype=np.float64),
        "def_y":      np.array(def_y, dtype=np.float64),
        "player_ids": player_ids,
    }


def _build_transfer_training_data(prior_years: list[int]) -> dict | None:
    """
    For each year T in prior_years, load team-changing players with:
      features  = T-1 PSS (baseline RAPM, box, mpg, off_poss — no on_court splits)
                + T   PSS (box_obpr/dbpr)
                + T   PSP (n_prior_seasons, role_bucket)
                + competition_delta_em (dest adj_em T − origin adj_em T-1)
      targets   = T baseline_obpr / baseline_dbpr
    """
    from ncaa.models import PlayerSeasonStats, PlayerSeasonProjection, TeamSeasonRatings

    off_X, off_y, def_X, def_y, player_ids = [], [], [], [], []

    for yr in prior_years:
        # Team ratings for competition adjustment
        origin_ratings = {
            r["team_id"]: r["adj_em"]
            for r in TeamSeasonRatings.objects.filter(
                season__year=yr - 1
            ).values("team_id", "adj_em")
        }
        dest_ratings = {
            r["team_id"]: r["adj_em"]
            for r in TeamSeasonRatings.objects.filter(
                season__year=yr
            ).values("team_id", "adj_em")
        }

        prev_qs = {
            r["player_id"]: r
            for r in PlayerSeasonStats.objects.filter(
                season__year=yr - 1,
                baseline_obpr__isnull=False,
                baseline_dbpr__isnull=False,
                box_obpr__isnull=False,
                box_dbpr__isnull=False,
                off_poss__gte=MIN_OFF_POSS_BPR,
            ).values(
                "player_id", "team_id",
                "baseline_obpr", "baseline_dbpr",
                "box_obpr", "box_dbpr",
                "mpg", "off_poss",
            )
        }

        curr_qs = {
            r["player_id"]: r
            for r in PlayerSeasonStats.objects.filter(
                season__year=yr,
                baseline_obpr__isnull=False,
                baseline_dbpr__isnull=False,
                box_obpr__isnull=False,
                box_dbpr__isnull=False,
                off_poss__gte=MIN_OFF_POSS_BPR,
            ).values(
                "player_id", "team_id",
                "baseline_obpr", "baseline_dbpr",
                "box_obpr", "box_dbpr",
                "off_poss",
            )
        }

        psp_meta = {
            r["player_id"]: r
            for r in PlayerSeasonProjection.objects.filter(
                from_season__year=yr,
            ).values("player_id", "n_prior_seasons", "role_bucket")
        }

        for pid, curr in curr_qs.items():
            prev = prev_qs.get(pid)
            if prev is None:
                continue
            # Transfer = team changed
            if prev["team_id"] == curr["team_id"]:
                continue

            origin_em = origin_ratings.get(prev["team_id"])
            dest_em   = dest_ratings.get(curr["team_id"])
            if origin_em is None or dest_em is None:
                continue

            comp_delta = float(dest_em) - float(origin_em)

            meta = psp_meta.get(pid, {})
            n_prior = meta.get("n_prior_seasons") or 1
            role = meta.get("role_bucket")

            feats = [
                float(prev["baseline_obpr"]),
                float(prev["baseline_dbpr"]),
                float(prev["box_obpr"]),
                float(prev["box_dbpr"]),
                float(prev["mpg"]) / 40.0,
                float(np.log1p(prev["off_poss"])),
                _n_prior_seasons_capped(n_prior),
                *_role_onehot(role),
                float(curr["box_obpr"]),
                float(curr["box_dbpr"]),
                comp_delta,
            ]

            off_X.append(feats)
            off_y.append(float(curr["baseline_obpr"]))
            def_X.append(feats)
            def_y.append(float(curr["baseline_dbpr"]))
            player_ids.append(pid)

    if len(off_X) < PRESEASON_MIN_PAIRS:
        return None

    logger.info(
        f"[Preseason] Transfer training: {len(off_X)} pairs from years "
        f"{[y - 1 for y in prior_years]}→{prior_years}"
    )
    return {
        "off_X":      np.array(off_X, dtype=np.float64),
        "off_y":      np.array(off_y, dtype=np.float64),
        "def_X":      np.array(def_X, dtype=np.float64),
        "def_y":      np.array(def_y, dtype=np.float64),
        "player_ids": player_ids,
    }


# ── Residual SD estimation ────────────────────────────────────────────────────

def _compute_residual_sds(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_prior_seasons_arr: np.ndarray,
) -> dict[str, float]:
    """
    Compute per-group residual SDs as player-specific prior SD estimates.

    Groups: (0=rookie, 1=sophomore, 2+= experienced).
    Returns dict keyed by group label → residual SD.
    """
    residuals = y_true - y_pred
    groups: dict[str, list[float]] = defaultdict(list)
    for r, n in zip(residuals, n_prior_seasons_arr):
        key = "0" if n == 0 else ("1" if n == 1 else "2+")
        groups[key].append(float(r))

    sds = {}
    for key, vals in groups.items():
        sds[key] = float(np.std(vals)) if len(vals) >= 5 else 2.5
    return sds


# ── Public API ────────────────────────────────────────────────────────────────

def train_preseason_models(season_year: int) -> dict:
    """
    Train returner and transfer Ridge sub-models on historical data.

    Uses seasons (season_year-3) through (season_year-1) as training targets,
    with (season_year-4) through (season_year-2) as prior-season feature sources.

    Returns: dict with model objects, scalers, residual SDs, and training metadata.
    Returns empty dict if training data is insufficient.
    """
    # Use up to 4 prior target years for training: e.g. [2022, 2023, 2024, 2025] for 2026.
    # Each T uses (T-1 features + T box) → T baseline targets; no target-year leakage.
    # Data builders gate on baseline_obpr__isnull=False so years without clean data are skipped.
    training_target_years = list(range(season_year - 4, season_year))  # e.g. [2022, 2023, 2024, 2025]

    if len(training_target_years) < 1:
        logger.warning("[Preseason] Not enough prior seasons to train preseason model.")
        return {}

    result: dict = {}

    # ── Returner model ───────────────────────────────────────────────────────
    ret_data = _build_returner_training_data(training_target_years)
    if ret_data and len(ret_data["off_X"]) >= PRESEASON_MIN_PAIRS:
        scaler_ret = StandardScaler()
        X_s = scaler_ret.fit_transform(ret_data["off_X"])

        model_ret_off = RidgeCV(alphas=PRESEASON_ALPHAS, cv=5).fit(X_s, ret_data["off_y"])
        model_ret_def = RidgeCV(alphas=PRESEASON_ALPHAS, cv=5).fit(X_s, ret_data["def_y"])

        # OOF residuals: use CV-selected alpha, predict each fold held-out
        # In-sample residuals underestimate OOS error — OOF gives unbiased SDs
        oof_ret_off = cross_val_predict(Ridge(alpha=model_ret_off.alpha_), X_s, ret_data["off_y"], cv=5)
        oof_ret_def = cross_val_predict(Ridge(alpha=model_ret_def.alpha_), X_s, ret_data["def_y"], cv=5)

        n_prior_col = ret_data["off_X"][:, 7] * 4  # un-normalise
        sd_off = _compute_residual_sds(ret_data["off_y"], oof_ret_off, n_prior_col)
        sd_def = _compute_residual_sds(ret_data["def_y"], oof_ret_def, n_prior_col)

        result["returner_off"]     = model_ret_off
        result["returner_def"]     = model_ret_def
        result["scaler_returner"]  = scaler_ret
        result["sd_returner_off"]  = sd_off
        result["sd_returner_def"]  = sd_def
        result["n_returner_train"] = len(ret_data["off_X"])
        logger.info(
            f"[Preseason] Returner model trained: n={len(ret_data['off_X'])}, "
            f"α_off={model_ret_off.alpha_:.3f}, α_def={model_ret_def.alpha_:.3f}"
        )
    else:
        logger.warning("[Preseason] Returner training data insufficient — model not trained.")

    # ── Transfer model ───────────────────────────────────────────────────────
    xfer_data = _build_transfer_training_data(training_target_years)
    if xfer_data and len(xfer_data["off_X"]) >= PRESEASON_MIN_PAIRS:
        scaler_xfer = StandardScaler()
        X_s = scaler_xfer.fit_transform(xfer_data["off_X"])

        model_xfer_off = RidgeCV(alphas=PRESEASON_ALPHAS, cv=5).fit(X_s, xfer_data["off_y"])
        model_xfer_def = RidgeCV(alphas=PRESEASON_ALPHAS, cv=5).fit(X_s, xfer_data["def_y"])

        oof_xfer_off = cross_val_predict(Ridge(alpha=model_xfer_off.alpha_), X_s, xfer_data["off_y"], cv=5)
        oof_xfer_def = cross_val_predict(Ridge(alpha=model_xfer_def.alpha_), X_s, xfer_data["def_y"], cv=5)

        n_prior_col = xfer_data["off_X"][:, 6] * 4
        sd_off = _compute_residual_sds(xfer_data["off_y"], oof_xfer_off, n_prior_col)
        sd_def = _compute_residual_sds(xfer_data["def_y"], oof_xfer_def, n_prior_col)

        result["transfer_off"]     = model_xfer_off
        result["transfer_def"]     = model_xfer_def
        result["scaler_transfer"]  = scaler_xfer
        result["sd_transfer_off"]  = sd_off
        result["sd_transfer_def"]  = sd_def
        result["n_transfer_train"] = len(xfer_data["off_X"])
        logger.info(
            f"[Preseason] Transfer model trained: n={len(xfer_data['off_X'])}, "
            f"α_off={model_xfer_off.alpha_:.3f}, α_def={model_xfer_def.alpha_:.3f}"
        )
    else:
        logger.warning("[Preseason] Transfer training data insufficient — model not trained.")

    result["training_target_years"] = training_target_years
    return result


def predict_preseason_priors(
    player_ids: list[int],
    season_year: int,
    box_bpr_preds: "dict[int, dict]",
    recruitment_types: "dict[int, str]",
    n_prior_seasons_map: "dict[int, int]",
    models: dict,
) -> "dict[int, dict]":
    """
    For each player, route to the appropriate sub-model and produce a prior.

    Returns:
        {player_id: {obpr_mean, dbpr_mean, obpr_sd, dbpr_sd}}

    Players with no prior PSS (freshmen, n_prior_seasons=0) are omitted —
    they fall through to the recruiting-tier star-bucket lookup in preseason.py.
    """
    from ncaa.models import PlayerSeasonStats, TeamSeasonRatings

    if not models:
        return {}

    # Load prior-season PSS for all target players
    prev_pss = {
        r["player_id"]: r
        for r in PlayerSeasonStats.objects.filter(
            season__year=season_year - 1,
            player_id__in=player_ids,
            baseline_obpr__isnull=False,
            baseline_dbpr__isnull=False,
            box_obpr__isnull=False,
            box_dbpr__isnull=False,
            off_poss__gte=MIN_OFF_POSS_BPR,
        ).values(
            "player_id", "team_id",
            "baseline_obpr", "baseline_dbpr",
            "box_obpr", "box_dbpr",
            "on_court_adj_em",
            "mpg", "off_poss",
        )
    }

    # Current-season PSS for team info (transfer origin) + current box signal
    curr_pss = {
        r["player_id"]: r
        for r in PlayerSeasonStats.objects.filter(
            season__year=season_year,
            player_id__in=player_ids,
        ).values("player_id", "team_id")
    }

    # Team ratings for competition adjustment
    origin_ratings = {
        r["team_id"]: r["adj_em"]
        for r in TeamSeasonRatings.objects.filter(
            season__year=season_year - 1
        ).values("team_id", "adj_em")
    }
    dest_ratings = {
        r["team_id"]: r["adj_em"]
        for r in TeamSeasonRatings.objects.filter(
            season__year=season_year
        ).values("team_id", "adj_em")
    }

    preds: dict[int, dict] = {}

    for pid in player_ids:
        n_prior = n_prior_seasons_map.get(pid, 0)
        if n_prior == 0:
            # Freshman — no prior PSS, fall through to star-tier lookup
            continue

        prev = prev_pss.get(pid)
        if prev is None:
            # No qualifying prior-season data despite n_prior_seasons > 0 (low minutes)
            continue

        box = box_bpr_preds.get(pid)
        if box is None:
            # No current-season box prediction — can't build full feature vector
            continue

        rec_type = recruitment_types.get(pid, "returner")
        curr = curr_pss.get(pid, {})
        role = None  # will try to infer from player projections
        n_prior_cap = _n_prior_seasons_capped(n_prior)

        if rec_type in ("returner", "newcomer"):
            # Use returner model
            mdl_off = models.get("returner_off")
            mdl_def = models.get("returner_def")
            scaler  = models.get("scaler_returner")
            sd_off_map = models.get("sd_returner_off", {})
            sd_def_map = models.get("sd_returner_def", {})

            if mdl_off is None or scaler is None:
                continue

            on_ct = float(prev.get("on_court_adj_em") or 0.0)
            feats = [
                float(prev["baseline_obpr"]),
                float(prev["baseline_dbpr"]),
                float(prev["box_obpr"]),
                float(prev["box_dbpr"]),
                on_ct,
                float(prev["mpg"]) / 40.0,
                float(np.log1p(prev["off_poss"])),
                n_prior_cap,
                *_role_onehot(role),
                float(box["box_obpr"]),
                float(box["box_dbpr"]),
            ]
            X = scaler.transform([feats])
            obpr_mean = float(mdl_off.predict(X)[0])
            dbpr_mean = float(mdl_def.predict(X)[0])

        else:
            # Transfer model
            mdl_off = models.get("transfer_off")
            mdl_def = models.get("transfer_def")
            scaler  = models.get("scaler_transfer")
            sd_off_map = models.get("sd_transfer_off", {})
            sd_def_map = models.get("sd_transfer_def", {})

            if mdl_off is None or scaler is None:
                continue

            origin_em = origin_ratings.get(prev.get("team_id"))
            dest_em   = dest_ratings.get(curr.get("team_id"))
            comp_delta = (float(dest_em) - float(origin_em)) if (origin_em is not None and dest_em is not None) else 0.0

            feats = [
                float(prev["baseline_obpr"]),
                float(prev["baseline_dbpr"]),
                float(prev["box_obpr"]),
                float(prev["box_dbpr"]),
                float(prev["mpg"]) / 40.0,
                float(np.log1p(prev["off_poss"])),
                n_prior_cap,
                *_role_onehot(role),
                float(box["box_obpr"]),
                float(box["box_dbpr"]),
                comp_delta,
            ]
            X = scaler.transform([feats])
            obpr_mean = float(mdl_off.predict(X)[0])
            dbpr_mean = float(mdl_def.predict(X)[0])

        # Prior SD from residual groups, with low-possession bonus
        n_group = "0" if n_prior == 0 else ("1" if n_prior == 1 else "2+")
        sd_o = sd_off_map.get(n_group, PRESEASON_FALLBACK_SD_RETURNER_OFF if rec_type != "transfer" else PRESEASON_FALLBACK_SD_TRANSFER_OFF)
        sd_d = sd_def_map.get(n_group, PRESEASON_FALLBACK_SD_RETURNER_DEF if rec_type != "transfer" else PRESEASON_FALLBACK_SD_TRANSFER_DEF)

        if float(prev.get("off_poss", 999)) < PRESEASON_LOW_POSS_THRESHOLD:
            sd_o += PRESEASON_LOW_POSS_SD_BONUS
            sd_d += PRESEASON_LOW_POSS_SD_BONUS

        preds[pid] = {
            "obpr_mean": round(obpr_mean, 4),
            "dbpr_mean": round(dbpr_mean, 4),
            "obpr_sd":   round(max(sd_o, 0.5), 4),
            "dbpr_sd":   round(max(sd_d, 0.5), 4),
        }

    logger.info(
        f"[Preseason] Predicted priors for {len(preds)}/{len(player_ids)} target players "
        f"(season {season_year})"
    )
    return preds
