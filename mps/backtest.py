"""
mps/backtest.py

MPS Backtest — Steps 2-5:
  1. Feature importance via random forest (all features + guard/big split)
  2. Pearson correlation matrix vs NBA VORP
  3. Build 4-pillar composite scores (Physical Profile excluded — no combine data yet)
  4. Grid search pillar weight optimization (minimize RMSE on 2010-2021 training set)
  5. Grade band calibration vs empirical NBA outcome distributions

Training set:  2010-2021 (years_available >= 1, busts included as vorp=0)
Holdout set:   2022 (2-3 years available, directional validation)
Dropped:       2023 (max 2 years available — too early to score)

Run:
    cd /home/spencer/Workspace/macfax
    backend/.venv/bin/python -m mps.backtest

Outputs:
    mps/output/feature_importance.png
    mps/output/feature_importance_guards.png
    mps/output/feature_importance_bigs.png
    mps/output/correlation_matrix.png
    mps/output/weight_optimization.png
    mps/output/grade_calibration.png
    mps/output/backtest_summary.csv
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

# ── Paths ──────────────────────────────────────────────────────────────────────

MPS_DIR    = Path(__file__).parent
DATA_DIR   = MPS_DIR / "data"
OUTPUT_DIR = MPS_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

DATASET    = DATA_DIR / "mps_dataset_raw.csv"

# ── Feature definitions ───────────────────────────────────────────────────────

# All college stat features used in analysis
ALL_FEATURES = [
    "bpm_college",   # box plus-minus — overall box score value
    "ts_pct",        # true shooting % — scoring efficiency
    "ft_pct",        # free throw % — shooting skill proxy
    "stl_pct",       # steal % — athleticism/instincts (guards)
    "orb_pct",       # offensive rebound % — motor/strength (bigs)
    "blk_pct",       # block % — athleticism (translatable)
    "ast_pct",       # assist % — playmaking
    "three_par",     # 3-point attempt rate — modern NBA fit
    "usg_pct",       # usage rate — context (high load bearer)
    "dws",           # defensive win shares — defensive IQ/effort
    "draft_age",     # age at draft
    "program_srs",   # program quality (SRS = KenPom AdjEM proxy)
]

# Pillar feature groupings
# NOTE: bpm_college EXCLUDED from college_efficiency — captured in age_x_production.
#       Having bpm_college in two pillars creates multicollinearity and lets the
#       optimizer double-count it while zeroing out other pillars.
PILLAR_FEATURES = {
    "college_efficiency": ["ts_pct", "stl_pct", "dws", "blk_pct", "ast_pct", "orb_pct"],
    # physical_profile: excluded (no combine data in this dataset)
    "age_x_production":  ["draft_age", "bpm_college"],   # interaction term
    "competition_ctx":   ["program_srs"],
    "nba_fit":           ["three_par", "ft_pct", "ast_pct"],  # ft_pct = NBA shooting proxy
}

# Within-pillar weights for college_efficiency (Pearson r with vorp_yr2_5_avg):
# ts_pct=0.155, stl_pct=0.149, dws=0.111, blk_pct=0.105, ast_pct=0.099, orb_pct=0.081
_EFF_FEATS = ["ts_pct", "stl_pct", "dws", "blk_pct", "ast_pct", "orb_pct"]
_EFF_CORR  = np.array([0.155, 0.149, 0.111, 0.105, 0.099, 0.081])
_EFF_WGTS  = _EFF_CORR / _EFF_CORR.sum()  # [0.221, 0.213, 0.159, 0.150, 0.141, 0.116]

# Starting pillar weights (research doc recommendation, 4-pillar model)
# Original: 35/20/20/15/10 with physical at 20%
# Physical excluded → renormalize remaining: 35/20/15/10 → 44/25/19/13 (≈100%)
STARTING_WEIGHTS = {
    "college_efficiency": 0.44,
    "age_x_production":   0.25,
    "competition_ctx":    0.19,
    "nba_fit":            0.12,
}

TARGET = "vorp_yr2_5_avg"


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load and split dataset.
    Returns (train_df, holdout_df).

    Training:  2010-2021, years_available >= 1
    Holdout:   2022, years_available >= 1
    Dropped:   2023 (insufficient NBA data)
    """
    df = pd.read_csv(DATASET)
    print(f"Raw dataset: {len(df)} rows across {df.draft_year.nunique()} years")

    # Drop 2023 — too early
    df = df[df.draft_year != 2023].copy()

    # Filter to players with at least 1 year of NBA data
    # (0s retained — valid bust outcomes for players who did have NBA time but
    #  produced nothing.  years_available=0 means zero NBA seasons — truly
    #  washed out before year 2; their vorp=0 is still a valid data point.)
    train = df[df.draft_year <= 2021].copy()
    hold  = df[df.draft_year == 2022].copy()

    print(f"Training set (2010-2021): {len(train)} players")
    print(f"Holdout set  (2022):      {len(hold)} players")
    print(f"Target (VORP yr2-5) — train mean: {train[TARGET].mean():.3f}  "
          f"std: {train[TARGET].std():.3f}")
    return train, hold


