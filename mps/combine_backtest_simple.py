"""
mps/combine_backtest_simple.py

Stripped combine validation — does physical measurement data from the NBA Draft
Combine actually predict NBA outcomes?

Steps:
  1. Fetch historical combine data (2010-2022 draft classes) from NBA Stats API
  2. Join to mps_dataset_raw.csv training set on (player_name, draft_year)
  3. Compute Pearson r for each physical metric vs vorp_yr2_5_avg
  4. Spearman ρ A/B comparison (BPM+age vs BPM+age+physical) on 2022 holdout
  5. Print verdict + paste-ready PHYS_WEIGHTS if signal warrants it

Run:
    cd /home/spencer/Workspace/macfax
    backend/.venv/bin/python mps/combine_backtest_simple.py
"""

from __future__ import annotations

import difflib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

# Reuse NBA Stats API helpers from combine_scraper
from mps.combine_scraper import _nba_fetch, _safe_float

# ── Paths ──────────────────────────────────────────────────────────────────────

MPS_DIR    = Path(__file__).parent
DATA_DIR   = MPS_DIR / "data"
DATASET    = DATA_DIR / "mps_dataset_raw.csv"
CACHE_FILE = DATA_DIR / "combine_historical.json"
CACHE_TTL  = 24 * 3600  # 24-hour TTL

# ── Season range ───────────────────────────────────────────────────────────────
# NBA SeasonYear convention: one-year-forward
# "2010-11" = 2010 draft class, ..., "2022-23" = 2022 draft class
SEASON_YEARS = [f"{y}-{str(y + 1)[-2:]}" for y in range(2010, 2023)]


# ── Age modifier (mirrors scorer.py) ─────────────────────────────────────────

def _age_modifier(age: float) -> float:
    if age < 19:   return 1.20
    if age < 20:   return 1.10
    if age < 21:   return 1.00
    if age < 22:   return 0.90
    if age < 23:   return 0.75
    return 0.50


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _load_cache() -> dict | None:
    """Return cached combine dict if fresh (24-hr TTL)."""
    if not CACHE_FILE.exists():
        return None
    try:
        with CACHE_FILE.open() as f:
            obj = json.load(f)
        fetched_at_str = obj.get("fetched_at", "")
        if not fetched_at_str:
            return None
        fetched_at = datetime.fromisoformat(fetched_at_str)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(tz=timezone.utc) - fetched_at).total_seconds()
        if age > CACHE_TTL:
            return None
        data = obj.get("data", {})
        print(f"  [cache] hit ({sum(len(v) for v in data.values())} total player-seasons, "
              f"age {age / 3600:.1f}h)")
        return data
    except Exception as exc:
        print(f"  [cache] read error: {exc}")
        return None


