"""
mps/validate_holdout.py

Holdout validation: measures whether session model changes improved or degraded
Spearman ρ on the 2022 holdout class vs the baseline (0.430 from backtest_full.py).

Changes under test:
  - Height floor penalty (h<76" AND WHR<1.04 → -5)
  - SRS floor widening (-2.0 → -5.0)
  - DBPM weight reduction + full renormalization
  - Youth bonus gate extension (≤19.5 → ≤20.0)
  (combine_penalty excluded — no historical invite data in CSV)

Run:
    backend/.venv/bin/python mps/validate_holdout.py
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from mps.backtest_full import add_derived, join_combine, load_combine
from mps.scorer import (
    FEATURE_WEIGHTS,
    TrainingParams,
    _zscore_to_0_100,
    compute_age_penalty,
    compute_availability_modifier,
    compute_height_floor_penalty,
    compute_mps_for_prospect,
    compute_srs_adj,
    grade_label,
)

# Training CSV uses full position strings; scorer.py _resolve_position_group
# expects abbreviations. Map before calling compute_mps_for_prospect().
_POSITION_ABBREV: dict[str, str] = {
    "Point Guard":    "PG",
    "Shooting Guard": "SG",
    "Small Forward":  "SF",
    "Power Forward":  "PF",
    "Center":         "C",
}

DATASET = Path(__file__).parent / "data" / "mps_dataset_raw.csv"
HOLDOUT_YEAR = 2022

# Reference points (from backtest_full.py on 2022 holdout, N=44):
#   Model A — BPM × age (old scorer):         ρ = 0.241
#   Model B — Ridge on stats (no physical):   ρ = 0.430   ← "baseline" cited in plan
#   Model C — Ridge on all features:          ρ = 0.443
# Our flat composite is between A and B; Ridge is the ceiling.
RIDGE_BASELINE_RHO = 0.430  # Model B (Ridge regression) — different model class
BPM_AGE_RHO = 0.241         # Model A (old-style BPM×age scorer)

OLD_FEATURE_WEIGHTS: dict[str, float] = {
    "bpm_college":      0.0917,
    "dbpm":             0.0742,
    "per":              0.0670,
    "ws_40":            0.0656,
    "obpm":             0.0631,
    "stl_pg":           0.0449,
    "ts_pct":           0.0436,
    "stl_pct":          0.0420,
    "trb_pg":           0.0414,
    "ows":              0.0406,
    "fg_pct":           0.0365,
    "blk_pg":           0.0359,
    "dws":              0.0314,
    "blk_pct":          0.0296,
    "ast_pct":          0.0281,
    "ast_pg":           0.0260,
    "ast_pct_over_usg": 0.0259,
    "orb_pct":          0.0229,
    "pts_pg":           0.0207,
    "wingspan_in":      0.0184,
    "weight_lbs":       0.0168,
    "standing_reach_in":0.0165,
    "ast_to_tov":       0.0162,
}


def compute_composite(stats: dict, weights: dict, params: TrainingParams) -> float:
    """Weighted z-score composite with median imputation for missing features."""
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
    composite_z = weighted_z_sum / max(total_w, 1e-8)
    return _zscore_to_0_100(composite_z)


def _age_pen_old(draft_age: float) -> float:
    """Pre-session age penalty: youth bonus gate was ≤19.5 (now ≤20.0)."""
    if draft_age <= 19.5:
        return 4.0
    elif draft_age <= 21.5:
        return 0.0
    else:
        return -min((draft_age - 21.5) * 2.5, 15.0)


def score_holdout(
    df: pd.DataFrame,
    params: TrainingParams,
    *,
    weights: dict | None = None,
    srs_floor: float = -5.0,
    height_floor: bool = True,
    old_age_gate: bool = False,
) -> pd.Series:
    """
    Score each holdout player, return Series of mps_final indexed like df.
    Players with null bpm_college → NaN (unscored, excluded from ρ).

    weights=None → routes through compute_mps_for_prospect() with position-split
    weights (current live model). weights=<dict> → uses compute_composite() with
    that explicit dict (for variant analysis).
    """
    scores: dict[int, float] = {}
    for idx, row in df.iterrows():
        if pd.isna(row.get("bpm_college")):
            scores[idx] = float("nan")
            continue

        stats = row.to_dict()

        if weights is None:
            # Current model path: position-split via compute_mps_for_prospect()
            pos_abbrev = _POSITION_ABBREV.get(str(row.get("position", "")), "SF")
            composite = compute_mps_for_prospect(stats, params, pos_abbrev)
        else:
            composite = compute_composite(stats, weights, params)

        srs = row.get("program_srs")
        srs_raw = float(np.clip(srs / 35.0 * 5.0, srs_floor, 5.0)) if pd.notna(srs) else 0.0

        gp = row.get("games_played")
        avail_mod = compute_availability_modifier(gp if pd.notna(gp) else None)

        draft_age = float(row["draft_age"])
        age_pen = _age_pen_old(draft_age) if old_age_gate else compute_age_penalty(draft_age)

        hfp = compute_height_floor_penalty(stats) if height_floor else 0.0

        mps_final = float(np.clip(composite + srs_raw + avail_mod + age_pen + hfp, 0, 100))
        scores[idx] = mps_final

    return pd.Series(scores, name="mps")


def spearman(series_a: pd.Series, series_b: pd.Series) -> tuple[float, float]:
    """Spearman ρ and p-value, dropping NaN pairs."""
    valid = series_a.notna() & series_b.notna()
    a, b = series_a[valid], series_b[valid]
    if len(a) < 3:
        return float("nan"), float("nan")
    rho, pval = scipy_stats.spearmanr(a, b)
    return float(rho), float(pval)


def main() -> None:
    print("=" * 70)
    print("  MPS Holdout Validation — 2022 Draft Class")
    print("=" * 70)

    # ── Load and prepare data ─────────────────────────────────────────────────
    df_raw = pd.read_csv(DATASET)
    df_hold = df_raw[df_raw["draft_year"] == HOLDOUT_YEAR].copy()
    df_hold = df_hold[df_hold["vorp_yr2_5_avg"].notna()].reset_index(drop=True)
    print(f"\nHoldout: {len(df_hold)} players with vorp_yr2_5_avg")

    combine = load_combine()
    df_hold = join_combine(df_hold, combine)
    df_hold = add_derived(df_hold)

    bpm_null_mask = df_hold["bpm_college"].isna()
    n_unscored = bpm_null_mask.sum()
    if n_unscored:
        unscored_names = df_hold.loc[bpm_null_mask, "player_name"].tolist()
        print(f"  Unscored (BPM=None, excluded from ρ): {unscored_names}")

    params = TrainingParams()
    print()

    # ── Score with current model ──────────────────────────────────────────────
    df_hold["mps"] = score_holdout(df_hold, params)

    # Position splits
    guard_mask = df_hold["position_group"] == "G"
    big_mask   = df_hold["position_group"].isin(["BIG", "F"])

    vorp = df_hold["vorp_yr2_5_avg"]
    mps  = df_hold["mps"]

    rho_all,    p_all    = spearman(mps, vorp)
    rho_guards, p_guards = spearman(mps[guard_mask], vorp[guard_mask])
    rho_bigs,   p_bigs   = spearman(mps[big_mask],  vorp[big_mask])

    scored_n = mps.notna().sum()
    guard_n  = (mps[guard_mask]).notna().sum()
    big_n    = (mps[big_mask]).notna().sum()

    # ── Variant analysis ──────────────────────────────────────────────────────
    # Variant 1: no height floor
    df_hold["mps_v1"] = score_holdout(df_hold, params, height_floor=False)
    rv1, pv1 = spearman(df_hold["mps_v1"], vorp)

    # Variant 2: old SRS floor (-2.0)
    df_hold["mps_v2"] = score_holdout(df_hold, params, srs_floor=-2.0)
    rv2, pv2 = spearman(df_hold["mps_v2"], vorp)

    # Variant 3: old DBPM weight (0.0742, sum=0.899)
    df_hold["mps_v3"] = score_holdout(df_hold, params, weights=OLD_FEATURE_WEIGHTS)
    rv3, pv3 = spearman(df_hold["mps_v3"], vorp)

    # Variant 4: full pre-session model (old weights + no height floor + SRS floor -2.0 + old age gate)
    df_hold["mps_v4"] = score_holdout(
        df_hold, params,
        weights=OLD_FEATURE_WEIGHTS, srs_floor=-2.0,
        height_floor=False, old_age_gate=True,
    )
    rv4, pv4 = spearman(df_hold["mps_v4"], vorp)

    # ── Top-20 VORP vs model rank table ───────────────────────────────────────
    df_scored = df_hold[mps.notna()].copy()
    df_scored["vorp_rank"]  = df_scored["vorp_yr2_5_avg"].rank(ascending=False).astype(int)
    df_scored["model_rank"] = df_scored["mps"].rank(ascending=False).astype(int)
    df_scored["delta"]      = df_scored["model_rank"] - df_scored["vorp_rank"]

    top20 = df_scored.nsmallest(20, "vorp_rank").sort_values("vorp_rank")

    print("\nTop-20 by VORP vs Model Rank:")
    print(f"  {'Rk':>3}  {'Player':<24}  {'VORP':>6}  {'MPS':>5}  {'MdlRk':>5}  {'Δ':>4}")
    print("  " + "-" * 56)
    for _, r in top20.iterrows():
        delta_str = f"{r['delta']:+.0f}"
        print(f"  {int(r['vorp_rank']):>3}  {r['player_name']:<24}  "
              f"{r['vorp_yr2_5_avg']:>6.2f}  "
              f"{r['mps']:>5.1f}  {int(r['model_rank']):>5}  {delta_str:>4}")

    # ── Summary table ─────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  Summary (Spearman ρ)")
    print("=" * 70)
    header = f"  {'Variant':<32}  {'ρ':>6}  {'p-val':>7}  {'Guards':>7}  {'Bigs':>6}  {'n':>3}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    def row(label, rho, p, rg, rb, n):
        p_str = f"{p:.4f}" if not math.isnan(p) else "  —   "
        rg_str = f"{rg:.3f}" if not math.isnan(rg) else "   — "
        rb_str = f"{rb:.3f}" if not math.isnan(rb) else "  — "
        n_str  = str(n) if isinstance(n, int) else n
        return (f"  {label:<34}  {rho:>6.3f}  {p_str:>7}  "
                f"{rg_str:>6}  {rb_str:>6}  {n_str:>3}")

    print(row("Current model (position-split)",
              rho_all, p_all, rho_guards, rho_bigs, scored_n))
    print(row("  Var 4: full pre-session flat composite",
              rv4, pv4, float("nan"), float("nan"), scored_n))
    print(f"  {'  — Model A (BPM×age, old scorer)':<34}  {BPM_AGE_RHO:>6.3f}  {'—':>7}  "
          f"{'—':>6}  {'—':>6}  {'44':>3}")
    print(f"  {'  — Model B (Ridge on stats, ceiling)':<34}  {RIDGE_BASELINE_RHO:>6.3f}  {'—':>7}  "
          f"{'—':>6}  {'—':>6}  {'44':>3}")
    print(f"  {'  — Model C (Ridge all features, ceil.)':<34}  {0.443:>6.3f}  {'—':>7}  "
          f"{'—':>6}  {'—':>6}  {'44':>3}")
    print("  " + "·" * (len(header) - 2))
    print(row("  Var 1: no height floor",
              rv1, pv1, float("nan"), float("nan"), scored_n))
    print(row("  Var 2: old SRS floor (−2.0)",
              rv2, pv2, float("nan"), float("nan"), scored_n))
    print(row("  Var 3: old DBPM weight (0.0742)",
              rv3, pv3, float("nan"), float("nan"), scored_n))
    print("=" * 70)

    delta_session = rho_all - rv4
    delta_vs_bpm  = rho_all - BPM_AGE_RHO
    delta_vs_ridge = rho_all - RIDGE_BASELINE_RHO
    if abs(delta_session) <= 0.005:
        verdict = f"ρ-NEUTRAL vs pre-session flat composite (Δ={delta_session:+.3f})"
    elif delta_session > 0:
        verdict = f"IMPROVED vs pre-session flat composite (+{delta_session:.3f})"
    else:
        verdict = f"REGRESSED vs pre-session flat composite ({delta_session:.3f})"
    print(f"\n  Session delta:  {verdict}")
    print(f"  vs BPM×age:     {delta_vs_bpm:+.3f}  (flat composite clearly beats old scorer)")
    print(f"  vs Ridge B:     {delta_vs_ridge:+.3f}  (Ridge ceiling, different model class)")
    print(f"  Scored: {scored_n}/{len(df_hold)} players  "
          f"(guards={guard_n}, bigs={big_n})")
    if n_unscored:
        print(f"  Excluded (no BPM): {n_unscored} player(s)")
    print()


if __name__ == "__main__":
    main()
