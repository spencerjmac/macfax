"""
mps/position_split_backtest.py

Task 1: Position-stratified Pearson r correlation analysis — derive GUARDS_WEIGHTS
        and BIGS_WEIGHTS from training data.
Task 2: 2022 holdout validation — compare universal vs position-split scoring.

Run:
    backend/.venv/bin/python -m mps.position_split_backtest
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from mps.backtest_full import (
    TARGET,
    add_derived,
    compute_correlations,
    join_combine,
    load_combine,
)
from mps.scorer import (
    FEATURE_WEIGHTS,
    TrainingParams,
    _zscore_to_0_100,
    compute_age_penalty,
    compute_availability_modifier,
    compute_srs_adj,
)

DATASET = Path(__file__).parent / "data" / "mps_dataset_raw.csv"
FEATURES = list(FEATURE_WEIGHTS.keys())

GUARD_POSITIONS = {"Point Guard", "Shooting Guard"}
BIG_POSITIONS   = {"Power Forward", "Center"}
WING_POSITIONS  = {"Small Forward"}


def _pos_group_csv(pos: str) -> str:
    if pos in GUARD_POSITIONS: return "guard"
    if pos in BIG_POSITIONS:   return "big"
    if pos in WING_POSITIONS:  return "wing"
    return "other"


def _normalize_weights(corr_rows: list[dict], min_floor: float = 0.005) -> dict[str, float]:
    """
    Derive normalized weight dict from correlation rows.
    raw = abs(r); if abs(r) < 0.03 → floor to min_floor. Normalize to sum=1.
    """
    raw: dict[str, float] = {}
    for row in corr_rows:
        feat = row["feature"]
        r = row.get("r")
        if r is None:
            raw[feat] = min_floor
        elif abs(r) < 0.03:
            raw[feat] = min_floor
        else:
            raw[feat] = abs(r)
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}


def _composite(stats: dict, weights: dict, params: TrainingParams) -> float:
    """Weighted z-score composite with median imputation."""
    weighted_z_sum = 0.0
    total_w = 0.0
    for feat, w in weights.items():
        mean, std, median = params.feat_stats[feat]
        val = stats.get(feat)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            val = median
        z = (float(val) - mean) / max(std, 1e-8)
        weighted_z_sum += w * z
        total_w += w
    return _zscore_to_0_100(weighted_z_sum / max(total_w, 1e-8))


def _score_holdout(df: pd.DataFrame, params: TrainingParams, weights_map: dict[str, dict]) -> pd.Series:
    """
    Score holdout players. weights_map maps position_group → weights dict.
    BPM-null players → NaN. No height_floor or combine_penalty.
    """
    scores: dict[int, float] = {}
    for idx, row in df.iterrows():
        if pd.isna(row.get("bpm_college")):
            scores[idx] = float("nan")
            continue
        grp = _pos_group_csv(str(row.get("position", "")))
        weights = weights_map.get(grp, weights_map.get("guard", FEATURE_WEIGHTS))
        stats = row.to_dict()
        composite = _composite(stats, weights, params)
        srs = row.get("program_srs")
        srs_adj = float(np.clip(srs / 35.0 * 5.0, -5.0, 5.0)) if pd.notna(srs) else 0.0
        gp = row.get("games_played")
        avail_mod = compute_availability_modifier(gp if pd.notna(gp) else None)
        age_pen = compute_age_penalty(float(row["draft_age"]))
        mps = float(np.clip(composite + srs_adj + avail_mod + age_pen, 0, 100))
        scores[idx] = mps
    return pd.Series(scores)


def _spearman(a: pd.Series, b: pd.Series) -> tuple[float, int]:
    valid = a.notna() & b.notna()
    a2, b2 = a[valid], b[valid]
    if len(a2) < 3:
        return float("nan"), 0
    rho, _ = scipy_stats.spearmanr(a2, b2)
    return float(rho), int(valid.sum())


def main() -> None:
    print("=" * 72)
    print("  Position-Split Feature Weights — Correlation Analysis + Holdout")
    print("=" * 72)

    # ── Load and prepare ─────────────────────────────────────────────────────
    df_raw = pd.read_csv(DATASET)
    combine = load_combine()
    df_raw = join_combine(df_raw, combine)
    df_raw = add_derived(df_raw)

    params = TrainingParams()
    print()

    # ── Task 1: Correlation analysis ─────────────────────────────────────────
    df_train = df_raw[(df_raw["draft_year"] <= 2021) & df_raw[TARGET].notna()].copy()
    df_train["_grp"] = df_train["position"].apply(_pos_group_csv)

    guards_df = df_train[df_train["_grp"] == "guard"]
    bigs_df   = df_train[df_train["_grp"] == "big"]
    wings_df  = df_train[df_train["_grp"] == "wing"]
    other_df  = df_train[df_train["_grp"] == "other"]

    print(f"Training set (≤2021, vorp not null): {len(df_train)} rows")
    for label, grp_df in [("Guards", guards_df), ("Bigs", bigs_df),
                           ("Wings", wings_df), ("Other", other_df)]:
        warn = "  ← WARNING: < 30 rows" if len(grp_df) < 30 else ""
        print(f"  {label}: {len(grp_df)}{warn}")

    corr_guards = compute_correlations(guards_df, FEATURES)
    corr_bigs   = compute_correlations(bigs_df, FEATURES)
    corr_wings  = compute_correlations(wings_df, FEATURES)
    corr_all    = compute_correlations(df_train, FEATURES)

    # Build lookup dicts for easy access
    rg = {c["feature"]: c["r"] for c in corr_guards}
    rb = {c["feature"]: c["r"] for c in corr_bigs}
    rw = {c["feature"]: c["r"] for c in corr_wings}
    ra = {c["feature"]: c["r"] for c in corr_all}

    # Side-by-side table sorted by abs split
    print("\n  Feature Correlations vs vorp_yr2_5_avg:")
    print(f"  {'Feature':<22}  {'r_guards':>9}  {'r_bigs':>8}  {'r_wings':>8}  {'r_all':>8}  {'|split|':>8}")
    print("  " + "-" * 72)
    rows_sorted = sorted(FEATURES, key=lambda f: abs((rg.get(f) or 0) - (rb.get(f) or 0)), reverse=True)
    for feat in rows_sorted:
        rg_v  = rg.get(feat)
        rb_v  = rb.get(feat)
        rw_v  = rw.get(feat)
        ra_v  = ra.get(feat)
        split = abs((rg_v or 0) - (rb_v or 0))
        def fmt(v): return f"{v:>+8.3f}" if v is not None else "     N/A"
        print(f"  {feat:<22}  {fmt(rg_v)}  {fmt(rb_v)}  {fmt(rw_v)}  {fmt(ra_v)}  {split:>8.3f}")

    # Derive weights
    guards_w = _normalize_weights(corr_guards)
    bigs_w   = _normalize_weights(corr_bigs)

    print(f"\n  GUARDS_WEIGHTS (n={len(guards_df)}, sum={sum(guards_w.values()):.4f}):")
    print("  GUARDS_WEIGHTS: dict[str, float] = {")
    for feat in FEATURES:
        print(f'      "{feat}":{" " * (22 - len(feat))}{guards_w[feat]:.4f},')
    print("  }")
    print(f"\n  BIGS_WEIGHTS (n={len(bigs_df)}, sum={sum(bigs_w.values()):.4f}):")
    print("  BIGS_WEIGHTS: dict[str, float] = {")
    for feat in FEATURES:
        print(f'      "{feat}":{" " * (22 - len(feat))}{bigs_w[feat]:.4f},')
    print("  }")

    # Wings info only
    print(f"\n  Wings correlations (n={len(wings_df)}, reference only):")
    for feat in FEATURES:
        v = rw.get(feat)
        print(f"    {feat:<22}  {fmt(v)}")

    # ── Task 2: Holdout validation ────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  Task 2: 2022 Holdout Validation")
    print("=" * 72)

    df_hold = df_raw[(df_raw["draft_year"] == 2022) & df_raw[TARGET].notna()].copy()
    df_hold["_grp"] = df_hold["position"].apply(_pos_group_csv)

    vorp = df_hold[TARGET]

    # Wing blend
    blended_w = {f: guards_w.get(f, 0) * 0.5 + bigs_w.get(f, 0) * 0.5 for f in guards_w}
    blend_total = sum(blended_w.values())
    blended_w = {k: v / blend_total for k, v in blended_w.items()}

    # Score A: universal
    mps_a = _score_holdout(df_hold, params, {"guard": FEATURE_WEIGHTS, "big": FEATURE_WEIGHTS, "wing": FEATURE_WEIGHTS})
    # Score B: split + wing blend
    mps_b = _score_holdout(df_hold, params, {"guard": guards_w, "big": bigs_w, "wing": blended_w})
    # Score C: split + wing = guards
    mps_c = _score_holdout(df_hold, params, {"guard": guards_w, "big": bigs_w, "wing": guards_w})

    g_mask = df_hold["_grp"] == "guard"
    b_mask = df_hold["_grp"] == "big"
    w_mask = df_hold["_grp"] == "wing"

    def rho_row(label, mps):
        r_all,  n_all  = _spearman(mps,         vorp)
        r_g,    n_g    = _spearman(mps[g_mask],  vorp[g_mask])
        r_b,    n_b    = _spearman(mps[b_mask],  vorp[b_mask])
        r_w,    n_w    = _spearman(mps[w_mask],  vorp[w_mask])
        def fs(v): return f"{v:>+6.3f}" if not math.isnan(v) else "   — "
        return (f"  {label:<30}  {fs(r_all)} ({n_all:>2})  {fs(r_g)} ({n_g:>2})  "
                f"{fs(r_b)} ({n_b:>2})  {fs(r_w)} ({n_w:>2})")

    print(f"\n  {'Method':<30}  {'ρ_all (n)':>10}  {'ρ_guards (n)':>12}  "
          f"{'ρ_bigs (n)':>11}  {'ρ_wings (n)':>12}")
    print("  " + "-" * 72)
    print(rho_row("Score A: universal weights", mps_a))
    print(rho_row("Score B: split + wing blend", mps_b))
    print(rho_row("Score C: split + wing=guards", mps_c))

    # Stop rule evaluation
    rho_a_all, _ = _spearman(mps_a, vorp)
    rho_b_all, _ = _spearman(mps_b, vorp)
    rho_c_all, _ = _spearman(mps_c, vorp)
    rho_a_g, _   = _spearman(mps_a[g_mask], vorp[g_mask])
    rho_b_g, _   = _spearman(mps_b[g_mask], vorp[g_mask])
    rho_c_g, _   = _spearman(mps_c[g_mask], vorp[g_mask])

    best_all = max(rho_b_all, rho_c_all)
    best_g   = max(rho_b_g,   rho_c_g)

    print()
    if best_all - rho_a_all >= 0.010 or best_g - rho_a_g >= 0.010:
        if rho_b_all >= rho_c_all:
            wing_choice = "blend (Score B)"
        else:
            wing_choice = "guards weights (Score C)"
        print(f"  RESULT: Position-split VALIDATES.")
        print(f"  Wing assignment: {wing_choice}")
        print(f"  Δρ_all={best_all - rho_a_all:+.3f}  Δρ_guards={best_g - rho_a_g:+.3f}")
        print(f"\n  → Implement Task 3 (scorer.py modification).")
    else:
        print(f"  WARNING: Position-split does NOT meet threshold.")
        print(f"  Best Δρ_all={best_all - rho_a_all:+.3f} (need ≥+0.010)")
        print(f"  Best Δρ_guards={best_g - rho_a_g:+.3f} (need ≥+0.010)")
        print(f"\n  → Do NOT modify scorer.py.")

    print()


if __name__ == "__main__":
    main()
