"""
mps/backtest_full.py

Phase 2 of the MPS rebuild: full correlation backtest across 4 feature groups.

Steps:
  1. Load enriched training CSV (after scraper_supplement.py has run)
  2. Join physical/combine data from combine_historical.json
  3. Compute Pearson r for every feature vs vorp_yr2_5_avg
  4. Group by A/B/C/D pillars, rank by |r|
  5. Spearman ρ: current model vs ridge regression on all features
  6. Output paste-ready pillar weights + top predictors per group

Run:
    cd /home/spencer/Workspace/macfax
    backend/.venv/bin/python mps/backtest_full.py
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

# ── Paths ──────────────────────────────────────────────────────────────────────

MPS_DIR    = Path(__file__).parent
DATA_DIR   = MPS_DIR / "data"
DATASET    = DATA_DIR / "mps_dataset_raw.csv"
CACHE_FILE = DATA_DIR / "combine_historical.json"

# ── Feature group definitions ──────────────────────────────────────────────────

GROUP_A_PHYSICAL = [
    "height_in", "draft_age", "max_vertical_in", "standing_reach_in",
    "wingspan_in", "weight_lbs",
    # Derived ratios (computed in join step)
    "wingspan_to_height_ratio", "standing_reach_to_height_ratio",
]

GROUP_B_PERGAME = [
    "games_played", "mp_pg", "fg_pct", "fg3_pct", "ft_pct",
    "trb_pg", "ast_pg", "blk_pg", "stl_pg", "tov_pg", "pts_pg",
]

GROUP_C_ADVANCED_I = [
    "ts_pct", "three_par", "usg_pct",
    # Derived (computed below)
    "ast_pct_over_usg", "ast_to_tov",
    # Already in CSV
    "stl_pct", "blk_pct", "orb_pct", "ast_pct",
]

GROUP_D_ADVANCED_II = [
    "per", "ows", "dws", "ws_40", "obpm", "dbpm", "bpm_college",
]

ALL_FEATURES = GROUP_A_PHYSICAL + GROUP_B_PERGAME + GROUP_C_ADVANCED_I + GROUP_D_ADVANCED_II

GROUP_LABELS = {
    "A — Physical/Combine": GROUP_A_PHYSICAL,
    "B — Per-Game":         GROUP_B_PERGAME,
    "C — Advanced I":       GROUP_C_ADVANCED_I,
    "D — Advanced II":      GROUP_D_ADVANCED_II,
}

TARGET = "vorp_yr2_5_avg"


# ── Age modifier (mirrors scorer.py) ─────────────────────────────────────────

def _age_modifier(age: float) -> float:
    if age < 19:   return 1.20
    if age < 20:   return 1.10
    if age < 21:   return 1.00
    if age < 22:   return 0.90
    if age < 23:   return 0.75
    return 0.50


# ── Load combine cache ─────────────────────────────────────────────────────────

def load_combine() -> dict[int, dict[str, dict]]:
    if not CACHE_FILE.exists():
        print("  [combine] Cache not found — physical columns will be absent.")
        return {}
    with CACHE_FILE.open() as f:
        obj = json.load(f)
    data = obj.get("data", {})
    return {int(k): v for k, v in data.items()}


# ── Join combine to dataframe ──────────────────────────────────────────────────

COMBINE_COLS = [
    "height_in", "wingspan_in", "standing_reach_in", "weight_lbs", "max_vertical_in",
    "wingspan_to_height_ratio", "standing_reach_to_height_ratio",
]


def join_combine(df: pd.DataFrame, combine: dict[int, dict[str, dict]]) -> pd.DataFrame:
    df = df.copy()
    for col in COMBINE_COLS:
        df[col] = np.nan

    for draft_year, players in combine.items():
        year_mask = df["draft_year"] == draft_year
        combine_names = list(players.keys())

        for idx in df[year_mask].index:
            pname = df.at[idx, "player_name"]
            matches = difflib.get_close_matches(pname, combine_names, n=1, cutoff=0.85)
            if not matches:
                continue
            meas = players[matches[0]]
            h  = meas.get("height_in")
            w  = meas.get("wingspan_in")
            sr = meas.get("standing_reach_in")
            df.at[idx, "height_in"]         = h
            df.at[idx, "wingspan_in"]        = w
            df.at[idx, "standing_reach_in"]  = sr
            df.at[idx, "weight_lbs"]         = meas.get("weight_lbs")
            df.at[idx, "max_vertical_in"]    = meas.get("max_vertical_in")
            df.at[idx, "wingspan_to_height_ratio"]        = (w / h) if (h and w) else None
            df.at[idx, "standing_reach_to_height_ratio"]  = (sr / h) if (h and sr) else None

    return df


# ── Derived features ───────────────────────────────────────────────────────────

def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # ast_pct / usg_pct ratio
    if "usg_pct" in df.columns and "ast_pct" in df.columns:
        df["ast_pct_over_usg"] = np.where(
            (df["usg_pct"].notna()) & (df["usg_pct"] > 0) & (df["ast_pct"].notna()),
            df["ast_pct"] / df["usg_pct"],
            np.nan,
        )
    else:
        df["ast_pct_over_usg"] = np.nan
    # ast / tov ratio
    if "ast_pg" in df.columns and "tov_pg" in df.columns:
        df["ast_to_tov"] = np.where(
            (df["tov_pg"].notna()) & (df["tov_pg"] > 0) & (df["ast_pg"].notna()),
            df["ast_pg"] / df["tov_pg"],
            np.nan,
        )
    else:
        df["ast_to_tov"] = np.nan
    return df


# ── Pearson r table ────────────────────────────────────────────────────────────

def compute_correlations(df: pd.DataFrame, features: list[str]) -> list[dict]:
    rows = []
    for feat in features:
        if feat not in df.columns:
            rows.append({"feature": feat, "n": 0, "r": None, "p": None, "rho": None})
            continue
        sub = df[[TARGET, feat]].dropna()
        if len(sub) < 10:
            rows.append({"feature": feat, "n": len(sub), "r": None, "p": None, "rho": None})
            continue
        r, p   = scipy_stats.pearsonr(sub[TARGET], sub[feat])
        rho, _ = scipy_stats.spearmanr(sub[TARGET], sub[feat])
        rows.append({
            "feature": feat,
            "n":       len(sub),
            "r":       float(r),
            "p":       float(p),
            "rho":     float(rho),
        })
    return rows


# ── Current model score (BPM × age) ───────────────────────────────────────────

def current_model_score(df: pd.DataFrame, bpm_min: float, bpm_max: float) -> pd.Series:
    bpm_range = max(bpm_max - bpm_min, 1e-8)
    bpm_norm  = np.clip(
        (df["bpm_college"].fillna(bpm_min) - bpm_min) / bpm_range * 100, 0, 100
    )
    age_mod = df["draft_age"].apply(_age_modifier)
    return bpm_norm * age_mod


# ── Ridge regression model ─────────────────────────────────────────────────────

def ridge_model_score(
    df_train: pd.DataFrame,
    df_test: pd.DataFrame,
    feature_cols: list[str],
) -> pd.Series | None:
    """Fit Ridge on training set, predict on test. Returns predictions or None."""
    available = [c for c in feature_cols if c in df_train.columns and c in df_test.columns]
    if len(available) < 3:
        return None

    X_train = df_train[available].copy()
    y_train = df_train[TARGET]

    # Drop rows with NaN in target
    mask = y_train.notna()
    X_train, y_train = X_train[mask], y_train[mask]

    # Drop columns that are entirely NaN in training (supplement not yet run)
    good_cols = [c for c in available if X_train[c].notna().any()]
    if len(good_cols) < 3:
        return None
    X_train = X_train[good_cols]

    # Impute with column median (training set only)
    medians = X_train.median()
    X_train = X_train.fillna(medians)

    X_test = df_test[good_cols].fillna(medians)

    # Require at least 20 training rows
    if len(X_train) < 20:
        return None

    scaler  = StandardScaler()
    X_tr_sc = scaler.fit_transform(X_train)
    X_te_sc = scaler.transform(X_test)

    model = RidgeCV(alphas=[0.1, 1.0, 10.0, 100.0])
    model.fit(X_tr_sc, y_train)

    preds = model.predict(X_te_sc)
    return pd.Series(preds, index=df_test.index)


# ── Print helpers ──────────────────────────────────────────────────────────────

def _print_group(group_name: str, corr_rows: list[dict]) -> None:
    valid = [c for c in corr_rows if c["r"] is not None]
    valid.sort(key=lambda c: abs(c["r"]), reverse=True)
    print(f"\n  {group_name}")
    print(f"  {'Feature':<36}  {'r':>7}  {'ρ':>7}  {'p':>7}  {'n':>5}  Signal?")
    print(f"  {'-'*36}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*5}  -------")
    for c in corr_rows:
        if c["r"] is None:
            print(f"  {c['feature']:<36}  {'N/A':>7}  {'N/A':>7}  {'N/A':>7}  {c['n']:>5}  (too few / missing)")
            continue
        flag = "SIGNAL" if abs(c["r"]) >= 0.05 else "noise"
        r_str   = f"{c['r']:>+7.3f}"
        rho_str = f"{c['rho']:>+7.3f}" if c["rho"] is not None else "    N/A"
        print(f"  {c['feature']:<36}  {r_str}  {rho_str}  {c['p']:>7.4f}  {c['n']:>5}  {flag}")

    if valid:
        top3 = valid[:3]
        top3_names = [c["feature"] for c in top3]
        print(f"  → Top 3: {top3_names}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print("  MPS FULL CORRELATION BACKTEST")
    print("=" * 70)

    # 1. Load data
    print("\n[1] Loading training CSV...")
    df = pd.read_csv(DATASET)
    print(f"  {len(df)} rows, {len(df.columns)} columns")

    missing_new = [c for c in ["per", "pts_pg", "trb_pg"] if c not in df.columns]
    if missing_new:
        print(f"  WARNING: supplement columns not present ({missing_new})")
        print(f"  Run mps/scraper_supplement.py first for full analysis.")
        print(f"  Continuing with available columns...\n")

    # 2. Join combine
    print("\n[2] Loading combine data...")
    combine = load_combine()
    if combine:
        df = join_combine(df, combine)
        n_matched = df["height_in"].notna().sum()
        print(f"  Matched {n_matched}/{len(df)} rows to combine data")
    else:
        print("  No combine data — Group A will show N/A")

    # 3. Derived features
    df = add_derived(df)

    # 4. Split: correlation set (≤2021) and holdout (2022)
    df_corr   = df[df["draft_year"] <= 2021].copy()
    df_hold   = df[df["draft_year"] == 2022].copy()
    df_target = df_corr[df_corr[TARGET].notna()]
    print(f"\n[3] Correlation set (≤2021, has VORP): {len(df_target)} rows")
    print(f"    2022 holdout: {len(df_hold)} rows")

    # 5. Pearson r per group
    print("\n[4] Computing correlations (Pearson r + Spearman ρ) vs vorp_yr2_5_avg...")
    all_corr: list[dict] = []
    for group_name, features in GROUP_LABELS.items():
        rows = compute_correlations(df_target, features)
        _print_group(group_name, rows)
        for row in rows:
            row["group"] = group_name
        all_corr.extend(rows)

    # 6. Spearman ρ A/B/C: current model vs ridge on all features
    print("\n\n[5] Spearman ρ holdout comparison...")

    # BPM bounds from training set
    bpm_vals  = df_corr["bpm_college"].dropna()
    bpm_min   = float(bpm_vals.quantile(0.02))
    bpm_max   = float(bpm_vals.quantile(0.98))

    # Need holdout rows with known VORP
    hold_with_vorp = df_hold[df_hold[TARGET].notna()].copy()

    if len(hold_with_vorp) < 3:
        print("  Not enough 2022 holdout rows with VORP. Skipping Spearman ρ.")
    else:
        # Model A: current (BPM × age)
        score_a = current_model_score(hold_with_vorp, bpm_min, bpm_max)
        rho_a, _ = scipy_stats.spearmanr(hold_with_vorp[TARGET], score_a)

        # Model B: ridge on Group B+C+D (stats-based, no physical)
        stats_features = GROUP_B_PERGAME + GROUP_C_ADVANCED_I + GROUP_D_ADVANCED_II
        df_corr_vorp   = df_corr[df_corr[TARGET].notna()]
        score_b = ridge_model_score(df_corr_vorp, hold_with_vorp, stats_features)
        rho_b   = None
        if score_b is not None:
            rho_b, _ = scipy_stats.spearmanr(hold_with_vorp[TARGET], score_b)

        # Model C: ridge on all features (including physical)
        score_c = ridge_model_score(df_corr_vorp, hold_with_vorp, ALL_FEATURES)
        rho_c   = None
        if score_c is not None:
            rho_c, _ = scipy_stats.spearmanr(hold_with_vorp[TARGET], score_c)

        print(f"\n  2022 holdout (N={len(hold_with_vorp)} rows with VORP):")
        print(f"    Model A — BPM × age (current):          ρ = {rho_a:+.3f}")
        if rho_b is not None:
            print(f"    Model B — Ridge on stats features:      ρ = {rho_b:+.3f}  (Δ = {rho_b - rho_a:+.3f})")
        else:
            print(f"    Model B — Ridge on stats features:      N/A (too few rows)")
        if rho_c is not None:
            print(f"    Model C — Ridge on all features:        ρ = {rho_c:+.3f}  (Δ = {rho_c - rho_a:+.3f})")
        else:
            print(f"    Model C — Ridge on all features:        N/A (too few rows)")

    # 7. Summary: top predictors overall + paste-ready weights
    print("\n\n[6] Top predictors across all groups (by |r|):")
    valid = [c for c in all_corr if c["r"] is not None and abs(c["r"]) >= 0.05]
    valid.sort(key=lambda c: abs(c["r"]), reverse=True)

    print(f"\n  {'Feature':<36}  {'Group':<24}  {'r':>7}  {'ρ':>7}")
    print(f"  {'-'*36}  {'-'*24}  {'-'*7}  {'-'*7}")
    for c in valid[:20]:
        r_str   = f"{c['r']:>+7.3f}"
        rho_str = f"{c['rho']:>+7.3f}"
        print(f"  {c['feature']:<36}  {c['group']:<24}  {r_str}  {rho_str}")

    if valid:
        total_r = sum(abs(c["r"]) for c in valid)
        weights = {c["feature"]: round(abs(c["r"]) / total_r, 4) for c in valid}
        print(f"\n  Paste-ready FEATURE_WEIGHTS (normalized to sum 1.0):")
        print(f"  FEATURE_WEIGHTS = {{")
        for feat, w in sorted(weights.items(), key=lambda x: x[1], reverse=True):
            print(f"      \"{feat}\": {w},")
        print(f"  }}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