# ── Feature prep ──────────────────────────────────────────────────────────────

def prepare_features(df: pd.DataFrame,
                     features: list[str],
                     impute: bool = True) -> np.ndarray:
    """Extract feature matrix, median-imputing missing values."""
    X = df[features].copy()
    if impute:
        imp = SimpleImputer(strategy="median")
        X = pd.DataFrame(imp.fit_transform(X), columns=features)
    return X.values


# ── Step 1: Random forest feature importance ──────────────────────────────────

def run_feature_importance(train: pd.DataFrame) -> dict[str, dict]:
    """
    Fit random forest on all features → feature_importances_.
    Run once on full dataset, then separately for guards and bigs.
    Returns dict of {group: {feature: importance}}.
    """
    results = {}

    groups = {
        "all":    train,
        "guards": train[train.position_group == "G"],
        "bigs":   train[train.position_group == "BIG"],
    }

    for group_name, subset in groups.items():
        subset = subset.dropna(subset=[TARGET])
        if len(subset) < 20:
            print(f"  [RF] {group_name}: too few samples ({len(subset)}), skipping")
            continue

        features_available = [f for f in ALL_FEATURES if f in subset.columns]
        X = prepare_features(subset, features_available)
        y = subset[TARGET].values

        rf = RandomForestRegressor(
            n_estimators=500,
            max_features="sqrt",
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
        )
        rf.fit(X, y)

        importances = dict(zip(features_available, rf.feature_importances_))
        results[group_name] = importances

        print(f"\n  [RF] {group_name.upper()} group ({len(subset)} players):")
        for feat, imp in sorted(importances.items(), key=lambda x: -x[1]):
            bar = "█" * int(imp * 200)
            print(f"    {feat:20s}  {imp:.4f}  {bar}")

    return results


def plot_feature_importance(results: dict[str, dict]) -> None:
    """Save feature importance bar charts."""
    for group_name, importances in results.items():
        fig, ax = plt.subplots(figsize=(9, 6))
        sorted_feats = sorted(importances.items(), key=lambda x: x[1])
        feats, imps = zip(*sorted_feats)

        colors = ["#2E86AB" if i >= len(imps) - 4 else "#A8DADC"
                  for i in range(len(imps))]
        ax.barh(feats, imps, color=colors)
        ax.set_xlabel("Feature Importance (RF)")
        ax.set_title(f"Feature Importance — {group_name.title()} "
                     f"(Target: NBA VORP yr2-5)")
        ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
        plt.tight_layout()
        path = OUTPUT_DIR / f"feature_importance_{group_name}.png"
        plt.savefig(path, dpi=150)
        plt.close()
        print(f"  Saved: {path}")


