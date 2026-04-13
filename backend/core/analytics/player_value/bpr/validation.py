"""
validation.py — BPR sanity checks and predictive evaluation.

Sanity checks (run after writing to DB):
  1. BPR = OBPR + DBPR for all records where both are non-null
  2. League-average OBPR ≈ 0 (within tolerance)
  3. BPR values within plausible range
  4. HCA sanity (from pipeline summary)
  5. Distribution statistics (percentiles, std, skew)

Quality checks:
  6. Qualified-player completeness — players who meet possession thresholds
     are checked separately (not constrained to bpr__isnull=False) to catch
     any truly missing qualified players.
  7. Partial BPR count — how many players have only one side (bpr_source="partial")

Predictive evaluation (compares model tiers via stored CV metrics):
  8. Held-out WMSE: box-only reference vs baseline RAPM vs prior-informed RAPM
     (box-only WMSE comes from sd_scale=0.01 reference evaluation done during CV)
  9. Top-player ranking sanity review (top-10 by BPR)
  10. Source distribution — how many players at each BPR source category
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from core.analytics.player_value.bpr.constants import (
    BPR_PLAUSIBLE_RANGE,
    MIN_OFF_POSS_BPR,
    MIN_DEF_POSS_BPR,
    HCA_PTS_PER_100,
    BPR_SOURCE_RAPM,
    BPR_SOURCE_BOX,
    BPR_SOURCE_MIXED,
    BPR_SOURCE_PARTIAL,
)

BPR_MAX_PLAUSIBLE = BPR_PLAUSIBLE_RANGE[1]

logger = logging.getLogger(__name__)

_AVG_SKEW_TOLERANCE = 2.0   # high-usage-filtered population skews ~+1 vs all-player average
_HCA_PLAUSIBLE_RANGE = (0.5, 6.0)  # pts/100 poss; flag if estimated HCA is outside this


def run_validation(season_year: int, pipeline_summary: Optional[dict] = None) -> dict:
    """
    Run all sanity checks and predictive evaluation for BPR in `season_year`.

    Optionally accepts a `pipeline_summary` dict from run_bpr_season() so
    we can include RAPM CV metrics in the validation report.

    Returns a dict of {check_name: passed/value}.
    Logs warnings for any failing checks.
    """
    from core.models import PlayerSeasonStats

    qs = PlayerSeasonStats.objects.filter(
        season__year=season_year,
        bpr__isnull=False,
    ).select_related("player").values(
        "player_id", "player__display_name", "bpr", "obpr", "dbpr",
        "box_bpr", "box_obpr", "box_dbpr",
        "baseline_obpr", "baseline_dbpr",
        "off_poss", "def_poss",
        "obpr_source", "dbpr_source", "bpr_source",
    )

    records = list(qs)
    if not records:
        logger.warning(f"[BPR Validation] No BPR records found for season {season_year}")
        return {"no_data": True}

    results: dict = {}

    # ── 1. BPR = OBPR + DBPR (within fp tolerance) ────────────────────────────
    mismatched = [
        r for r in records
        if r["obpr"] is not None and r["dbpr"] is not None
        and abs((r["obpr"] + r["dbpr"]) - (r["bpr"] or 0)) > 0.011
    ]
    results["bpr_sum_check"] = len(mismatched) == 0
    if mismatched:
        logger.warning(f"[BPR Validation] {len(mismatched)} records where BPR ≠ OBPR + DBPR")

    # ── 2. League average ≈ 0 ─────────────────────────────────────────────────
    obprs = [r["obpr"] for r in records if r["obpr"] is not None]
    dbprs = [r["dbpr"] for r in records if r["dbpr"] is not None]
    avg_obpr = float(np.mean(obprs)) if obprs else float("nan")
    avg_dbpr = float(np.mean(dbprs)) if dbprs else float("nan")
    results["avg_obpr"] = round(avg_obpr, 3)
    results["avg_dbpr"] = round(avg_dbpr, 3)
    if abs(avg_obpr) > _AVG_SKEW_TOLERANCE:
        logger.warning(f"[BPR Validation] League avg OBPR={avg_obpr:.3f} (expected ≈0)")
    if abs(avg_dbpr) > _AVG_SKEW_TOLERANCE:
        logger.warning(f"[BPR Validation] League avg DBPR={avg_dbpr:.3f} (expected ≈0)")

    # ── 3. Plausible range ────────────────────────────────────────────────────
    n_records_total = len(records)
    max_oor = max(5, round(0.005 * n_records_total))
    out_of_range = [
        r for r in records
        if (r["obpr"] is not None and abs(r["obpr"]) > BPR_MAX_PLAUSIBLE)
        or (r["dbpr"] is not None and abs(r["dbpr"]) > BPR_MAX_PLAUSIBLE)
    ]
    results["out_of_range_count"] = len(out_of_range)
    if len(out_of_range) > max_oor:
        logger.warning(
            f"[BPR Validation] {len(out_of_range)} player-seasons with |OBPR| or |DBPR| > "
            f"{BPR_MAX_PLAUSIBLE} (threshold: {max_oor})"
        )

    # ── 4. HCA sanity (from pipeline summary) ────────────────────────────────
    if pipeline_summary:
        prior_info = pipeline_summary.get("phases", {}).get("prior_rapm", {})
        hca_est = prior_info.get("hca")
        baseline_info = pipeline_summary.get("phases", {}).get("baseline_rapm", {})
        if hca_est is None:
            hca_est = baseline_info.get("hca")
        if hca_est is not None:
            results["estimated_hca"] = round(float(hca_est), 3)
            hca_ok = _HCA_PLAUSIBLE_RANGE[0] <= hca_est <= _HCA_PLAUSIBLE_RANGE[1]
            results["hca_plausible"] = hca_ok
            if not hca_ok:
                logger.warning(
                    f"[BPR Validation] Estimated HCA={hca_est:.3f} is outside "
                    f"plausible range {_HCA_PLAUSIBLE_RANGE}"
                )

    # ── 5. Distribution statistics ────────────────────────────────────────────
    bpr_vals = [r["bpr"] for r in records if r["bpr"] is not None]
    if bpr_vals:
        arr = np.array(bpr_vals)
        results["distribution"] = {
            "p5":    round(float(np.percentile(arr,  5)), 3),
            "p25":   round(float(np.percentile(arr, 25)), 3),
            "p50":   round(float(np.percentile(arr, 50)), 3),
            "p75":   round(float(np.percentile(arr, 75)), 3),
            "p95":   round(float(np.percentile(arr, 95)), 3),
            "std":   round(float(np.std(arr)), 3),
            "skew":  round(float(_skewness(arr)), 3),
        }

    # ── 6. Qualified player completeness check ──────────────────────────────────
    # Query WITHOUT bpr__isnull=False so we can detect qualified players missing BPR.
    # (The main query starts from bpr__isnull=False and cannot catch these.)
    qual_qs = PlayerSeasonStats.objects.filter(
        season__year=season_year,
        off_poss__gte=MIN_OFF_POSS_BPR,
        def_poss__gte=MIN_DEF_POSS_BPR,
    )
    n_qualified    = qual_qs.count()
    n_qual_w_bpr   = qual_qs.filter(bpr__isnull=False).count()
    n_qual_missing = n_qualified - n_qual_w_bpr
    results["qualified_player_check"] = {
        "n_qualified":          n_qualified,
        "n_qualified_with_bpr": n_qual_w_bpr,
        "n_qualified_missing":  n_qual_missing,
        "passed":               n_qual_missing == 0,
    }
    if n_qual_missing > 0:
        logger.warning(
            f"[BPR Validation] {n_qual_missing} qualified players "
            f"(poss >= threshold) are missing BPR values."
        )

    # ── 7. Partial BPR and source distribution ────────────────────────────────
    source_counts: dict[str, int] = {}
    for r in records:
        src = r.get("bpr_source") or "unknown"
        source_counts[src] = source_counts.get(src, 0) + 1
    n_partial = source_counts.get(BPR_SOURCE_PARTIAL, 0)
    results["source_distribution"] = source_counts
    results["n_partial_bpr"] = n_partial
    if n_partial > 0:
        logger.warning(
            f"[BPR Validation] {n_partial} players have partial BPR "
            f"(bpr_source='partial'; only one side available)."
        )

    # ── 8. Predictive evaluation (WMSE comparison) ────────────────────────────
    results["predictive_eval"] = _compare_predictive_wmse(
        records=records,
        pipeline_summary=pipeline_summary,
    )

    # ── 9. Top-player sanity review ───────────────────────────────────────────
    top_players = sorted(
        [r for r in records if r["bpr"] is not None],
        key=lambda r: r["bpr"],
        reverse=True,
    )[:10]
    results["top10_by_bpr"] = [
        {
            "player_id":  r["player_id"],
            "name":       r.get("player__display_name", "?"),
            "bpr":        round(r["bpr"], 3),
            "obpr":       round(r["obpr"], 3) if r["obpr"] is not None else None,
            "dbpr":       round(r["dbpr"], 3) if r["dbpr"] is not None else None,
            "off_poss":   round(r["off_poss"], 0) if r["off_poss"] is not None else None,
            "bpr_source": r.get("bpr_source"),
        }
        for r in top_players
    ]
    logger.info(
        "[BPR Validation] Top-10 by BPR: "
        + ", ".join(
            f"{r['name']} ({r['bpr']:+.2f}"
            + (" PARTIAL" if r.get("bpr_source") == BPR_SOURCE_PARTIAL else "")
            + ")"
            for r in results["top10_by_bpr"]
        )
    )

    results["n_records"]    = len(records)
    results["n_with_obpr"]  = len(obprs)

    # ── all_passed_core: arithmetic correctness + plausible range ─────────────
    # This is the minimum bar — the model output is self-consistent.
    results["all_passed_core"] = (
        results["bpr_sum_check"] and
        abs(avg_obpr) <= _AVG_SKEW_TOLERANCE and
        abs(avg_dbpr) <= _AVG_SKEW_TOLERANCE and
        results["out_of_range_count"] <= max_oor
    )

    # ── all_passed_strict: also checks completeness, HCA, predictive gain ─────
    # All of these must hold for the leaderboard to be considered publication-ready.
    _qualified_ok   = results.get("qualified_player_check", {}).get("passed", True)
    _hca_ok         = results.get("hca_plausible", True)   # absent = not checked = OK
    _pred_ok        = results.get("predictive_eval", {}).get("prior_rapm_improves_baseline", True)
    _n_total        = max(len(records), 1)
    _partial_rate_ok = results.get("n_partial_bpr", 0) < max(10, round(0.05 * _n_total))
    results["all_passed_strict"] = (
        results["all_passed_core"] and
        _qualified_ok and
        _hca_ok and
        _pred_ok and
        _partial_rate_ok
    )

    # Backward-compat alias (kept so existing callers don't break)
    results["all_passed"] = results["all_passed_core"]

    # ── 10. Component influence diagnostics (v1.3) ───────────────────────────
    results["component_influence"] = _component_influence_diagnostics(records)

    # ── 11. Ranking sanity: strict_bpr vs all_players vs box_bpr (v1.3) ──────
    results["ranking_sanity"] = _ranking_sanity(records)

    # ── 12. Multi-year RAPM metadata audit (v1.3.1) ──────────────────────────
    if pipeline_summary is not None:
        results["multi_year_audit"] = _multi_year_audit(pipeline_summary, records)

    logger.info(f"[BPR Validation] Results: {results}")
    return results


# ── Predictive evaluation helpers ─────────────────────────────────────────────

def _compare_predictive_wmse(records: list[dict], pipeline_summary: Optional[dict]) -> dict:
    """
    Compare held-out WMSE across model tiers using stored CV metrics.

    Baseline RAPM WMSE and prior-informed WMSE come from the CV runs during
    the pipeline.  Box-only WMSE is extracted from the sd_scale CV at the
    BOX_ONLY_SD_SCALE_REF=0.01 reference point.
    """
    eval_results: dict = {}

    if pipeline_summary is None:
        return {"note": "No pipeline_summary provided"}

    phases = pipeline_summary.get("phases", {})

    # Baseline RAPM CV metrics
    baseline_cv = phases.get("baseline_rapm", {}).get("cv_metrics")
    if baseline_cv:
        best_lam  = baseline_cv.get("best_lambda")
        best_wmse = baseline_cv.get("mean_wmse", {}).get(best_lam) if best_lam else None
        eval_results["baseline_rapm"] = {
            "best_lambda": best_lam,
            "best_wmse":   round(best_wmse, 4) if best_wmse else None,
        }

    # SD scale CV metrics (joint and separate)
    sd_cv = phases.get("sd_scale_cv", {})
    if sd_cv:
        joint_cv   = sd_cv.get("joint", {})
        sep_cv     = sd_cv.get("separate", {})
        chosen     = sd_cv.get("chosen_tuning")
        sd_off     = sd_cv.get("sd_scale_off")
        sd_def     = sd_cv.get("sd_scale_def")

        # Best prior-informed WMSE (from whichever tuning was chosen)
        if chosen == "joint":
            best_scale = joint_cv.get("best_sd_scale")
            prior_wmse = joint_cv.get("mean_wmse", {}).get(best_scale) if best_scale else None
        else:
            prior_wmse = sep_cv.get("combined_wmse")

        eval_results["prior_informed_rapm"] = {
            "sd_scale_off":    sd_off,
            "sd_scale_def":    sd_def,
            "chosen_tuning":   chosen,
            "best_wmse":       round(prior_wmse, 4) if prior_wmse else None,
        }

        # Box-only reference WMSE (at sd_scale=0.01, near-box-only)
        box_only_wmse = joint_cv.get("box_only_reference_wmse")
        if box_only_wmse is not None:
            eval_results["box_only_reference"] = {
                "wmse":  round(box_only_wmse, 4),
                "note":  "near-box-only (sd_scale=0.01); held-out WMSE treating box BPR as sole predictor",
            }

        # Improvement from baseline to prior-informed
        baseline_best = eval_results.get("baseline_rapm", {}).get("best_wmse")
        prior_best    = eval_results.get("prior_informed_rapm", {}).get("best_wmse")
        if baseline_best and prior_best:
            delta = prior_best - baseline_best
            eval_results["wmse_delta_vs_baseline"] = round(delta, 4)
            eval_results["prior_rapm_improves_baseline"] = delta < 0
            if delta >= 0:
                logger.warning(
                    f"[BPR Validation] Prior-informed RAPM does NOT improve on baseline RAPM "
                    f"in held-out WMSE (delta={delta:+.4f}). Consider reviewing prior SD scale."
                )

        # Improvement from box-only to prior-informed
        if box_only_wmse and prior_best:
            delta_vs_box = prior_best - box_only_wmse
            eval_results["wmse_delta_vs_box_only"] = round(delta_vs_box, 4)

    # Box BPR summary metadata
    box_phase = phases.get("box_bpr", {})
    if box_phase:
        eval_results["box_bpr"] = {
            "n_train":         box_phase.get("n_train"),
            "training_method": box_phase.get("training_method"),
        }

    # Possessions-weighted MAE between box_bpr and final bpr
    paired = [
        r for r in records
        if r["bpr"] is not None and r["box_bpr"] is not None and r["off_poss"]
    ]
    if paired:
        final_vals = np.array([r["bpr"]     for r in paired])
        box_vals   = np.array([r["box_bpr"] for r in paired])
        poss_w     = np.array([r["off_poss"] for r in paired])
        wmae = float(np.average(np.abs(final_vals - box_vals), weights=poss_w))
        eval_results["box_vs_final_wmae"] = round(wmae, 4)

    return eval_results


def _skewness(arr: np.ndarray) -> float:
    """Pearson's moment coefficient of skewness."""
    n = len(arr)
    if n < 3:
        return 0.0
    mean = arr.mean()
    std  = arr.std()
    if std == 0:
        return 0.0
    return float(np.mean(((arr - mean) / std) ** 3))


