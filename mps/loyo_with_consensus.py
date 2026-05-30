"""
mps/loyo_with_consensus.py

Phase 3: 11-fold LOYO comparison using scraped NBADraft.net consensus ranks.

Variants:
  Baseline:   23 features (mean ρ = 0.368 known)
  Scraped-S:  23 + consensus_tier_score (scraped pre-draft ranks)
  Draft-T4:   23 + scout_rank (T4 from actual draft_pick — reference/upper bound)
  Scraped-B:  23 + blended score (consensus where available, draft_pick T4 fallback)

Decision: Scraped-S mean ρ ≥ 0.378 → VALIDATED → derive empirical weight → Phase 4.

Run:
    backend/.venv/bin/python -m mps.loyo_with_consensus
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from mps.backtest_full import add_derived, join_combine, load_combine
from mps.loyo_sensitivity import (
    FEATURES_23,
    TARGET,
    run_loyo_fold_feat,
)
from mps.loyo_validation import (
    _blend_weights,
    _pos_group_csv,
    _spearman,
)

DATA_DIR        = Path(__file__).parent / "data"
CONSENSUS_CSV   = DATA_DIR / "mps_dataset_with_consensus.csv"

TRAINING_YEARS  = {2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021}
LOYO_YEARS      = sorted(TRAINING_YEARS)

BASELINE_RHO    = 0.368  # authoritative from rederive_params
THRESHOLD       = BASELINE_RHO + 0.010  # 0.378

FEATURES_S  = FEATURES_23 + ["consensus_tier_score"]
FEATURES_D  = FEATURES_23 + ["scout_rank"]
FEATURES_B  = FEATURES_23 + ["blended_consensus"]


# ── T4 transform (for draft_pick reference variant) ───────────────────────────

def _t4(pick) -> float:
    if pd.isna(pick) or float(pick) <= 0:
        return 0.050
    p = float(pick)
    if p <= 5:  return 0.900
    if p <= 14: return 0.700
    if p <= 30: return 0.500
    if p <= 60: return 0.250
    return 0.050


# ── Data loading ──────────────────────────────────────────────────────────────

def load_df() -> pd.DataFrame:
    df = pd.read_csv(CONSENSUS_CSV)
    df = df[df["draft_year"].isin(TRAINING_YEARS) & df[TARGET].notna()].copy()
    combine = load_combine()
    df = join_combine(df, combine)
    df = add_derived(df)
    df["pos_group"] = df["position"].apply(_pos_group_csv)

    # Draft-T4 reference feature
    df["scout_rank"] = df["draft_pick"].apply(_t4)

    # Blended: consensus where available (73%), draft_pick T4 as fallback
    df["blended_consensus"] = df.apply(
        lambda r: r["consensus_tier_score"]
        if pd.notna(r.get("consensus_tier_score")) and r.get("consensus_source") != "no_board"
        else r["scout_rank"],
        axis=1,
    )

    # Fill any remaining NaN in consensus_tier_score with 0.050 (neutral)
    df["consensus_tier_score"] = df["consensus_tier_score"].fillna(0.050)

    return df[df[TARGET].notna()].copy()


# ── Pearson r helper ──────────────────────────────────────────────────────────

def _pearson_r(a: pd.Series, b: pd.Series) -> tuple[float, int]:
    valid = a.notna() & b.notna()
    a2, b2 = a[valid], b[valid]
    if len(a2) < 3:
        return float("nan"), 0
    r, _ = scipy_stats.pearsonr(a2, b2)
    return float(r), int(valid.sum())


# ── LOYO runner ───────────────────────────────────────────────────────────────

def _run_loyo(df: pd.DataFrame, features: list[str]) -> dict:
    """Run 11-fold LOYO. Returns per-fold and aggregate stats."""
    fold_rhos: list[float] = []
    fold_rhos_g: list[float] = []
    fold_rhos_b: list[float] = []
    fold_pearson_r: list[float] = []  # for consensus feature specifically
    per_fold: dict[int, dict] = {}

    consensus_feat = next((f for f in features if f not in FEATURES_23), None)

    for year in LOYO_YEARS:
        fold_df = run_loyo_fold_feat(year, df, features)
        if fold_df is None:
            continue

        r, n = _spearman(fold_df["mps"], fold_df[TARGET])
        fold_rhos.append(r)

        g = fold_df[fold_df["pos_group"] == "guard"]
        b = fold_df[fold_df["pos_group"] == "big"]
        rg, ng = _spearman(g["mps"], g[TARGET])
        rb, nb = _spearman(b["mps"], b[TARGET])

        if ng >= 3:
            fold_rhos_g.append(rg)
        if nb >= 3:
            fold_rhos_b.append(rb)

        # Pearson r of consensus feature in training fold
        if consensus_feat:
            train_df = df[df["draft_year"] != year]
            train_vorp = train_df[train_df[TARGET].notna()]
            pr, pn = _pearson_r(train_vorp[consensus_feat], train_vorp[TARGET])
            if not math.isnan(pr):
                fold_pearson_r.append(pr)

        per_fold[year] = {"rho": r, "n": n, "rho_g": rg, "n_g": ng, "rho_b": rb}

    return {
        "per_fold":     per_fold,
        "mean":         float(np.mean(fold_rhos))    if fold_rhos   else float("nan"),
        "mg":           float(np.mean(fold_rhos_g))  if fold_rhos_g else float("nan"),
        "mb":           float(np.mean(fold_rhos_b))  if fold_rhos_b else float("nan"),
        "mean_r_feat":  float(np.mean(fold_pearson_r)) if fold_pearson_r else float("nan"),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Phase 3: LOYO Validation with Scraped Consensus Ranks")
    print()

    df = load_df()
    print(f"  Training rows: {len(df)}")
    n_with_consensus = (df["consensus_tier_score"] != 0.050).sum()
    print(f"  Rows with consensus signal: {n_with_consensus} ({n_with_consensus/len(df):.1%})")
    print()

    # Overall Pearson r stats
    r_all, _ = _pearson_r(df["consensus_tier_score"], df[TARGET])
    r_d, _   = _pearson_r(df["scout_rank"], df[TARGET])
    print(f"  Pearson r (consensus_tier_score vs VORP): {r_all:+.3f}")
    print(f"  Pearson r (draft_pick T4 vs VORP):        {r_d:+.3f}")
    print()

    # Run all variants
    print("  Running LOYO variants...")
    print("  (baseline, Scraped-S, Draft-T4, Blended)...")
    print()

    res_base = _run_loyo(df, FEATURES_23)
    res_s    = _run_loyo(df, FEATURES_S)
    res_d    = _run_loyo(df, FEATURES_D)
    res_b    = _run_loyo(df, FEATURES_B)

    variants = {
        "Baseline":  res_base,
        "Scraped-S": res_s,
        "Draft-T4":  res_d,
        "Blended-B": res_b,
    }

    # Per-fold table
    print(f"  {'Year':>4}  {'n':>3}  {'Base':>7}  {'Scrap-S':>8}  {'Draft-T4':>9}  {'Blend-B':>8}")
    print("  " + "-" * 54)

    for year in LOYO_YEARS:
        base_pf = res_base["per_fold"].get(year)
        if base_pf is None:
            continue
        n = base_pf["n"]
        r_b = f"{res_base['per_fold'][year]['rho']:>+7.3f}" if year in res_base["per_fold"] else "     n/a"
        r_s = f"{res_s['per_fold'][year]['rho']:>+8.3f}"    if year in res_s["per_fold"]    else "      n/a"
        r_d = f"{res_d['per_fold'][year]['rho']:>+9.3f}"    if year in res_d["per_fold"]    else "       n/a"
        r_bl= f"{res_b['per_fold'][year]['rho']:>+8.3f}"    if year in res_b["per_fold"]    else "      n/a"
        print(f"  {year:>4}  {n:>3}  {r_b}  {r_s}  {r_d}  {r_bl}")

    print("  " + "-" * 54)
    base_m = res_base["mean"]
    print(f"  {'MEAN':>4}  {'':>3}  {base_m:>+7.3f}  {res_s['mean']:>+8.3f}  {res_d['mean']:>+9.3f}  {res_b['mean']:>+8.3f}")
    print(f"  {'Δ':>4}  {'':>3}  {'base':>7}  {res_s['mean']-base_m:>+8.3f}  {res_d['mean']-base_m:>+9.3f}  {res_b['mean']-base_m:>+8.3f}")

    # Position-split summary
    print(f"\n  Position-split means:")
    print(f"  {'Variant':<12}  {'Mean ρ':>7}  {'Δ':>7}  {'Guards':>7}  {'Δg':>7}  {'Bigs':>7}  {'Δb':>7}  {'feat r':>7}")
    print("  " + "-" * 74)
    base_mg = res_base["mg"]
    base_mb = res_base["mb"]
    for name, res in variants.items():
        d = res["mean"] - base_m if name != "Baseline" else 0.0
        dg = res["mg"] - base_mg  if name != "Baseline" else 0.0
        db = res["mb"] - base_mb  if name != "Baseline" else 0.0
        d_s  = "  base" if name == "Baseline" else f"{d:>+7.3f}"
        dg_s = "  base" if name == "Baseline" else f"{dg:>+7.3f}"
        db_s = "  base" if name == "Baseline" else f"{db:>+7.3f}"
        fr_s = f"{res['mean_r_feat']:>7.3f}" if not math.isnan(res["mean_r_feat"]) else "    n/a"
        mg_s = f"{res['mg']:>7.3f}" if not math.isnan(res["mg"]) else "    n/a"
        mb_s = f"{res['mb']:>7.3f}" if not math.isnan(res["mb"]) else "    n/a"
        print(f"  {name:<12}  {res['mean']:>+7.3f}  {d_s}  {mg_s}  {dg_s}  {mb_s}  {db_s}  {fr_s}")

    # Decision
    print(f"\n  {'=' * 60}")
    s_rho = res_s["mean"]
    d_rho = res_d["mean"]
    mean_r_scraped = res_s["mean_r_feat"]

    print(f"\n  Mean |Pearson r| of consensus_tier_score across folds: {mean_r_scraped:.3f}")
    print(f"  Mean |Pearson r| of draft_pick T4 reference:           {res_d['mean_r_feat']:.3f}")

    if math.isnan(s_rho):
        print("\n  STOP: Scraped-S LOYO produced NaN. Check data pipeline.")
        return

    print(f"\n  Decision (threshold = {THRESHOLD:.3f}):")
    if s_rho >= THRESHOLD:
        print(f"  → VALIDATED  (Scraped-S ρ {s_rho:.3f} ≥ {THRESHOLD:.3f})")
        print(f"  Scout consensus from NBADraft.net has real predictive value.")

        # Derive empirical weight
        empirical_weight = min(abs(mean_r_scraped) * 0.12, 0.12)
        empirical_weight = round(empirical_weight, 4)
        print(f"\n  Empirical weight derivation:")
        print(f"    mean |r| across folds = {mean_r_scraped:.4f}")
        print(f"    empirical_weight = min({mean_r_scraped:.4f} × 0.12, 0.12) = {empirical_weight:.4f}")
        print(f"    Current weight in scorer.py: 0.08 (provisional)")
        print(f"    → {'INCREASE' if empirical_weight > 0.08 else 'DECREASE' if empirical_weight < 0.08 else 'KEEP'} weight to {empirical_weight}")
        print(f"\n  → Proceed to Phase 4: update weight={empirical_weight} in compute_scout_tier_adjustment()")

        return empirical_weight

    else:
        delta = s_rho - BASELINE_RHO
        d_delta = d_rho - BASELINE_RHO
        print(f"  → BELOW THRESHOLD (Scraped-S Δρ = {delta:+.3f} < 0.010)")
        print(f"  Scraped pre-draft consensus adds less signal than draft_pick proxy (Δρ={d_delta:+.3f})")
        print(f"  Draft-T4 still valid (from debiased_scout_test.py) — keep current weight=0.08")
        print(f"  Do NOT proceed to Phase 4.")
        print(f"\n  Likely cause: scraped data covers 9/11 years (2014/2019 missing = {46+52} rows")
        print(f"  neutral), diluting the scraped signal vs draft_pick which has 100% coverage.")


if __name__ == "__main__":
    main()