# ── Step 2: Pearson correlation matrix ────────────────────────────────────────

def run_correlations(train: pd.DataFrame) -> pd.Series:
    """Pearson correlation of each feature vs VORP yr2-5."""
    features_available = [f for f in ALL_FEATURES if f in train.columns]
    corr = train[features_available + [TARGET]].corr()[TARGET].drop(TARGET)
    corr = corr.sort_values(ascending=False)

    print("\n  [Corr] Pearson r vs VORP yr2-5:")
    for feat, r in corr.items():
        bar = "█" * int(abs(r) * 40)
        sign = "+" if r >= 0 else "-"
        print(f"    {feat:20s}  r={r:+.3f}  {sign}{bar}")

    return corr


def plot_correlation_matrix(train: pd.DataFrame) -> None:
    """Save heatmap of feature × feature correlations + VORP column."""
    features_available = [f for f in ALL_FEATURES if f in train.columns]
    cols = features_available + [TARGET]
    corr_matrix = train[cols].corr()

    fig, ax = plt.subplots(figsize=(12, 10))
    im = ax.imshow(corr_matrix.values, cmap="RdBu_r", vmin=-1, vmax=1)
    plt.colorbar(im, ax=ax)
    ax.set_xticks(range(len(cols)))
    ax.set_yticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(cols, fontsize=9)
    ax.set_title("Feature Correlation Matrix (Training Set 2010-2021)")

    # Annotate cells
    for i in range(len(cols)):
        for j in range(len(cols)):
            val = corr_matrix.values[i, j]
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=7, color="black" if abs(val) < 0.6 else "white")

    plt.tight_layout()
    path = OUTPUT_DIR / "correlation_matrix.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Saved: {path}")


# ── Step 3: Pillar score computation ─────────────────────────────────────────

def _age_production_score(df: pd.DataFrame) -> np.ndarray:
    """
    Age × Production interaction score.

    Logic:
      - Base: normalize bpm_college to 0-100
      - Age modifier:
          < 19:  1.20  (exceptional youth)
          19-20: 1.10
          20-21: 1.00  (baseline)
          21-22: 0.90
          22-23: 0.75
          >= 23: 0.50  (hard cliff — research confirms this)
      - Final: base × age_modifier, clipped 0-100
    """
    bpm = df["bpm_college"].fillna(df["bpm_college"].median())
    age = df["draft_age"].fillna(21.5)  # median age at draft

    # Normalize BPM to 0-100 scale using training-set percentiles
    bpm_min, bpm_max = bpm.quantile(0.02), bpm.quantile(0.98)
    bpm_norm = ((bpm - bpm_min) / (bpm_max - bpm_min)).clip(0, 1) * 100

    def age_modifier(a: float) -> float:
        if a < 19:   return 1.20
        if a < 20:   return 1.10
        if a < 21:   return 1.00
        if a < 22:   return 0.90
        if a < 23:   return 0.75
        return 0.50

    modifiers = age.apply(age_modifier).values
    scores = (bpm_norm.values * modifiers).clip(0, 100)
    return scores