# ── Task 7: Component influence diagnostics ───────────────────────────────────

def _component_influence_diagnostics(records: list[dict]) -> dict:
    """
    Measure how much the prior-informed RAPM pulled players away from their
    baseline RAPM estimates.  High |delta_obpr| indicates strong prior influence.

    For defensive analysis, also flags players where dbpr >> obpr relative to
    baseline — a potential sign of defensive overrating by box priors.

    Returns summary stats + top-10 players by absolute prior pull (off and def).
    """
    # Players with both final and baseline RAPM for comparison
    with_baseline = [
        r for r in records
        if r["obpr"] is not None and r["baseline_obpr"] is not None
        and r["dbpr"] is not None and r["baseline_dbpr"] is not None
    ]

    if not with_baseline:
        return {"note": "No players with baseline RAPM for comparison"}

    delta_off = np.array([r["obpr"] - r["baseline_obpr"] for r in with_baseline])
    delta_def = np.array([r["dbpr"] - r["baseline_dbpr"] for r in with_baseline])
    poss_w    = np.array([r["off_poss"] or 1.0 for r in with_baseline])

    wmean_pull_off = float(np.average(np.abs(delta_off), weights=poss_w))
    wmean_pull_def = float(np.average(np.abs(delta_def), weights=poss_w))

    # Top 10 by offensive prior pull
    top_off_pull = sorted(
        with_baseline,
        key=lambda r: abs(r["obpr"] - r["baseline_obpr"]),
        reverse=True,
    )[:10]

    # Top 10 by defensive prior pull
    top_def_pull = sorted(
        with_baseline,
        key=lambda r: abs(r["dbpr"] - r["baseline_dbpr"]),
        reverse=True,
    )[:10]

    def _entry(r: dict, delta_o: float, delta_d: float) -> dict:
        return {
            "name":          r.get("player__display_name", "?"),
            "player_id":     r["player_id"],
            "obpr":          round(r["obpr"], 3),
            "baseline_obpr": round(r["baseline_obpr"], 3),
            "delta_obpr":    round(delta_o, 3),
            "dbpr":          round(r["dbpr"], 3),
            "baseline_dbpr": round(r["baseline_dbpr"], 3),
            "delta_dbpr":    round(delta_d, 3),
            "bpr_source":    r.get("bpr_source"),
        }

    deltas = {
        r["player_id"]: (r["obpr"] - r["baseline_obpr"], r["dbpr"] - r["baseline_dbpr"])
        for r in with_baseline
    }

    # Defensive overrating check: players where dbpr is much higher than baseline_dbpr
    # but obpr is not correspondingly dragged up — suggests box def priors dominate
    def_inflation = [
        r for r in with_baseline
        if (r["dbpr"] - r["baseline_dbpr"]) > 2.0  # prior pulled def up by > 2 pts/100
        and abs(r["obpr"] - r["baseline_obpr"]) < 1.0  # but off barely moved
    ]

    result = {
        "n_with_baseline":       len(with_baseline),
        "wmean_abs_pull_off":    round(wmean_pull_off, 3),
        "wmean_abs_pull_def":    round(wmean_pull_def, 3),
        "n_def_inflation":       len(def_inflation),
        "top10_off_prior_pull": [
            _entry(r, *deltas[r["player_id"]]) for r in top_off_pull
        ],
        "top10_def_prior_pull": [
            _entry(r, *deltas[r["player_id"]]) for r in top_def_pull
        ],
    }

    if def_inflation:
        logger.warning(
            f"[BPR Validation] {len(def_inflation)} players have defensive prior inflation "
            f"(dbpr > baseline_dbpr by >2 pts/100 while off is stable). "
            f"Consider reviewing defensive prior strength or DEF_FEATURES."
        )

    return result