def _write_cache(data: dict) -> None:
    """Write combine data to cache: {draft_year: {player_name: {metrics}}}."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    obj = {
        "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
        "seasons":    list(data.keys()),
        "data":       data,
    }
    try:
        with CACHE_FILE.open("w") as f:
            json.dump(obj, f, indent=2)
        total = sum(len(v) for v in data.values())
        print(f"  [cache] written → {CACHE_FILE} ({total} player-seasons)")
    except Exception as exc:
        print(f"  [cache] write error: {exc}")


# ── Fetch historical combine data ─────────────────────────────────────────────

def fetch_historical_combine() -> dict[int, dict[str, dict]]:
    """
    Fetch historical combine data for all seasons in SEASON_YEARS.

    Returns
    -------
    dict[draft_year, dict[player_name, {height_in, wingspan_in,
                                        standing_reach_in, weight_lbs,
                                        max_vertical_in}]]
    """
    cached = _load_cache()
    if cached is not None:
        # Keys from JSON are strings; convert back to int
        return {int(k): v for k, v in cached.items()}

    result: dict[int, dict[str, dict]] = {}

    for season_year in SEASON_YEARS:
        draft_year = int(season_year[:4])
        print(f"  [NBA API] {season_year} (draft class {draft_year})...")

        # Anthropometric measurements
        anthro_rows = _nba_fetch("draftcombineplayeranthro",
                                  {"LeagueID": "00", "SeasonYear": season_year})
        time.sleep(4)

        # Athleticism drills (max vertical only)
        drill_rows = _nba_fetch("draftcombinedrillresults",
                                 {"LeagueID": "00", "SeasonYear": season_year})
        time.sleep(4)

        players: dict[str, dict] = {}

        for row in anthro_rows:
            name = row.get("PLAYER_NAME", "").strip()
            if not name:
                continue
            players[name] = {
                "height_in":         _safe_float(row.get("HEIGHT_WO_SHOES")),
                "wingspan_in":       _safe_float(row.get("WINGSPAN")),
                "standing_reach_in": _safe_float(row.get("STANDING_REACH")),
                "weight_lbs":        _safe_float(row.get("WEIGHT")),
            }

        for row in drill_rows:
            name = row.get("PLAYER_NAME", "").strip()
            if not name:
                continue
            entry = players.setdefault(name, {})
            entry["max_vertical_in"] = _safe_float(row.get("MAX_VERTICAL_LEAP"))

        result[draft_year] = players
        n_anthro = len(anthro_rows)
        n_drill  = len(drill_rows)
        print(f"    → {len(players)} players  (anthro={n_anthro}, drills={n_drill})")

    # Cache with string keys (JSON requires string keys)
    _write_cache({str(k): v for k, v in result.items()})
    return result


# ── Join combine to training CSV ──────────────────────────────────────────────

_PHYSICAL_METRICS = [
    "height_in",
    "wingspan_in",
    "wingspan_to_height_ratio",
    "standing_reach_in",
    "standing_reach_to_height_ratio",
    "weight_lbs",
    "max_vertical_in",
]


def join_to_training(
    combine_data: dict[int, dict[str, dict]],
    df_train: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join combine measurements to training rows.

    Match strategy: fuzzy (difflib, cutoff=0.85) on (player_name, draft_year).
    Returns df_train with physical metric columns appended.
    Matched column: 'combine_matched' (bool).
    """
    records = []
    skipped_top10: list[str] = []

    for draft_year, players in combine_data.items():
        year_rows = df_train[df_train["draft_year"] == draft_year]
        combine_names = list(players.keys())

        for _, row in year_rows.iterrows():
            pname = row["player_name"]

            # Fuzzy match
            matches = difflib.get_close_matches(pname, combine_names, n=1, cutoff=0.85)
            if not matches:
                # Check if top-10 pick (likely skipped combine, not a data issue)
                pick = row.get("draft_pick")
                if pd.notna(pick) and int(pick) <= 10:
                    skipped_top10.append(f"{pname} ({draft_year}, pick {int(pick)})")
                records.append((row.name, {}))
                continue

            meas = players[matches[0]]
            h = meas.get("height_in")
            w = meas.get("wingspan_in")
            sr = meas.get("standing_reach_in")

            entry = dict(meas)
            entry["wingspan_to_height_ratio"]       = (w / h) if (h and w) else None
            entry["standing_reach_to_height_ratio"] = (sr / h) if (h and sr) else None
            records.append((row.name, entry))

    # Build joined DataFrame
    idx_list = [r[0] for r in records]
    metric_rows = [r[1] for r in records]

    phys_df = pd.DataFrame(metric_rows, index=idx_list)
    result = df_train.copy()
    for col in _PHYSICAL_METRICS:
        result[col] = np.nan
    for col in _PHYSICAL_METRICS:
        if col in phys_df.columns:
            result.loc[phys_df.index, col] = phys_df[col].values

    result["combine_matched"] = result["height_in"].notna()
    return result, skipped_top10


# ── Pearson r table ───────────────────────────────────────────────────────────