def build_pillar_scores(df: pd.DataFrame, scaler: StandardScaler | None = None
                        ) -> tuple[pd.DataFrame, StandardScaler]:
    """
    Build normalized 0-100 pillar scores for each player.

    Physical Profile pillar excluded (no combine data).
    Returns (df_with_pillars, fitted_scaler).
    """
    result = df.copy()

    # ── Pillar 1: College Efficiency ─────────────────────────────────────────
    # bpm_college excluded (it's in age_x_production pillar).
    # Use correlation-proportional weights from training-set Pearson r values.
    avail_idx   = [(i, f) for i, f in enumerate(_EFF_FEATS) if f in df.columns]
    avail_feats = [f for _, f in avail_idx]
    avail_wgts  = np.array([_EFF_WGTS[i] for i, _ in avail_idx])
    avail_wgts  = avail_wgts / avail_wgts.sum()  # renormalize if any feature missing

    X_eff = prepare_features(df, avail_feats)
    if scaler is None:
        sc = StandardScaler()
        X_eff_scaled = sc.fit_transform(X_eff)
    else:
        sc = scaler
        X_eff_scaled = sc.transform(X_eff)
    # Weighted mean z-score → map to 0-100
    eff_raw = (X_eff_scaled * avail_wgts).sum(axis=1)
    result["pillar_efficiency"] = _zscore_to_0_100(eff_raw)

    # ── Pillar 2: Age × Production ───────────────────────────────────────────
    result["pillar_age_prod"] = _age_production_score(df)

    # ── Pillar 3: Competition Context ────────────────────────────────────────
    srs = df["program_srs"].fillna(df["program_srs"].median() if "program_srs" in df.columns else 0)
    srs_min, srs_max = srs.quantile(0.02), srs.quantile(0.98)
    result["pillar_competition"] = ((srs - srs_min) / (srs_max - srs_min)).clip(0, 1).values * 100

    # ── Pillar 4: NBA Fit ─────────────────────────────────────────────────────
    # three_par (3PA rate = modern NBA skill), ft_pct (shooting translates), ast_pct
    fit_feats = ["three_par", "ft_pct", "ast_pct"]
    avail_fit = [f for f in fit_feats if f in df.columns]
    X_fit = prepare_features(df, avail_fit)
    X_fit_z = StandardScaler().fit_transform(X_fit)
    result["pillar_nba_fit"] = _zscore_to_0_100(X_fit_z.mean(axis=1))

    return result, sc


def _zscore_to_0_100(z: np.ndarray) -> np.ndarray:
    """Map z-score array (mean≈0, std≈1) to 0-100 scale using ±3σ range."""
    normalized = (z - (-3)) / (3 - (-3))   # map [-3, +3] → [0, 1]
    return (normalized.clip(0, 1) * 100)


def compute_mps(df: pd.DataFrame, weights: dict[str, float]) -> np.ndarray:
    """
    Compute final MPS (0-100) from pillar scores and weights.
    weights keys: college_efficiency, age_x_production, competition_ctx, nba_fit
    """
    w_eff  = weights["college_efficiency"]
    w_age  = weights["age_x_production"]
    w_comp = weights["competition_ctx"]
    w_fit  = weights["nba_fit"]

    mps = (
        df["pillar_efficiency"]  * w_eff  +
        df["pillar_age_prod"]    * w_age  +
        df["pillar_competition"] * w_comp +
        df["pillar_nba_fit"]     * w_fit
    ).values
    return mps


# ── Step 4: Weight optimization ───────────────────────────────────────────────

