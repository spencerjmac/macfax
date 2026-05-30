"""
mps/debiased_scout_test.py

De-bias the draft_pick scout signal using four progressive transformations.
Tests whether quality signal survives when the minutes-opportunity gradient
is compressed out.

T1 — Raw 1/pick (biased upper bound, recomputed fresh for consistency)
T2 — Log-compressed
T3 — Tier-percentile (primary de-bias target)
T4 — Tier-flat (maximum compression, zero within-tier ordering)

Run:
    backend/.venv/bin/python -m mps.debiased_scout_test
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
    MIN_FOLD_N,
    _blend_weights,
    _pos_group_csv,
    _spearman,
)

DATASET_PATH   = Path(__file__).parent / "data" / "mps_dataset_raw.csv"
TRAINING_YEARS = {2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021}
LOYO_YEARS     = sorted(TRAINING_YEARS)
FEATURES_24    = FEATURES_23 + ["scout_rank"]

BASELINE_23_RHO   = 0.368   # authoritative from rederive_params LOYO gate
BASELINE_23_G_RHO = 0.256   # 12-fold guards mean; used in decision thresholds
THRESHOLD_STRONG   = BASELINE_23_RHO + 0.010  # 0.378
THRESHOLD_MARGINAL = BASELINE_23_RHO + 0.005  # 0.373
GUARD_THRESHOLD    = BASELINE_23_G_RHO + 0.015  # 0.271


# ── Transformations ───────────────────────────────────────────────────────────

def _t1_raw(pick: float) -> float:
    return 1.0 / pick if pick > 0 else 0.0


def _t2_log(pick: float) -> float:
    if 0 < pick <= 60:
        return math.log(61 - pick) / math.log(60)
    return 0.0


def _t3_tier_pct(pick: float) -> float:
    if pick <= 5:
        return 1.000 - (pick - 1) / 4 * 0.15
    if pick <= 14:
        return 0.850 - (pick - 6) / 8 * 0.15
    if pick <= 30:
        return 0.700 - (pick - 15) / 15 * 0.20
    if pick <= 60:
        return 0.500 - (pick - 31) / 29 * 0.40
    return 0.0


def _t4_tier_flat(pick: float) -> float:
    if pick <= 5:  return 0.900
    if pick <= 14: return 0.700
    if pick <= 30: return 0.500
    if pick <= 60: return 0.250
    return 0.0


TRANSFORMS = {
    "T1 (raw)":       _t1_raw,
    "T2 (log)":       _t2_log,
    "T3 (tier-pct)":  _t3_tier_pct,
    "T4 (tier-flat)": _t4_tier_flat,
}


# ── Data loading ──────────────────────────────────────────────────────────────

def load_base_df() -> pd.DataFrame:
    df_raw = pd.read_csv(DATASET_PATH)
    df = df_raw[df_raw["draft_year"].isin(TRAINING_YEARS)].copy()
    combine = load_combine()
    df = join_combine(df, combine)
    df = add_derived(df)
    df["pos_group"] = df["position"].apply(_pos_group_csv)
    return df[df[TARGET].notna()].copy()


def _apply_transform(df: pd.DataFrame, fn) -> pd.DataFrame:
    """Return copy of df with scout_rank column computed from draft_pick via fn."""
    df = df.copy()
    null_count = 0

    def _safe(pick):
        nonlocal null_count
        if pd.isna(pick) or float(pick) <= 0:
            null_count += 1
            return 0.0
        return fn(float(pick))

    df["scout_rank"] = df["draft_pick"].apply(_safe)
    if null_count:
        print(f"    WARNING: {null_count} null/zero draft_pick values → scout_rank=0.0")
    return df


# ── Pearson r helper ──────────────────────────────────────────────────────────

def _pearson_r(a: pd.Series, b: pd.Series) -> tuple[float, int]:
    valid = a.notna() & b.notna()
    a2, b2 = a[valid], b[valid]
    if len(a2) < 3:
        return float("nan"), 0
    r, _ = scipy_stats.pearsonr(a2, b2)
    return float(r), int(valid.sum())


# ── Task 1: Transformation stats and r decay ──────────────────────────────────

def task1_stats(df: pd.DataFrame) -> dict[str, dict]:
    print("=" * 90)
    print("  Task 1: Transformation Stats and Opportunity-Bias Diagnostic")
    print("=" * 90)

    guards_df = df[df["pos_group"] == "guard"]
    bigs_df   = df[df["pos_group"] == "big"]

    example_picks = [1, 5, 14, 30, 60]

    header = (f"\n  {'Transform':<18}  {'r_all':>7}  {'r_g':>7}  {'r_b':>7}"
              + "".join(f"  {'p' + str(p):>6}" for p in example_picks))
    print(header)
    print("  " + "-" * 80)

    r_table: dict[str, dict] = {}
    for name, fn in TRANSFORMS.items():
        df_t = _apply_transform(df, fn)
        g_t  = df_t[df_t["pos_group"] == "guard"]
        b_t  = df_t[df_t["pos_group"] == "big"]
        r_all, _ = _pearson_r(df_t["scout_rank"], df_t[TARGET])
        r_g, _   = _pearson_r(g_t["scout_rank"],  g_t[TARGET])
        r_b, _   = _pearson_r(b_t["scout_rank"],  b_t[TARGET])
        examples = {p: fn(float(p)) for p in example_picks}
        r_table[name] = {"r_all": r_all, "r_g": r_g, "r_b": r_b, "examples": examples}
        ex_str = "".join(f"  {examples[p]:>6.3f}" for p in example_picks)
        print(f"  {name:<18}  {r_all:>+7.3f}  {r_g:>+7.3f}  {r_b:>+7.3f}{ex_str}")

    print(f"\n  r decay (vs T1 baseline r={r_table['T1 (raw)']['r_all']:+.3f}):")
    r1 = r_table["T1 (raw)"]["r_all"]
    for name, d in r_table.items():
        delta = d["r_all"] - r1
        mark = "  ← baseline" if name == "T1 (raw)" else f"  (Δ = {delta:+.3f})"
        print(f"    {name:<18}: r = {d['r_all']:+.3f}{mark}")

    total_drop = r1 - r_table["T4 (tier-flat)"]["r_all"]
    print()
    if total_drop > 0.150:
        print(f"  SIGNIFICANT BIAS DETECTED — T1→T4 r drop = {total_drop:.3f} > 0.150")
        print(f"  Most T1 signal is opportunity (minutes, not quality).")
    elif total_drop < 0.100:
        print(f"  SIGNAL ROBUST — T1→T4 r drop = {total_drop:.3f} < 0.100")
        print(f"  Tier compression preserves most correlation.")
    else:
        print(f"  MODERATE BIAS — T1→T4 r drop = {total_drop:.3f} (0.100-0.150 range)")
        print(f"  Meaningful bias present; de-biased signal may still be useful.")

    return r_table


# ── LOYO runner ───────────────────────────────────────────────────────────────

def _run_loyo(df_with_scout: pd.DataFrame, features: list[str]) -> dict:
    """Run 11-fold LOYO, return per-fold and aggregate ρ stats."""
    fold_rhos, fold_rhos_g, fold_rhos_b = [], [], []
    per_fold: dict[int, dict] = {}

    for year in LOYO_YEARS:
        fold_df = run_loyo_fold_feat(year, df_with_scout, features)
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

        per_fold[year] = {"rho": r, "n": n, "rho_g": rg, "n_g": ng, "rho_b": rb, "n_b": nb}

    return {
        "per_fold": per_fold,
        "mean":  float(np.mean(fold_rhos))   if fold_rhos   else float("nan"),
        "mg":    float(np.mean(fold_rhos_g)) if fold_rhos_g else float("nan"),
        "mb":    float(np.mean(fold_rhos_b)) if fold_rhos_b else float("nan"),
    }


# ── Task 2: LOYO comparison ───────────────────────────────────────────────────

def task2_loyo(df: pd.DataFrame) -> dict[str, dict]:
    print("\n" + "=" * 90)
    print("  Task 2: LOYO Comparison — 23-feature baseline vs T1/T2/T3/T4")
    print("  NOTE: T1 Δρ is biased upper bound (opportunity confound).")
    print("=" * 90)

    # Compute 23-feature baseline fresh
    print("\n  Computing 23-feature baseline...")
    base_results = _run_loyo(df, FEATURES_23)

    all_results: dict[str, dict] = {"Base (23f)": base_results}

    for name, fn in TRANSFORMS.items():
        print(f"  Running {name}...")
        df_t = _apply_transform(df, fn)
        all_results[name] = _run_loyo(df_t, FEATURES_24)

    # Per-fold table
    header = (f"\n  {'Year':>4}  {'n':>3}  {'ρ_base':>7}  "
              + "  ".join(f"{'ρ_' + k.split()[0]:>7}" for k in TRANSFORMS.keys()))
    print(header)
    print("  " + "-" * 80)

    for year in LOYO_YEARS:
        base_pf = base_results["per_fold"].get(year)
        if base_pf is None:
            print(f"  {year:>4}  skipped")
            continue
        row = f"  {year:>4}  {base_pf['n']:>3}  {base_pf['rho']:>+7.3f}"
        for name, res in list(all_results.items())[1:]:
            pf = res["per_fold"].get(year)
            rstr = f"{pf['rho']:>+7.3f}" if pf else "    n/a"
            row += f"  {rstr}"
        print(row)

    print("  " + "-" * 80)

    base_mean = base_results["mean"]
    row = f"  {'MEAN':>4}  {'':>3}  {base_mean:>+7.3f}"
    for name, res in list(all_results.items())[1:]:
        row += f"  {res['mean']:>+7.3f}"
    print(row)

    row = f"  {'Δ':>4}  {'':>3}  {'base':>7}"
    for name, res in list(all_results.items())[1:]:
        d = res["mean"] - base_mean
        row += f"  {d:>+7.3f}"
    print(row)

    # Position-split summary
    print(f"\n  {'Transform':<18}  {'Mean ρ':>7}  {'Δ':>7}  {'Guards ρ':>9}  {'Δg':>7}  {'Bigs ρ':>7}  {'Δb':>7}")
    print("  " + "-" * 78)

    base_mg = base_results["mg"]
    base_mb = base_results["mb"]

    for name, res in all_results.items():
        d_mean = res["mean"] - base_mean if name != "Base (23f)" else 0.0
        d_mg   = res["mg"]   - base_mg   if name != "Base (23f)" else 0.0
        d_mb   = res["mb"]   - base_mb   if name != "Base (23f)" else 0.0
        d_mean_s = "   base" if name == "Base (23f)" else f"{d_mean:>+7.3f}"
        d_mg_s   = "   base" if name == "Base (23f)" else f"{d_mg:>+7.3f}"
        d_mb_s   = "   base" if name == "Base (23f)" else f"{d_mb:>+7.3f}"
        mg_s = f"{res['mg']:>9.3f}" if not math.isnan(res["mg"]) else "      n/a"
        mb_s = f"{res['mb']:>7.3f}" if not math.isnan(res["mb"]) else "    n/a"
        print(f"  {name:<18}  {res['mean']:>+7.3f}  {d_mean_s}  {mg_s}  {d_mg_s}  {mb_s}  {d_mb_s}")

    return all_results


# ── Task 3: Decision ──────────────────────────────────────────────────────────

def task3_decision(all_results: dict[str, dict]) -> tuple[str, str, float]:
    print("\n" + "=" * 90)
    print("  Task 3: Decision Logic")
    print("=" * 90)

    debiased = {k: v for k, v in all_results.items() if k not in ("Base (23f)", "T1 (raw)")}
    best_name = max(debiased, key=lambda k: debiased[k]["mean"])
    best = debiased[best_name]
    best_mean = best["mean"]
    best_mg   = best["mg"]

    t1_mean = all_results["T1 (raw)"]["mean"]
    base_mean = all_results["Base (23f)"]["mean"]

    denom = t1_mean - BASELINE_23_RHO
    if abs(denom) < 1e-6:
        bias_fraction = 0.0
    else:
        bias_fraction = max(0.0, min(1.0, (t1_mean - best_mean) / denom))

    print(f"\n  Best de-biased transform: {best_name}")
    print(f"  Best de-biased mean ρ: {best_mean:.3f}")
    print(f"  Guards ρ: {best_mg:.3f}  (threshold: {GUARD_THRESHOLD:.3f})")
    print(f"  T1 mean ρ: {t1_mean:.3f}  |  Baseline: {BASELINE_23_RHO:.3f}")
    print(f"\n  Bias fraction = ({t1_mean:.3f} - {best_mean:.3f}) / ({t1_mean:.3f} - {BASELINE_23_RHO:.3f})"
          f" = {bias_fraction:.1%}")
    if bias_fraction > 0.60:
        print(f"  Majority of T1 signal ({bias_fraction:.0%}) was opportunity bias.")
    elif bias_fraction < 0.40:
        print(f"  Minority of T1 signal ({bias_fraction:.0%}) was bias — mostly real quality signal.")
    else:
        print(f"  Mixed: {bias_fraction:.0%} of T1 gain was opportunity bias.")

    if best_mean >= THRESHOLD_STRONG and not math.isnan(best_mg) and best_mg >= GUARD_THRESHOLD:
        verdict = "SIGNAL SURVIVES"
        print(f"\n  → SIGNAL SURVIVES DEBIASING (mean ρ {best_mean:.3f} ≥ {THRESHOLD_STRONG:.3f}, "
              f"guards {best_mg:.3f} ≥ {GUARD_THRESHOLD:.3f})")
        print(f"  Scout consensus has real independent predictive value beyond opportunity bias.")
        print(f"  Recommended action: proceed with NBADraft.net historical scraping")
        print(f"    for 2010-2019, 2021 training classes.")
        print(f"  Use {best_name} transformation on historical mocks.")
        print(f"  Wire Tankathon rank (same transform) as immediate 2026 proxy.")
        print(f"\n  Paste-ready transformation code for {best_name}:")
        if best_name == "T2 (log)":
            print("""
    def _transform_scout_rank(pick: float | None) -> float:
        if pick is None or pick <= 0:
            return 0.0
        if pick > 60:
            return 0.0
        return math.log(61 - pick) / math.log(60)
