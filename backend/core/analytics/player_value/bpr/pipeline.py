"""
pipeline.py — BPR orchestration: runs all phases in sequence for one season.

Phase order:
  1. Build RAPM dataset (lineup segment extraction)
  2. Fit baseline RAPM (global prior μ=0, λ by CV)
     2b. Write baseline_obpr / baseline_dbpr to DB  ← v1.2: clean teacher targets
  3. Load PlayerSeasonStats for box feature extraction
  4a. Attempt prior-season Box BPR training on baseline RAPM targets (leak-free, preferred)
  4b. Fall back to out-of-fold Box BPR (leak-free, same-season)
  5. Tune prior SD scales by CV (joint and separate off/def; pick better)
  6. Build prior maps + fit prior-informed RAPM (final BPR estimate)
  7. Write all results to PlayerSeasonStats (with source provenance)

Possession-threshold policy (Phase 7):
  - OBPR from RAPM requires off_poss >= MIN_OFF_POSS_BPR
  - DBPR from RAPM requires def_poss >= MIN_DEF_POSS_BPR
  - If one side qualifies but not the other, the qualifying side uses RAPM
    and the non-qualifying side uses the box prior (or null if no box).
  - BPR (total) = obpr + dbpr when both are present.
    If only one side is present, bpr = that component and bpr_source = "partial".
  - Source provenance (obpr_source, dbpr_source, bpr_source) is always written.

v1.2 key change — eliminating recursive prior-target contamination:
  Prior-season Box BPR now trains on baseline_obpr / baseline_dbpr (raw baseline
  RAPM before prior-informed fit), NOT on the final obpr / dbpr fields.
  Teacher-student chain: baseline RAPM → Box BPR → final prior-informed RAPM.

# TODO MULTI-YEAR: to support rolling multi-season RAPM, extend build_rapm_dataset()
#   in datasets.py to accept a list of season_years and combine observations across
#   seasons before fitting.  The player_index and n_players would cover all seasons.
#   Mark the artifact with rapm_window="multi_season".

Returns a summary dict with per-phase stats for logging and validation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
from django.db import transaction

from core.analytics.player_value.bpr.constants import (
    BPR_MODEL_VERSION,
    MIN_OFF_POSS_BPR,
    MIN_DEF_POSS_BPR,
    MIN_PRIOR_TRAINING_SAMPLES,
    MIN_GP_BOX_BPR,
    MIN_MPG_BOX_BPR,
    BPR_SOURCE_RAPM,
    BPR_SOURCE_BOX,
    BPR_SOURCE_MIXED,
    BPR_SOURCE_PARTIAL,
)
from core.analytics.player_value.bpr.datasets import build_rapm_dataset
from core.analytics.player_value.bpr.rapm import (
    fit_baseline_rapm,
    fit_prior_informed_rapm,
    tune_prior_sd_scale,
    tune_prior_sd_scales_separate,
)
from core.analytics.player_value.bpr.box_bpr import (
    extract_box_features,
    train_box_bpr_prior_seasons,
    out_of_fold_box_bpr,
    predict_box_bpr,
    export_model_artifacts,
    get_coefficient_table,
)
from core.analytics.player_value.bpr.preseason import build_prior_maps

logger = logging.getLogger(__name__)


def run_bpr_season(
    season_year: int,
    skip_box_bpr: bool = False,
    skip_prior_rapm: bool = False,
    rapm_lambda_override: float | None = None,
    verbose: bool = True,
) -> dict:
    """
    Run the full BPR pipeline for `season_year`.

    Returns a summary dict with statistics from each phase.
    """
    from core.models import PlayerSeasonStats, BPRModelArtifact, Season

    summary: dict = {"season_year": season_year, "phases": {}}
    now = datetime.now(tz=timezone.utc)

    # ── Phase 1: Build RAPM dataset ───────────────────────────────────────────
    logger.info(f"[BPR] Phase 1: Building RAPM dataset for season {season_year}")
    dataset = build_rapm_dataset(season_year, verbose=verbose)
    n_obs  = dataset["n_observations"]
    n_players = dataset["n_players"]
    summary["phases"]["dataset"] = {
        "n_observations": n_obs,
        "n_players": n_players,
    }

    has_stint_data = n_obs > 0

    if not has_stint_data:
        logger.warning(
            f"[BPR] Season {season_year} has no lineup segments "
            f"(no PBP stint data).  Box BPR only."
        )

    # ── Phase 2+3: Baseline RAPM (only when stint data exists) ────────────────
    baseline_rapm: dict | None = None
    if has_stint_data:
        logger.info(f"[BPR] Phase 2+3: Fitting baseline RAPM  ({n_obs} segments, {n_players} players)")
        baseline_rapm = fit_baseline_rapm(
            observations=dataset["observations"],
            player_index=dataset["player_index"],
            n_players=n_players,
            run_cv=(rapm_lambda_override is None),
            lambda_override=rapm_lambda_override,
        )
        summary["phases"]["baseline_rapm"] = {
            "lambda":     baseline_rapm["lambda"],
            "intercept":  baseline_rapm["intercept"],
            "hca":        baseline_rapm["hca"],
            "cv_metrics": baseline_rapm.get("cv_metrics"),
        }

        # Phase 2b: Write baseline RAPM targets to DB before any prior-informed fit.
        # This ensures future seasons can train Box BPR on clean baseline targets,
        # not on final prior-informed values (v1.2 recursive contamination fix).
        logger.info("[BPR] Phase 2b: Writing baseline RAPM targets to DB")
        n_baseline_written = _write_baseline_rapm(
            season_year=season_year,
            baseline_obpr=baseline_rapm["obpr"],
            baseline_dbpr=baseline_rapm["dbpr"],
            off_poss_map=dataset["possession_totals"],
            def_poss_map=dataset["possession_totals"],
        )
        summary["phases"]["baseline_rapm"]["n_baseline_written"] = n_baseline_written

    # ── Phase 3: Load PlayerSeasonStats for box feature extraction ────────────
    logger.info(f"[BPR] Phase 3: Loading PlayerSeasonStats for season {season_year}")
    pss_qs = PlayerSeasonStats.objects.filter(
        season__year=season_year,
    ).values(
        "player_id", "gp", "mpg",
        "pts", "ast", "tov", "stl", "blk", "pf", "reb",
        "oreb_pg", "dreb_pg",
        "fga_pg", "fg3a_pg", "fta_pg", "ftm_pg",
        "efg_pct", "ts_pct",
        "on_court_secs_pg",
    )
    player_season_stats = list(pss_qs)
    summary["phases"]["player_season_stats"] = {"n_records": len(player_season_stats)}

    # ── Phase 4: Box BPR — leak-free training ─────────────────────────────────
    off_poss_map = {pid: v["off"] for pid, v in dataset["possession_totals"].items()}
    def_poss_map = {pid: v["def"] for pid, v in dataset["possession_totals"].items()}

    model_artifacts: dict | None = None
    box_bpr_preds:   dict | None = None

    if not skip_box_bpr and baseline_rapm is not None:
        logger.info("[BPR] Phase 4: Box BPR (leak-free training)")

        # 4a. Try prior-season training first (preferred, no leakage by construction)
        prior_train_data = _load_prior_season_box_data(season_year, player_season_stats, off_poss_map, def_poss_map)
        n_prior = len(prior_train_data["off_y"]) if prior_train_data else 0

        try:
            if n_prior >= MIN_PRIOR_TRAINING_SAMPLES:
                logger.info(
                    f"[BPR] Phase 4a: Training Box BPR on {n_prior} prior-season records"
                )
                model_artifacts, box_bpr_preds = train_box_bpr_prior_seasons(
                    train_off_X=prior_train_data["off_X"],
                    train_off_y=prior_train_data["off_y"],
                    train_def_X=prior_train_data["def_X"],
                    train_def_y=prior_train_data["def_y"],
                    current_season_stats=player_season_stats,
                    current_off_poss_map=off_poss_map,
                    current_def_poss_map=def_poss_map,
                )
                model_artifacts["training_source"] = f"prior_seasons (n={n_prior})"
            else:
                # 4b. Fall back to out-of-fold (same season, but each player's prior
                #     is trained on OTHER players' RAPM targets only)
                logger.info(
                    f"[BPR] Phase 4b: Prior-season data insufficient ({n_prior} < "
                    f"{MIN_PRIOR_TRAINING_SAMPLES}); using OOF Box BPR"
                )
                model_artifacts, box_bpr_preds = out_of_fold_box_bpr(
                    player_season_stats=player_season_stats,
                    off_poss_map=off_poss_map,
                    def_poss_map=def_poss_map,
                    rapm_obpr=baseline_rapm["obpr"],
                    rapm_dbpr=baseline_rapm["dbpr"],
                )
                model_artifacts["training_source"] = "out_of_fold"

            summary["phases"]["box_bpr"] = {
                "n_train":          model_artifacts["n_train"],
                "n_predicted":      len(box_bpr_preds),
                "off_alpha":        model_artifacts["off_cv_alpha"],
                "def_alpha":        model_artifacts["def_cv_alpha"],
                "training_method":  model_artifacts.get("training_method"),
                "training_source":  model_artifacts.get("training_source"),
                "coefficients":     get_coefficient_table(model_artifacts),
            }
            logger.info(
                f"[BPR] Box BPR: {model_artifacts['n_train']} training samples, "
                f"{len(box_bpr_preds)} predictions, "
                f"method={model_artifacts.get('training_method')}"
            )
        except ValueError as exc:
            logger.warning(f"[BPR] Box BPR skipped: {exc}")
            box_bpr_preds = {}

    # ── Phase 5: Build priors + tune SD scales + fit prior-informed RAPM ──────
    final_obpr: dict | None = None
    final_dbpr: dict | None = None
    prior_mean_obpr: dict = {}
    prior_mean_dbpr: dict = {}
    prior_sd_obpr:   dict = {}
    prior_sd_dbpr:   dict = {}

    if has_stint_data and not skip_prior_rapm:
        logger.info("[BPR] Phase 5: Building prior maps")
        box_preds_for_prior = box_bpr_preds or {}
        prior_mean_obpr, prior_mean_dbpr, prior_sd_obpr, prior_sd_dbpr = build_prior_maps(
            player_ids=dataset["player_ids"],
            box_bpr_preds=box_preds_for_prior,
        )

        # Tune prior SD scales by CV:
        # a) Joint global scale (single multiplier for off + def)
        # b) Separate off/def scales (1D coordinate descent)
        # Pick whichever gives lower held-out WMSE.
        logger.info("[BPR] Phase 5: Tuning prior SD scale (joint) by CV")
        joint_scale, joint_cv = tune_prior_sd_scale(
            observations=dataset["observations"],
            player_index=dataset["player_index"],
            n_players=n_players,
            prior_mean_obpr=prior_mean_obpr,
            prior_mean_dbpr=prior_mean_dbpr,
            prior_sd_obpr=prior_sd_obpr,
            prior_sd_dbpr=prior_sd_dbpr,
            baseline_lambda=baseline_rapm["lambda"],
        )

        logger.info("[BPR] Phase 5: Tuning prior SD scales (separate off/def) by CV")
        sep_off, sep_def, sep_wmse, sep_cv = tune_prior_sd_scales_separate(
            observations=dataset["observations"],
            player_index=dataset["player_index"],
            n_players=n_players,
            prior_mean_obpr=prior_mean_obpr,
            prior_mean_dbpr=prior_mean_dbpr,
            prior_sd_obpr=prior_sd_obpr,
            prior_sd_dbpr=prior_sd_dbpr,
            baseline_lambda=baseline_rapm["lambda"],
        )

        # Select whichever tuning approach gives lower held-out WMSE
        joint_wmse = joint_cv["mean_wmse"][joint_scale]
        if sep_wmse < joint_wmse:
            sd_scale_off = sep_off
            sd_scale_def = sep_def
            chosen_tuning = "separate"
            logger.info(
                f"[BPR] Separate SD tuning wins: off={sep_off:.3f}, def={sep_def:.3f}, "
                f"WMSE={sep_wmse:.4f} vs joint WMSE={joint_wmse:.4f}"
            )
        else:
            sd_scale_off = joint_scale
            sd_scale_def = joint_scale
            chosen_tuning = "joint"
            logger.info(
                f"[BPR] Joint SD tuning wins: scale={joint_scale:.3f}, "
                f"WMSE={joint_wmse:.4f} vs separate WMSE={sep_wmse:.4f}"
            )

        summary["phases"]["sd_scale_cv"] = {
            "joint": joint_cv,
            "separate": sep_cv,
            "chosen_tuning": chosen_tuning,
            "sd_scale_off": sd_scale_off,
            "sd_scale_def": sd_scale_def,
            # For backward-compat with validation which reads best_sd_scale
            "best_sd_scale": sd_scale_off if chosen_tuning == "joint" else sep_off,
        }

        logger.info("[BPR] Phase 5: Fitting prior-informed RAPM")
        prior_rapm = fit_prior_informed_rapm(
            observations=dataset["observations"],
            player_index=dataset["player_index"],
            n_players=n_players,
            prior_mean_obpr=prior_mean_obpr,
            prior_mean_dbpr=prior_mean_dbpr,
            prior_sd_obpr=prior_sd_obpr,
            prior_sd_dbpr=prior_sd_dbpr,
            baseline_lambda=baseline_rapm["lambda"],
            sd_scale_off=sd_scale_off,
            sd_scale_def=sd_scale_def,
        )
        final_obpr = prior_rapm["obpr"]
        final_dbpr = prior_rapm["dbpr"]
        summary["phases"]["prior_rapm"] = {
            "intercept":    prior_rapm["intercept"],
            "hca":          prior_rapm["hca"],
            "sd_scale_off": prior_rapm["sd_scale_off"],
            "sd_scale_def": prior_rapm["sd_scale_def"],
        }
    elif baseline_rapm is not None:
        # No box BPR available — use baseline RAPM as final
        final_obpr = baseline_rapm["obpr"]
        final_dbpr = baseline_rapm["dbpr"]

    # ── Phase 6: Write results to PlayerSeasonStats ───────────────────────────
    logger.info("[BPR] Phase 6: Writing BPR results to database")
    written = _write_bpr_results(
        season_year=season_year,
        final_obpr=final_obpr or {},
        final_dbpr=final_dbpr or {},
        box_bpr_preds=box_bpr_preds or {},
        prior_mean_obpr=prior_mean_obpr if has_stint_data and not skip_prior_rapm else {},
        prior_mean_dbpr=prior_mean_dbpr if has_stint_data and not skip_prior_rapm else {},
        prior_sd_obpr=prior_sd_obpr if has_stint_data and not skip_prior_rapm else {},
        prior_sd_dbpr=prior_sd_dbpr if has_stint_data and not skip_prior_rapm else {},
        off_poss_map=off_poss_map,
        def_poss_map=def_poss_map,
        now=now,
    )
    summary["phases"]["write"] = written

    # ── Phase 7: Save model artifacts to DB ───────────────────────────────────
    if model_artifacts is not None:
        _save_model_artifact(
            season_year=season_year,
            model_artifacts=model_artifacts,
            baseline_rapm=baseline_rapm,
            sd_cv_summary=summary["phases"].get("sd_scale_cv", {}),
            export_fn=export_model_artifacts,
        )
        summary["phases"]["artifact_saved"] = True

    logger.info(f"[BPR] Pipeline complete for season {season_year}. Summary: {summary['phases']}")
    return summary


# ── DB write helpers ──────────────────────────────────────────────────────────

def _write_baseline_rapm(
    season_year: int,
    baseline_obpr: dict[int, float],
    baseline_dbpr: dict[int, float],
    off_poss_map: dict,   # player_id → {"off": float, "def": float}  (possession_totals)
    def_poss_map: dict,   # same dict (off_poss_map and def_poss_map passed identically)
) -> int:
    """
    Write raw baseline RAPM targets (baseline_obpr, baseline_dbpr) to PlayerSeasonStats.

    Only writes for players who meet the possession threshold on each side —
    the same filter used in _load_prior_season_box_data() so future seasons
    can safely query baseline_obpr__isnull=False to get clean training targets.

    This MUST be called after fitting baseline RAPM and BEFORE fitting the
    prior-informed RAPM, so that the stored values are the uncontaminated targets.
    """
    from core.models import PlayerSeasonStats

    all_pids = set(baseline_obpr) | set(baseline_dbpr)
    pss_qs = PlayerSeasonStats.objects.filter(
        season__year=season_year,
        player_id__in=all_pids,
    )

    to_update = []
    for pss in pss_qs:
        pid = pss.player_id
        off_poss = off_poss_map.get(pid, {}).get("off", 0.0) if isinstance(off_poss_map.get(pid), dict) else off_poss_map.get(pid, 0.0)
        def_poss = def_poss_map.get(pid, {}).get("def", 0.0) if isinstance(def_poss_map.get(pid), dict) else def_poss_map.get(pid, 0.0)

        # Only store when the player meets thresholds (mirrors _load_prior_season_box_data filter)
        pss.baseline_obpr = (
            round(baseline_obpr[pid], 4)
            if pid in baseline_obpr and off_poss >= MIN_OFF_POSS_BPR
            else None
        )
        pss.baseline_dbpr = (
            round(baseline_dbpr[pid], 4)
            if pid in baseline_dbpr and def_poss >= MIN_DEF_POSS_BPR
            else None
        )
        to_update.append(pss)

    with transaction.atomic():
        PlayerSeasonStats.objects.bulk_update(
            to_update, ["baseline_obpr", "baseline_dbpr"], batch_size=500
        )

    n_with_both = sum(
        1 for pss in to_update
        if pss.baseline_obpr is not None and pss.baseline_dbpr is not None
    )
    logger.info(
        f"[BPR] Wrote baseline RAPM targets: {n_with_both} players with both sides "
        f"({len(to_update)} total PSS records updated)"
    )
    return n_with_both


def _load_prior_season_box_data(
    season_year: int,
    current_season_stats: list[dict],
    current_off_poss_map: dict[int, float],
    current_def_poss_map: dict[int, float],
    n_prior_seasons: int = 3,
) -> dict | None:
    """
    Load box features + CLEAN BASELINE RAPM targets for qualifying players in prior seasons.

    v1.2 fix: uses baseline_obpr / baseline_dbpr (raw RAPM before prior-informed fit)
    as training targets, NOT the final obpr / dbpr values.  This eliminates the
    recursive contamination where final BPR (influenced by box priors) becomes the
    target for the next season's box model, creating a feedback loop.

    Teacher-student chain guaranteed:
        baseline RAPM → Box BPR prior → final prior-informed RAPM

    Returns a dict {off_X, off_y, def_X, def_y, prior_years} (numpy arrays),
    or None if no qualifying prior-season data is found.
    """
    from core.models import PlayerSeasonStats

    prior_years = list(range(season_year - n_prior_seasons, season_year))
    if not prior_years:
        return None

    qs = PlayerSeasonStats.objects.filter(
        season__year__in=prior_years,
        # v1.2: use clean baseline RAPM targets, not final BPR outputs
        baseline_obpr__isnull=False,
        baseline_dbpr__isnull=False,
        off_poss__isnull=False,
        off_poss__gte=MIN_OFF_POSS_BPR,
        def_poss__isnull=False,
        def_poss__gte=MIN_DEF_POSS_BPR,
        gp__gte=MIN_GP_BOX_BPR,
        mpg__gte=MIN_MPG_BOX_BPR,
    ).values(
        "player_id", "gp", "mpg",
        "pts", "ast", "tov", "stl", "blk", "pf", "reb",
        "oreb_pg", "dreb_pg",
        "fga_pg", "fg3a_pg", "fta_pg", "ftm_pg",
        "efg_pct", "ts_pct",
        "on_court_secs_pg",
        "baseline_obpr", "baseline_dbpr",  # v1.2: clean targets
        "off_poss", "def_poss",
    )

    prior_records = list(qs)
    if not prior_records:
        return None

    # Build per-player poss maps from stored values
    prior_off_poss = {r["player_id"]: r["off_poss"] for r in prior_records}
    prior_def_poss = {r["player_id"]: r["def_poss"] for r in prior_records}

    # Reuse extract_box_features() for consistent feature ordering
    prior_box_feats = extract_box_features(prior_records, prior_off_poss, prior_def_poss)

    off_X, off_y, def_X, def_y = [], [], [], []
    for r in prior_records:
        pid = r["player_id"]
        if pid not in prior_box_feats:
            continue
        feats = prior_box_feats[pid]
        off_X.append(feats["off"])
        off_y.append(float(r["baseline_obpr"]))   # v1.2: clean baseline target
        def_X.append(feats["def"])
        def_y.append(float(r["baseline_dbpr"]))   # v1.2: clean baseline target

    if not off_X:
        return None

    return {
        "off_X": np.array(off_X, dtype=np.float64),
        "off_y": np.array(off_y, dtype=np.float64),
        "def_X": np.array(def_X, dtype=np.float64),
        "def_y": np.array(def_y, dtype=np.float64),
        "prior_years": prior_years,
    }


def _write_bpr_results(
    season_year: int,
    final_obpr: dict[int, float],
    final_dbpr: dict[int, float],
    box_bpr_preds: dict[int, dict],
    prior_mean_obpr: dict[int, float],
    prior_mean_dbpr: dict[int, float],
    prior_sd_obpr: dict[int, float],
    prior_sd_dbpr: dict[int, float],
    off_poss_map: dict[int, float],
    def_poss_map: dict[int, float],
    now: datetime,
) -> dict:
    from core.models import PlayerSeasonStats

    all_player_ids = set(final_obpr) | set(final_dbpr) | set(box_bpr_preds)

    if not all_player_ids:
        logger.warning("[BPR] No BPR results to write")
        return {"n_updated": 0}

    pss_qs = PlayerSeasonStats.objects.filter(
        season__year=season_year,
        player_id__in=all_player_ids,
    ).select_related("player", "season")

    to_update = []
    for pss in pss_qs:
        pid = pss.player_id
        obpr_val = final_obpr.get(pid)
        dbpr_val = final_dbpr.get(pid)
        box = box_bpr_preds.get(pid, {})

        changed = False

        # ── Possession-threshold policy ───────────────────────────────────────
        # OBPR from RAPM requires sufficient offensive possessions.
        # DBPR from RAPM requires sufficient defensive possessions.
        # If one side does not qualify, fall back to the box prior for that side.
        # If the box prior is also unavailable, that component is null.
        player_off_poss = off_poss_map.get(pid, 0.0)
        player_def_poss = def_poss_map.get(pid, 0.0)
        has_off_poss = player_off_poss >= MIN_OFF_POSS_BPR
        has_def_poss = player_def_poss >= MIN_DEF_POSS_BPR

        if obpr_val is not None and has_off_poss:
            pss.obpr = round(obpr_val, 4)
            obpr_src = BPR_SOURCE_RAPM
        elif box:
            pss.obpr = round(box.get("box_obpr", 0.0), 4)
            obpr_src = BPR_SOURCE_BOX
        else:
            pss.obpr = None
            obpr_src = None
        changed = True

        if dbpr_val is not None and has_def_poss:
            pss.dbpr = round(dbpr_val, 4)
            dbpr_src = BPR_SOURCE_RAPM
        elif box:
            pss.dbpr = round(box.get("box_dbpr", 0.0), 4)
            dbpr_src = BPR_SOURCE_BOX
        else:
            pss.dbpr = None
            dbpr_src = None
        changed = True

        # ── Source provenance ─────────────────────────────────────────────────
        pss.obpr_source = obpr_src
        pss.dbpr_source = dbpr_src

        if pss.obpr is not None and pss.dbpr is not None:
            pss.bpr = round(pss.obpr + pss.dbpr, 4)
            if obpr_src == BPR_SOURCE_RAPM and dbpr_src == BPR_SOURCE_RAPM:
                pss.bpr_source = BPR_SOURCE_RAPM
            elif obpr_src == BPR_SOURCE_BOX and dbpr_src == BPR_SOURCE_BOX:
                pss.bpr_source = BPR_SOURCE_BOX
            else:
                pss.bpr_source = BPR_SOURCE_MIXED
        elif pss.obpr is not None:
            # Only one side: call partial rather than letting bpr impersonate full value.
            # bpr still stored so queries work, but bpr_source = "partial" signals caveat.
            pss.bpr = pss.obpr
            pss.bpr_source = BPR_SOURCE_PARTIAL
        elif pss.dbpr is not None:
            pss.bpr = pss.dbpr
            pss.bpr_source = BPR_SOURCE_PARTIAL
        else:
            pss.bpr = None
            pss.bpr_source = None

        # ── Box BPR ───────────────────────────────────────────────────────────
        if box:
            pss.box_obpr = round(box.get("box_obpr", 0.0), 4)
            pss.box_dbpr = round(box.get("box_dbpr", 0.0), 4)
            pss.box_bpr  = round(pss.box_obpr + pss.box_dbpr, 4)
            changed = True

        # ── Prior parameters ──────────────────────────────────────────────────
        if pid in prior_mean_obpr:
            pss.prior_mean_obpr = round(prior_mean_obpr[pid], 4)
            pss.prior_mean_dbpr = round(prior_mean_dbpr.get(pid, 0.0), 4)
            pss.prior_sd_obpr   = round(prior_sd_obpr.get(pid, 0.0), 4)
            pss.prior_sd_dbpr   = round(prior_sd_dbpr.get(pid, 0.0), 4)
            changed = True

        # ── Possession counts ─────────────────────────────────────────────────
        op = off_poss_map.get(pid)
        dp = def_poss_map.get(pid)
        if op is not None:
            pss.off_poss = round(op, 2)
            pss.def_poss = round(dp, 2) if dp is not None else None
            changed = True

        if changed:
            pss.bpr_model_version = BPR_MODEL_VERSION
            pss.bpr_last_updated  = now
            to_update.append(pss)

    update_fields = [
        "obpr", "dbpr", "bpr",
        "obpr_source", "dbpr_source", "bpr_source",
        "box_obpr", "box_dbpr", "box_bpr",
        "prior_mean_obpr", "prior_mean_dbpr", "prior_sd_obpr", "prior_sd_dbpr",
        "off_poss", "def_poss",
        "bpr_model_version", "bpr_last_updated",
    ]

    with transaction.atomic():
        PlayerSeasonStats.objects.bulk_update(to_update, update_fields, batch_size=500)

    n_partial = sum(1 for pss in to_update if pss.bpr_source == BPR_SOURCE_PARTIAL)
    n_mixed   = sum(1 for pss in to_update if pss.bpr_source == BPR_SOURCE_MIXED)
    logger.info(
        f"[BPR] Wrote BPR results for {len(to_update)} players "
        f"(partial={n_partial}, mixed_source={n_mixed})"
    )
    return {
        "n_updated":  len(to_update),
        "n_partial":  n_partial,
        "n_mixed":    n_mixed,
    }


def _save_model_artifact(
    season_year: int,
    model_artifacts: dict,
    baseline_rapm: dict,
    sd_cv_summary: dict,
    export_fn,
) -> None:
    from core.models import BPRModelArtifact, Season

    try:
        season_obj = Season.objects.get(year=season_year)
    except Season.DoesNotExist:
        logger.warning(f"[BPR] Cannot save artifact: Season {season_year} not found")
        return

    exported = export_fn(model_artifacts, season_year)

    BPRModelArtifact.objects.update_or_create(
        season=season_obj,
        model_type="box_bpr",
        defaults={
            "version":              BPR_MODEL_VERSION,
            "feature_names":        exported["off"]["feature_names"] + exported["def"]["feature_names"],
            "coefficients":         {"off": exported["off"], "def": exported["def"]},
            "intercept":            None,
            "regularization_alpha": exported["off"]["alpha"],
            "n_observations":       exported["n_train"],
            "n_players":            model_artifacts["n_train"],
            "assumptions": {
                "model_type":       "box_bpr",
                "rapm_window":      "single_season",  # TODO MULTI-YEAR: change when pooling seasons
                "training_method":  model_artifacts.get("training_method"),
                "training_source":  model_artifacts.get("training_source"),
                "rapm_lambda":      baseline_rapm.get("lambda"),
                "rapm_intercept":   baseline_rapm.get("intercept"),
                "rapm_hca":         baseline_rapm.get("hca"),
                "off_alpha":        model_artifacts.get("off_cv_alpha"),
                "def_alpha":        model_artifacts.get("def_cv_alpha"),
                "off_features":     model_artifacts.get("off_features"),
                "def_features":     model_artifacts.get("def_features"),
                "sd_scale_off":     sd_cv_summary.get("sd_scale_off"),
                "sd_scale_def":     sd_cv_summary.get("sd_scale_def"),
                "sd_tuning_mode":   sd_cv_summary.get("chosen_tuning"),
                "target_contamination_fixed": True,  # v1.2: uses baseline RAPM targets
            },
        },
    )