def optimize_weights(train: pd.DataFrame) -> dict[str, float]:
    """
    Grid search + COBYLA refine to maximize Spearman rank correlation
    between MPS score and actual NBA VORP yr2-5.

    Spearman (not RMSE) is the correct objective: we care about ranking
    prospects correctly, not predicting their exact VORP value.

    Grid search: 5% increments (min 5% per pillar to avoid degenerate solutions).
    COBYLA polish: gradient-free, handles non-smooth rank correlation.
    Returns optimized weight dict.
    """
    from scipy.optimize import minimize as sp_minimize
    from scipy.stats import spearmanr

    train_scored, sc = build_pillar_scores(train)
    y_true = train_scored[TARGET].values

    pillar_cols = ["pillar_efficiency", "pillar_age_prod",
                   "pillar_competition", "pillar_nba_fit"]
    X_pillars = train_scored[pillar_cols].values  # shape (n, 4)

    def neg_spearman(w: np.ndarray) -> float:
        """Negative Spearman rho (minimize = maximize rank correlation)."""
        mps = (X_pillars * w).sum(axis=1)
        rho, _ = spearmanr(mps, y_true)
        return -rho if not np.isnan(rho) else 0.0

    # ── Grid search (5% increments, each pillar ≥ 5%) ───────────────────────
    print("\n  [Grid] Searching weight combinations (5% increments, each pillar ≥ 5%)...")
    best_rho    = -float("inf")
    best_weights = None

    steps = list(range(5, 86, 5))  # 5–85 in 5% steps; 4 pillars must sum to 100
    count = 0
    for w1 in steps:
        for w2 in steps:
            if w1 + w2 > 90:
                break
            for w3 in steps:
                if w1 + w2 + w3 > 95:
                    break
                w4 = 100 - w1 - w2 - w3
                if w4 < 5:
                    continue
                w = np.array([w1, w2, w3, w4]) / 100.0
                rho = -neg_spearman(w)
                count += 1
                if rho > best_rho:
                    best_rho    = rho
                    best_weights = w.copy()

    print(f"  [Grid] Searched {count} combinations")
    print(f"  [Grid] Best grid Spearman rho: {best_rho:.4f}")
    print(f"  [Grid] Best grid weights: eff={best_weights[0]:.2f} "
          f"age={best_weights[1]:.2f} comp={best_weights[2]:.2f} "
          f"fit={best_weights[3]:.2f}")

    # ── COBYLA polish (gradient-free, handles non-smooth Spearman) ───────────
    # Constraints: sum=1, each pillar >= 5%
    constraints = [
        {"type": "ineq", "fun": lambda w:  sum(w) - 0.9999},   # sum >= 1
        {"type": "ineq", "fun": lambda w:  1.0001 - sum(w)},   # sum <= 1
        *[{"type": "ineq", "fun": lambda w, i=i: w[i] - 0.05}  # w_i >= 5%
          for i in range(4)],
    ]

    result = sp_minimize(
        neg_spearman,
        x0=best_weights,
        method="COBYLA",
        constraints=constraints,
        options={"maxiter": 3000, "rhobeg": 0.05},
    )

    if result.success or result.fun < -best_rho:
        refined = np.abs(result.x)
        refined = refined / refined.sum()  # renormalize
        refined_rho = -neg_spearman(refined)
        if refined_rho >= best_rho:
            print(f"  [Refined] Spearman rho: {refined_rho:.4f}")
            print(f"  [Refined] Weights: eff={refined[0]:.3f} age={refined[1]:.3f} "
                  f"comp={refined[2]:.3f} fit={refined[3]:.3f}")
            final_w = refined
        else:
            print(f"  [scipy] COBYLA did not improve over grid; using grid result")
            final_w = best_weights
    else:
        print(f"  [scipy] COBYLA did not converge; using grid result")
        final_w = best_weights

    opt_weights = {
        "college_efficiency": float(final_w[0]),
        "age_x_production":   float(final_w[1]),
        "competition_ctx":    float(final_w[2]),
        "nba_fit":            float(final_w[3]),
    }
    return opt_weights, best_rho


def validate_on_holdout(train: pd.DataFrame,
                        hold: pd.DataFrame,
                        opt_weights: dict[str, float],
                        start_weights: dict[str, float]) -> dict:
    """Score holdout (2022) with both starting and optimized weights."""
    # Fit scaler on training data
    train_scored, sc = build_pillar_scores(train)
    hold_scored, _   = build_pillar_scores(hold, scaler=sc)

    y_hold = hold_scored[TARGET].values

    mps_start = compute_mps(hold_scored, start_weights)
    mps_opt   = compute_mps(hold_scored, opt_weights)

    rmse_start = np.sqrt(mean_squared_error(y_hold, mps_start / 100 * 10))
    rmse_opt   = np.sqrt(mean_squared_error(y_hold, mps_opt   / 100 * 10))

    # Spearman rank correlation (ranking matters more than absolute value)
    from scipy.stats import spearmanr
    rho_start, p_start = spearmanr(mps_start, y_hold)
    rho_opt,   p_opt   = spearmanr(mps_opt,   y_hold)

    print(f"\n  [Holdout 2022] Starting weights:  Spearman rho={rho_start:.3f} (p={p_start:.3f})")
    print(f"  [Holdout 2022] Optimized weights: Spearman rho={rho_opt:.3f}   (p={p_opt:.3f})")

    return {
        "rho_starting":   rho_start,
        "rho_optimized":  rho_opt,
        "p_starting":     p_start,
        "p_optimized":    p_opt,
    }