def compute_correlations(df: pd.DataFrame) -> list[dict]:
    """
    Compute Pearson r for each physical metric vs vorp_yr2_5_avg.
    Only rows where both metric and vorp are non-null.
    """
    rows = []
    for metric in _PHYSICAL_METRICS:
        sub = df[["vorp_yr2_5_avg", metric]].dropna()
        if len(sub) < 5:
            rows.append({
                "metric": metric, "n": len(sub),
                "r": None, "p": None, "signal": False,
            })
            continue
        r, p = scipy_stats.pearsonr(sub["vorp_yr2_5_avg"], sub[metric])
        rows.append({
            "metric": metric,
            "n":      len(sub),
            "r":      float(r),
            "p":      float(p),
            "signal": abs(r) >= 0.05,
        })
    return rows


# ── Spearman ρ A/B ────────────────────────────────────────────────────────────

def spearman_ab(
    df_holdout: pd.DataFrame,
    corr_rows: list[dict],
    bpm_min: float,
    bpm_max: float,
) -> tuple[float, float, list[dict]]:
    """
    Compare Model A (BPM+age) vs Model B (BPM+age + top-2 physical) on holdout.

    Returns (rho_A, rho_B, top2_metrics_used).
    Only uses holdout rows that have combine data AND vorp_yr2_5_avg.
    """
    sub = df_holdout[df_holdout["combine_matched"] & df_holdout["vorp_yr2_5_avg"].notna()].copy()
    if len(sub) < 3:
        return float("nan"), float("nan"), []

    # BPM normalization (training-set bounds)
    bpm_range = max(bpm_max - bpm_min, 1e-8)
    sub["bpm_norm"] = np.clip(
        (sub["bpm_college"].fillna(bpm_min) - bpm_min) / bpm_range * 100, 0, 100
    )
    sub["age_mod"]   = sub["draft_age"].apply(_age_modifier)
    sub["model_a"]   = sub["bpm_norm"] * sub["age_mod"]

    # Top-2 physical predictors (by |r|, signal only)
    signal_corrs = [c for c in corr_rows if c["signal"] and c["r"] is not None
                    and c["metric"] in sub.columns]
    signal_corrs = sorted(signal_corrs, key=lambda c: abs(c["r"]), reverse=True)
    top2 = signal_corrs[:2]

    if not top2:
        # No physical signal at all — can't build Model B
        rho_a, _ = scipy_stats.spearmanr(sub["vorp_yr2_5_avg"], sub["model_a"])
        return float(rho_a), float("nan"), []

    # Normalize physical features to [0,100] using holdout set (small — only z-score option)
    phys_cols = [c["metric"] for c in top2]
    phys_r    = np.array([abs(c["r"]) for c in top2])
    phys_w    = phys_r / phys_r.sum()

    phys_score = np.zeros(len(sub))
    for i, col in enumerate(phys_cols):
        col_vals  = sub[col].fillna(sub[col].median())
        col_std   = col_vals.std()
        col_mean  = col_vals.mean()
        z_score   = (col_vals - col_mean) / max(col_std, 1e-8)
        phys_score += phys_w[i] * np.clip(z_score * 16.67 + 50, 0, 100)  # z→[0,100]

    sub["model_b"] = sub["model_a"] + phys_score * 0.10  # 10% weight on physical

    rho_a, _ = scipy_stats.spearmanr(sub["vorp_yr2_5_avg"], sub["model_a"])
    rho_b, _ = scipy_stats.spearmanr(sub["vorp_yr2_5_avg"], sub["model_b"])

    return float(rho_a), float(rho_b), top2


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("MPS COMBINE BACKTEST (stripped)")
    print("=" * 60)

    # 1. Fetch historical combine data
    print("\n[1] Fetching historical combine data...")
    combine_data = fetch_historical_combine()

    # 2. Load training set
    print("\n[2] Loading training CSV...")
    df_train = pd.read_csv(DATASET)
    # Use 2010-2021 for correlation analysis (excludes 2022 holdout)
    df_full = df_train.copy()
    df_corr = df_train[df_train["draft_year"] <= 2021].copy()
    df_2022 = df_train[df_train["draft_year"] == 2022].copy()

    print(f"  Full training set: {len(df_train)} rows")
    print(f"  Correlation set (≤2021): {len(df_corr)} rows")
    print(f"  2022 holdout: {len(df_2022)} rows")

    # 3. Join combine data
    print("\n[3] Joining combine data to training rows...")
    df_corr_joined, skipped_top10 = join_to_training(combine_data, df_corr)
    df_2022_joined, _             = join_to_training(combine_data, df_2022)

    n_matched = df_corr_joined["combine_matched"].sum()
    n_total   = len(df_corr_joined)
    match_pct = n_matched / n_total * 100 if n_total > 0 else 0

    print(f"  Matched {n_matched}/{n_total} rows ({match_pct:.1f}%) to combine data")

    # 4. Pearson r correlations
    print("\n[4] Computing Pearson r (physical metrics vs vorp_yr2_5_avg)...")
    corr_rows = compute_correlations(df_corr_joined)

    # 5. Spearman ρ A/B on 2022 holdout
    print("\n[5] Spearman ρ A/B on 2022 holdout...")
    # Use training-set BPM bounds for normalization
    bpm_vals = df_corr["bpm_college"].dropna()
    bpm_min  = float(bpm_vals.quantile(0.02))
    bpm_max  = float(bpm_vals.quantile(0.98))

    rho_a, rho_b, top2 = spearman_ab(df_2022_joined, corr_rows, bpm_min, bpm_max)

    # ── Print results ─────────────────────────────────────────────────────────

    print("\n")
    print("=" * 60)
    print("  ===== COMBINE BACKTEST SUMMARY =====")
    print("=" * 60)
    print(f"  Training rows: {n_total}  |  Combine matches: {n_matched} ({match_pct:.1f}%)")

    if skipped_top10:
        print(f"\n  Top-10 picks with no combine match (likely skipped):")
        for p in skipped_top10:
            print(f"    - {p}")

    print(f"\n  Physical metric correlations vs vorp_yr2_5_avg (N≈{n_matched}):")
    print(f"  {'Metric':<38}  {'r':>7}  {'p':>7}  {'n':>5}  Signal?")
    print(f"  {'-'*38}  {'-'*7}  {'-'*7}  {'-'*5}  -------")
    for c in corr_rows:
        if c["r"] is None:
            print(f"  {c['metric']:<38}  {'N/A':>7}  {'N/A':>7}  {c['n']:>5}  (too few)")
            continue
        flag = "SIGNAL" if c["signal"] else "NOISE"
        print(f"  {c['metric']:<38}  {c['r']:>+7.3f}  {c['p']:>7.4f}  {c['n']:>5}  {flag}")

    print(f"\n  2022 holdout:")
    if not np.isnan(rho_a):
        print(f"    Model A (BPM×age):                  Spearman ρ = {rho_a:+.3f}")
    if not np.isnan(rho_b):
        used = [t["metric"] for t in top2]
        print(f"    Model B (BPM×age + {used}):  Spearman ρ = {rho_b:+.3f}")
        delta = rho_b - rho_a
        print(f"    Δρ = {delta:+.3f}")
    elif top2:
        print(f"    Model B: N/A (not enough holdout rows with combine data)")
    else:
        print(f"    Model B: N/A (no physical metrics above noise threshold)")

    print()
    if np.isnan(rho_a) or np.isnan(rho_b):
        verdict = "INSUFFICIENT DATA — cannot evaluate"
    elif (rho_b - rho_a) > 0.02:
        # Derive correlation-proportional weights
        signal_metrics = [c for c in corr_rows if c["signal"] and c["r"] is not None]
        total_r = sum(abs(c["r"]) for c in signal_metrics)
        phys_weights = {c["metric"]: round(abs(c["r"]) / total_r, 4) for c in signal_metrics}
        verdict = (
            f"Physical signal confirmed — Δρ > 0.02.\n"
            f"\n  Suggested PHYS_WEIGHTS (paste into scorer.py):\n"
            f"  PHYS_WEIGHTS = {phys_weights}"
        )
    else:
        verdict = "combine adds marginal signal — keep ±10 cap as tiebreaker"

    print(f"  Verdict: {verdict}")
    print("=" * 60)


if __name__ == "__main__":
    main()