# ── Task 8: Ranking sanity ────────────────────────────────────────────────────

def _ranking_sanity(records: list[dict], top_n: int = 25) -> dict:
    """
    Compare leaderboard composition across three filtered views:
      - strict_bpr:    bpr_source == 'rapm'  (both sides from RAPM)
      - full_two_sided: both obpr + dbpr non-null, not partial
      - box_only:      compare with box_bpr rankings

    Also reports what fraction of the global top-100 by BPR have non-rapm source.
    This makes it easy to see how much contamination exists in the public leaderboard.
    """
    all_with_bpr = [r for r in records if r["bpr"] is not None]
    all_ranked   = sorted(all_with_bpr, key=lambda r: r["bpr"], reverse=True)

    def _fmt(r: dict) -> dict:
        return {
            "name":       r.get("player__display_name", "?"),
            "player_id":  r["player_id"],
            "bpr":        round(r["bpr"], 3),
            "obpr":       round(r["obpr"], 3) if r["obpr"] is not None else None,
            "dbpr":       round(r["dbpr"], 3) if r["dbpr"] is not None else None,
            "bpr_source": r.get("bpr_source"),
        }

    strict_records = [r for r in all_ranked if r.get("bpr_source") == BPR_SOURCE_RAPM]
    full_two_sided = [
        r for r in all_ranked
        if r["obpr"] is not None and r["dbpr"] is not None
        and r.get("bpr_source") != BPR_SOURCE_PARTIAL
    ]

    # Box BPR ranking (where available)
    box_ranked = sorted(
        [r for r in records if r["box_bpr"] is not None],
        key=lambda r: r["box_bpr"],
        reverse=True,
    )

    # Non-rapm % in global top-100
    top100 = all_ranked[:100]
    n_non_rapm_in_top100 = sum(
        1 for r in top100 if r.get("bpr_source") != BPR_SOURCE_RAPM
    )
    pct_non_rapm = round(100.0 * n_non_rapm_in_top100 / max(len(top100), 1), 1)

    if pct_non_rapm > 30:
        logger.warning(
            f"[BPR Validation] {pct_non_rapm}% of top-100 BPR players have non-rapm source. "
            f"Consider using bpr_mode=strict_bpr or full_two_sided for public rankings."
        )

    san = {
        "top{n}_strict_bpr".format(n=top_n):    [_fmt(r) for r in strict_records[:top_n]],
        "top{n}_full_two_sided".format(n=top_n): [_fmt(r) for r in full_two_sided[:top_n]],
        "top{n}_box_bpr".format(n=top_n):        [_fmt(r) for r in box_ranked[:top_n]],
        "n_strict_bpr_players":    len(strict_records),
        "n_full_two_sided_players": len(full_two_sided),
        "pct_non_rapm_in_top100": pct_non_rapm,
    }

    logger.info(
        f"[BPR Validation] Ranking sanity: "
        f"strict_bpr={len(strict_records)}, "
        f"full_two_sided={len(full_two_sided)}, "
        f"non_rapm_in_top100={pct_non_rapm}%"
    )

    return san


