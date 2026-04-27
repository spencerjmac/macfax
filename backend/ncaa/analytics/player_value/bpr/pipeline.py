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

# Multi-year RAPM is supported via build_rapm_dataset(season_years=[...]).
# Pass rapm_years to run_bpr_season() to activate rolling window mode.

Returns a summary dict with per-phase stats for logging and validation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
from django.db import transaction

from ncaa.analytics.player_value.bpr.constants import (
    BPR_MODEL_VERSION,
    MIN_OFF_POSS_BPR,
    MIN_DEF_POSS_BPR,
    MIN_PRIOR_TRAINING_SAMPLES,
    MIN_GP_BOX_BPR,
    MIN_MPG_BOX_BPR,
    PRIOR_SD_BOX_OFF,
    PRIOR_SD_BOX_DEF,
    PRIOR_SD_DEFAULT_OFF,
    PRIOR_SD_DEFAULT_DEF,
    BPR_SOURCE_RAPM,
    BPR_SOURCE_BOX,
    BPR_SOURCE_MIXED,
    BPR_SOURCE_PARTIAL,
)
from ncaa.analytics.player_value.bpr.datasets import build_rapm_dataset
from ncaa.analytics.player_value.bpr.rapm import (
    fit_baseline_rapm,
    fit_prior_informed_rapm,
    tune_prior_sd_scale,
    tune_prior_sd_scales_separate,
    extract_target_season,
)
from ncaa.analytics.player_value.bpr.box_bpr import (
    extract_box_features,
    train_box_bpr_prior_seasons,
    out_of_fold_box_bpr,
    predict_box_bpr,
    export_model_artifacts,
    get_coefficient_table,
    compute_prior_sds_from_r2,
)
from ncaa.analytics.player_value.bpr.preseason import build_prior_maps
from ncaa.analytics.player_value.bpr.preseason_model import (
    train_preseason_models,
    predict_preseason_priors,
)

logger = logging.getLogger(__name__)


