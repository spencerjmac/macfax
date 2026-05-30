"""
mps/rederive_params.py

Re-derive all training parameters excluding the 2020 draft class
(COVID bubble anomaly, LOYO Δρ=+0.021 confirmed).

Tasks:
  1. Compute _HARDCODED_FEAT_STATS, FEATURE_WEIGHTS, FEATURE_WEIGHTS_GUARDS,
     FEATURE_WEIGHTS_BIGS from 11 training classes (2010-2019, 2021).
  2. Verify via 11-fold LOYO before touching scorer.py.

Run:
    backend/.venv/bin/python -m mps.rederive_params
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from mps.backtest_full import add_derived, compute_correlations, join_combine, load_combine
from mps.loyo_sensitivity import FEATURES_23, run_loyo_fold_feat
from mps.loyo_validation import _pos_group_csv, _spearman
from mps.scorer import (
    FEATURE_WEIGHTS,
    FEATURE_WEIGHTS_BIGS as OLD_BIGS,
    FEATURE_WEIGHTS_GUARDS as OLD_GUARDS,
)

DATASET_PATH   = Path(__file__).parent / "data" / "mps_dataset_raw.csv"
TARGET         = "vorp_yr2_5_avg"
TRAINING_YEARS = {2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021}
ALL_FEATURES   = list(FEATURE_WEIGHTS.keys())   # 23 features


# ── Weight derivation ─────────────────────────────────────────────────────────

def _derive_weights(df_with_vorp: pd.DataFrame, features: list[str]) -> dict[str, float]:
    """Derive normalized |Pearson r| weights. n<10 → floor 0.005."""
    corr_rows = compute_correlations(df_with_vorp, features)
    raw: dict[str, float] = {}
    for row in corr_rows:
        feat = row["feature"]
        r    = row.get("r")
        n    = row.get("n", 0) or 0
        if r is None or n < 10:
            raw[feat] = 0.005
        else:
            raw[feat] = max(abs(float(r)), 0.005)
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}


# ── Task 1: Compute new parameters ───────────────────────────────────────────

def task1_compute_params() -> dict:
    print("=" * 76)
    print("  Task 1: Compute New Training Parameters (11 classes, no 2020)")
    print("=" * 76)

    # A. Load and filter
    df_raw = pd.read_csv(DATASET_PATH)
    df = df_raw[df_raw["draft_year"].isin(TRAINING_YEARS)].copy()
    years_present = sorted(df["draft_year"].unique().tolist())
    print(f"\n  A. Loaded {len(df)} rows")
    print(f"  Years present: {years_present}")
    print(f"  2020 absent: {2020 not in years_present}")

    # B. Join combine + derived features
    combine = load_combine()
    df = join_combine(df, combine)
    df = add_derived(df)
    df["pos_group"] = df["position"].apply(_pos_group_csv)
    n_height = df["height_in"].notna().sum()
    print(f"\n  B. Rows with height_in: {n_height}/{len(df)}")

    df_vorp = df[df[TARGET].notna()].copy()
    print(f"  Rows with vorp: {len(df_vorp)} (all rows for this training set)")

    # C. _HARDCODED_FEAT_STATS
    print(f"\n  C. New _HARDCODED_FEAT_STATS (from all {len(df)} rows):")
    print(f"  _HARDCODED_FEAT_STATS: dict[str, tuple[float, float, float]] = {{")
    new_feat_stats: dict[str, tuple[float, float, float]] = {}
    for feat in ALL_FEATURES:
        if feat not in df.columns:
            print(f"    # WARNING: {feat} not in DataFrame")
            continue
        col = df[feat].dropna()
        mean   = float(col.mean())   if len(col) > 0 else 0.0
        std    = float(col.std(ddof=1)) if len(col) > 1 else 1.0
        median = float(col.median()) if len(col) > 0 else 0.0
        new_feat_stats[feat] = (round(mean, 4), round(max(std, 1e-8), 4), round(median, 4))
        print(f'    "{feat}":{" " * (22 - len(feat))}({round(mean, 4)}, {round(max(std,1e-8), 4)}, {round(median, 4)}),')
    print("  }")

    # D. Universal weights
    print(f"\n  D. New FEATURE_WEIGHTS (universal, n={len(df_vorp)}):")
    new_univ = _derive_weights(df_vorp, ALL_FEATURES)
    print("  FEATURE_WEIGHTS: dict[str, float] = {")
    for feat in ALL_FEATURES:
        print(f'    "{feat}":{" " * (22 - len(feat))}{round(new_univ[feat], 4)},')
    print("  }")

    # E. Guards weights
    guards_df = df_vorp[df_vorp["pos_group"] == "guard"]
    print(f"\n  E. New FEATURE_WEIGHTS_GUARDS (n={len(guards_df)}):")
    new_guards = _derive_weights(guards_df, ALL_FEATURES)
    print("  FEATURE_WEIGHTS_GUARDS: dict[str, float] = {")
    for feat in ALL_FEATURES:
        print(f'    "{feat}":{" " * (22 - len(feat))}{round(new_guards[feat], 4)},')
    print("  }")

    # F. Bigs weights
    bigs_df = df_vorp[df_vorp["pos_group"] == "big"]
    print(f"\n  F. New FEATURE_WEIGHTS_BIGS (n={len(bigs_df)}):")
    new_bigs = _derive_weights(bigs_df, ALL_FEATURES)
    print("  FEATURE_WEIGHTS_BIGS: dict[str, float] = {")
    for feat in ALL_FEATURES:
        print(f'    "{feat}":{" " * (22 - len(feat))}{round(new_bigs[feat], 4)},')
    print("  }")

    # G. Comparison table
    print(f"\n  G. Weight Comparison (OLD vs NEW, flagging |Δ| > 0.010):")
    print(f"  {'Feature':<22}  {'OldG':>6}  {'NewG':>6}  {'ΔG':>6}  "
          f"{'OldB':>6}  {'NewB':>6}  {'ΔB':>6}  Flags")
    print("  " + "-" * 74)
    for feat in ALL_FEATURES:
        og = OLD_GUARDS.get(feat, 0.0)
        ng = new_guards.get(feat, 0.0)
        ob = OLD_BIGS.get(feat, 0.0)
        nb = new_bigs.get(feat, 0.0)
        dg = ng - og
        db = nb - ob
        flags = ""
        if abs(dg) > 0.010: flags += f" [G:{dg:+.3f}]"
        if abs(db) > 0.010: flags += f" [B:{db:+.3f}]"
        flag_str = flags if flags else ""
        print(f"  {feat:<22}  {og:>6.4f}  {ng:>6.4f}  {dg:>+6.3f}  "
              f"{ob:>6.4f}  {nb:>6.4f}  {db:>+6.3f}  {flag_str}")

    # H. Validate sums
    print(f"\n  H. Weight sum validation:")
    sums = {
        "FEATURE_WEIGHTS":        sum(new_univ.values()),
        "FEATURE_WEIGHTS_GUARDS": sum(new_guards.values()),
        "FEATURE_WEIGHTS_BIGS":   sum(new_bigs.values()),
    }
    all_ok = True
    for name, s in sums.items():
        ok = abs(s - 1.0) < 1e-4
        all_ok = all_ok and ok
        print(f"    {name}: sum={s:.6f}  {'OK' if ok else 'FAIL'}")
    if all_ok:
        print(f"  All weight sums verified: 1.0000")

    return {
        "feat_stats":  new_feat_stats,
        "univ":        new_univ,
        "guards":      new_guards,
        "bigs":        new_bigs,
        "df_no2020":   df,
    }


# ── Task 2: LOYO verification ─────────────────────────────────────────────────

def task2_loyo_verify(df_no2020: pd.DataFrame) -> bool:
    print("\n" + "=" * 76)
    print("  Task 2: 11-fold LOYO Verification (no 2020 in any fold)")
    print("=" * 76)

    LOYO_YEARS_NO2020 = [y for y in range(2010, 2022) if y != 2020]

    fold_rhos: list[float] = []
    for year in LOYO_YEARS_NO2020:
        fold_df = run_loyo_fold_feat(year, df_no2020, FEATURES_23)
        if fold_df is None or fold_df.empty:
            print(f"  Fold {year}: skipped")
            continue
        rho, n = _spearman(fold_df["mps"], fold_df[TARGET])
        fold_rhos.append(rho)
        print(f"  Fold {year} | n={n:>2} | ρ={rho:+.3f}")

    mean_rho = float(np.mean(fold_rhos))
    std_rho  = float(np.std(fold_rhos, ddof=1))
    ci = 1.96 * std_rho / math.sqrt(len(fold_rhos))
    expected = 0.368
    delta = mean_rho - expected

    print(f"\n  11-fold LOYO mean ρ (no 2020): {mean_rho:.3f}")
    print(f"  95% CI: [{mean_rho - ci:.3f}, {mean_rho + ci:.3f}]")
    print(f"  Expected from sensitivity test: ~{expected:.3f}")
    print(f"  Δ from expected: {delta:+.3f}")

    in_range = 0.340 <= mean_rho <= 0.400
    gate = "PASS" if in_range else "FAIL"
    print(f"  Gate [0.340, 0.400]: {gate}")

    if not in_range:
        print(f"\n  STOP — LOYO ρ outside expected range. Do not modify scorer.py.")

    return in_range


# ── Paste-ready scorer.py update blocks ──────────────────────────────────────

def print_scorer_update_blocks(params: dict) -> None:
    """Print complete ready-to-paste replacement blocks for scorer.py."""
    print("\n" + "=" * 76)
    print("  Paste-ready scorer.py update blocks")
    print("=" * 76)

    comment = (
        "    # Re-derived 2026-05-28: 11 training classes (2010-2019, 2021)\n"
        "    # 2020 excluded — COVID bubble anomaly (LOYO Δρ=+0.021 confirmed)"
    )

    print(f"\n  --- _HARDCODED_FEAT_STATS ---")
    print(comment)
    print("    {")
    for feat, (mean, std, median) in params["feat_stats"].items():
        print(f'        "{feat}":{" " * (22 - len(feat))}({mean}, {std}, {median}),')
    print("    }")

    for dict_name, wdict in [
        ("FEATURE_WEIGHTS",        params["univ"]),
        ("FEATURE_WEIGHTS_GUARDS", params["guards"]),
        ("FEATURE_WEIGHTS_BIGS",   params["bigs"]),
    ]:
        print(f"\n  --- {dict_name} ---")
        print(comment)
        print("    {")
        for feat in ALL_FEATURES:
            w = round(wdict[feat], 4)
            print(f'        "{feat}":{" " * (22 - len(feat))}{w},')
        print("    }")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("MPS Parameter Re-derivation  |  Excluding 2020 COVID anomaly")
    print()

    params = task1_compute_params()
    gate_passed = task2_loyo_verify(params["df_no2020"])

    if gate_passed:
        print_scorer_update_blocks(params)
        print(f"\n  Task 2 PASSED. Proceed to update scorer.py with blocks above.")
    else:
        print(f"\n  Task 2 FAILED. scorer.py unchanged.")

    return params, gate_passed


if __name__ == "__main__":
    main()