# ── 12. Multi-year RAPM audit (v1.3.1) ───────────────────────────────────────

def _multi_year_audit(pipeline_summary: dict, records: list[dict]) -> dict:
    """
    Verify multi-year-specific correctness properties:

    1. Confirm n_player_seasons > n_target_players when rapm_window != "single_season"
       (proves separate per-season columns were emitted)
    2. Confirm player_season_keyed flag is True in artifact metadata
    3. Report how many target-season players have RAPM-source BPR vs box-only
    4. Report n_player_seasons, n_target_players, rapm_window from pipeline metadata
    """
    dataset_phase = pipeline_summary.get("phases", {}).get("dataset", {})
    rapm_window    = dataset_phase.get("rapm_window", "unknown")
    n_ps           = dataset_phase.get("n_player_seasons", 0)
    n_tp           = dataset_phase.get("n_target_players", 0)
    keyed          = dataset_phase.get("player_season_keyed", False)
    season_years   = dataset_phase.get("season_years", [])
    target_year    = dataset_phase.get("target_year")

    audit: dict = {
        "rapm_window":             rapm_window,
        "season_years":            season_years,
        "target_year":             target_year,
        "n_player_seasons":        n_ps,
        "n_target_players":        n_tp,
        "player_season_keyed":     keyed,
    }

    is_multi = rapm_window != "single_season"

    if is_multi:
        # In multi-year mode, player-seasons must outnumber target-season players
        coef_identity_ok = n_ps > n_tp if (n_ps and n_tp) else None
        audit["coefficient_identity_check"] = {
            "passed":  coef_identity_ok,
            "note":    (
                f"n_player_seasons={n_ps} > n_target_players={n_tp} \u2714"
                if coef_identity_ok
                else f"n_player_seasons={n_ps} should exceed n_target_players={n_tp}"
            ),
        }
    else:
        audit["coefficient_identity_check"] = {
            "passed": True,
            "note":   "single_season mode \u2014 one column per player; check not applicable",
        }

    if not keyed:
        logger.warning(
            "[BPR Validation] player_season_keyed=False in pipeline metadata. "
            "Coefficients may NOT be season-specific. Do not use for multi-year production runs."
        )
        audit["coefficient_identity_check"]["passed"] = False

    # Count target-season write outcomes from records
    n_rapm_source  = sum(1 for r in records if r.get("bpr_source") == BPR_SOURCE_RAPM)
    n_box_source   = sum(1 for r in records if r.get("bpr_source") == BPR_SOURCE_BOX)
    n_mixed        = sum(1 for r in records if r.get("bpr_source") == BPR_SOURCE_MIXED)
    n_partial      = sum(1 for r in records if r.get("bpr_source") == BPR_SOURCE_PARTIAL)
    audit["target_season_write_counts"] = {
        "rapm":    n_rapm_source,
        "box":     n_box_source,
        "mixed":   n_mixed,
        "partial": n_partial,
        "total":   len(records),
    }

    logger.info(
        "[BPR Validation] Multi-year audit: window=%s, n_player_seasons=%s, "
        "n_target=%s, player_season_keyed=%s, rapm_writes=%s",
        rapm_window, n_ps, n_tp, keyed, n_rapm_source,
    )

    return audit
