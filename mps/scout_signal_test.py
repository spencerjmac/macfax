"""
mps/scout_signal_test.py

Validation test: does scout consensus add independent predictive signal
beyond college stats?

Proxy: draft_pick → scout_rank = 1/draft_pick (undrafted = 0.0).
Upper-bound note: actual draft pick encodes both pre-draft scout consensus
AND post-draft opportunity (top picks get more minutes → higher VORP
mechanically). Measured improvement is an upper bound on what pre-draft
mock rank would provide.

Run:
    backend/.venv/bin/python -m mps.scout_signal_test
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
    _compute_fold_stats,
    _derive_weights_feat,
    _score_player_feat,
    _zscore_to_0_100,
)
from mps.loyo_validation import (
    MIN_FOLD_N,
    _blend_weights,
    _pos_group_csv,
    _spearman,
)

DATASET_PATH   = Path(__file__).parent / "data" / "mps_dataset_raw.csv"
TRAINING_YEARS = {2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021}
LOYO_YEARS     = sorted(TRAINING_YEARS)
FEATURES_24    = FEATURES_23 + ["scout_rank"]

BASELINE_MEAN_RHO   = 0.368
BASELINE_GUARDS_RHO = 0.256  # 12-fold; 11-fold recomputed fresh below


# ── Data loading ──────────────────────────────────────────────────────────────

def load_training_df() -> pd.DataFrame:
    df_raw = pd.read_csv(DATASET_PATH)
    df = df_raw[df_raw["draft_year"].isin(TRAINING_YEARS)].copy()
    combine = load_combine()
    df = join_combine(df, combine)
    df = add_derived(df)
    df["pos_group"] = df["position"].apply(_pos_group_csv)

    # Compute scout_rank from actual draft_pick (all players in training set
    # are drafted — vorp_yr2_5_avg is only available for NBA players).
    def _scout_rank(pick):
        if pd.isna(pick) or float(pick) <= 0:
            return 0.0
        return 1.0 / float(pick)

    df["scout_rank"] = df["draft_pick"].apply(_scout_rank)
    return df[df[TARGET].notna()].copy()


# ── Pearson r helper ──────────────────────────────────────────────────────────

def _pearson_r(a: pd.Series, b: pd.Series) -> tuple[float, int]:
    valid = a.notna() & b.notna()
    a2, b2 = a[valid], b[valid]
    if len(a2) < 3:
        return float("nan"), 0
    r, _ = scipy_stats.pearsonr(a2, b2)
    return float(r), int(valid.sum())


# ── Single fold engine (24 features, position-split) ─────────────────────────

def _run_fold(holdout_year: int, full_df: pd.DataFrame, features: list[str]) -> pd.DataFrame | None:
    train_df = full_df[full_df["draft_year"] != holdout_year].copy()
    hold_df  = full_df[full_df["draft_year"] == holdout_year].copy()

    if len(hold_df) < MIN_FOLD_N:
        return None

    fold_stats = _compute_fold_stats(train_df, features)

    train_vorp = train_df[train_df[TARGET].notna()].copy()
    w_all    = _derive_weights_feat(train_vorp, features)
    t_guards = train_vorp[train_vorp["pos_group"] == "guard"]
    t_bigs   = train_vorp[train_vorp["pos_group"] == "big"]
    w_guards = _derive_weights_feat(t_guards, features) if len(t_guards) >= 20 else w_all
    w_bigs   = _derive_weights_feat(t_bigs,   features) if len(t_bigs)   >= 20 else w_all
    w_wings  = _blend_weights(w_guards, w_bigs)

    rows = []
    for _, row in hold_df.iterrows():
        pg = str(row.get("pos_group", "wing"))
        weights = w_guards if pg == "guard" else (w_bigs if pg == "big" else w_wings)
        mps = _score_player_feat(row, weights, fold_stats)
        if mps is None:
            continue
        rows.append({
            "draft_year": holdout_year,
            "pos_group":  pg,
            TARGET:       row.get(TARGET),
            "mps":        mps,
        })

    return pd.DataFrame(rows) if rows else None


# ── Task 1: Coverage and Pearson r ───────────────────────────────────────────

def task1_coverage(df: pd.DataFrame) -> float:
    print("=" * 80)
    print("  Task 1: draft_pick Coverage and scout_rank Signal Strength")
    print("=" * 80)

    n_total    = len(df)
    n_non_null = df["draft_pick"].notna().sum()
    n_null     = n_total - n_non_null

    print(f"\n  Rows (11 training classes, vorp not null): {n_total}")
    print(f"  draft_pick not null: {n_non_null}")
    print(f"  draft_pick null (scout_rank=0.0): {n_null}")

    picks = df["draft_pick"].dropna()
    bins = {
        "Top 5 (1-5)":     ((picks >= 1) & (picks <= 5)).sum(),
        "Lottery (6-14)":  ((picks >= 6) & (picks <= 14)).sum(),
        "Late 1st (15-30)":((picks >= 15) & (picks <= 30)).sum(),
        "2nd Rd (31-60)":  ((picks >= 31) & (picks <= 60)).sum(),
        "60+":             (picks > 60).sum(),
    }
    print("\n  Draft pick distribution:")
    for label, cnt in bins.items():
        print(f"    {label:<20}: {cnt}")

    r_all, n_all = _pearson_r(df["scout_rank"], df[TARGET])
    guards_df    = df[df["pos_group"] == "guard"]
    bigs_df      = df[df["pos_group"] == "big"]
    r_g, n_g     = _pearson_r(guards_df["scout_rank"], guards_df[TARGET])
    r_b, n_b     = _pearson_r(bigs_df["scout_rank"],   bigs_df[TARGET])

    print(f"\n  Pearson r (scout_rank vs {TARGET}):")
    print(f"    Overall (n={n_all}): r = {r_all:+.3f}")
    print(f"    Guards  (n={n_g}): r = {r_g:+.3f}")
    print(f"    Bigs    (n={n_b}): r = {r_b:+.3f}")

    if abs(r_all) < 0.15:
        print(f"\n  WARNING: |r| = {abs(r_all):.3f} < 0.15 — scout_rank is weak signal.")
        print(f"  Scraping ESPN mocks is unlikely to meaningfully improve the model.")
    else:
        print(f"\n  scout_rank has reasonable signal (|r| ≥ 0.15). Proceeding with LOYO.")

    return r_all


# ── Task 2: LOYO comparison 23 vs 24 features ────────────────────────────────

def task2_loyo(df: pd.DataFrame) -> dict:
    print("\n" + "=" * 80)
    print("  Task 2: LOYO Comparison — 23 vs 24 Features (+ scout_rank)")
    print("  NOTE: Measured Δρ is an UPPER BOUND — draft_pick encodes post-draft")
    print("  opportunity (top picks get more minutes → higher VORP).")
    print("=" * 80)

    hdr = (f"\n  {'Year':>4}  {'n':>3}  {'ρ_23':>6}  {'ρ_24':>6}  {'Δ':>6}  "
           f"{'g_23':>6}  {'g_24':>6}  {'Δg':>6}  {'ng':>4}")
    print(hdr)
    print("  " + "-" * 70)

    rhos_23, rhos_24 = [], []
    grhos_23, grhos_24 = [], []
    brhos_23, brhos_24 = [], []

    for year in LOYO_YEARS:
        fold23 = _run_fold(year, df, FEATURES_23)
        fold24 = _run_fold(year, df, FEATURES_24)

        if fold23 is None or fold24 is None:
            print(f"  {year:>4}  skipped")
            continue

        r23, n23 = _spearman(fold23["mps"], fold23[TARGET])
        r24, _   = _spearman(fold24["mps"], fold24[TARGET])
        rhos_23.append(r23)
        rhos_24.append(r24)

        g23 = fold23[fold23["pos_group"] == "guard"]
        g24 = fold24[fold24["pos_group"] == "guard"]
        rg23, ng23 = _spearman(g23["mps"], g23[TARGET])
        rg24, _    = _spearman(g24["mps"], g24[TARGET])

        b23 = fold23[fold23["pos_group"] == "big"]
        b24 = fold24[fold24["pos_group"] == "big"]
        rb23, nb23 = _spearman(b23["mps"], b23[TARGET])
        rb24, _    = _spearman(b24["mps"], b24[TARGET])

        if ng23 >= 3:
            grhos_23.append(rg23)
            grhos_24.append(rg24)
            gstr23 = f"{rg23:+.3f}"
            gstr24 = f"{rg24:+.3f}"
            dgstr  = f"{rg24 - rg23:+.3f}"
        else:
            gstr23 = "  n<3"
            gstr24 = "  n<3"
            dgstr  = "    —"

        if nb23 >= 3:
            brhos_23.append(rb23)
            brhos_24.append(rb24)

        delta = r24 - r23
        print(f"  {year:>4}  {n23:>3}  {r23:>+6.3f}  {r24:>+6.3f}  {delta:>+6.3f}  "
              f"{gstr23:>6}  {gstr24:>6}  {dgstr:>6}  {ng23:>4}")

    mean23 = float(np.mean(rhos_23))
    mean24 = float(np.mean(rhos_24))
    d_mean = mean24 - mean23
    mg23   = float(np.mean(grhos_23)) if grhos_23 else float("nan")
    mg24   = float(np.mean(grhos_24)) if grhos_24 else float("nan")
    d_mg   = mg24 - mg23 if not (math.isnan(mg23) or math.isnan(mg24)) else float("nan")
    mb23   = float(np.mean(brhos_23)) if brhos_23 else float("nan")
    mb24   = float(np.mean(brhos_24)) if brhos_24 else float("nan")
    d_mb   = mb24 - mb23 if not (math.isnan(mb23) or math.isnan(mb24)) else float("nan")

    print("  " + "-" * 70)
    dg_str = f"{d_mg:>+6.3f}" if not math.isnan(d_mg) else "    —"
    mg23_s = f"{mg23:>+6.3f}" if not math.isnan(mg23) else "  n/a"
    mg24_s = f"{mg24:>+6.3f}" if not math.isnan(mg24) else "  n/a"
    print(f"  {'MEAN':>4}  {'':>3}  {mean23:>+6.3f}  {mean24:>+6.3f}  {d_mean:>+6.3f}  "
          f"{mg23_s:>6}  {mg24_s:>6}  {dg_str:>6}")

    print(f"\n  Position-split means ({len(grhos_23)}-fold guards, {len(rhos_23)}-fold overall):")
    print(f"    Guards ρ: 23-feat = {mg23:.3f}  |  24-feat = {mg24:.3f}  |  Δ = {d_mg:+.3f}")
    print(f"    Bigs ρ:   23-feat = {mb23:.3f}  |  24-feat = {mb24:.3f}  |  Δ = {d_mb:+.3f}")

    return {
        "mean23": mean23, "mean24": mean24, "d_mean": d_mean,
        "mg23": mg23, "mg24": mg24, "d_mg": d_mg,
        "mb23": mb23, "mb24": mb24, "d_mb": d_mb,
    }


# ── Task 3: Decision ──────────────────────────────────────────────────────────

def task3_decision(results: dict) -> str:
    print("\n" + "=" * 80)
    print("  Task 3: Decision and Recommendation")
    print("=" * 80)

    d_mean = results["d_mean"]
    d_mg   = results["d_mg"]
    mean24 = results["mean24"]
    mg24   = results["mg24"]
    thresh = BASELINE_MEAN_RHO + 0.010

    if mean24 >= thresh and not math.isnan(d_mg) and d_mg >= 0.015:
        verdict = "STRONG"
        print(f"\n  → STRONG SIGNAL (mean ρ Δ={d_mean:+.3f} ≥ 0.010, guards Δ={d_mg:+.3f} ≥ 0.015)")
        print(f"  Scout consensus adds meaningful independent value.")
        print(f"  Recommend: build historical ESPN/consensus mock draft scraper")
        print(f"    for 2010-2019, 2021 training classes.")
        print(f"  For 2026 board: use tankathon_rank as immediate proxy until")
        print(f"    historical mocks are scraped.")

    elif mean24 >= thresh:
        verdict = "WEAK"
        print(f"\n  → WEAK SIGNAL (mean ρ Δ={d_mean:+.3f} ≥ 0.010, but guards Δ={d_mg:+.3f} < 0.015)")
        print(f"  Scout consensus improves overall ρ but doesn't fix the guards problem.")
        print(f"  The improvement likely reflects opportunity bias (top picks = more minutes)")
        print(f"  rather than genuine pre-draft scout signal.")
        print(f"  Recommend: cautious. Consider tankathon_rank as minor feature but")
        print(f"    do NOT invest in historical scraping.")

    elif mean24 > BASELINE_MEAN_RHO:
        verdict = "MARGINAL"
        print(f"\n  → MARGINAL (mean ρ Δ={d_mean:+.3f} < 0.010 threshold)")
        print(f"  Scout consensus adds some signal but below threshold.")
        print(f"  Recommend: skip historical scraping. Close Step 3.")
        print(f"  Guards ρ problem is structural — not fixable with available features.")
        print(f"  Document as known limitation.")

    else:
        verdict = "NEGATIVE"
        print(f"\n  → NEGATIVE (24-feat mean ρ {mean24:.3f} < 23-feat baseline {results['mean23']:.3f})")
        print(f"  Draft pick hurts the model — opportunity bias masking real signal or adding noise.")
        print(f"  Recommend: do NOT add any scout consensus feature. Close Step 3.")

    return verdict


# ── Task 4: Tankathon rank historical availability ────────────────────────────

def task4_tankathon(df: pd.DataFrame) -> None:
    print("\n" + "=" * 80)
    print("  Task 4: Tankathon Rank Historical Availability")
    print("=" * 80)

    if "tankathon_rank" not in df.columns:
        print("\n  tankathon_rank is 2026-only — historical data not available.")
        print("  Cannot test as proxy without scraping.")
        return

    n_hist = df["tankathon_rank"].notna().sum()
    if n_hist == 0:
        print(f"\n  tankathon_rank column exists but has 0 non-null values in training set.")
        print(f"  tankathon_rank is 2026-only — historical data not available.")
        print(f"  Cannot test as proxy without scraping.")
        return

    print(f"\n  tankathon_rank has {n_hist}/{len(df)} non-null values in training set.")
    print(f"  Running LOYO with tankathon_rank as scout proxy...")

    df2 = df.copy()
    df2["scout_rank"] = df2["tankathon_rank"].apply(
        lambda v: 1.0 / float(v) if pd.notna(v) and float(v) > 0 else 0.0
    )
    feats_tank = FEATURES_23 + ["scout_rank"]

    rhos_t = []
    grhos_t = []
    for year in LOYO_YEARS:
        fold = _run_fold(year, df2, feats_tank)
        if fold is None:
            continue
        r, _ = _spearman(fold["mps"], fold[TARGET])
        rhos_t.append(r)
        g = fold[fold["pos_group"] == "guard"]
        rg, ng = _spearman(g["mps"], g[TARGET])
        if ng >= 3:
            grhos_t.append(rg)

    mt = float(np.mean(rhos_t)) if rhos_t else float("nan")
    mgt = float(np.mean(grhos_t)) if grhos_t else float("nan")
    print(f"\n  Tankathon proxy LOYO ({len(rhos_t)}-fold):")
    print(f"    Mean ρ:   {mt:.3f}  (vs draft_pick proxy baseline from Task 2)")
    print(f"    Guards ρ: {mgt:.3f}  (avoids opportunity bias — pre-draft consensus only)")


# ── Task 5: Summary box ───────────────────────────────────────────────────────

def task5_summary(r_all: float, r_guards: float, results: dict, verdict: str) -> None:
    d_mean = results["d_mean"]
    mean24 = results["mean24"]
    mg24   = results["mg24"]
    d_mg   = results["d_mg"]

    dg_s = f"{d_mg:+.3f}" if not math.isnan(d_mg) else "  n/a"
    mg24_s = f"{mg24:.3f}" if not math.isnan(mg24) else "n/a"

    if verdict == "STRONG":
        next_step = "Scrape historical ESPN/consensus mocks for 2010-2019, 2021"
    elif verdict == "WEAK":
        next_step = "Use Tankathon rank as minor feature — skip historical scraping"
    elif verdict == "MARGINAL":
        next_step = "Close Step 3 — guards ρ gap is structural, known limitation"
    else:
        next_step = "Do not add scout consensus feature — Close Step 3"

    w = 68
    def row(left, right=""):
        if right:
            content = f"  {left:<38}{right}"
        else:
            content = f"  {left}"
        pad = w - 2 - len(content)
        return "│" + content + " " * max(pad, 0) + "│"

    print("\n" + "┌" + "─" * w + "┐")
    print(row("SCOUT SIGNAL VALIDATION RESULTS"))
    print(row(""))
    print(row("Proxy: draft_pick → scout_rank = 1/pick"))
    print(row("Upper bound: encodes post-draft opportunity bias"))
    print(row(""))
    print(row(f"scout_rank Pearson r vs VORP (overall):", f"r = {r_all:+.3f}"))
    print(row(f"scout_rank Pearson r vs VORP (guards):", f"r = {r_guards:+.3f}"))
    print(row(""))
    print(row("LOYO results (11-fold, 2020 excluded):"))
    print(row(f"  23-feature mean ρ (baseline):", f"{results['mean23']:.3f}"))
    print(row(f"  24-feature mean ρ (+ scout):", f"{mean24:.3f}"))
    print(row(f"  Δ overall:", f"{d_mean:+.3f}"))
    print(row(f"  Guards ρ baseline:", f"{results['mg23']:.3f}"))
    print(row(f"  Guards ρ with scout:", mg24_s))
    print(row(f"  Δ guards:", dg_s))
    print(row(""))
    print(row(f"Verdict: {verdict}"))
    print(row(""))
    print(row("Recommended next step:"))
    print(row(f"  {next_step}"))
    print("└" + "─" * w + "┘")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Scout Signal Validation — draft_pick as consensus proxy")
    print()

    df = load_training_df()

    r_all = task1_coverage(df)

    guards_df = df[df["pos_group"] == "guard"]
    r_guards, _ = _pearson_r(guards_df["scout_rank"], guards_df[TARGET])

    results = task2_loyo(df)
    verdict = task3_decision(results)
    task4_tankathon(df)
    task5_summary(r_all, r_guards, results, verdict)


if __name__ == "__main__":
    main()
