"""
mps/loyo_validation.py

Leave-One-Year-Out (LOYO) cross-validation across 2010-2021 training classes.

For each year Y in [2010..2021]:
  - Train  = all other years with known vorp_yr2_5_avg
  - Holdout = year Y players with known vorp_yr2_5_avg
  - Weights and normalization params recomputed from train only
  - Score holdout, compute Spearman ρ

12 folds × ~44-53 players ≈ 586 total evaluation points.
Mean ρ across folds is the real model accuracy estimate.

Run:
    backend/.venv/bin/python -m mps.loyo_validation
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from mps.backtest_full import add_derived, compute_correlations, join_combine, load_combine
from mps.scorer import (
    FEATURE_WEIGHTS,
    TrainingParams,
    _zscore_to_0_100,
    compute_age_penalty,
    compute_availability_modifier,
    compute_height_floor_penalty,
    compute_mps_for_prospect,
    compute_srs_adj,
)

# ── Constants ─────────────────────────────────────────────────────────────────

DATASET_PATH      = Path(__file__).parent / "data" / "mps_dataset_raw.csv"
TARGET            = "vorp_yr2_5_avg"
ALL_LOYO_FEATURES = list(FEATURE_WEIGHTS.keys())   # 23 features — exactly the live model set
LOYO_YEARS        = list(range(2010, 2022))         # 2010–2021 inclusive
MIN_FOLD_N        = 5

# Live model uses position abbreviations; CSV uses full strings.
_POSITION_ABBREV: dict[str, str] = {
    "Point Guard":    "PG",
    "Shooting Guard": "SG",
    "Small Forward":  "SF",
    "Power Forward":  "PF",
    "Center":         "C",
}


# ── Position resolver (CSV full strings → guard/big/wing) ────────────────────

def _pos_group_csv(pos: str) -> str:
    primary = str(pos).split(",")[0].strip().lower()
    if "point guard" in primary or "shooting guard" in primary:
        return "guard"
    if "power forward" in primary or primary == "center":
        return "big"
    return "wing"


# ── Task 1: Data preparation ──────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    print("=" * 76)
    print("  Task 1: Data Preparation")
    print("=" * 76)

    df_raw = pd.read_csv(DATASET_PATH)
    df = df_raw[df_raw[TARGET].notna() & (df_raw["draft_year"] <= 2021)].copy()
    print(f"\n  Rows (vorp not null, ≤2021): {len(df)}")

    year_dist = df.groupby("draft_year").size()
    print(f"\n  {'Year':<6}  {'n':>3}")
    for yr, n in year_dist.items():
        print(f"  {yr:<6}  {n:>3}")
    print(f"  Mean VORP: {df[TARGET].mean():.3f}  |  Median: {df[TARGET].median():.3f}")

    print(f"\n  Joining combine data...")
    combine = load_combine()
    df = join_combine(df, combine)
    n_height = df["height_in"].notna().sum()
    print(f"  Rows with height_in: {n_height}/{len(df)}")

    df = add_derived(df)
    df["pos_group"] = df["position"].apply(_pos_group_csv)

    print(f"\n  Position distribution:")
    for grp, cnt in df["pos_group"].value_counts().items():
        print(f"    {grp}: {cnt}")

    # Verify all 23 features exist in DataFrame
    missing_feats = [f for f in ALL_LOYO_FEATURES if f not in df.columns]
    if missing_feats:
        print(f"\n  WARNING: missing features: {missing_feats}")

    return df


# ── Weight derivation ─────────────────────────────────────────────────────────

def _derive_weights(df_train: pd.DataFrame) -> dict[str, float]:
    """
    Derive normalized weights from |Pearson r| vs vorp_yr2_5_avg.
    Features with r<0, missing r, or n<10 get weight=0. Normalized to sum=1.
    """
    corr_rows = compute_correlations(df_train, ALL_LOYO_FEATURES)
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
        w = 1.0 / len(ALL_LOYO_FEATURES)
        return {f: w for f in ALL_LOYO_FEATURES}
    return {k: v / total for k, v in raw.items()}


def _blend_weights(
    guards_w: dict[str, float], bigs_w: dict[str, float]
) -> dict[str, float]:
    blended = {
        f: guards_w.get(f, 0.0) * 0.5 + bigs_w.get(f, 0.0) * 0.5
        for f in guards_w
    }
    total = sum(blended.values())
    if total < 1e-8:
        return blended
    return {k: v / total for k, v in blended.items()}


# ── Scoring helper ────────────────────────────────────────────────────────────

def _score_player(
    row: pd.Series,
    weights: dict[str, float],
    fold_stats: dict[str, tuple[float, float, float]],
) -> float | None:
    """Weighted z-score composite with fold-specific normalization + additive adjustments."""
    stats = {}
    for feat in ALL_LOYO_FEATURES:
        v = row.get(feat)
        stats[feat] = None if (v is None or (isinstance(v, float) and math.isnan(v))) else v

    n_non_null = sum(1 for v in stats.values() if v is not None)
    if n_non_null < 3:
        return None

    weighted_z_sum = 0.0
    total_w = 0.0
    for feat, w in weights.items():
        mean, std, median = fold_stats[feat]
        val = stats.get(feat)
        if val is None:
            val = median   # neutral imputation
        z = (float(val) - mean) / max(std, 1e-8)
        weighted_z_sum += w * z
        total_w += w

    composite = _zscore_to_0_100(weighted_z_sum / max(total_w, 1e-8))

    srs   = row.get("program_srs")
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


# ── Task 2: LOYO fold engine ──────────────────────────────────────────────────

def run_loyo_fold(
    holdout_year: int, full_df: pd.DataFrame
) -> tuple[pd.DataFrame | None, dict[str, dict[str, float]]]:
    """
    Returns (scored_holdout_df, weights_dict) where weights_dict has keys
    "overall", "guards", "bigs".  scored_holdout_df is None if fold is skipped.
    """
    train_df = full_df[full_df["draft_year"] != holdout_year].copy()
    hold_df  = full_df[full_df["draft_year"] == holdout_year].copy()

    if len(hold_df) < MIN_FOLD_N:
        print(f"  Fold {holdout_year}: only {len(hold_df)} rows — skipping")
        return None, {}

    # B. Fold normalization stats from train only
    fold_stats: dict[str, tuple[float, float, float]] = {}
    for feat in ALL_LOYO_FEATURES:
        if feat in train_df.columns:
            col = train_df[feat].dropna()
        else:
            col = pd.Series([], dtype=float)
        mean   = float(col.mean())      if len(col) > 0 else 0.0
        std    = float(col.std(ddof=1)) if len(col) > 1 else 1.0
        median = float(col.median())    if len(col) > 0 else 0.0
        fold_stats[feat] = (mean, max(std, 1e-8), median)

    # C. Overall weights
    train_with_vorp = train_df[train_df[TARGET].notna()].copy()
    fold_weights_overall = _derive_weights(train_with_vorp)

    # D. Position-split weights
    train_guards = train_with_vorp[train_with_vorp["pos_group"] == "guard"]
    train_bigs   = train_with_vorp[train_with_vorp["pos_group"] == "big"]

    fold_weights_guards = (
        _derive_weights(train_guards)
        if len(train_guards) >= 20
        else fold_weights_overall
    )
    fold_weights_bigs = (
        _derive_weights(train_bigs)
        if len(train_bigs) >= 20
        else fold_weights_overall
    )
    fold_weights_wings = _blend_weights(fold_weights_guards, fold_weights_bigs)

    weights_dict = {
        "overall": fold_weights_overall,
        "guards":  fold_weights_guards,
        "bigs":    fold_weights_bigs,
    }

    # E. Score holdout players
    scored_rows = []
    n_excluded = 0

    for _, row in hold_df.iterrows():
        pg = str(row.get("pos_group", "wing"))
        if pg == "guard":
            weights = fold_weights_guards
        elif pg == "big":
            weights = fold_weights_bigs
        else:
            weights = fold_weights_wings

        mps = _score_player(row, weights, fold_stats)
        if mps is None:
            n_excluded += 1
            continue

        scored_rows.append({
            "player_name":    row.get("player_name"),
            "draft_year":     holdout_year,
            "position":       row.get("position"),
            "pos_group":      pg,
            TARGET:           row.get(TARGET),
            "mps":            mps,
            "draft_age":      row.get("draft_age"),
        })

    if n_excluded > 0:
        print(f"  Fold {holdout_year}: excluded {n_excluded} players (<3 non-null features)")

    return pd.DataFrame(scored_rows), weights_dict


# ── Spearman helper ───────────────────────────────────────────────────────────

def _spearman(a: pd.Series, b: pd.Series) -> tuple[float, int]:
    valid = a.notna() & b.notna()
    a2, b2 = a[valid], b[valid]
    if len(a2) < 3:
        return float("nan"), 0
    rho, _ = scipy_stats.spearmanr(a2, b2)
    return float(rho), int(valid.sum())


# ── Task 3: Run all 12 folds ──────────────────────────────────────────────────

def run_all_folds(
    full_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict], dict[int, dict[str, dict[str, float]]]]:
    """
    Returns:
      combined_df       — all scored holdout rows
      fold_summaries    — list of per-fold ρ dicts
      weights_by_year   — {year: {"overall":..., "guards":..., "bigs":...}}
    """
    print("\n" + "=" * 76)
    print("  Task 3: Run All 12 LOYO Folds")
    print("=" * 76 + "\n")

    all_dfs: list[pd.DataFrame] = []
    fold_summaries: list[dict] = []
    weights_by_year: dict[int, dict[str, dict[str, float]]] = {}

    for year in LOYO_YEARS:
        fold_df, wdict = run_loyo_fold(year, full_df)
        if fold_df is None or fold_df.empty:
            continue

        weights_by_year[year] = wdict

        vorp = fold_df[TARGET]
        mps  = fold_df["mps"]
        g_mask = fold_df["pos_group"] == "guard"
        b_mask = fold_df["pos_group"] == "big"
        w_mask = fold_df["pos_group"] == "wing"

        rho_all, n_all = _spearman(mps, vorp)
        rho_g,   n_g   = _spearman(mps[g_mask], vorp[g_mask])
        rho_b,   n_b   = _spearman(mps[b_mask], vorp[b_mask])
        rho_w,   n_w   = _spearman(mps[w_mask], vorp[w_mask])

        fold_summaries.append({
            "year":  year,
            "n":     n_all,
            "rho":   rho_all,
            "rho_g": rho_g, "n_g": n_g,
            "rho_b": rho_b, "n_b": n_b,
            "rho_w": rho_w, "n_w": n_w,
        })

        g_str = f"{rho_g:+.3f}" if not math.isnan(rho_g) else "  N/A"
        b_str = f"{rho_b:+.3f}" if not math.isnan(rho_b) else "  N/A"
        print(f"  Fold {year} | n={n_all:>2} | ρ={rho_all:+.3f} | "
              f"guards ρ={g_str} (n={n_g}) | bigs ρ={b_str} (n={n_b})")

        all_dfs.append(fold_df)

    combined = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
    return combined, fold_summaries, weights_by_year


# ── Task 4: Aggregate results ─────────────────────────────────────────────────

def task4_aggregate(fold_summaries: list[dict]) -> None:
    print("\n" + "=" * 76)
    print("  Task 4: Aggregate Results")
    print("=" * 76)

    rhos   = [s["rho"]   for s in fold_summaries if not math.isnan(s["rho"])]
    rhos_g = [s["rho_g"] for s in fold_summaries if not math.isnan(s["rho_g"])]
    rhos_b = [s["rho_b"] for s in fold_summaries if not math.isnan(s["rho_b"])]
    rhos_w = [s["rho_w"] for s in fold_summaries if not math.isnan(s["rho_w"])]

    mean_rho = float(np.mean(rhos)) if rhos else float("nan")
    std_rho  = float(np.std(rhos, ddof=1)) if len(rhos) > 1 else float("nan")

    # A. Per-fold ρ table
    print(f"\n  {'Year':<6}  {'n':>3}  {'ρ_fold':>7}  {'ρ_guards':>9}  "
          f"{'(n)':>4}  {'ρ_bigs':>7}  {'(n)':>4}  {'ρ_wings':>8}  {'(n)':>4}  Note")
    print("  " + "-" * 74)

    for s in fold_summaries:
        rg_s = f"{s['rho_g']:+.3f}" if not math.isnan(s["rho_g"]) else "   N/A"
        rb_s = f"{s['rho_b']:+.3f}" if not math.isnan(s["rho_b"]) else "   N/A"
        rw_s = f"{s['rho_w']:+.3f}" if not math.isnan(s["rho_w"]) else "   N/A"
        wing_note = " [n<10]" if s["n_w"] < 10 else ""
        print(f"  {s['year']:<6}  {s['n']:>3}  {s['rho']:>+7.3f}  {rg_s:>9}  "
              f"{s['n_g']:>4}  {rb_s:>7}  {s['n_b']:>4}  {rw_s:>8}  {s['n_w']:>4}  {wing_note}")

    print("  " + "-" * 74)

    def _fmt_agg(vals, label):
        if not vals:
            return f"  {label:<6}  {'':>3}  {'N/A':>7}"
        v = float(np.mean(vals))
        return f"  {label:<6}  {'':>3}  {v:>+7.3f}"

    mean_g = float(np.mean(rhos_g)) if rhos_g else float("nan")
    mean_b = float(np.mean(rhos_b)) if rhos_b else float("nan")
    mean_w = float(np.mean(rhos_w)) if rhos_w else float("nan")
    std_g  = float(np.std(rhos_g, ddof=1)) if len(rhos_g) > 1 else float("nan")
    std_b  = float(np.std(rhos_b, ddof=1)) if len(rhos_b) > 1 else float("nan")

    mg_s = f"{mean_g:>+7.3f}" if not math.isnan(mean_g) else "     N/A"
    mb_s = f"{mean_b:>+7.3f}" if not math.isnan(mean_b) else "     N/A"
    mw_s = f"{mean_w:>+7.3f}" if not math.isnan(mean_w) else "     N/A"
    sg_s = f"{std_g:>7.3f}"   if not math.isnan(std_g)  else "     N/A"
    sb_s = f"{std_b:>7.3f}"   if not math.isnan(std_b)  else "     N/A"

    print(f"  {'MEAN':<6}  {'':>3}  {mean_rho:>+7.3f}  {mg_s:>9}  {'':>4}  {mb_s:>7}  {'':>4}  {mw_s:>8}")
    print(f"  {'STD':<6}  {'':>3}  {std_rho:>7.3f}  {sg_s:>9}  {'':>4}  {sb_s:>7}")
    if rhos:
        print(f"  {'MIN':<6}  {'':>3}  {min(rhos):>+7.3f}")
        print(f"  {'MAX':<6}  {'':>3}  {max(rhos):>+7.3f}")

    # B. 95% CI
    n_folds = len(rhos)
    ci = 1.96 * std_rho / math.sqrt(n_folds) if n_folds > 1 and not math.isnan(std_rho) else float("nan")
    ci_lo = mean_rho - ci if not math.isnan(ci) else float("nan")
    ci_hi = mean_rho + ci if not math.isnan(ci) else float("nan")

    print(f"\n  B. 95% CI (mean ± 1.96×σ/√{n_folds}): [{ci_lo:+.3f}, {ci_hi:+.3f}]")

    # C. Comparison table
    print(f"\n  C. Comparison Table")
    print(f"  {'-'*60}")
    rows_c = [
        (f"LOYO mean ρ ({n_folds} folds, ~586 pts)", f"{mean_rho:+.3f}"),
        (f"LOYO 95% CI",                             f"[{ci_lo:+.3f}, {ci_hi:+.3f}]"),
        ("Single 2022 holdout (current)",             "  0.400"),
        ("Single 2022 holdout 95% CI",               "[~0.27, ~0.53]"),
        ("BPM×age (Model A, old scorer)",             "  0.241"),
        ("Ridge ceiling (Model B, 2022 only)",        "  0.430"),
    ]
    for label, val in rows_c:
        print(f"  {label:<44}  {val}")
    print(f"  {'-'*60}")

    # E. Position ρ consistency (before D to print while context is fresh)
    print(f"\n  E. Position ρ Consistency Across 12 Folds")
    print(f"  Guards: mean={mean_g:+.3f}  std={std_g:.3f}  (2022 holdout was +0.225)")
    print(f"  Bigs:   mean={mean_b:+.3f}  std={std_b:.3f}  (2022 holdout was +0.304)")

    # F. Best/worst draft classes
    sorted_folds = sorted(fold_summaries, key=lambda s: s["rho"], reverse=True)
    print(f"\n  F. Best/Worst Draft Classes")
    print(f"  Top 3:")
    for s in sorted_folds[:3]:
        print(f"    {s['year']}: ρ={s['rho']:+.3f}  (n={s['n']})")
    print(f"  Bottom 3:")
    for s in sorted_folds[-3:]:
        print(f"    {s['year']}: ρ={s['rho']:+.3f}  (n={s['n']})")


# ── Task 5: Weight drift table ────────────────────────────────────────────────

def task5_weight_drift(
    weights_by_year: dict[int, dict[str, dict[str, float]]]
) -> None:
    print("\n" + "=" * 76)
    print("  Task 5: Feature Weight Drift Across Folds (overall weights)")
    print("=" * 76)

    years = sorted(weights_by_year.keys())
    if not years:
        print("  No fold data available.")
        return

    # Collect per-feature weights across folds
    feat_weights: dict[str, list[float]] = {f: [] for f in ALL_LOYO_FEATURES}
    for year in years:
        w = weights_by_year[year].get("overall", {})
        for feat in ALL_LOYO_FEATURES:
            feat_weights[feat].append(w.get(feat, 0.0))

    live_w = FEATURE_WEIGHTS

    # Header
    yr_cols = "  ".join(f"{str(y)[2:]:>4}" for y in years)
    print(f"\n  {'Feature':<22}  {yr_cols}  {'Live':>6}  {'Mean':>6}  {'Std':>6}  {'CV':>6}  Flags")
    print("  " + "-" * (22 + len(years) * 6 + 32))

    feat_cv: dict[str, float] = {}
    zeroed_features: list[str] = []

    for feat in ALL_LOYO_FEATURES:
        vals = feat_weights[feat]
        mean_w = float(np.mean(vals))
        std_w  = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
        cv     = std_w / mean_w if mean_w > 1e-6 else float("inf")
        feat_cv[feat] = cv

        w_cols = "  ".join(f"{v:>4.3f}" for v in vals)
        live   = live_w.get(feat, 0.0)

        flags = ""
        zero_folds = [years[i] for i, v in enumerate(vals) if v < 1e-6]
        if zero_folds:
            flags += f"[zero in {','.join(str(y)[2:] for y in zero_folds)}]"
            zeroed_features.append(feat)

        print(f"  {feat:<22}  {w_cols}  {live:>6.3f}  {mean_w:>6.3f}  {std_w:>6.4f}  {cv:>6.3f}  {flags}")

    # D. Stability summary
    sorted_by_cv = sorted(feat_cv.items(), key=lambda x: x[1])
    print(f"\n  D. Weight Stability Summary (CV = std/mean)")
    print(f"  Top 10 most stable (low CV):")
    for feat, cv in sorted_by_cv[:10]:
        print(f"    {feat:<26}  CV={cv:.3f}")
    print(f"  Top 5 most unstable (high CV):")
    for feat, cv in sorted_by_cv[-5:]:
        flag = " ← zero in some folds" if feat in zeroed_features else ""
        print(f"    {feat:<26}  CV={cv:.3f}{flag}")

    if zeroed_features:
        print(f"\n  Features zeroed in ≥1 fold: {zeroed_features}")
        print(f"  (r<0 or n<10 in that training subset — potential removal candidates)")


# ── Task 6: LOYO 2022 vs live model ──────────────────────────────────────────

def task6_live_comparison(
    full_df: pd.DataFrame, weights_by_year: dict[int, dict[str, dict[str, float]]]
) -> None:
    print("\n" + "=" * 76)
    print("  Task 6: LOYO 2022 vs Live Model on 2022 Holdout")
    print("=" * 76)

    # Load 2022 holdout separately — full_df only contains ≤2021 rows
    df_raw_all_t6 = pd.read_csv(DATASET_PATH)
    hold22 = df_raw_all_t6[(df_raw_all_t6["draft_year"] == 2022) & df_raw_all_t6[TARGET].notna()].copy()
    combine_t6 = load_combine()
    hold22 = join_combine(hold22, combine_t6)
    hold22 = add_derived(hold22)
    hold22["pos_group"] = hold22["position"].apply(_pos_group_csv)

    vorp22 = hold22[TARGET]
    params = TrainingParams()

    # ── A. Live model (hardcoded weights + hardcoded normalization) ───────────
    live_scores: dict[int, float] = {}
    for idx, row in hold22.iterrows():
        pos_full = str(row.get("position", ""))
        pos_abbrev = _POSITION_ABBREV.get(pos_full.split(",")[0].strip(), "SF")
        stats = row.to_dict()
        bpm = stats.get("bpm_college")
        if bpm is None or (isinstance(bpm, float) and math.isnan(bpm)):
            live_scores[idx] = float("nan")
            continue
        composite = compute_mps_for_prospect(stats, params, pos_abbrev)
        srs = stats.get("program_srs")
        srs_v = float(srs) if (srs is not None and not (isinstance(srs, float) and math.isnan(srs))) else None
        srs_adj = compute_srs_adj(srs_v)
        gp = stats.get("games_played")
        gp_v = float(gp) if (gp is not None and not (isinstance(gp, float) and math.isnan(gp))) else None
        avail = compute_availability_modifier(gp_v, team_games=33)
        da = stats.get("draft_age")
        age_pen = compute_age_penalty(float(da)) if (da is not None and not (isinstance(da, float) and math.isnan(da))) else 0.0
        hf_pen = compute_height_floor_penalty(stats)
        mps = float(np.clip(composite + srs_adj + avail + age_pen + hf_pen, 0, 100))
        live_scores[idx] = mps

    live_mps = pd.Series(live_scores)
    rho_live, n_live = _spearman(live_mps, vorp22)

    # ── B. LOYO 2022 fold (weights derived from 2010–2021 only) ─────────────
    # full_df = 2010–2021 training set; hold22 is the 2022 holdout (already loaded)
    loyo_df_2022 = pd.concat([full_df, hold22], ignore_index=True)

    loyo_fold_df, _ = run_loyo_fold(2022, loyo_df_2022)

    if loyo_fold_df is not None and not loyo_fold_df.empty:
        rho_loyo22, n_loyo22 = _spearman(loyo_fold_df["mps"], loyo_fold_df[TARGET])
    else:
        rho_loyo22, n_loyo22 = float("nan"), 0

    print(f"\n  {'Method':<44}  {'ρ':>7}  {'n':>3}")
    print("  " + "-" * 58)
    print(f"  {'Live model (hardcoded weights + stats)':<44}  {rho_live:>+7.3f}  {n_live:>3}")
    rloyo_s = f"{rho_loyo22:>+7.3f}" if not math.isnan(rho_loyo22) else "    N/A"
    print(f"  {'LOYO fold 2022 (weights from 2010-2021)':<44}  {rloyo_s}  {n_loyo22:>3}")

    if not math.isnan(rho_live) and not math.isnan(rho_loyo22):
        diff = rho_live - rho_loyo22
        verdict = "potential overfit to 2022" if abs(diff) > 0.02 else "no meaningful overfit"
        print(f"\n  Δ = {diff:+.3f}  →  {verdict}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("MPS LOYO Cross-Validation  |  Leave-One-Year-Out  |  2010–2021")
    print(f"Feature set: {len(ALL_LOYO_FEATURES)} features (same as live model)")
    print()

    full_df = load_data()

    combined, fold_summaries, weights_by_year = run_all_folds(full_df)

    task4_aggregate(fold_summaries)

    task5_weight_drift(weights_by_year)

    task6_live_comparison(full_df, weights_by_year)

    print("\n" + "=" * 76)
    print("  LOYO validation complete.")
    print("=" * 76)


if __name__ == "__main__":
    main()
