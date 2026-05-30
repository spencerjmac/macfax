"""
mps/loyo_sensitivity.py

Two targeted sensitivity analyses using the LOYO framework.

  Task 1: 2020 anomaly test — is ρ=0.112 genuine anomaly or normal variance?
  Task 2: obpm collinearity removal — does dropping obpm improve LOYO ρ by ≥0.005?
  Task 3: combined summary

Run:
    backend/.venv/bin/python -m mps.loyo_sensitivity
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from mps.backtest_full import compute_correlations
from mps.loyo_validation import (
    MIN_FOLD_N,
    LOYO_YEARS,
    _blend_weights,
    _pos_group_csv,
    _spearman,
    load_data,
)
from mps.scorer import (
    FEATURE_WEIGHTS,
    FEATURE_WEIGHTS_BIGS,
    FEATURE_WEIGHTS_GUARDS,
    _zscore_to_0_100,
    compute_age_penalty,
    compute_availability_modifier,
    compute_height_floor_penalty,
    compute_srs_adj,
)

# ── Hardcoded Variant A results (from loyo_validation.py run — do NOT recompute) ──

VARIANT_A_FOLD_RHOS: dict[int, dict] = {
    2010: {"rho":  0.351, "rho_g": -0.015, "n_g": 14, "rho_b": 0.702, "n_b": 22, "n": 53},
    2011: {"rho":  0.415, "rho_g":  0.329, "n_g": 22, "rho_b": 0.658, "n_b": 16, "n": 46},
    2012: {"rho":  0.416, "rho_g":  0.477, "n_g": 18, "rho_b": 0.382, "n_b": 23, "n": 51},
    2013: {"rho":  0.449, "rho_g":  0.220, "n_g": 23, "rho_b": 0.678, "n_b": 14, "n": 47},
    2014: {"rho":  0.257, "rho_g":  0.119, "n_g": 21, "rho_b": 0.691, "n_b": 14, "n": 46},
    2015: {"rho":  0.396, "rho_g":  0.332, "n_g": 15, "rho_b": 0.612, "n_b": 19, "n": 46},
    2016: {"rho":  0.252, "rho_g":  0.274, "n_g": 20, "rho_b": 0.229, "n_b": 18, "n": 44},
    2017: {"rho":  0.322, "rho_g":  0.406, "n_g": 22, "rho_b": 0.258, "n_b": 20, "n": 50},
    2018: {"rho":  0.364, "rho_g":  0.184, "n_g": 23, "rho_b": 0.462, "n_b": 16, "n": 51},
    2019: {"rho":  0.285, "rho_g":  0.038, "n_g": 23, "rho_b": 0.459, "n_b": 19, "n": 52},
    2020: {"rho":  0.112, "rho_g":  0.117, "n_g": 26, "rho_b": 0.254, "n_b": 16, "n": 49},
    2021: {"rho":  0.537, "rho_g":  0.592, "n_g": 23, "rho_b": 0.568, "n_b": 17, "n": 51},
}
VARIANT_A_MEAN_RHO  = 0.346
VARIANT_A_CI_LO     = 0.283
VARIANT_A_CI_HI     = 0.409

TARGET = "vorp_yr2_5_avg"
FEATURES_23 = list(FEATURE_WEIGHTS.keys())
FEATURES_22 = [f for f in FEATURES_23 if f != "obpm"]


# ── Parameterized fold engine ─────────────────────────────────────────────────

def _derive_weights_feat(df_train: pd.DataFrame, features: list[str]) -> dict[str, float]:
    """Derive normalized weights from |Pearson r| for the given feature list."""
    corr_rows = compute_correlations(df_train, features)
    raw: dict[str, float] = {}
    for row in corr_rows:
        feat = row["feature"]
        r    = row.get("r")
        n    = row.get("n", 0) or 0
        if r is None or n < 10:
            raw[feat] = 0.0
        else:
            raw[feat] = max(abs(float(r)), 0.0)
    total = sum(raw.values())
    if total < 1e-8:
        w = 1.0 / len(features)
        return {f: w for f in features}
    return {k: v / total for k, v in raw.items()}


def _compute_fold_stats(
    train_df: pd.DataFrame, features: list[str]
) -> dict[str, tuple[float, float, float]]:
    """Compute per-feature (mean, std, median) from training set only."""
    stats: dict[str, tuple[float, float, float]] = {}
    for feat in features:
        col = train_df[feat].dropna() if feat in train_df.columns else pd.Series([], dtype=float)
        mean   = float(col.mean())      if len(col) > 0 else 0.0
        std    = float(col.std(ddof=1)) if len(col) > 1 else 1.0
        median = float(col.median())    if len(col) > 0 else 0.0
        stats[feat] = (mean, max(std, 1e-8), median)
    return stats


def _score_player_feat(
    row: pd.Series,
    weights: dict[str, float],
    fold_stats: dict[str, tuple[float, float, float]],
) -> float | None:
    """
    Weighted z-score composite using only weights.keys() as feature set.
    Missing values imputed with fold median. Returns None if <3 non-null features.
    """
    n_non_null = 0
    for feat in weights:
        v = row.get(feat)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            n_non_null += 1
    if n_non_null < 3:
        return None

    weighted_z_sum = 0.0
    total_w = 0.0
    for feat, w in weights.items():
        mean, std, median = fold_stats[feat]
        v = row.get(feat)
        val = v if (v is not None and not (isinstance(v, float) and math.isnan(v))) else median
        z = (float(val) - mean) / max(std, 1e-8)
        weighted_z_sum += w * z
        total_w += w

    composite = _zscore_to_0_100(weighted_z_sum / max(total_w, 1e-8))

    srs = row.get("program_srs")
    srs_v = float(srs) if (srs is not None and not (isinstance(srs, float) and math.isnan(srs))) else None
    srs_adj = compute_srs_adj(srs_v)

    gp = row.get("games_played")
    gp_v = float(gp) if (gp is not None and not (isinstance(gp, float) and math.isnan(gp))) else None
    avail = compute_availability_modifier(gp_v, team_games=33)

    da = row.get("draft_age")
    age_pen = compute_age_penalty(float(da)) if (da is not None and not (isinstance(da, float) and math.isnan(da))) else 0.0

    h   = row.get("height_in")
    whr = row.get("wingspan_to_height_ratio")
    hf_pen = compute_height_floor_penalty({
        "height_in":               float(h)   if (h   is not None and not (isinstance(h,   float) and math.isnan(h)))   else None,
        "wingspan_to_height_ratio": float(whr) if (whr is not None and not (isinstance(whr, float) and math.isnan(whr))) else None,
    })

    return float(np.clip(composite + srs_adj + avail + age_pen + hf_pen, 0, 100))


def run_loyo_fold_feat(
    holdout_year: int, full_df: pd.DataFrame, features: list[str]
) -> pd.DataFrame | None:
    """
    Run one LOYO fold with the given feature set. Returns scored holdout DataFrame
    or None if fold is skipped (n < MIN_FOLD_N).
    """
    train_df = full_df[full_df["draft_year"] != holdout_year].copy()
    hold_df  = full_df[full_df["draft_year"] == holdout_year].copy()

    if len(hold_df) < MIN_FOLD_N:
        return None

    fold_stats = _compute_fold_stats(train_df, features)

    train_with_vorp = train_df[train_df[TARGET].notna()].copy()
    weights_overall = _derive_weights_feat(train_with_vorp, features)

    train_guards = train_with_vorp[train_with_vorp["pos_group"] == "guard"]
    train_bigs   = train_with_vorp[train_with_vorp["pos_group"] == "big"]

    weights_guards = (
        _derive_weights_feat(train_guards, features)
        if len(train_guards) >= 20
        else weights_overall
    )
    weights_bigs = (
        _derive_weights_feat(train_bigs, features)
        if len(train_bigs) >= 20
        else weights_overall
    )
    weights_wings = _blend_weights(weights_guards, weights_bigs)

    scored_rows = []
    n_excluded = 0

    for _, row in hold_df.iterrows():
        pg = str(row.get("pos_group", "wing"))
        weights = weights_guards if pg == "guard" else (weights_bigs if pg == "big" else weights_wings)
        mps = _score_player_feat(row, weights, fold_stats)
        if mps is None:
            n_excluded += 1
            continue
        scored_rows.append({
            "player_name": row.get("player_name"),
            "draft_year":  holdout_year,
            "pos_group":   pg,
            TARGET:        row.get(TARGET),
            "mps":         mps,
        })

    if n_excluded > 0:
        print(f"    Fold {holdout_year}: excluded {n_excluded} players (<3 non-null features)")

    return pd.DataFrame(scored_rows)


# ── Aggregate helper ──────────────────────────────────────────────────────────

def _aggregate(fold_rhos: list[float]) -> tuple[float, float, float, float]:
    """Returns (mean, std, ci_lo, ci_hi)."""
    n = len(fold_rhos)
    mean = float(np.mean(fold_rhos))
    std  = float(np.std(fold_rhos, ddof=1)) if n > 1 else 0.0
    ci   = 1.96 * std / math.sqrt(n)
    return mean, std, mean - ci, mean + ci


# ── Task 1: 2020 anomaly test ─────────────────────────────────────────────────

def task1_2020_sensitivity() -> dict:
    print("=" * 72)
    print("  Task 1: 2020 Anomaly Sensitivity Test")
    print("=" * 72)

    rhos_all = [v["rho"] for v in VARIANT_A_FOLD_RHOS.values()]
    rhos_no20 = [v["rho"] for yr, v in VARIANT_A_FOLD_RHOS.items() if yr != 2020]

    mean_12, std_12, ci12_lo, ci12_hi = _aggregate(rhos_all)
    mean_11, std_11, ci11_lo, ci11_hi = _aggregate(rhos_no20)
    delta = mean_11 - mean_12

    print(f"\n  {'Scope':<32}  {'Folds':>5}  {'Mean ρ':>7}  {'95% CI':>16}  {'Δ':>7}")
    print("  " + "-" * 74)
    print(f"  {'Full 12-fold LOYO':<32}  {12:>5}  {mean_12:>+7.3f}  "
          f"[{ci12_lo:+.3f}, {ci12_hi:+.3f}]  {'baseline':>7}")
    print(f"  {'Without 2020 fold':<32}  {11:>5}  {mean_11:>+7.3f}  "
          f"[{ci11_lo:+.3f}, {ci11_hi:+.3f}]  {delta:>+7.3f}")

    anomalous = delta > 0.010
    verdict = "ANOMALOUS" if anomalous else "NORMAL VARIANCE"
    print(f"\n  Δ = {delta:+.3f}  →  Verdict: 2020 is {verdict}")

    if anomalous:
        rho_2020 = VARIANT_A_FOLD_RHOS[2020]["rho"]
        z_score  = (rho_2020 - mean_12) / std_12 if std_12 > 0 else float("nan")
        print(f"\n  2020 ρ = {rho_2020:.3f}  ({z_score:.1f}σ below 12-fold mean)")
        print(f"  Likely causes: COVID-shortened season (~72g vs 82g norm), bubble play,")
        print(f"  condensed schedule altering per-game stats; fewer GP data → noisier BPM.")
        print(f"  Bigs ρ = {VARIANT_A_FOLD_RHOS[2020]['rho_b']:.3f} still positive — guards drove the miss.")
    else:
        print(f"\n  2020 is a hard class for the model, not a data anomaly.")
        print(f"  Δ ≤ 0.010 — within normal fold-to-fold variance.")

    return {
        "verdict": verdict,
        "delta":   delta,
        "mean_12": mean_12,
        "mean_11": mean_11,
        "ci11_lo": ci11_lo,
        "ci11_hi": ci11_hi,
    }


# ── Task 2: obpm collinearity removal ────────────────────────────────────────

def task2_obpm_removal(full_df: pd.DataFrame) -> dict:
    print("\n" + "=" * 72)
    print("  Task 2: obpm Collinearity Removal Test (23 → 22 features)")
    print("=" * 72)
    print(f"\n  Variant A: 23 features (baseline, cached results)")
    print(f"  Variant B: 22 features (obpm removed)")
    print(f"\n  Running 12 LOYO folds with FEATURES_22...")

    fold_b_results: list[dict] = []

    for year in LOYO_YEARS:
        fold_df = run_loyo_fold_feat(year, full_df, FEATURES_22)
        if fold_df is None or fold_df.empty:
            print(f"  Fold {year}: skipped")
            continue

        vorp = fold_df[TARGET]
        mps  = fold_df["mps"]
        g_mask = fold_df["pos_group"] == "guard"
        b_mask = fold_df["pos_group"] == "big"

        rho_all, n_all = _spearman(mps, vorp)
        rho_g,   n_g   = _spearman(mps[g_mask], vorp[g_mask])
        rho_b,   n_b   = _spearman(mps[b_mask], vorp[b_mask])

        # Check n matches Variant A
        a_n = VARIANT_A_FOLD_RHOS[year]["n"]
        if n_all != a_n:
            print(f"  WARNING Fold {year}: Variant B n={n_all} ≠ Variant A n={a_n}")

        fold_b_results.append({
            "year":  year,
            "n":     n_all,
            "rho":   rho_all,
            "rho_g": rho_g, "n_g": n_g,
            "rho_b": rho_b, "n_b": n_b,
        })

    # B. Side-by-side table
    print(f"\n  {'Year':<6}  {'n':>3}  {'ρ_A (23)':>9}  {'ρ_B (22)':>9}  {'Δ':>7}")
    print("  " + "-" * 48)

    rhos_b = []
    rhos_bg, rhos_bb = [], []

    for s in fold_b_results:
        year  = s["year"]
        rho_a = VARIANT_A_FOLD_RHOS[year]["rho"]
        rho_b = s["rho"]
        delta = rho_b - rho_a
        rhos_b.append(rho_b)
        if not math.isnan(s["rho_g"]): rhos_bg.append(s["rho_g"])
        if not math.isnan(s["rho_b"]): rhos_bb.append(s["rho_b"])
        print(f"  {year:<6}  {s['n']:>3}  {rho_a:>+9.3f}  {rho_b:>+9.3f}  {delta:>+7.3f}")

    print("  " + "-" * 48)
    mean_b, std_b, ci_b_lo, ci_b_hi = _aggregate(rhos_b)
    delta_overall = mean_b - VARIANT_A_MEAN_RHO
    print(f"  {'MEAN':<6}  {'':>3}  {VARIANT_A_MEAN_RHO:>+9.3f}  {mean_b:>+9.3f}  {delta_overall:>+7.3f}")

    # C. Position-split comparison
    mean_bg = float(np.mean(rhos_bg)) if rhos_bg else float("nan")
    mean_bb = float(np.mean(rhos_bb)) if rhos_bb else float("nan")
    guards_baseline = 0.256
    bigs_baseline   = 0.496

    print(f"\n  C. Position-split ρ comparison:")
    print(f"  {'Group':<8}  {'Variant A (23)':>15}  {'Variant B (22)':>15}  {'Δ':>7}")
    print("  " + "-" * 50)
    bg_d = mean_bg - guards_baseline if not math.isnan(mean_bg) else float("nan")
    bb_d = mean_bb - bigs_baseline   if not math.isnan(mean_bb) else float("nan")
    bg_s = f"{mean_bg:>+15.3f}" if not math.isnan(mean_bg) else "            N/A"
    bb_s = f"{mean_bb:>+15.3f}" if not math.isnan(mean_bb) else "            N/A"
    bg_ds = f"{bg_d:>+7.3f}" if not math.isnan(bg_d) else "    N/A"
    bb_ds = f"{bb_d:>+7.3f}" if not math.isnan(bb_d) else "    N/A"
    print(f"  {'Guards':<8}  {guards_baseline:>+15.3f}  {bg_s}  {bg_ds}")
    print(f"  {'Bigs':<8}  {bigs_baseline:>+15.3f}  {bb_s}  {bb_ds}")

    # D. Decision
    removes_obpm = mean_b >= VARIANT_A_MEAN_RHO + 0.005
    print(f"\n  D. Decision: mean_B ({mean_b:.3f}) vs mean_A ({VARIANT_A_MEAN_RHO:.3f}) + 0.005 threshold")

    verdict = "REMOVE obpm" if removes_obpm else "KEEP obpm"
    print(f"  Verdict: {verdict}  (Δ = {delta_overall:+.3f})")

    if removes_obpm:
        print(f"\n  Paste-ready updated weights (obpm removed, remaining renormalized):")
        for name, w_dict in [("FEATURE_WEIGHTS_GUARDS", FEATURE_WEIGHTS_GUARDS),
                              ("FEATURE_WEIGHTS_BIGS",   FEATURE_WEIGHTS_BIGS)]:
            obpm_w = w_dict.get("obpm", 0.0)
            remaining = {k: v for k, v in w_dict.items() if k != "obpm"}
            scale = 1.0 / (1.0 - obpm_w) if (1.0 - obpm_w) > 1e-8 else 1.0
            renorm = {k: round(v * scale, 4) for k, v in remaining.items()}
            print(f"\n  {name}: dict[str, float] = {{")
            for feat, w in renorm.items():
                print(f'      "{feat}":{" " * (22 - len(feat))}{w},')
            print(f"  }}  # sum = {sum(renorm.values()):.4f}")
    else:
        print(f"  obpm removal does not improve LOYO ρ by threshold — "
              f"collinearity concern noted but not binding.")

    return {
        "verdict":        verdict,
        "removes_obpm":   removes_obpm,
        "delta":          delta_overall,
        "mean_b":         mean_b,
        "ci_b_lo":        ci_b_lo,
        "ci_b_hi":        ci_b_hi,
        "guards_mean_b":  mean_bg,
        "bigs_mean_b":    mean_bb,
    }


# ── Task 3: Combined summary ──────────────────────────────────────────────────

def task3_summary(t1: dict, t2: dict) -> None:
    # Combined best config
    features_n = 22 if t2["removes_obpm"] else 23
    incl_2020  = "NO" if t1["verdict"] == "ANOMALOUS" else "YES"

    # Expected LOYO mean ρ under combined config
    # If 2020 excluded AND obpm removed: use t2 mean_b (which still includes 2020)
    # → best estimate is t1.mean_11 if only excluding 2020, or t2.mean_b if only removing obpm
    # For combined effect, add deltas (linear approximation)
    combined_rho = VARIANT_A_MEAN_RHO + t1["delta"] + t2["delta"]

    print("\n" + "┌" + "─" * 68 + "┐")
    print("│  LOYO SENSITIVITY RESULTS" + " " * 42 + "│")
    print("│" + " " * 68 + "│")

    def _box_line(label, val, width=68):
        content = f"  {label:<38}  {val}"
        pad = width - len(content)
        print(f"│{content}{' ' * max(pad, 0)}│")

    _box_line("Step 1b — 2020 anomaly test:", "")
    _box_line("  12-fold mean ρ:", f"0.346")
    _box_line(f"  11-fold mean ρ (no 2020):", f"{t1['mean_11']:.3f}  [{t1['ci11_lo']:+.3f}, {t1['ci11_hi']:+.3f}]")
    _box_line("  Δ:", f"{t1['delta']:+.3f}")
    _box_line("  Verdict:", t1["verdict"])
    print("│" + " " * 68 + "│")
    _box_line("Step 2 — obpm collinearity removal:", "")
    _box_line("  23-feature mean ρ:", f"0.346  [{VARIANT_A_CI_LO:.3f}, {VARIANT_A_CI_HI:.3f}]")
    _box_line("  22-feature mean ρ:", f"{t2['mean_b']:.3f}  [{t2['ci_b_lo']:+.3f}, {t2['ci_b_hi']:+.3f}]")
    _box_line("  Δ:", f"{t2['delta']:+.3f}")
    _box_line("  Verdict:", t2["verdict"])
    print("│" + " " * 68 + "│")
    _box_line("Combined best configuration:", "")
    _box_line("  Features:", str(features_n))
    _box_line("  Include 2020 in training:", incl_2020)
    _box_line("  Expected LOYO mean ρ (linear approx):", f"{combined_rho:.3f}")
    print("│" + " " * 68 + "│")
    print("└" + "─" * 68 + "┘")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("MPS LOYO Sensitivity Analysis")
    print(f"Baseline: 12-fold mean ρ = {VARIANT_A_MEAN_RHO}  |  "
          f"23 features  |  2020 included\n")

    t1 = task1_2020_sensitivity()

    print("\nLoading training data for Task 2...")
    full_df = load_data()

    t2 = task2_obpm_removal(full_df)

    task3_summary(t1, t2)

    print()


if __name__ == "__main__":
    main()
