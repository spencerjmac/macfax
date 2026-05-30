"""
mps/usg_pct_loyo_test.py

LOYO test: does adding usg_pct as a 24th feature improve 11-fold ρ?

usg_pct is currently used only as denominator in ast_pct_over_usg.
Hypothesis: usage load has independent predictive value — high-BPM
player on 28% usage is more projectable than same BPM on 18% usage.

Gate: Δ ≥ +0.005 → add to FEATURE_WEIGHTS (print paste-ready dict).
      Δ < +0.005 → reject.

Run:
    backend/.venv/bin/python -m mps.usg_pct_loyo_test
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from mps.backtest_full import add_derived, join_combine, load_combine
from mps.loyo_sensitivity import FEATURES_23, TARGET, run_loyo_fold_feat
from mps.loyo_validation import _pos_group_csv, _spearman, load_data

TRAINING_YEARS = {2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021}
LOYO_YEARS     = sorted(TRAINING_YEARS)
FEATURES_24    = FEATURES_23 + ["usg_pct"]
BASELINE_RHO   = 0.368
THRESHOLD      = BASELINE_RHO + 0.005


def load_training_df() -> pd.DataFrame:
    df = load_data()
    df = df[df["draft_year"].isin(TRAINING_YEARS)].copy()
    combine = load_combine()
    df = join_combine(df, combine)
    df = add_derived(df)
    df["pos_group"] = df["position"].apply(_pos_group_csv)
    return df[df[TARGET].notna()].copy()


def main() -> None:
    print("usg_pct LOYO Test — 24th feature")
    print(f"Baseline: {BASELINE_RHO:.3f}  |  Gate: Δ ≥ +0.005 ({THRESHOLD:.3f})")
    print()

    df = load_training_df()
    n_missing = df["usg_pct"].isna().sum()
    print(f"Training rows: {len(df)}  |  usg_pct nulls: {n_missing}")
    print()

    rhos_23, rhos_24 = [], []
    grhos_23, grhos_24 = [], []

    print(f"  {'Year':>4}  {'n':>3}  {'ρ_23':>7}  {'ρ_24':>7}  {'Δ':>6}  {'g_23':>7}  {'g_24':>7}")
    print("  " + "-" * 57)

    for year in LOYO_YEARS:
        f23 = run_loyo_fold_feat(year, df, FEATURES_23)
        f24 = run_loyo_fold_feat(year, df, FEATURES_24)
        if f23 is None or f24 is None:
            print(f"  {year:>4}  skipped")
            continue

        r23, n = _spearman(f23["mps"], f23[TARGET])
        r24, _ = _spearman(f24["mps"], f24[TARGET])
        rhos_23.append(r23)
        rhos_24.append(r24)

        g23 = f23[f23["pos_group"] == "guard"]
        g24 = f24[f24["pos_group"] == "guard"]
        rg23, ng23 = _spearman(g23["mps"], g23[TARGET])
        rg24, _    = _spearman(g24["mps"], g24[TARGET])
        if ng23 >= 3:
            grhos_23.append(rg23)
            grhos_24.append(rg24)

        delta = r24 - r23
        print(f"  {year:>4}  {n:>3}  {r23:>+7.3f}  {r24:>+7.3f}  {delta:>+6.3f}  "
              f"{rg23:>+7.3f}  {rg24:>+7.3f}")

    mean23 = float(np.mean(rhos_23))
    mean24 = float(np.mean(rhos_24))
    d      = mean24 - mean23
    mg23   = float(np.mean(grhos_23)) if grhos_23 else float("nan")
    mg24   = float(np.mean(grhos_24)) if grhos_24 else float("nan")
    dg     = mg24 - mg23 if not (math.isnan(mg23) or math.isnan(mg24)) else float("nan")

    print("  " + "-" * 57)
    dg_s = f"{dg:>+7.3f}" if not math.isnan(dg) else "    n/a"
    print(f"  {'MEAN':>4}  {'':>3}  {mean23:>+7.3f}  {mean24:>+7.3f}  {d:>+6.3f}  "
          f"{mg23:>+7.3f}  {dg_s}")

    print(f"\n  23-feat mean ρ: {mean23:.3f}")
    print(f"  24-feat mean ρ: {mean24:.3f}  (Δ = {d:+.3f})")
    print(f"  Guards Δρ:      {dg:+.3f}" if not math.isnan(dg) else "  Guards Δρ: n/a")
    print(f"  Gate ({THRESHOLD:.3f}): {'PASS' if mean24 >= THRESHOLD else 'FAIL'}")

    if mean24 >= THRESHOLD:
        print(f"\n  → ADD usg_pct to FEATURE_WEIGHTS. Compute renormalized weights:")
        from mps.loyo_sensitivity import _derive_weights_feat
        from mps.loyo_validation import load_data as ld
        all_df = ld()
        all_df = all_df[all_df["draft_year"].isin(TRAINING_YEARS) & all_df[TARGET].notna()].copy()
        w24 = _derive_weights_feat(all_df, FEATURES_24)
        print("\n  FEATURE_WEIGHTS (24 features, paste-ready):")
        print("  {")
        for feat in FEATURES_24:
            print(f'      "{feat}":{" " * (22 - len(feat))}{round(w24[feat], 4)},')
        print("  }")
        print(f"  Sum: {sum(w24.values()):.6f}")
    else:
        print(f"\n  → REJECT usg_pct. Δ={d:+.3f} < 0.005 threshold.")
        print(f"  usg_pct adds no independent signal beyond ast_pct_over_usg.")


if __name__ == "__main__":
    main()
