"""
mps/loyo_athletic_test.py

LOYO validation for athletic testing metrics from the NBA Draft Combine.

Tests whether vertical leap, lane agility, and 3/4-court sprint add
independent predictive signal beyond the 23-feature baseline (ρ=0.368).

Metrics that cleared 30% coverage threshold:
  max_vertical_in   (higher = better)
  lane_agility_sec  (lower = better — inverted to neg_lane_agility)
  sprint_sec        (lower = better — inverted to neg_sprint)

shuttle_run_sec excluded: 0% coverage in API response (field absent).

Decision gate: Δρ ≥ +0.005 → validates; print paste-ready additions.

Run:
    backend/.venv/bin/python -m mps.loyo_athletic_test
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from mps.backtest_full import add_derived, join_combine, load_combine
from mps.loyo_sensitivity import FEATURES_23, TARGET, run_loyo_fold_feat
from mps.loyo_validation import _pos_group_csv, _spearman, load_data

TRAINING_YEARS = {2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021}
LOYO_YEARS     = sorted(TRAINING_YEARS)
BASELINE_RHO   = 0.368
THRESHOLD      = BASELINE_RHO + 0.005

HIST_FILE = Path(__file__).parent / "data" / "combine_historical.json"

ATHLETIC_FEATS = ["max_vertical_in", "neg_lane_agility", "neg_sprint"]


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_raw_combine() -> dict[int, dict[str, dict]]:
    raw = json.loads(HIST_FILE.read_text())
    data = raw.get("data", raw)
    return {int(y): v for y, v in data.items()}


def load_training_df() -> pd.DataFrame:
    df = load_data()
    df = df[df["draft_year"].isin(TRAINING_YEARS)].copy()
    combine = load_combine()
    df = join_combine(df, combine)
    df = add_derived(df)
    df["pos_group"] = df["position"].apply(_pos_group_csv)
    df = df[df[TARGET].notna()].copy()

    # Manually join raw athletic metrics (not in join_combine)
    raw = _load_raw_combine()
    for feat in ["lane_agility_sec", "sprint_sec"]:
        df[feat] = None
    for feat in ["lane_agility_sec", "sprint_sec"]:
        for _, row in df.iterrows():
            y = int(row["draft_year"])
            pname = str(row["player_name"])
            val = raw.get(y, {}).get(pname, {}).get(feat)
            if val is not None:
                df.at[row.name, feat] = float(val)
        df[feat] = pd.to_numeric(df[feat], errors="coerce")

    # Invert time-based metrics (lower time = faster = better = positive signal)
    df["neg_lane_agility"] = -df["lane_agility_sec"]
    df["neg_sprint"]       = -df["sprint_sec"]

    return df


# ── Coverage report ───────────────────────────────────────────────────────────

def print_coverage(df: pd.DataFrame) -> None:
    n = len(df)
    print(f"\n  Training rows: {n}")
    print(f"  {'Feature':<22}  {'n_covered':>10}  {'pct':>6}")
    print("  " + "-" * 44)
    for feat in ["max_vertical_in", "lane_agility_sec", "sprint_sec",
                 "neg_lane_agility", "neg_sprint"]:
        nc = df[feat].notna().sum() if feat in df.columns else 0
        pct = nc / n * 100
        print(f"  {feat:<22}  {nc:>10}  {pct:>5.1f}%")


# ── LOYO runner ───────────────────────────────────────────────────────────────

def _run_loyo(df: pd.DataFrame, features: list[str]) -> dict:
    rhos, grhos, brhos = [], [], []
    per_fold = {}
    for year in LOYO_YEARS:
        fold = run_loyo_fold_feat(year, df, features)
        if fold is None:
            continue
        r, n = _spearman(fold["mps"], fold[TARGET])
        rhos.append(r)
        g = fold[fold["pos_group"] == "guard"]
        b = fold[fold["pos_group"] == "big"]
        rg, ng = _spearman(g["mps"], g[TARGET])
        rb, nb = _spearman(b["mps"], b[TARGET])
        if ng >= 3: grhos.append(rg)
        if nb >= 3: brhos.append(rb)
        per_fold[year] = {"rho": r, "n": n, "rho_g": rg, "rho_b": rb}
    return {
        "per_fold": per_fold,
        "mean": float(np.mean(rhos)) if rhos else float("nan"),
        "mg":   float(np.mean(grhos)) if grhos else float("nan"),
        "mb":   float(np.mean(brhos)) if brhos else float("nan"),
    }


# ── Pearson r per athletic feature ───────────────────────────────────────────

def _pearson_r(a: pd.Series, b: pd.Series) -> tuple[float, int]:
    valid = a.notna() & b.notna()
    a2, b2 = a[valid], b[valid]
    if len(a2) < 3:
        return float("nan"), 0
    r, _ = scipy_stats.pearsonr(a2, b2)
    return float(r), int(valid.sum())


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("LOYO Athletic Testing Validation")
    print(f"Gate: mean ρ ≥ {THRESHOLD:.3f} (baseline {BASELINE_RHO:.3f} + 0.005)")
    print()

    df = load_training_df()
    print_coverage(df)

    # Pearson r for each athletic feature vs vorp
    print(f"\n  Pearson r vs {TARGET} (full training set):")
    for feat in ATHLETIC_FEATS:
        if feat in df.columns:
            r, n = _pearson_r(df[feat], df[TARGET])
            print(f"    {feat:<22}: r={r:+.3f}  (n={n})")

    configs = {
        "Base (23f)":         FEATURES_23,
        "+ vertical":         FEATURES_23 + ["max_vertical_in"],
        "+ all athletic":     FEATURES_23 + ATHLETIC_FEATS,
    }

    print(f"\n  Running LOYO for {len(configs)} configs...")
    results = {}
    for name, feats in configs.items():
        print(f"    {name}...", flush=True)
        results[name] = _run_loyo(df, feats)

    # Per-fold table for best config
    base_res = results["Base (23f)"]
    best_name = max(
        (n for n in results if n != "Base (23f)"),
        key=lambda n: results[n]["mean"]
    )
    best_res = results[best_name]

    print(f"\n  Per-fold results — best config: {best_name}")
    print(f"  {'Year':>4}  {'n':>3}  {'ρ_base':>7}  {'ρ_best':>7}  {'Δ':>6}")
    print("  " + "-" * 40)
    for year in LOYO_YEARS:
        bp = base_res["per_fold"].get(year)
        if bp is None: continue
        bst = best_res["per_fold"].get(year, {})
        r_b = bp["rho"]
        r_s = bst.get("rho", float("nan"))
        d   = r_s - r_b if not math.isnan(r_s) else float("nan")
        d_s = f"{d:>+6.3f}" if not math.isnan(d) else "    —"
        print(f"  {year:>4}  {bp['n']:>3}  {r_b:>+7.3f}  {r_s:>+7.3f}  {d_s}")

    # Summary table
    print(f"\n  {'Config':<22}  {'Mean ρ':>7}  {'Δ':>7}  {'Guards ρ':>9}  {'Δg':>7}  {'Bigs ρ':>7}")
    print("  " + "-" * 72)
    base_mean = base_res["mean"]
    base_mg   = base_res["mg"]
    base_mb   = base_res["mb"]
    for name, res in results.items():
        d  = res["mean"] - base_mean if name != "Base (23f)" else 0.0
        dg = res["mg"]   - base_mg   if name != "Base (23f)" and not math.isnan(res["mg"]) else 0.0
        d_s  = "   base" if name == "Base (23f)" else f"{d:>+7.3f}"
        dg_s = "   base" if name == "Base (23f)" else f"{dg:>+7.3f}"
        mg_s = f"{res['mg']:>9.3f}" if not math.isnan(res["mg"]) else "      n/a"
        mb_s = f"{res['mb']:>7.3f}" if not math.isnan(res["mb"]) else "    n/a"
        print(f"  {name:<22}  {res['mean']:>+7.3f}  {d_s}  {mg_s}  {dg_s}  {mb_s}")

    # Decision
    best_d = best_res["mean"] - base_mean
    print(f"\n  Best config: {best_name}  |  Δρ = {best_d:+.3f}  |  Gate: {'PASS' if best_res['mean'] >= THRESHOLD else 'FAIL'}")

    if best_res["mean"] >= THRESHOLD:
        print(f"\n  → VALIDATES: Athletic testing adds signal (Δρ={best_d:+.3f} ≥ 0.005)")
        new_feats = [f for f in configs[best_name] if f not in FEATURES_23]
        print(f"  Features to add: {new_feats}")

        # Paste-ready _HARDCODED_FEAT_STATS additions
        train_df = df[df["draft_year"].isin(TRAINING_YEARS)].copy()
        print(f"\n  Paste-ready _HARDCODED_FEAT_STATS additions:")
        print("  {")
        for feat in new_feats:
            col = train_df[feat].dropna()
            if len(col) > 1:
                mean   = float(col.mean())
                std    = float(col.std(ddof=1))
                median = float(col.median())
                print(f'      "{feat}":{" " * (22 - len(feat))}({round(mean,4)}, {round(max(std,1e-8),4)}, {round(median,4)}),')
        print("  }")

        print(f"\n  Do NOT modify scorer.py yet — review first.")
    else:
        print(f"\n  → REJECTED: Δρ={best_d:+.3f} < 0.005 threshold")
        print(f"  Athletic testing metrics do not add independent predictive signal.")
        print(f"  combine_historical.json enriched with athletic data for future use.")
        print(f"\n  Signal strength (|r| vs VORP, for reference):")
        for feat in ATHLETIC_FEATS:
            if feat in df.columns:
                r, n = _pearson_r(df[feat], df[TARGET])
                print(f"    {feat:<22}: |r| = {abs(r):.3f}  (n={n})")


if __name__ == "__main__":
    main()