""")
        elif best_name == "T3 (tier-pct)":
            print("""
    def _transform_scout_rank(pick: float | None) -> float:
        if pick is None or pick <= 0:
            return 0.0
        if pick <= 5:   return 1.000 - (pick - 1) / 4 * 0.15
        if pick <= 14:  return 0.850 - (pick - 6) / 8 * 0.15
        if pick <= 30:  return 0.700 - (pick - 15) / 15 * 0.20
        if pick <= 60:  return 0.500 - (pick - 31) / 29 * 0.40
        return 0.0
""")
        elif best_name == "T4 (tier-flat)":
            print("""
    def _transform_scout_rank(pick: float | None) -> float:
        if pick is None or pick <= 0:
            return 0.0
        if pick <= 5:  return 0.900
        if pick <= 14: return 0.700
        if pick <= 30: return 0.500
        if pick <= 60: return 0.250
        return 0.0
""")
    elif best_mean >= THRESHOLD_STRONG:
        verdict = "MARGINAL"
        print(f"\n  → MARGINAL (mean ρ {best_mean:.3f} ≥ {THRESHOLD_STRONG:.3f} but "
              f"guards ρ {best_mg:.3f} < {GUARD_THRESHOLD:.3f})")
        print(f"  Scout consensus improves overall ρ but does not fix the guards problem.")
        print(f"  Improvement likely reflects residual opportunity bias, not guard-specific quality signal.")
        print(f"  Recommended action: scraping not justified. Close Step 3.")
    elif best_mean >= THRESHOLD_MARGINAL:
        verdict = "MARGINAL"
        print(f"\n  → MARGINAL (best de-biased mean ρ {best_mean:.3f}, Δ = {best_mean - BASELINE_23_RHO:+.3f}, "
              f"threshold = +0.010)")
        print(f"  Scout consensus adds some signal but below threshold after debiasing.")
        print(f"  Recommended action: skip historical scraping. Close Step 3.")
        print(f"  Guards ρ gap ({best_mg:.3f} vs 0.256) is structural — document as known limitation.")
    else:
        verdict = "DOES NOT SURVIVE"
        print(f"\n  → SIGNAL DOES NOT SURVIVE DEBIASING (best mean ρ {best_mean:.3f} < {THRESHOLD_MARGINAL:.3f})")
        print(f"  T1 improvement was primarily opportunity bias, not real scout signal.")
        print(f"  Recommended action: Close Step 3 permanently.")
        print(f"  Do not add any scout consensus feature to the model.")
        print(f"  The gap to Ridge ceiling is structural — not closeable without opportunity contamination.")

    return verdict, best_name, bias_fraction


# ── Task 4: Summary box ───────────────────────────────────────────────────────

def task4_summary(
    r_table: dict[str, dict],
    all_results: dict[str, dict],
    verdict: str,
    best_name: str,
    bias_fraction: float,
) -> None:
    t1_r   = r_table["T1 (raw)"]["r_all"]
    t2_r   = r_table["T2 (log)"]["r_all"]
    t3_r   = r_table["T3 (tier-pct)"]["r_all"]
    t4_r   = r_table["T4 (tier-flat)"]["r_all"]

    base23_mean = all_results["Base (23f)"]["mean"]
    t1_mean     = all_results["T1 (raw)"]["mean"]
    t2_mean     = all_results["T2 (log)"]["mean"]
    t3_mean     = all_results["T3 (tier-pct)"]["mean"]
    t4_mean     = all_results["T4 (tier-flat)"]["mean"]

    base23_mg = all_results["Base (23f)"]["mg"]
    t1_mg     = all_results["T1 (raw)"]["mg"]

    best = all_results[best_name]
    best_mean = best["mean"]
    best_mg   = best["mg"]

    if verdict == "SIGNAL SURVIVES":
        next_step = "Proceed with NBADraft.net scraping for 2010-2019, 2021"
    elif verdict == "MARGINAL":
        next_step = "Close Step 3 — guards ρ gap is structural, known limitation"
    else:
        next_step = "Close Step 3 permanently — signal is opportunity bias"

    w = 72

    def row(left, right=""):
        content = f"  {left:<42}{right}" if right else f"  {left}"
        pad = w - 2 - len(content)
        return "│" + content + " " * max(pad, 0) + "│"

    print("\n" + "┌" + "─" * w + "┐")
    print(row("SCOUT SIGNAL DE-BIAS RESULTS"))
    print(row(""))
    print(row("Pearson r decay (opportunity bias diagnostic):"))
    print(row(f"  T1 (raw 1/pick):      r = {t1_r:.3f}", "(biased upper bound)"))
    print(row(f"  T2 (log-compressed):  r = {t2_r:.3f}", f"(Δ = {t2_r - t1_r:+.3f})"))
    print(row(f"  T3 (tier-percentile): r = {t3_r:.3f}", f"(Δ = {t3_r - t1_r:+.3f})"))
    print(row(f"  T4 (tier-flat):       r = {t4_r:.3f}", f"(Δ = {t4_r - t1_r:+.3f})"))
    print(row(f"  Bias fraction estimate: {bias_fraction:.0%}"))
    print(row(""))
    print(row("LOYO mean ρ (11-fold, 2020 excluded):"))
    print(row(f"  Baseline (23 features):", f"{base23_mean:.3f}"))
    print(row(f"  T1 (raw, biased):", f"{t1_mean:.3f}  Δ = {t1_mean - base23_mean:+.3f}"))
    print(row(f"  T2 (log):", f"{t2_mean:.3f}  Δ = {t2_mean - base23_mean:+.3f}"))
    print(row(f"  T3 (tier-percentile):", f"{t3_mean:.3f}  Δ = {t3_mean - base23_mean:+.3f}"))
    print(row(f"  T4 (tier-flat):", f"{t4_mean:.3f}  Δ = {t4_mean - base23_mean:+.3f}"))
    print(row(""))
    print(row(f"Best de-biased transform: {best_name}"))
    print(row(f"Best de-biased mean ρ: {best_mean:.3f}"))
    mg_str = f"{best_mg:.3f}" if not math.isnan(best_mg) else "n/a"
    dg_str = f"{best_mg - base23_mg:+.3f}" if not math.isnan(best_mg) else "n/a"
    print(row(f"Guards ρ improvement:", f"{base23_mg:.3f} → {mg_str} ({dg_str})"))
    print(row(""))
    print(row(f"Bias fraction: {bias_fraction:.0%} of T1 gain was opportunity bias"))
    print(row(""))
    print(row(f"Verdict: {verdict}"))
    print(row(""))
    print(row("Next step:"))
    print(row(f"  {next_step}"))
    print("└" + "─" * w + "┘")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("De-biased Scout Signal Test")
    print("Compressing opportunity gradient to isolate quality signal")
    print()

    df = load_base_df()

    r_table     = task1_stats(df)
    all_results = task2_loyo(df)
    verdict, best_name, bias_fraction = task3_decision(all_results)
    task4_summary(r_table, all_results, verdict, best_name, bias_fraction)


if __name__ == "__main__":
    main()
