"""
mps/age_penalty_investigation.py

Task 1: Full divergence audit — model vs Tankathon consensus, categorized by age.
Task 2: Test 4 age penalty curves on 2022 holdout Spearman ρ.
Task 3: Preview penalty changes on 2026 prospects under winning curve.

Run:
    backend/.venv/bin/python -m mps.age_penalty_investigation
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from mps.backtest_full import add_derived, join_combine, load_combine
from mps.scorer import (
    TrainingParams,
    compute_availability_modifier,
    compute_height_floor_penalty,
    compute_mps_for_prospect,
    compute_srs_adj,
)

BOARD_PATH   = Path(__file__).parent / "output" / "2026_big_board.csv"
DATASET_PATH = Path(__file__).parent / "data"   / "mps_dataset_raw.csv"
HOLDOUT_YEAR = 2022
TARGET       = "vorp_yr2_5_avg"

_POSITION_ABBREV: dict[str, str] = {
    "Point Guard":    "PG",
    "Shooting Guard": "SG",
    "Small Forward":  "SF",
    "Power Forward":  "PF",
    "Center":         "C",
}


# ── Age penalty curves ────────────────────────────────────────────────────────

def _curve_a(age: float) -> float:
    """Current: ≤20.0 → +4.0, 20-21.5 → 0, >21.5 → -2.5/yr, cap -15."""
    if age <= 20.0:
        return 4.0
    if age <= 21.5:
        return 0.0
    return -min((age - 21.5) * 2.5, 15.0)


def _curve_b(age: float) -> float:
    """Steeper, earlier: ≤20.0 → +4.0, 20-21.0 → 0, >21.0 → -3.5/yr, cap -15."""
    if age <= 20.0:
        return 4.0
    if age <= 21.0:
        return 0.0
    return -min((age - 21.0) * 3.5, 15.0)


def _curve_c(age: float) -> float:
    """Steeper same start: ≤20.0 → +4.0, 20-21.5 → 0, >21.5 → -3.5/yr, cap -15."""
    if age <= 20.0:
        return 4.0
    if age <= 21.5:
        return 0.0
    return -min((age - 21.5) * 3.5, 15.0)


def _curve_d(age: float) -> float:
    """Much steeper, earlier: ≤20.0 → +5.0, 20-21.0 → 0, >21.0 → -4.0/yr, cap -15."""
    if age <= 20.0:
        return 5.0
    if age <= 21.0:
        return 0.0
    return -min((age - 21.0) * 4.0, 15.0)


CURVES = {
    "A": (_curve_a, "-2.5/yr", "21.5"),
    "B": (_curve_b, "-3.5/yr", "21.0"),
    "C": (_curve_c, "-3.5/yr", "21.5"),
    "D": (_curve_d, "-4.0/yr", "21.0"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _spearman(a: pd.Series, b: pd.Series) -> tuple[float, int]:
    valid = a.notna() & b.notna()
    a2, b2 = a[valid], b[valid]
    if len(a2) < 3:
        return float("nan"), 0
    rho, _ = scipy_stats.spearmanr(a2, b2)
    return float(rho), int(valid.sum())


def _score_holdout_with_curve(
    df: pd.DataFrame,
    params: TrainingParams,
    age_fn,
) -> pd.Series:
    """Score holdout using current scorer weights + specified age curve.
    BPM-null → NaN. No combine_penalty (no historical invite data).
    """
    scores: dict[int, float] = {}
    for idx, row in df.iterrows():
        if pd.isna(row.get("bpm_college")):
            scores[idx] = float("nan")
            continue
        pos_abbrev = _POSITION_ABBREV.get(str(row.get("position", "")), "SF")
        stats = row.to_dict()
        composite = compute_mps_for_prospect(stats, params, pos_abbrev)
        srs = row.get("program_srs")
        srs_adj = float(np.clip(srs / 35.0 * 5.0, -5.0, 5.0)) if pd.notna(srs) else 0.0
        gp = row.get("games_played")
        avail_mod = compute_availability_modifier(gp if pd.notna(gp) else None)
        hfp = compute_height_floor_penalty(stats)
        age_pen = age_fn(float(row["draft_age"]))
        mps = float(np.clip(composite + srs_adj + avail_mod + age_pen + hfp, 0, 100))
        scores[idx] = mps
    return pd.Series(scores)


# ── Task 1: Divergence audit ──────────────────────────────────────────────────

def task1_divergence_audit() -> None:
    print("=" * 90)
    print("  Task 1: 2026 Model vs Tankathon Divergence Audit")
    print("=" * 90)

    df = pd.read_csv(BOARD_PATH)
    df_div = df[df["tankathon_rank"].notna() & df["mps"].notna()].copy()

    # rank column is 1-based already; use it as model_rank
    df_div["model_rank"] = df_div["rank"].astype(int)
    df_div["tankathon_rank"] = df_div["tankathon_rank"].astype(int)
    df_div["divergence"] = df_div["tankathon_rank"] - df_div["model_rank"]

    def categorize(row):
        if row["divergence"] > 10 and row["draft_age"] > 21.5:
            return "age_likely"
        if row["divergence"] < -10 and row["draft_age"] < 20.5:
            return "youth_likely"
        return "other"

    df_div["category"] = df_div.apply(categorize, axis=1)
    df_div = df_div.sort_values("divergence", ascending=False)

    print(f"\n  {'Player':<24}  {'Age':>5}  {'Pos':>4}  {'MPS':>5}  "
          f"{'TankRk':>7}  {'MdlRk':>6}  {'Div':>5}  {'AgePen':>7}  Category")
    print("  " + "-" * 84)
    for _, r in df_div.iterrows():
        age_pen = r.get("age_penalty", 0.0)
        age_pen_str = f"{age_pen:+.1f}" if pd.notna(age_pen) else "  — "
        div_str = f"{int(r['divergence']):+d}"
        print(f"  {r['player_name']:<24}  {r['draft_age']:>5.1f}  {r['position']:>4}  "
              f"{r['mps']:>5.1f}  {int(r['tankathon_rank']):>7}  {int(r['model_rank']):>6}  "
              f"{div_str:>5}  {age_pen_str:>7}  {r['category']}")

    cats = df_div["category"].value_counts()
    print(f"\n  Category counts (n={len(df_div)} players with both ranks):")
    print(f"    age_likely   (model overranks older): {cats.get('age_likely',0)}")
    print(f"    youth_likely (model underranks young): {cats.get('youth_likely',0)}")
    print(f"    other:       {cats.get('other',0)}")


# ── Task 2: Holdout curve comparison ─────────────────────────────────────────

def task2_curve_comparison() -> str:
    print("\n" + "=" * 90)
    print("  Task 2: Age Penalty Curve Comparison — 2022 Holdout")
    print("=" * 90)

    df_raw = pd.read_csv(DATASET_PATH)
    combine = load_combine()
    df_raw = join_combine(df_raw, combine)
    df_raw = add_derived(df_raw)

    df_hold = df_raw[(df_raw["draft_year"] == HOLDOUT_YEAR) & df_raw[TARGET].notna()].copy()
    bpm_null = df_hold["bpm_college"].isna()
    if bpm_null.any():
        unscored = df_hold.loc[bpm_null, "player_name"].tolist()
        print(f"\n  Unscored (BPM null, excluded): {unscored}")

    params = TrainingParams()
    print()

    vorp = df_hold[TARGET]
    guard_pos = {"Point Guard", "Shooting Guard"}
    big_pos   = {"Power Forward", "Center"}
    g_mask = df_hold["position"].isin(guard_pos)
    b_mask = df_hold["position"].isin(big_pos)

    results = {}
    for cname, (age_fn, rate_label, start_label) in CURVES.items():
        mps = _score_holdout_with_curve(df_hold, params, age_fn)
        r_all, n_all = _spearman(mps, vorp)
        r_g, n_g     = _spearman(mps[g_mask], vorp[g_mask])
        r_b, n_b     = _spearman(mps[b_mask], vorp[b_mask])
        results[cname] = {
            "rate": rate_label, "start": start_label,
            "rho_all": r_all, "rho_g": r_g, "rho_b": r_b,
            "n": n_all,
        }

    baseline = results["A"]["rho_all"]
    print(f"  {'Curve':<6}  {'Rate':>8}  {'Start':>6}  {'ρ_all':>7}  "
          f"{'ρ_guards':>9}  {'ρ_bigs':>8}  {'vs_cur':>8}")
    print("  " + "-" * 66)
    for cname, r in results.items():
        vs = "" if cname == "A" else f"{r['rho_all'] - baseline:+.3f}"
        vs_str = "baseline" if cname == "A" else vs
        rg_str = f"{r['rho_g']:.3f}" if not math.isnan(r['rho_g']) else "  — "
        rb_str = f"{r['rho_b']:.3f}" if not math.isnan(r['rho_b']) else "  — "
        print(f"  {cname:<6}  {r['rate']:>8}  {r['start']:>6}  "
              f"{r['rho_all']:>7.3f}  {rg_str:>9}  {rb_str:>8}  {vs_str:>8}")

    # Determine winner
    best_curve = max(results, key=lambda c: results[c]["rho_all"])
    best_rho   = results[best_curve]["rho_all"]
    improvement = best_rho - baseline
    print()
    if improvement >= 0.005 and best_curve != "A":
        print(f"  → Winner: Curve {best_curve} (Δρ={improvement:+.3f} ≥ 0.005 threshold)")
    else:
        print(f"  → No curve beats baseline by ≥0.005.  Best: Curve {best_curve} "
              f"(Δρ={improvement:+.3f})")
    return best_curve if improvement >= 0.005 else "A"


# ── Task 3: Preview penalty changes on 2026 board ────────────────────────────

def task3_preview(winning_curve: str) -> None:
    print("\n" + "=" * 90)
    print(f"  Task 3: 2026 Penalty Preview — Curve {winning_curve} vs Current (Curve A)")
    print("=" * 90)

    age_fn_new = CURVES[winning_curve][0]
    df = pd.read_csv(BOARD_PATH)
    df_scored = df[df["mps"].notna()].copy()

    df_scored["old_pen"] = df_scored["draft_age"].apply(_curve_a)
    df_scored["new_pen"] = df_scored["draft_age"].apply(age_fn_new)
    df_scored["delta"]   = df_scored["new_pen"] - df_scored["old_pen"]
    df_scored["direction"] = df_scored["delta"].apply(
        lambda d: "UP" if d > 0 else ("DOWN" if d < 0 else "—")
    )

    changed = df_scored[df_scored["delta"].abs() > 0.001].sort_values("delta")

    if winning_curve == "A":
        print("\n  No change — current curve already optimal.")
    else:
        print(f"\n  {'Player':<24}  {'Age':>5}  {'OldPen':>7}  {'NewPen':>7}  "
              f"{'Delta':>6}  {'OldRk':>6}  Dir")
        print("  " + "-" * 68)
        for _, r in changed.sort_values("delta").iterrows():
            print(f"  {r['player_name']:<24}  {r['draft_age']:>5.1f}  "
                  f"{r['old_pen']:>+7.1f}  {r['new_pen']:>+7.1f}  "
                  f"{r['delta']:>+6.1f}  {int(r['rank']):>6}  {r['direction']}")

    # Spotlight players
    spotlight = [
        "Zuby Ejiofor", "Yaxel Lendeborg", "Tarris Reed Jr.", "Aday Mara",
        "Morez Johnson Jr.", "AJ Dybantsa", "Darryn Peterson", "Caleb Wilson",
    ]
    print("\n  Spotlight players:")
    print(f"  {'Player':<24}  {'Age':>5}  {'OldPen':>7}  {'NewPen':>7}  {'Delta':>6}  Dir")
    print("  " + "-" * 58)
    for name in spotlight:
        rows = df_scored[df_scored["player_name"] == name]
        if rows.empty:
            print(f"  {name:<24}  — not found")
            continue
        r = rows.iloc[0]
        print(f"  {r['player_name']:<24}  {r['draft_age']:>5.1f}  "
              f"{r['old_pen']:>+7.1f}  {r['new_pen']:>+7.1f}  "
              f"{r['delta']:>+6.1f}  {r['direction']}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    task1_divergence_audit()
    winner = task2_curve_comparison()
    task3_preview(winner)

    print("\n" + "=" * 90)
    if winner != "A":
        print(f"  VERDICT: Curve {winner} validated (Δρ ≥ 0.005).")
        print(f"  Task 4: Update compute_age_penalty() in scorer.py with Curve {winner}.")
    else:
        print("  VERDICT: No age curve improvement ≥ 0.005.")
        print("  Age penalty is empirically calibrated — divergences are model limitations.")
        print("  Fundamental gaps (not tunable by age):")
        print("    Dybantsa, Peterson, Ament — model sees production, scouts see ceiling/athleticism")
        print("    These players are drafted on traits that don't appear in college box scores.")
    print()


if __name__ == "__main__":
    main()
