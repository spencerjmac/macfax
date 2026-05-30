"""
mps/senior_penalty_test.py

LOYO validation for the senior plateau penalty (-4.0 for draft_age ≥ 23.5).
Tests whether the penalty improves 11-fold LOYO ρ vs baseline 0.368.

Gate: mean ρ ≥ 0.378 (+0.010) → integrate into scorer.py.

Run:
    backend/.venv/bin/python -m mps.senior_penalty_test
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from mps.backtest_full import add_derived, join_combine, load_combine
from mps.loyo_sensitivity import FEATURES_23, TARGET, run_loyo_fold_feat
from mps.loyo_validation import _pos_group_csv, _spearman, load_data
from mps.scorer import compute_senior_plateau_penalty

TRAINING_YEARS = {2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021}
LOYO_YEARS     = sorted(TRAINING_YEARS)
BASELINE_RHO   = 0.368
THRESHOLD      = BASELINE_RHO + 0.010


def load_training_df() -> pd.DataFrame:
    df = load_data()
    df = df[df["draft_year"].isin(TRAINING_YEARS)].copy()
    combine = load_combine()
    df = join_combine(df, combine)
    df = add_derived(df)
    df["pos_group"] = df["position"].apply(_pos_group_csv)
    return df[df[TARGET].notna()].copy()


def main() -> None:
    print("Senior Plateau Penalty LOYO Test")
    print(f"Penalty: -4.0 for draft_age ≥ 23.5")
    print(f"Gate: mean ρ ≥ {THRESHOLD:.3f} (baseline {BASELINE_RHO:.3f} + 0.010)")
    print()

    df = load_training_df()

    # Build a draft_age lookup per (player_name, draft_year) for merging
    age_lookup = df.set_index(["player_name", "draft_year"])["draft_age"].to_dict()

    print(f"  {'Year':>4}  {'n':>3}  {'ρ_base':>7}  {'ρ_senior':>9}  {'Δ':>6}  {'n_aff':>6}  {'g_base':>7}  {'g_sen':>7}")
    print("  " + "-" * 66)

    rhos_base, rhos_senior = [], []
    grhos_base, grhos_senior = [], []

    for year in LOYO_YEARS:
        fold_df = run_loyo_fold_feat(year, df, FEATURES_23)
        if fold_df is None:
            print(f"  {year:>4}  skipped")
            continue

        # Merge draft_age back in
        fold_df = fold_df.copy()
        fold_df["draft_age"] = fold_df.apply(
            lambda r: age_lookup.get((r["player_name"], r["draft_year"])),
            axis=1,
        )
        fold_df["senior_pen"] = fold_df["draft_age"].apply(
            lambda a: compute_senior_plateau_penalty(float(a)) if pd.notna(a) else 0.0
        )
        fold_df["mps_senior"] = (fold_df["mps"] + fold_df["senior_pen"]).clip(0, 100)

        n_affected = (fold_df["senior_pen"] < 0).sum()

        r_base, n   = _spearman(fold_df["mps"],        fold_df[TARGET])
        r_sen, _    = _spearman(fold_df["mps_senior"], fold_df[TARGET])
        rhos_base.append(r_base)
        rhos_senior.append(r_sen)

        g = fold_df[fold_df["pos_group"] == "guard"]
        b = fold_df[fold_df["pos_group"] == "big"]
        rg_b, ng = _spearman(g["mps"],        g[TARGET])
        rg_s, _  = _spearman(g["mps_senior"], g[TARGET])
        if ng >= 3:
            grhos_base.append(rg_b)
            grhos_senior.append(rg_s)

        delta = r_sen - r_base
        print(f"  {year:>4}  {n:>3}  {r_base:>+7.3f}  {r_sen:>+9.3f}  {delta:>+6.3f}  {n_affected:>6}  "
              f"{rg_b:>+7.3f}  {rg_s:>+7.3f}")

    mean_base   = float(np.mean(rhos_base))
    mean_senior = float(np.mean(rhos_senior))
    delta_mean  = mean_senior - mean_base
    mg_base     = float(np.mean(grhos_base))   if grhos_base   else float("nan")
    mg_senior   = float(np.mean(grhos_senior)) if grhos_senior else float("nan")
    dg          = mg_senior - mg_base if not (math.isnan(mg_base) or math.isnan(mg_senior)) else float("nan")

    print("  " + "-" * 66)
    dg_s = f"{dg:>+7.3f}" if not math.isnan(dg) else "    n/a"
    print(f"  {'MEAN':>4}  {'':>3}  {mean_base:>+7.3f}  {mean_senior:>+9.3f}  {delta_mean:>+6.3f}  "
          f"{'':>6}  {mg_base:>+7.3f}  {mg_senior:>+7.3f}")

    print(f"\n  Baseline mean ρ:       {mean_base:.3f}")
    print(f"  With senior penalty:   {mean_senior:.3f}  (Δ = {delta_mean:+.3f})")
    print(f"  Guards Δρ:             {dg:+.3f}" if not math.isnan(dg) else "  Guards Δρ: n/a")
    print(f"  Threshold:             {THRESHOLD:.3f}")

    passed = mean_senior >= THRESHOLD
    print(f"\n  Gate: {'PASS' if passed else 'FAIL'}")

    if passed:
        print(f"\n  → INTEGRATE: Senior plateau penalty validated (Δρ={delta_mean:+.3f} ≥ 0.010).")
        print(f"  Add to scorer.py mps_final calculation.")
    else:
        print(f"\n  → REJECT: Δρ={delta_mean:+.3f} does not clear 0.010 threshold.")
        print(f"  Senior plateau penalty does not clear LOYO threshold.")
        print(f"  Lendeborg at #4 is a validated model conviction.")
        print(f"  Remove compute_senior_plateau_penalty() from scorer.py.")


if __name__ == "__main__":
    main()