# ── Step 5: Grade band calibration ────────────────────────────────────────────

def calibrate_grade_bands(train: pd.DataFrame,
                          opt_weights: dict[str, float]) -> dict[str, float]:
    """
    Find MPS cutoffs that match empirical NBA outcome distributions.

    Target distribution per ~50-player draft class:
      All-Star caliber (VORP yr2-5 > 3.0):   ~2-3 per class  → ~5%
      Starter     (VORP 1.0 - 3.0):           ~6-8 per class  → ~14%
      Rotation    (VORP 0.1 - 1.0):           ~12-15 per class → ~25%
      Fringe      (VORP -0.5 - 0.1):          ~8-10 per class  → ~17%
      Bust/Wash   (VORP < -0.5 or 0 years):   rest            → ~39%

    Finds MPS thresholds where empirical grade bands above match these proportions.
    """
    train_scored, _ = build_pillar_scores(train)
    train_scored["mps"] = compute_mps(train_scored, opt_weights)
    vorp = train_scored[TARGET]
    mps  = train_scored["mps"]

    # Percentile-based band targets (per ~50-player class, ~14 years = ~700 draftees):
    #   Grade S (All-Star potential):  top 8%   ~  4 players/class
    #   Grade A (Starter):             8–25%    ~  9 players/class
    #   Grade B (Rotation):           25–45%    ~ 10 players/class
    #   Grade C (Fringe):             45–65%    ~ 10 players/class
    #   Grade D (Bust/Wash):          bottom 35%
    print("\n  [Grades] Calibrating grade bands (percentile-based)...")

    thresholds = {
        "S_min": float(np.percentile(mps, 92)),   # top 8%
        "A_min": float(np.percentile(mps, 75)),   # top 25%
        "B_min": float(np.percentile(mps, 55)),   # top 45%
        "C_min": float(np.percentile(mps, 35)),   # top 65%
    }

    print(f"  Grade S (All-Star):  MPS >= {thresholds['S_min']:.1f}")
    print(f"  Grade A (Starter):   MPS >= {thresholds['A_min']:.1f}")
    print(f"  Grade B (Rotation):  MPS >= {thresholds['B_min']:.1f}")
    print(f"  Grade C (Fringe):    MPS >= {thresholds['C_min']:.1f}")
    print(f"  Grade D (Bust):      MPS <  {thresholds['C_min']:.1f}")

    # Validate: what % of each grade actually became starters/stars?
    def grade_label(mps_val: float) -> str:
        if mps_val >= thresholds["S_min"]: return "S"
        if mps_val >= thresholds["A_min"]: return "A"
        if mps_val >= thresholds["B_min"]: return "B"
        if mps_val >= thresholds["C_min"]: return "C"
        return "D"

    train_scored["grade"] = train_scored["mps"].apply(grade_label)
    print("\n  [Grades] Outcome rates by grade (% VORP yr2-5 > threshold):")
    for grade in ["S", "A", "B", "C", "D"]:
        subset = train_scored[train_scored.grade == grade]
        if len(subset) == 0:
            continue
        star_pct    = (subset[TARGET] > 3.0).mean() * 100
        starter_pct = (subset[TARGET] > 1.0).mean() * 100
        n = len(subset)
        print(f"    Grade {grade} (n={n:3d}):  "
              f"All-Star={star_pct:.0f}%  Starter+={starter_pct:.0f}%  "
              f"mean VORP={subset[TARGET].mean():.2f}")

    return thresholds