def run_bpr_season(
    season_year: int,
    skip_box_bpr: bool = False,
    skip_prior_rapm: bool = False,
    rapm_lambda_override: float | None = None,
    rapm_years: "list[int] | None" = None,
    rapm_window_size: int = 4,
    verbose: bool = True,
) -> dict:
    """
    Run the full BPR pipeline for `season_year`.

    Args:
        season_year:          The target season (BPR written to this season's records).
        rapm_years:           Explicit list of season years to pool for RAPM estimation.
                              When provided, rapm_window_size is ignored.
                              Example: [2024, 2025, 2026] for a 3-year window.
        rapm_window_size:     Number of consecutive seasons to pool, ending at season_year.
                              Default is 4 (mirrors EvanMiya methodology).
                              Ignored if rapm_years is provided explicitly.
                              Pass 1 to revert to single-season mode.
        skip_box_bpr:         Skip Box BPR training (RAPM-only mode).
        skip_prior_rapm:      Skip prior-informed RAPM (baseline RAPM = final).
        rapm_lambda_override: Override CV lambda selection with a fixed value.
        verbose:              Log progress information.

    Returns a summary dict with statistics from each phase.
    """
    from ncaa.models import PlayerSeasonStats, BPRModelArtifact, Season

    summary: dict = {"season_year": season_year, "phases": {}}
    now = datetime.now(tz=timezone.utc)

    # Resolve which season(s) contribute RAPM observations.
    # If rapm_years is provided explicitly, use it as-is.
    # Otherwise build a rolling window of rapm_window_size seasons ending at season_year.
    if rapm_years is not None:
        _rapm_years = rapm_years
    else:
        _rapm_years = list(range(season_year - rapm_window_size + 1, season_year + 1))
        # e.g. season_year=2026, window=4 → [2023, 2024, 2025, 2026]

    # ── Phase 1: Build RAPM dataset ───────────────────────────────────────────
    logger.info(f"[BPR] Phase 1: Building RAPM dataset for seasons {_rapm_years}")
    dataset = build_rapm_dataset(_rapm_years, verbose=verbose)
    n_obs            = dataset["n_observations"]
    n_player_seasons = dataset["n_player_seasons"]
    n_target_players = len(dataset["target_season_player_ids"])
    # Use actual seasons after FGA-coverage filtering, not the requested window
    _effective_years = dataset["season_years"]
    target_year      = max(_effective_years)
    rapm_window      = dataset["rapm_window"]
    summary["phases"]["dataset"] = {
        "n_observations":      n_obs,
        "n_player_seasons":    n_player_seasons,
        "n_target_players":    n_target_players,
        "rapm_window":         rapm_window,
        "season_years":        _effective_years,
        "target_year":         target_year,
        "player_season_keyed": True,
    }

    # possession_totals_target is always target-season-only (v1.3.1 datasets.py guarantee)
    _write_poss_totals = dataset["possession_totals_target"]
    if len(_effective_years) > 1:
        logger.info(
            "[BPR] Multi-year RAPM: seasons=%s, target=%s.  "
            "Coefficients are player-season-specific (v1.3.1 — production multi-year RAPM).  "
            "Write operations use target-season possession totals only.",
            _effective_years, target_year,
        )

    has_stint_data = n_obs > 0

    if not has_stint_data:
        logger.warning(
            f"[BPR] Season {season_year} has no lineup segments "
            f"(no PBP stint data).  Box BPR only."
        )

    # ── Phase 2+3: Baseline RAPM (only when stint data exists) ────────────────
    baseline_rapm: dict | None = None
    if has_stint_data:
        logger.info(f"[BPR] Phase 2+3: Fitting baseline RAPM  ({n_obs} segments, {n_player_seasons} player-seasons, {n_target_players} target-season players)")
        baseline_rapm = fit_baseline_rapm(
            observations=dataset["observations"],
            player_season_index=dataset["player_season_index"],
            n_player_seasons=n_player_seasons,
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
        # Extract only target-season coefficients before writing.
        logger.info("[BPR] Phase 2b: Writing baseline RAPM targets to DB")
        _baseline_obpr_target = extract_target_season(baseline_rapm["obpr"], target_year)
        _baseline_dbpr_target = extract_target_season(baseline_rapm["dbpr"], target_year)
        n_baseline_written = _write_baseline_rapm(
            season_year=season_year,
            baseline_obpr=_baseline_obpr_target,
            baseline_dbpr=_baseline_dbpr_target,
            off_poss_map=_write_poss_totals,
            def_poss_map=_write_poss_totals,
        )
        summary["phases"]["baseline_rapm"]["n_baseline_written"] = n_baseline_written

    # ── Phase 3: Load PlayerSeasonStats for box feature extraction ────────────
    logger.info(f"[BPR] Phase 3: Loading PlayerSeasonStats for season {season_year}")
    pss_qs = PlayerSeasonStats.objects.filter(
        season__year=season_year,
    ).values(
        "player_id", "team_id", "gp", "mpg",
        "pts", "ast", "tov", "stl", "blk", "pf", "reb",
        "oreb_pg", "dreb_pg",
        "fga_pg", "fg3a_pg", "fta_pg", "ftm_pg",
        "efg_pct", "ts_pct",
        "on_court_secs_pg",
    )
    player_season_stats = list(pss_qs)
    summary["phases"]["player_season_stats"] = {"n_records": len(player_season_stats)}

    opp_quality_map = _build_opponent_quality_map(season_year)
    logger.info(f"[BPR] Phase 3: opponent quality map built for {len(opp_quality_map)} teams")

    # ── Phase 4: Box BPR — leak-free training ─────────────────────────────────
    # Use current-season-only possession totals (not pooled multi-year totals) so
    # that Box BPR per-100-poss feature normalization reflects this season only.
    off_poss_map = {pid: v["off"] for pid, v in _write_poss_totals.items()}
    def_poss_map = {pid: v["def"] for pid, v in _write_poss_totals.items()}

    model_artifacts: dict | None = None
    box_bpr_preds:   dict | None = None

    if not skip_box_bpr and baseline_rapm is not None:
        logger.info("[BPR] Phase 4: Box BPR (leak-free training)")

        # 4a. Prefer multi-year RAPM non-target coefficients as Box BPR training targets.
        # These are jointly estimated across all window seasons → lower noise than
        # single-season DB baselines. This is the EvanMiya methodology: train Box BPR
        # on stable multi-year RAPM coefficients, not noisy single-season estimates.
        # Fall back to prior-season DB baselines when multi-year is unavailable
        # (single-season mode or first run without prior window seasons).
        prior_train_data = None
        if len(_rapm_years) > 1 and baseline_rapm is not None:
            prior_train_data = _load_box_bpr_training_from_multi_year_rapm(
                baseline_rapm_obpr=baseline_rapm["obpr"],
                baseline_rapm_dbpr=baseline_rapm["dbpr"],
                target_year=target_year,
                current_season_stats=player_season_stats,
                current_off_poss_map=off_poss_map,
                current_def_poss_map=def_poss_map,
            )
            if prior_train_data:
                prior_train_data["training_source_type"] = "multi_year_rapm"

        if prior_train_data is None:
            # Fallback: load single-season baseline RAPM targets from DB
            prior_train_data = _load_prior_season_box_data(
                season_year, player_season_stats, off_poss_map, def_poss_map
            )
            if prior_train_data:
                prior_train_data["training_source_type"] = "db_baseline"

        n_prior = len(prior_train_data["off_y"]) if prior_train_data else 0

        try:
            if n_prior >= MIN_PRIOR_TRAINING_SAMPLES:
                logger.info(
                    f"[BPR] Phase 4a: Training Box BPR on {n_prior} pooled records "
                    f"from seasons {prior_train_data.get('prior_years', [])}"
                )
                model_artifacts, box_bpr_preds = train_box_bpr_prior_seasons(
                    train_off_X=prior_train_data["off_X"],
                    train_off_y=prior_train_data["off_y"],
                    train_def_X=prior_train_data["def_X"],
                    train_def_y=prior_train_data["def_y"],
                    current_season_stats=player_season_stats,
                    current_off_poss_map=off_poss_map,
                    current_def_poss_map=def_poss_map,
                    opp_quality_map=opp_quality_map,
                )
                src_type = prior_train_data.get("training_source_type", "db_baseline")
                model_artifacts["training_source"] = (
                    f"{src_type} (n={n_prior}, "
                    f"years={prior_train_data.get('prior_years', [])})"
                )
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
                    rapm_obpr=_baseline_obpr_target,
                    rapm_dbpr=_baseline_dbpr_target,
                    opp_quality_map=opp_quality_map,
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

    # ── Phase 4.5: Compute R²-derived prior SDs from the fitted box model ─────
    # Replaces hardcoded PRIOR_SD_BOX_OFF / PRIOR_SD_BOX_DEF constants.
    # prior_sd = sqrt(1 - R²) × σ_rapm — tighter when box model fits well.
    r2_prior_sd_off: float = PRIOR_SD_BOX_OFF
    r2_prior_sd_def: float = PRIOR_SD_BOX_DEF

    if model_artifacts is not None and baseline_rapm is not None:
        target_obpr = extract_target_season(baseline_rapm["obpr"], target_year)
        target_dbpr = extract_target_season(baseline_rapm["dbpr"], target_year)

        if model_artifacts.get("training_method") == "out_of_fold":
            # OOF path: use stored OOF predictions directly — truly out-of-sample
            oof_obpr = {
                pid: v["box_obpr"]
                for pid, v in (box_bpr_preds or {}).items()
                if pid in target_obpr
            }
            oof_dbpr = {
                pid: v["box_dbpr"]
                for pid, v in (box_bpr_preds or {}).items()
                if pid in target_dbpr
            }
            r2_prior_sd_off, r2_prior_sd_def = compute_prior_sds_from_r2(
                model_artifacts=model_artifacts,
                rapm_obpr=target_obpr,
                rapm_dbpr=target_dbpr,
                player_season_stats=player_season_stats,
                off_poss_map=off_poss_map,
                def_poss_map=def_poss_map,
                opp_quality_map=opp_quality_map,
                precomputed_off_preds=oof_obpr,
                precomputed_def_preds=oof_dbpr,
            )
        else:
            # Prior-season training path: predict current season → true OOS R²
            r2_prior_sd_off, r2_prior_sd_def = compute_prior_sds_from_r2(
                model_artifacts=model_artifacts,
                rapm_obpr=target_obpr,
                rapm_dbpr=target_dbpr,
                player_season_stats=player_season_stats,
                off_poss_map=off_poss_map,
                def_poss_map=def_poss_map,
                opp_quality_map=opp_quality_map,
            )

        summary["phases"]["box_bpr"]["r2_prior_sd_off"] = round(r2_prior_sd_off, 4)
        summary["phases"]["box_bpr"]["r2_prior_sd_def"] = round(r2_prior_sd_def, 4)
        logger.info(
            f"[BPR] Phase 4.5: R²-derived prior SDs — "
            f"off={r2_prior_sd_off:.3f}, def={r2_prior_sd_def:.3f}"
        )

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

        # Load prior-season baseline RAPM for returning players (v1.3 history signals)
        prior_history = _load_prior_season_history(
            season_year=season_year,
            player_ids=dataset["target_season_player_ids"],
        )
        logger.info(
            f"[BPR] Phase 5: prior-history loaded for {len(prior_history)} returning players"
        )

        # Load recruiting profiles for freshmen in this season (Phase C1)
        recruiting_priors = _load_recruiting_priors(
            season_year=season_year,
            player_ids=dataset["target_season_player_ids"],
        )
        n_recruiting = len(recruiting_priors)
        if n_recruiting:
            logger.info(
                f"[BPR] Phase 5: recruiting priors loaded for {n_recruiting} players"
            )
        # Only apply recruiting priors for players who have no box BPR data.
        # Filtering happens inside build_prior_maps (box always takes precedence).

        # ── Preseason regression model (replaces flat box+history blend) ─────
        # Train returner + transfer Ridge sub-models on historical data,
        # then predict prior means + per-player SDs for target-season players.
        from ncaa.models import PlayerSeasonProjection as _PSP
        psp_meta_qs = _PSP.objects.filter(
            from_season__year=season_year,
            player_id__in=dataset["target_season_player_ids"],
        ).values("player_id", "recruitment_type", "n_prior_seasons")
        _recruitment_types    = {r["player_id"]: r["recruitment_type"]  for r in psp_meta_qs}
        _n_prior_seasons_map  = {r["player_id"]: r["n_prior_seasons"]   for r in psp_meta_qs}

        logger.info("[BPR] Phase 5: Training preseason regression models")
        _preseason_models = train_preseason_models(season_year)
        preseason_preds   = predict_preseason_priors(
            player_ids       = dataset["target_season_player_ids"],
            season_year      = season_year,
            box_bpr_preds    = box_preds_for_prior,
            recruitment_types= _recruitment_types,
            n_prior_seasons_map = _n_prior_seasons_map,
            models           = _preseason_models,
        )
        logger.info(
            f"[BPR] Phase 5: Preseason model coverage: "
            f"{len(preseason_preds)}/{len(dataset['target_season_player_ids'])} players"
        )
        n_preseason = len(preseason_preds)
        summary["phases"].setdefault("sd_scale_cv", {})["n_preseason_priors"] = n_preseason

        # Write preseason predictions to DB (preseason_obpr/dbpr already exist on PSS)
        _write_preseason_predictions(season_year, preseason_preds)

        prior_mean_obpr, prior_mean_dbpr, prior_sd_obpr, prior_sd_dbpr = build_prior_maps(
            player_ids=dataset["target_season_player_ids"],
            box_bpr_preds=box_preds_for_prior,
            prior_history=prior_history if prior_history else None,
            recruiting_priors=recruiting_priors if recruiting_priors else None,
            preseason_preds=preseason_preds if preseason_preds else None,
            prior_sd_box_off=r2_prior_sd_off,
            prior_sd_box_def=r2_prior_sd_def,
        )

        # Convert player_id-keyed priors → (player_id, season_year)-keyed for multi-year safety.
        # Target-season rows receive their computed box-BPR prior.
        # Non-target-season rows get neutral priors (mean=0, default SD) so that
        # RAPM data dominates for those observations — no cross-season prior bleed.
        # In single-season mode all rows share target_year so this is a no-op.
        ps_prior_mean_obpr: dict[tuple[int, int], float] = {}
        ps_prior_mean_dbpr: dict[tuple[int, int], float] = {}
        ps_prior_sd_obpr:   dict[tuple[int, int], float] = {}
        ps_prior_sd_dbpr:   dict[tuple[int, int], float] = {}
        n_target_priors = 0
        n_neutral_priors = 0
        for (pid, yr) in dataset["player_season_index"]:
            ps_key = (pid, yr)
            if yr == target_year:
                ps_prior_mean_obpr[ps_key] = prior_mean_obpr.get(pid, 0.0)
                ps_prior_mean_dbpr[ps_key] = prior_mean_dbpr.get(pid, 0.0)
                ps_prior_sd_obpr[ps_key]   = prior_sd_obpr.get(pid, PRIOR_SD_DEFAULT_OFF)
                ps_prior_sd_dbpr[ps_key]   = prior_sd_dbpr.get(pid, PRIOR_SD_DEFAULT_DEF)
                n_target_priors += 1
            else:
                # Non-target season: neutral priors so data dominates
                ps_prior_mean_obpr[ps_key] = 0.0
                ps_prior_mean_dbpr[ps_key] = 0.0
                ps_prior_sd_obpr[ps_key]   = PRIOR_SD_DEFAULT_OFF
                ps_prior_sd_dbpr[ps_key]   = PRIOR_SD_DEFAULT_DEF
                n_neutral_priors += 1

        if n_neutral_priors > 0:
            logger.info(
                f"[BPR] Phase 5: player-season prior conversion — "
                f"{n_target_priors} target-season priors, "
                f"{n_neutral_priors} neutral non-target priors (multi-year mode)"
            )

        # Tune prior SD scales by CV:
        # a) Joint global scale (single multiplier for off + def)
        # b) Separate off/def scales (1D coordinate descent)
        # Pick whichever gives lower held-out WMSE.
        logger.info("[BPR] Phase 5: Tuning prior SD scale (joint) by CV")
        joint_scale, joint_cv = tune_prior_sd_scale(
            observations=dataset["observations"],
            player_season_index=dataset["player_season_index"],
            n_player_seasons=n_player_seasons,
            prior_mean_obpr=ps_prior_mean_obpr,
            prior_mean_dbpr=ps_prior_mean_dbpr,
            prior_sd_obpr=ps_prior_sd_obpr,
            prior_sd_dbpr=ps_prior_sd_dbpr,
            baseline_lambda=baseline_rapm["lambda"],
        )

        logger.info("[BPR] Phase 5: Tuning prior SD scales (separate off/def) by CV")
        sep_off, sep_def, sep_wmse, sep_cv = tune_prior_sd_scales_separate(
            observations=dataset["observations"],
            player_season_index=dataset["player_season_index"],
            n_player_seasons=n_player_seasons,
            prior_mean_obpr=ps_prior_mean_obpr,
            prior_mean_dbpr=ps_prior_mean_dbpr,
            prior_sd_obpr=ps_prior_sd_obpr,
            prior_sd_dbpr=ps_prior_sd_dbpr,
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
            # Prior-keying audit fields
            "prior_keying": "player_season",
            "n_target_priors": n_target_priors,
            "n_neutral_non_target_priors": n_neutral_priors,
            "n_recruiting_priors": n_recruiting,
        }

        logger.info("[BPR] Phase 5: Fitting prior-informed RAPM")
        prior_rapm = fit_prior_informed_rapm(
            observations=dataset["observations"],
            player_season_index=dataset["player_season_index"],
            n_player_seasons=n_player_seasons,
            prior_mean_obpr=ps_prior_mean_obpr,
            prior_mean_dbpr=ps_prior_mean_dbpr,
            prior_sd_obpr=ps_prior_sd_obpr,
            prior_sd_dbpr=ps_prior_sd_dbpr,
            baseline_lambda=baseline_rapm["lambda"],
            sd_scale_off=sd_scale_off,
            sd_scale_def=sd_scale_def,
        )
        # Slice to target-season coefficients only before writing
        final_obpr = extract_target_season(prior_rapm["obpr"], target_year)
        final_dbpr = extract_target_season(prior_rapm["dbpr"], target_year)
        summary["phases"]["prior_rapm"] = {
            "intercept":    prior_rapm["intercept"],
            "hca":          prior_rapm["hca"],
            "sd_scale_off": prior_rapm["sd_scale_off"],
            "sd_scale_def": prior_rapm["sd_scale_def"],
        }
    elif baseline_rapm is not None:
        # No box BPR available — use baseline RAPM as final (target season only)
        final_obpr = extract_target_season(baseline_rapm["obpr"], target_year)
        final_dbpr = extract_target_season(baseline_rapm["dbpr"], target_year)

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
            rapm_window=rapm_window,
            n_player_seasons=n_player_seasons,
            n_target_players=n_target_players,
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
    from ncaa.models import PlayerSeasonStats

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


def _build_opponent_quality_map(season_year: int) -> dict[int, float]:
    """
    Build team_id → mean adj_em of opponents faced this season.

    Used as a schedule-strength feature in Box BPR to correct for the inflation
    that mid-major players get from facing weak opponents. adj_em is zero-sum
    across D1 so no centering needed — league average is ~0.

    Missing teams (no games or no ratings) → 0.0 (league average, neutral).
    """
    from collections import defaultdict
    from ncaa.models import Game, TeamSeasonRatings

    ratings = {
        r["team_id"]: r["adj_em"]
        for r in TeamSeasonRatings.objects.filter(
            season__year=season_year,
        ).values("team_id", "adj_em")
    }
    if not ratings:
        logger.warning(
            f"[BPR] _build_opponent_quality_map: no TeamSeasonRatings for {season_year}"
        )
        return {}

    opp_em_lists: dict[int, list[float]] = defaultdict(list)
    for g in Game.objects.filter(
        season_year=season_year,
        status="final",
    ).values("home_team_id", "away_team_id"):
        home, away = g["home_team_id"], g["away_team_id"]
        if home and away:
            if away in ratings:
                opp_em_lists[home].append(ratings[away])
            if home in ratings:
                opp_em_lists[away].append(ratings[home])

    result = {tid: sum(em) / len(em) for tid, em in opp_em_lists.items()}
    logger.info(
        f"[BPR] Opponent quality map: {len(result)} teams, "
        f"mean={sum(result.values()) / max(len(result), 1):.2f}"
    )
    return result


def _load_prior_season_box_data(
    season_year: int,
    current_season_stats: list[dict],
    current_off_poss_map: dict[int, float],
    current_def_poss_map: dict[int, float],
    n_prior_seasons: int | None = None,
) -> dict | None:
    """
    Load box features + CLEAN BASELINE RAPM targets for qualifying players in prior seasons.

    v1.2 fix: uses baseline_obpr / baseline_dbpr (raw RAPM before prior-informed fit)
    as training targets, NOT the final obpr / dbpr values.  This eliminates the
    recursive contamination where final BPR (influenced by box priors) becomes the
    target for the next season's box model, creating a feedback loop.

    Teacher-student chain guaranteed:
        baseline RAPM → Box BPR prior → final prior-informed RAPM

    Phase A2: n_prior_seasons=None (default) uses ALL available prior seasons with
    clean baseline RAPM data, giving the Box BPR model the largest possible stable
    training set.  Pass an integer to restrict to a fixed lookback window.

    Returns a dict {off_X, off_y, def_X, def_y, prior_years} (numpy arrays),
    or None if no qualifying prior-season data is found.
    """
    from ncaa.models import PlayerSeasonStats

    if n_prior_seasons is not None:
        candidate_years = list(range(season_year - n_prior_seasons, season_year))
    else:
        # All years before target that have any RAPM data; coverage check follows.
        candidate_years = None   # resolved below from DB

    # Apply the same FGA-coverage gate used in build_rapm_dataset():
    # prior years with <50% team_fga coverage have corrupted possession estimates
    # → their baseline_obpr/baseline_dbpr targets are unreliable → exclude them.
    MIN_FGA_COVERAGE = 0.50
    from ncaa.models import PlayerGameStint as _PGS
    if candidate_years is not None:
        years_to_check = candidate_years
    else:
        # Discover which years have baseline RAPM data at all
        years_to_check = list(
            PlayerSeasonStats.objects.filter(
                season__year__lt=season_year,
                baseline_obpr__isnull=False,
            ).values_list("season__year", flat=True).distinct().order_by("season__year")
        )

    reliable_years: list[int] = []
    for yr in years_to_check:
        total = _PGS.objects.filter(game__season_year=yr).count()
        if total == 0:
            continue
        with_fga = _PGS.objects.filter(game__season_year=yr, team_fga__gt=0).count()
        if (with_fga / total) >= MIN_FGA_COVERAGE:
            reliable_years.append(yr)
        else:
            logger.debug(
                f"[BPR] Phase A2: Excluding prior year {yr} from Box BPR training "
                f"(FGA coverage {with_fga/total:.1%} < {MIN_FGA_COVERAGE:.0%} — "
                f"corrupted possession estimates in baseline RAPM)"
            )

    if not reliable_years:
        return None

    prior_year_filter = {"season__year__in": reliable_years}

    qs = PlayerSeasonStats.objects.filter(
        **prior_year_filter,
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
        "player_id", "team_id", "season__year", "gp", "mpg",
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

    prior_years = sorted({r["season__year"] for r in prior_records})

    # Process each year independently to avoid player_id collision in poss maps
    # (the same player across multiple seasons needs per-season features).
    off_X, off_y, def_X, def_y = [], [], [], []
    player_ids: list[int] = []   # parallel to off_X/def_X rows — used by Change 3 target substitution
    for yr in prior_years:
        yr_records = [r for r in prior_records if r["season__year"] == yr]
        yr_off_poss = {r["player_id"]: r["off_poss"] for r in yr_records}
        yr_def_poss = {r["player_id"]: r["def_poss"] for r in yr_records}
        yr_opp_quality = _build_opponent_quality_map(yr)
        yr_feats = extract_box_features(
            yr_records, yr_off_poss, yr_def_poss,
            opp_quality_map=yr_opp_quality,
        )
        for r in yr_records:
            pid = r["player_id"]
            if pid not in yr_feats:
                continue
            feats = yr_feats[pid]
            off_X.append(feats["off"])
            off_y.append(float(r["baseline_obpr"]))   # v1.2: clean baseline target
            def_X.append(feats["def"])
            def_y.append(float(r["baseline_dbpr"]))   # v1.2: clean baseline target
            player_ids.append(pid)

    if not off_X:
        return None

    logger.info(
        f"[BPR] Phase A2: Pooled Box BPR training — {len(off_X)} records "
        f"from {len(prior_years)} prior seasons: {prior_years}"
    )

    return {
        "off_X":       np.array(off_X, dtype=np.float64),
        "off_y":       np.array(off_y, dtype=np.float64),
        "def_X":       np.array(def_X, dtype=np.float64),
        "def_y":       np.array(def_y, dtype=np.float64),
        "prior_years": prior_years,
        "player_ids":  player_ids,   # list[int], parallel to row arrays
    }


def _write_preseason_predictions(
    season_year: int,
    preseason_preds: "dict[int, dict]",
) -> None:
    """
    Write preseason model predictions to PlayerSeasonStats.preseason_obpr / preseason_dbpr.
    Fields already exist on the model (nullable FloatField).
    """
    from ncaa.models import PlayerSeasonStats

    if not preseason_preds:
        return

    qs = PlayerSeasonStats.objects.filter(
        season__year=season_year,
        player_id__in=list(preseason_preds),
    )
    to_update = []
    for pss in qs:
        pred = preseason_preds.get(pss.player_id)
        if pred:
            pss.preseason_obpr = round(pred["obpr_mean"], 4)
            pss.preseason_dbpr = round(pred["dbpr_mean"], 4)
            to_update.append(pss)

    with transaction.atomic():
        PlayerSeasonStats.objects.bulk_update(
            to_update, ["preseason_obpr", "preseason_dbpr"], batch_size=500
        )
    logger.info(
        f"[BPR] Wrote preseason predictions to DB for {len(to_update)} players"
    )


def _load_box_bpr_training_from_multi_year_rapm(
    baseline_rapm_obpr: "dict[tuple[int, int], float]",
    baseline_rapm_dbpr: "dict[tuple[int, int], float]",
    target_year: int,
    current_season_stats: list[dict],
    current_off_poss_map: dict[int, float],
    current_def_poss_map: dict[int, float],
) -> "dict | None":
    """
    Build Box BPR training data using the current multi-year RAPM run's
    non-target-season coefficients as targets.

    EvanMiya trains Box BPR on multi-year RAPM coefficients — stable, jointly
    estimated values with lower variance than single-season DB baselines.
    This function gives us the same property: the (player_id, yr) coefficients
    for yr != target_year are from the same joint 4-year estimation, so they
    benefit from regularization across all four seasons simultaneously.

    Avoids leakage: we only use non-target-season coefficients as targets, so
    the current-season Box BPR predictions never see their own RAPM target.
    """
    from ncaa.models import PlayerSeasonStats

    # Non-target-season (player_id, year) pairs with RAPM coefficients
    prior_keys_obpr = {(pid, yr) for (pid, yr) in baseline_rapm_obpr if yr != target_year}
    prior_keys_dbpr = {(pid, yr) for (pid, yr) in baseline_rapm_dbpr if yr != target_year}
    usable_keys = prior_keys_obpr & prior_keys_dbpr
    if not usable_keys:
        return None

    prior_years = sorted({yr for _, yr in usable_keys})

    qs = (
        PlayerSeasonStats.objects
        .filter(
            season__year__in=prior_years,
            off_poss__gte=MIN_OFF_POSS_BPR,
            def_poss__gte=MIN_DEF_POSS_BPR,
            gp__gte=MIN_GP_BOX_BPR,
            mpg__gte=MIN_MPG_BOX_BPR,
        )
        .values(
            "player_id", "team_id", "season__year", "gp", "mpg",
            "pts", "ast", "tov", "stl", "blk", "pf", "reb",
            "oreb_pg", "dreb_pg",
            "fga_pg", "fg3a_pg", "fta_pg", "ftm_pg",
            "efg_pct", "ts_pct",
            "on_court_secs_pg",
            "off_poss", "def_poss",
        )
    )

    prior_records = list(qs)
    if not prior_records:
        return None

    actual_prior_years = sorted({r["season__year"] for r in prior_records})

    off_X, off_y, def_X, def_y, player_ids = [], [], [], [], []
    for yr in actual_prior_years:
        yr_records = [r for r in prior_records if r["season__year"] == yr]
        yr_off_poss = {r["player_id"]: r["off_poss"] for r in yr_records}
        yr_def_poss = {r["player_id"]: r["def_poss"] for r in yr_records}
        yr_opp_quality = _build_opponent_quality_map(yr)
        yr_feats = extract_box_features(
            yr_records, yr_off_poss, yr_def_poss,
            opp_quality_map=yr_opp_quality,
        )
        for r in yr_records:
            pid = r["player_id"]
            ps_key = (pid, yr)
            if pid not in yr_feats or ps_key not in usable_keys:
                continue
            feats = yr_feats[pid]
            off_X.append(feats["off"])
            off_y.append(baseline_rapm_obpr[ps_key])
            def_X.append(feats["def"])
            def_y.append(baseline_rapm_dbpr[ps_key])   # already sign-flipped (positive=good)
            player_ids.append(pid)

    if not off_X:
        return None

    logger.info(
        f"[BPR] Phase 4a (multi-year): {len(off_X)} training samples from non-target "
        f"seasons {actual_prior_years} — multi-year-stabilized RAPM targets"
    )
    return {
        "off_X":       np.array(off_X, dtype=np.float64),
        "off_y":       np.array(off_y, dtype=np.float64),
        "def_X":       np.array(def_X, dtype=np.float64),
        "def_y":       np.array(def_y, dtype=np.float64),
        "prior_years": actual_prior_years,
        "player_ids":  player_ids,
    }


def _load_averaged_rapm_targets(
    season_year: int,
    window_size: int = 4,
) -> "dict[int, dict] | None":
    """
    For each player who has baseline RAPM in multiple prior seasons, return an
    averaged (player_id → avg_baseline_obpr, avg_baseline_dbpr) target.

    Using averaged multi-year targets instead of single-season targets as Box BPR
    training labels reduces noise and produces more stable feature weights — closer
    to how EvanMiya trains his Box BPR on pooled multi-year RAPM coefficients.

    Returns: {player_id: {"baseline_obpr": float, "baseline_dbpr": float}}
    or None if fewer than MIN_PRIOR_TRAINING_SAMPLES players have multi-year data.
    """
    from collections import defaultdict
    from ncaa.models import PlayerSeasonStats

    prior_years = list(range(season_year - window_size, season_year))
    if not prior_years:
        return None

    qs = (
        PlayerSeasonStats.objects
        .filter(
            season__year__in=prior_years,
            baseline_obpr__isnull=False,
            baseline_dbpr__isnull=False,
            off_poss__gte=MIN_OFF_POSS_BPR,
            def_poss__gte=MIN_DEF_POSS_BPR,
        )
        .values("player_id", "season__year", "baseline_obpr", "baseline_dbpr")
    )

    player_vals: dict[int, list] = defaultdict(list)
    for row in qs:
        player_vals[row["player_id"]].append({
            "baseline_obpr": float(row["baseline_obpr"]),
            "baseline_dbpr": float(row["baseline_dbpr"]),
        })

    if not player_vals:
        return None

    averaged = {
        pid: {
            "baseline_obpr": sum(r["baseline_obpr"] for r in records) / len(records),
            "baseline_dbpr": sum(r["baseline_dbpr"] for r in records) / len(records),
        }
        for pid, records in player_vals.items()
    }

    logger.info(
        f"[BPR] Averaged RAPM targets: {len(averaged)} players "
        f"across prior years {prior_years} (window={window_size})"
    )
    return averaged


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
    from ncaa.models import PlayerSeasonStats

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


def _load_prior_season_history(
    season_year: int,
    player_ids: list[int],
    n_prior_seasons: int = 2,
) -> dict[int, dict]:
    """
    Load prior-season baseline RAPM values for players appearing in the current dataset.

    Used to blend historical actual performance into preseason priors (v1.3).
    Only returns records where BOTH baseline_obpr and baseline_dbpr are non-null
    (i.e. the player met possession thresholds in the prior season).

    Returns: {player_id: {"baseline_obpr": float, "baseline_dbpr": float}}
    """
    from ncaa.models import PlayerSeasonStats

    prior_years = list(range(season_year - n_prior_seasons, season_year))

    qs = (
        PlayerSeasonStats.objects
        .filter(
            season__year__in=prior_years,
            player_id__in=player_ids,
            baseline_obpr__isnull=False,
            baseline_dbpr__isnull=False,
        )
        .values("player_id", "season__year", "baseline_obpr", "baseline_dbpr")
        .order_by("player_id", "-season__year")  # most recent first
    )

    # Keep only the most recent prior-season record per player
    history: dict[int, dict] = {}
    for row in qs:
        pid = row["player_id"]
        if pid not in history:
            history[pid] = {
                "baseline_obpr": float(row["baseline_obpr"]),
                "baseline_dbpr": float(row["baseline_dbpr"]),
            }
    return history


def _load_recruiting_priors(
    season_year: int,
    player_ids: list[int],
) -> dict[int, dict]:
    """
    Load PlayerRecruitingProfile records for players whose first college season
    is `season_year`, enriched with national_rank and destination team adj_em.

    Returns: {player_id: {stars, composite_score, national_rank, team_adj_em}}
    """
    from ncaa.models import PlayerRecruitingProfile, PlayerSeasonStats, TeamSeasonRatings

    player_ids_set = set(player_ids)
    qs = (
        PlayerRecruitingProfile.objects
        .filter(class_year=season_year, player_id__in=player_ids_set)
        .values("player_id", "stars", "composite_score", "national_rank")
    )

    # Team adj_em for each player's current-season team
    team_by_player = dict(
        PlayerSeasonStats.objects
        .filter(season__year=season_year, player_id__in=player_ids_set)
        .values_list("player_id", "team_id")
    )
    adj_em_by_team = dict(
        TeamSeasonRatings.objects
        .filter(season__year=season_year)
        .values_list("team_id", "adj_em")
    )

    result = {}
    for row in qs:
        pid = row["player_id"]
        team_id = team_by_player.get(pid)
        team_adj_em = float(adj_em_by_team.get(team_id, 0.0)) if team_id else 0.0
        result[pid] = {
            "stars":           row["stars"],
            "composite_score": row["composite_score"],
            "national_rank":   row["national_rank"],
            "team_adj_em":     team_adj_em,
        }
    return result


def _save_model_artifact(
    season_year: int,
    model_artifacts: dict,
    baseline_rapm: dict,
    sd_cv_summary: dict,
    export_fn,
    rapm_window: str = "single_season",
    n_player_seasons: int = 0,
    n_target_players: int = 0,
) -> None:
    from ncaa.models import BPRModelArtifact, Season

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
                "model_type":              "box_bpr",
                "rapm_window":             rapm_window,
                "n_player_seasons":        n_player_seasons,
                "n_target_players":        n_target_players,
                "player_season_keyed":     True,   # v1.3.1: coefficients keyed by (player_id, season_year)
                "training_method":         model_artifacts.get("training_method"),
                "training_source":         model_artifacts.get("training_source"),
                "rapm_lambda":             baseline_rapm.get("lambda"),
                "rapm_intercept":          baseline_rapm.get("intercept"),
                "rapm_hca":                baseline_rapm.get("hca"),
                "off_alpha":               model_artifacts.get("off_cv_alpha"),
                "def_alpha":               model_artifacts.get("def_cv_alpha"),
                "off_features":            model_artifacts.get("off_features"),
                "def_features":            model_artifacts.get("def_features"),
                "sd_scale_off":            sd_cv_summary.get("sd_scale_off"),
                "sd_scale_def":            sd_cv_summary.get("sd_scale_def"),
                "sd_tuning_mode":          sd_cv_summary.get("chosen_tuning"),
                "target_contamination_fixed": True,   # v1.2: baseline RAPM targets
            },
        },
    )
