"""
ffi/pipeline.py — Orchestrate factor RAPM fits and compute the new
Four Factor Impact Index (FFII / four_factor_impact_index).

Steps:
  1. Run 4 factor RAPMs  → 8 player impact coefficients
  2. Compute 4 combined margins
  3. Standardize margins across qualified players
  4. Combine with existing Macfax Four Factor weights → FFII (0-100 scale)
  5. Return per-player result dicts ready for DB write

Qualified players: off_poss AND def_poss ≥ MIN_POSS_FFI threshold.

The FFII uses the same formula as the team Four Factor Index and the existing
on_court_ffi:
    wz = Σ weight_k * z_k
    ffii = clamp(0, 100, 50 + FOUR_FACTOR_SCALE * wz)
"""

from __future__ import annotations

import logging
import statistics

from core.constants import FOUR_FACTOR_SCALE, FOUR_FACTOR_WEIGHTS
from core.analytics.player_value.ffi.datasets import build_ffi_dataset
from core.analytics.player_value.ffi.rapm import run_all_factors, tune_factor_lambda, FFI_RAPM_LAMBDA_DEFAULT

logger = logging.getLogger(__name__)

MIN_POSS_FFI = 100  # minimum off and def possessions to receive FFII


def _safe_z(val: float, mean: float, std: float) -> float:
    return (val - mean) / std if std > 0 else 0.0


def run_ffi_pipeline(
    season_years: "int | list[int]",
    lambda_val: float = FFI_RAPM_LAMBDA_DEFAULT,
    auto_tune_lambda: bool = True,
    verbose: bool = True,
) -> dict[int, dict]:
    """
    Full FFI pipeline for the given season(s).

    When auto_tune_lambda=True (default), per-factor λ is selected via 5-fold
    game-split CV independently for each of the 4 factors.  lambda_val is used
    as the fallback for any factor that has no valid observations.

    Set auto_tune_lambda=False to use lambda_val for all factors (legacy
    behaviour or when an explicit --lambda CLI flag is passed).

    Returns {player_id: {
        # 8 impact components (positive-good)
        "off_efg_impact", "def_efg_impact",
        "off_tov_impact", "def_tov_impact",
        "off_orb_impact", "def_reb_impact",
        "off_ftr_impact", "def_ftr_impact",
        # 4 combined margins
        "efg_impact_margin", "tov_impact_margin",
        "reb_impact_margin", "ftr_impact_margin",
        # Final index (0-100)
        "four_factor_impact_index",
    }}
    """
    if verbose:
        logger.info("FFI pipeline: building dataset …")
    dataset = build_ffi_dataset(season_years, verbose=verbose)

    # Phase A3: per-factor λ CV (or fixed fallback)
    if auto_tune_lambda:
        if verbose:
            logger.info("FFI pipeline: tuning λ per factor via 5-fold CV …")
        lambda_per_factor: dict[str, float] = {}
        for factor in ("efg", "tov", "orb", "ftr"):
            best_lam, _ = tune_factor_lambda(dataset, factor)
            lambda_per_factor[factor] = best_lam
        if verbose:
            logger.info(
                f"FFI pipeline: per-factor λ — "
                + ", ".join(f"{f}={lambda_per_factor[f]:.0f}" for f in ("efg", "tov", "orb", "ftr"))
            )
    else:
        lambda_per_factor = {f: lambda_val for f in ("efg", "tov", "orb", "ftr")}
        if verbose:
            logger.info(f"FFI pipeline: fitting factor RAPMs (λ={lambda_val}) …")

    raw_impacts = run_all_factors(dataset, lambda_val=lambda_val, lambda_per_factor=lambda_per_factor)

    poss = dataset["possession_totals_target"]  # {pid: {off, def}}

    # ── Step 1: compute margins ───────────────────────────────────────────────
    all_results: dict[int, dict] = {}
    for pid, impacts in raw_impacts.items():
        # All 8 components must be present
        required = [
            "off_efg_impact", "def_efg_impact",
            "off_tov_impact", "def_tov_impact",
            "off_orb_impact", "def_reb_impact",
            "off_ftr_impact", "def_ftr_impact",
        ]
        if any(k not in impacts for k in required):
            continue

        d = dict(impacts)
        d["efg_impact_margin"] = round(d["off_efg_impact"] + d["def_efg_impact"], 4)
        d["tov_impact_margin"] = round(d["off_tov_impact"] + d["def_tov_impact"], 4)
        d["reb_impact_margin"] = round(d["off_orb_impact"] + d["def_reb_impact"], 4)
        d["ftr_impact_margin"] = round(d["off_ftr_impact"] + d["def_ftr_impact"], 4)
        d["four_factor_impact_index"] = None  # filled in Step 3
        all_results[pid] = d

    # ── Step 2: identify qualified players (min possessions) ─────────────────
    qualified_pids = [
        pid for pid in all_results
        if poss.get(pid, {}).get("off", 0) >= MIN_POSS_FFI
        and poss.get(pid, {}).get("def", 0) >= MIN_POSS_FFI
    ]

    if verbose:
        logger.info(
            f"FFI pipeline: {len(all_results)} players with factor impacts, "
            f"{len(qualified_pids)} qualified (≥{MIN_POSS_FFI} poss)"
        )

    if len(qualified_pids) < 5:
        logger.warning("FFI pipeline: too few qualified players to standardize — FFII not computed")
        return all_results

    # ── Step 3: standardize margins across qualified players ──────────────────
    margins_efg = [all_results[p]["efg_impact_margin"] for p in qualified_pids]
    margins_tov = [all_results[p]["tov_impact_margin"] for p in qualified_pids]
    margins_reb = [all_results[p]["reb_impact_margin"] for p in qualified_pids]
    margins_ftr = [all_results[p]["ftr_impact_margin"] for p in qualified_pids]

    means = {
        "efg": statistics.mean(margins_efg),
        "tov": statistics.mean(margins_tov),
        "reb": statistics.mean(margins_reb),
        "ftr": statistics.mean(margins_ftr),
    }
    stds = {
        "efg": statistics.pstdev(margins_efg),  # population std (all qualified players)
        "tov": statistics.pstdev(margins_tov),
        "reb": statistics.pstdev(margins_reb),
        "ftr": statistics.pstdev(margins_ftr),
    }

    w = FOUR_FACTOR_WEIGHTS  # efg=0.45, tov=0.24, reb=0.22, ftr=0.09

    for pid in qualified_pids:
        d = all_results[pid]
        z_efg = _safe_z(d["efg_impact_margin"], means["efg"], stds["efg"])
        z_tov = _safe_z(d["tov_impact_margin"], means["tov"], stds["tov"])
        z_reb = _safe_z(d["reb_impact_margin"], means["reb"], stds["reb"])
        z_ftr = _safe_z(d["ftr_impact_margin"], means["ftr"], stds["ftr"])
        wz = (
            w["efg"] * z_efg +
            w["tov"] * z_tov +
            w["reb"] * z_reb +
            w["ftr"] * z_ftr
        )
        ffii = max(0.0, min(100.0, 50.0 + FOUR_FACTOR_SCALE * wz))
        d["four_factor_impact_index"] = round(ffii, 2)

    if verbose:
        ffii_count = sum(1 for d in all_results.values() if d["four_factor_impact_index"] is not None)
        logger.info(f"FFI pipeline: {ffii_count} players received four_factor_impact_index")

    return all_results