# ── Visualization helpers ─────────────────────────────────────────────────────

def plot_weight_comparison(start_w: dict, opt_w: dict) -> None:
    """Bar chart comparing starting vs optimized weights."""
    labels = list(start_w.keys())
    x = np.arange(len(labels))
    w = 0.35

    fig, ax = plt.subplots(figsize=(9, 5))
    bars1 = ax.bar(x - w/2, [start_w[k] for k in labels], w,
                   label="Starting (research-derived)", color="#2E86AB", alpha=0.8)
    bars2 = ax.bar(x + w/2, [opt_w[k]   for k in labels], w,
                   label="Optimized (data-derived)",    color="#E84855", alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels([l.replace("_", "\n") for l in labels], fontsize=9)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
    ax.set_title("MPS Pillar Weights: Research-Derived vs Data-Optimized")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path = OUTPUT_DIR / "weight_optimization.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Saved: {path}")


def plot_mps_vs_vorp(train: pd.DataFrame, opt_weights: dict) -> None:
    """Scatter: MPS score vs actual VORP yr2-5 on training set."""
    scored, _ = build_pillar_scores(train)
    scored["mps"] = compute_mps(scored, opt_weights)

    fig, ax = plt.subplots(figsize=(9, 6))
    colors = {1: "#2E86AB", 2: "#A8DADC"}
    for rnd in [1, 2]:
        sub = scored[scored.draft_round == rnd]
        ax.scatter(sub["mps"], sub[TARGET],
                   c=colors[rnd], alpha=0.5, s=25,
                   label=f"Round {rnd}")

    # Trend line
    z = np.polyfit(scored["mps"], scored[TARGET], 1)
    p = np.poly1d(z)
    x_line = np.linspace(scored["mps"].min(), scored["mps"].max(), 100)
    ax.plot(x_line, p(x_line), "k--", linewidth=1.5, label="Trend")

    ax.set_xlabel("MPS Score (0-100)")
    ax.set_ylabel("NBA VORP Years 2-5 (avg)")
    ax.set_title("MPS Score vs Actual NBA Outcomes (Training Set 2010-2021)")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    path = OUTPUT_DIR / "mps_vs_vorp.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Saved: {path}")


# ── Output summary ────────────────────────────────────────────────────────────

def save_summary(train: pd.DataFrame,
                 hold: pd.DataFrame,
                 feature_corr: pd.Series,
                 rf_results: dict,
                 start_weights: dict,
                 opt_weights: dict,
                 holdout_stats: dict,
                 grade_thresholds: dict) -> None:
    """Save consolidated backtest summary CSV + print findings table."""

    # Feature summary table
    feat_df = pd.DataFrame({
        "feature":           feature_corr.index,
        "pearson_r_vs_vorp": feature_corr.values,
        "rf_importance_all": [rf_results.get("all", {}).get(f, np.nan)
                              for f in feature_corr.index],
        "rf_importance_G":   [rf_results.get("guards", {}).get(f, np.nan)
                              for f in feature_corr.index],
        "rf_importance_BIG": [rf_results.get("bigs", {}).get(f, np.nan)
                              for f in feature_corr.index],
    })

    # Weight summary
    weight_df = pd.DataFrame([
        {"pillar": k, "weight_starting": v, "weight_optimized": opt_weights[k]}
        for k, v in start_weights.items()
    ])

    # Grade threshold summary
    grade_df = pd.DataFrame([
        {"grade": "S", "label": "All-Star",  "mps_min": grade_thresholds["S_min"]},
        {"grade": "A", "label": "Starter",   "mps_min": grade_thresholds["A_min"]},
        {"grade": "B", "label": "Rotation",  "mps_min": grade_thresholds["B_min"]},
        {"grade": "C", "label": "Fringe",    "mps_min": grade_thresholds["C_min"]},
        {"grade": "D", "label": "Bust",      "mps_min": 0},
    ])

    # Write to CSV
    path = OUTPUT_DIR / "backtest_summary.csv"
    with open(path, "w") as f:
        f.write("# MPS Backtest Summary\n")
        f.write(f"# Training: 2010-2021 ({len(train)} players)\n")
        f.write(f"# Holdout: 2022 ({len(hold)} players)\n")
        f.write(f"# Holdout Spearman rho (optimized): "
                f"{holdout_stats['rho_optimized']:.3f} "
                f"(p={holdout_stats['p_optimized']:.3f})\n")
        f.write("\n## Feature Importance & Correlation\n")
        feat_df.to_csv(f, index=False)
        f.write("\n## Pillar Weights\n")
        weight_df.to_csv(f, index=False)
        f.write("\n## Grade Thresholds\n")
        grade_df.to_csv(f, index=False)

    print(f"\n  Saved summary: {path}")

    # Print findings table
    print("\n" + "="*65)
    print("BACKTEST FINDINGS SUMMARY")
    print("="*65)
    print("\nFeature Signal (sorted by Pearson r):")
    for _, row in feat_df.sort_values("pearson_r_vs_vorp", ascending=False).iterrows():
        rf_all = f"{row.rf_importance_all:.3f}" if not np.isnan(row.rf_importance_all) else "  —  "
        print(f"  {row.feature:20s}  r={row.pearson_r_vs_vorp:+.3f}  RF={rf_all}")

    print("\nOptimized Pillar Weights:")
    for k, v in opt_weights.items():
        change = v - start_weights[k]
        arrow = "↑" if change > 0.02 else ("↓" if change < -0.02 else "→")
        print(f"  {k:25s}  {v:.1%}  {arrow} (was {start_weights[k]:.1%})")

    print(f"\nHoldout Validation (2022 class):")
    print(f"  Spearman rho (starting):  {holdout_stats['rho_starting']:.3f}")
    print(f"  Spearman rho (optimized): {holdout_stats['rho_optimized']:.3f}")

    print("\nGrade Thresholds:")
    for _, row in grade_df.iterrows():
        print(f"  Grade {row.grade} ({row.label:10s}):  MPS >= {row.mps_min:.1f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("MPS Backtest")
    print("Training: 2010-2021  |  Holdout: 2022  |  Dropped: 2023")
    print()

    # Load
    train, hold = load_data()

    # Step 1: Feature importance
    print("\n── Step 1: Random Forest Feature Importance ─────────────────")
    rf_results = run_feature_importance(train)
    plot_feature_importance(rf_results)

    # Step 2: Correlations
    print("\n── Step 2: Pearson Correlations vs VORP yr2-5 ───────────────")
    feature_corr = run_correlations(train)
    plot_correlation_matrix(train)

    # Step 3+4: Pillar scores + weight optimization
    print("\n── Steps 3-4: Pillar Scores + Weight Optimization ──────────")
    opt_weights, train_rho = optimize_weights(train)
    print(f"\n  Starting weights: {STARTING_WEIGHTS}")
    print(f"  Optimized weights: {opt_weights}")
    plot_weight_comparison(STARTING_WEIGHTS, opt_weights)

    # Validate on holdout
    holdout_stats = validate_on_holdout(train, hold, opt_weights, STARTING_WEIGHTS)

    # Scatter plot
    plot_mps_vs_vorp(train, opt_weights)

    # Step 5: Grade band calibration
    print("\n── Step 5: Grade Band Calibration ───────────────────────────")
    grade_thresholds = calibrate_grade_bands(train, opt_weights)

    # Save everything
    save_summary(train, hold, feature_corr, rf_results,
                 STARTING_WEIGHTS, opt_weights, holdout_stats, grade_thresholds)

    print("\nDone. Outputs in mps/output/")


if __name__ == "__main__":
    main()
