"""
nba_bpr_calibration.py

Post-processing calibration: maps player BPR aggregates → team wins.
Does not modify the core BPR model. Learns scale and feature weighting
to close the retrodiction gap (BPR RMSE 5.636 vs BPM 3.559).

Train: seasons 2022-2025 (120 team-seasons, all data from Django DB)
Hold-out: season 2026 (30 team-seasons)

Run:
    backend/.venv/bin/python nba_bpr_calibration.py
"""

from __future__ import annotations

import json
import os
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.stats
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.metrics import mean_squared_error

# ── Constants ──────────────────────────────────────────────────────────────────

SCRIPT_DIR  = Path(__file__).parent
OUTPUT_DIR  = SCRIPT_DIR / "metrics_output"
OUTPUT_DIR.mkdir(exist_ok=True)

DB_TO_BBREF = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO"}

TOP8_WEIGHTS       = [0.22, 0.18, 0.15, 0.13, 0.11, 0.09, 0.07, 0.05]
MIN_PLAYER_MINUTES = 200    # mpg * gp — below this, exclude from aggregation
STAR_BPR_THRESHOLD = 4.0   # BPR > 4.0 qualifies as star
STAR_MIN_THRESHOLD = 1500   # total minutes — must also meet this

TRAIN_SEASONS = [2022, 2023, 2024, 2025]
VAL_SEASON    = 2026
ALL_SEASONS   = TRAIN_SEASONS + [VAL_SEASON]

# Known benchmark values (from retrodiction script output)
BPR_RAW_RMSE = 5.636
BPM_RMSE     = 3.559
GAP          = BPR_RAW_RMSE - BPM_RMSE   # 2.077

FEATURE_SETS: dict[str, list[str]] = {
    "Calib_A_top8":  ["bpr_top8"],
    "Calib_B_multi": ["bpr_top8", "obpr_top8", "dbpr_top8"],
    "Calib_C_ridge": ["bpr_top8", "bpr_star", "star_count", "obpr_top8", "dbpr_top8", "bpr_mean"],
}

PROBLEM_TEAMS = {"IND", "LAL", "MIA", "TOR", "DAL"}

# ── Django setup ───────────────────────────────────────────────────────────────

sys.path.insert(0, str(SCRIPT_DIR / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from nba.models import NBAGame, NBAPlayerSeasonStats, NBATeamSeasonRatings


# ── Data loading ───────────────────────────────────────────────────────────────

def load_team_outcomes(season_years: list[int]) -> pd.DataFrame:
    """Wins from NBAGame + adj_net from NBATeamSeasonRatings, all seasons."""
    rows = []
    for year in season_years:
        wins: dict[int, int] = defaultdict(int)
        for game in NBAGame.objects.filter(
            season__year=year,
            status="Final",
            counts_toward_regular_season=True,
        ).select_related("home_team", "away_team"):
            if game.home_score and game.away_score:
                if game.home_score > game.away_score:
                    wins[game.home_team.pk] += 1
                else:
                    wins[game.away_team.pk] += 1

        n_teams = 0
        for r in NBATeamSeasonRatings.objects.filter(
            season__year=year, season_type="regular"
        ).select_related("team"):
            team_bbref = DB_TO_BBREF.get(r.team.abbreviation, r.team.abbreviation)
            rows.append({
                "season":      year,
                "team":        team_bbref,
                "actual_wins": wins.get(r.team.pk, np.nan),
                "adj_net":     r.adj_net,
            })
            n_teams += 1
        print(f"  {year}: {n_teams} teams, wins range [{min(wins.values(), default=0)}, {max(wins.values(), default=0)}]")

    return pd.DataFrame(rows)


def build_team_bpr_aggregates(season_years: list[int]) -> pd.DataFrame:
    """
    6 BPR features per team-season from NBAPlayerSeasonStats.
    Players with < MIN_PLAYER_MINUTES total minutes are excluded.
    """
    rows = []
    for year in season_years:
        qs = list(
            NBAPlayerSeasonStats.objects.filter(
                season__year=year,
                season_type="regular",
                bpr__isnull=False,
                team__isnull=False,
            ).select_related("team").values(
                "team__abbreviation",
                "bpr", "obpr", "dbpr", "mpg", "gp",
            )
        )

        team_players: dict[str, list[dict]] = defaultdict(list)
        for p in qs:
            total_min = (p["mpg"] or 0.0) * (p["gp"] or 0)
            if total_min < MIN_PLAYER_MINUTES:
                continue
            team_bbref = DB_TO_BBREF.get(p["team__abbreviation"], p["team__abbreviation"])
            team_players[team_bbref].append({
                "bpr":       p["bpr"]  or 0.0,
                "obpr":      p["obpr"] or 0.0,
                "dbpr":      p["dbpr"] or 0.0,
                "total_min": total_min,
            })

        for team, players in team_players.items():
            players_sorted = sorted(players, key=lambda x: x["total_min"], reverse=True)
            total_w = sum(p["total_min"] for p in players_sorted)

            # Feature 1: minutes-weighted mean BPR
            bpr_mean = (
                sum(p["bpr"] * p["total_min"] for p in players_sorted) / total_w
                if total_w else 0.0
            )

            # Feature 2: top-8 weighted BPR
            top8 = players_sorted[:8]
            n = len(top8)
            w8      = TOP8_WEIGHTS[:n]
            w8_norm = [w / sum(w8) for w in w8]
            bpr_top8  = sum(p["bpr"]  * w for p, w in zip(top8, w8_norm))
            obpr_top8 = sum(p["obpr"] * w for p, w in zip(top8, w8_norm))
            dbpr_top8 = sum(p["dbpr"] * w for p, w in zip(top8, w8_norm))

            # Feature 3: star premium
            stars = [
                p for p in players_sorted
                if p["bpr"] > STAR_BPR_THRESHOLD and p["total_min"] >= STAR_MIN_THRESHOLD
            ]
            if stars:
                star_w   = sum(p["total_min"] for p in stars)
                bpr_star = sum(p["bpr"] * p["total_min"] for p in stars) / star_w
            else:
                bpr_star = 0.0

            rows.append({
                "season":    year,
                "team":      team,
                "bpr_mean":  round(bpr_mean,  4),
                "bpr_top8":  round(bpr_top8,  4),
                "bpr_star":  round(bpr_star,  4),
                "star_count": len(stars),
                "obpr_top8": round(obpr_top8, 4),
                "dbpr_top8": round(dbpr_top8, 4),
                "n_players": len(players_sorted),
            })

        print(f"  {year}: {len(team_players)} teams aggregated")

    return pd.DataFrame(rows)


# ── Calibration ────────────────────────────────────────────────────────────────

def fit_calibration_models(df: pd.DataFrame) -> dict:
    train = df[df["season"] <= 2025].dropna(subset=["actual_wins"])
    val   = df[df["season"] == VAL_SEASON].dropna(subset=["actual_wins"])

    print(f"\nTrain: {len(train)} team-seasons ({TRAIN_SEASONS[0]}-{TRAIN_SEASONS[-1]})")
    print(f"Val:   {len(val)} team-seasons ({VAL_SEASON})")

    results = {}

    for name, features in FEATURE_SETS.items():
        train_sub = train[features + ["actual_wins", "team"]].dropna()
        val_sub   = val[features + ["actual_wins", "team"]].dropna()

        if name == "Calib_C_ridge":
            model = RidgeCV(alphas=[0.1, 1.0, 10.0, 100.0])
        else:
            model = LinearRegression()

        X_tr, y_tr = train_sub[features].values, train_sub["actual_wins"].values
        model.fit(X_tr, y_tr)

        tr_pred   = model.predict(X_tr)
        tr_rmse   = float(np.sqrt(mean_squared_error(y_tr, tr_pred)))
        tr_r2     = float(model.score(X_tr, y_tr))

        X_val, y_val = val_sub[features].values, val_sub["actual_wins"].values
        v_pred    = model.predict(X_val)
        v_rmse    = float(np.sqrt(mean_squared_error(y_val, v_pred)))
        v_r2      = float(1 - np.sum((y_val - v_pred) ** 2) / np.sum((y_val - y_val.mean()) ** 2))

        val_adj = val[features + ["adj_net"]].dropna()
        if len(val_adj) >= 5:
            srs_r = float(scipy.stats.pearsonr(
                model.predict(val_adj[features].values),
                val_adj["adj_net"].values,
            )[0])
        else:
            srs_r = float("nan")

        results[name] = {
            "model":      model,
            "features":   features,
            "train_rmse": round(tr_rmse, 3),
            "train_r2":   round(tr_r2,   3),
            "val_rmse":   round(v_rmse,  3),
            "val_r2":     round(v_r2,    3),
            "srs_r":      round(srs_r,   3),
            "val_teams":  val_sub["team"].tolist(),
            "val_actual": y_val.tolist(),
            "val_pred":   v_pred.tolist(),
        }

    return results


# ── Output ─────────────────────────────────────────────────────────────────────

def print_comparison_table(cal_results: dict) -> None:
    print("\n" + "=" * 78)
    print("CALIBRATION MODEL COMPARISON")
    print("=" * 78)
    print(f"{'Model':<20} {'Train_R²':>8} {'Tr_RMSE':>8} {'Val_RMSE':>9} {'Val_R²':>7} {'SRS_r':>7}")
    print("-" * 65)
    print(f"{'BPR (no calib)':<20} {'—':>8} {'—':>8} {BPR_RAW_RMSE:>9.3f} {'0.816':>7} {'0.934':>7}")
    print(f"{'BPM (benchmark)':<20} {'—':>8} {'—':>8} {BPM_RMSE:>9.3f} {'0.932':>7} {'0.997':>7}")
    print("-" * 65)
    for name, res in cal_results.items():
        label = name.replace("Calib_", "Calib_").replace("_", " ")
        overfit = res["train_rmse"] - res["val_rmse"]
        flag = " ⚠ overfit" if overfit < -1.5 else ""
        print(
            f"  {label:<18} {res['train_r2']:>8.3f} {res['train_rmse']:>8.3f} "
            f"{res['val_rmse']:>9.3f} {res['val_r2']:>7.3f} {res['srs_r']:>7.3f}{flag}"
        )
    print("=" * 78)


def select_best_model(cal_results: dict) -> str:
    """Lowest val_rmse that doesn't overfit (train_rmse - val_rmse < 1.5)."""
    candidates = {
        name: res for name, res in cal_results.items()
        if (res["train_rmse"] - res["val_rmse"]) > -1.5
    }
    if not candidates:
        candidates = cal_results  # fallback: ignore overfitting guard
    return min(candidates, key=lambda k: candidates[k]["val_rmse"])


def print_team_breakdown(best_name: str, best: dict, val_df: pd.DataFrame) -> None:
    print(f"\n{'='*78}")
    print(f"PER-TEAM BREAKDOWN — 2026 — {best_name}")
    print(f"{'='*78}")
    print(f"  {'Team':<6} {'Actual':>7} {'Raw_pred':>9} {'Calib_pred':>11} {'Raw_err':>8} {'Cal_err':>8}")
    print(f"  {'-'*52}")

    # Raw BPR predicted wins — use a simple linear fit on 2026 bpr_mean for comparison
    raw_reg = LinearRegression().fit(
        val_df[["bpr_mean"]].values,
        val_df["actual_wins"].values,
    )
    raw_pred = raw_reg.predict(val_df[["bpr_mean"]].values)

    calib_map = dict(zip(best["val_teams"], best["val_pred"]))
    actual_map = dict(zip(best["val_teams"], best["val_actual"]))

    rows = []
    for team in best["val_teams"]:
        actual  = actual_map.get(team, np.nan)
        cal_p   = calib_map.get(team, np.nan)
        idx     = val_df[val_df["team"] == team].index
        raw_p   = raw_pred[val_df.index.get_loc(idx[0])] if len(idx) else np.nan
        rows.append((team, actual, raw_p, cal_p, raw_p - actual, cal_p - actual))

    rows_sorted = sorted(rows, key=lambda x: abs(x[5]), reverse=True)
    for team, actual, raw_p, cal_p, raw_e, cal_e in rows_sorted:
        flag = " ◀ problem" if team in PROBLEM_TEAMS else ""
        better = " ✓ better" if abs(cal_e) < abs(raw_e) else ""
        worse  = " ✗ worse"  if abs(cal_e) > abs(raw_e) + 1.0 else ""
        note   = flag or better or worse
        print(
            f"  {team:<6} {actual:>7.0f} {raw_p:>9.1f} {cal_p:>11.1f} "
            f"{raw_e:>+8.1f} {cal_e:>+8.1f}{note}"
        )


def save_artifacts(best_name: str, best: dict, merged_df: pd.DataFrame) -> None:
    # Pickle the sklearn model
    model_path = OUTPUT_DIR / "bpr_calibration_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(best["model"], f)

    # JSON metadata
    meta = {
        "model_name":       best_name,
        "features":         best["features"],
        "training_seasons": TRAIN_SEASONS,
        "val_season":       VAL_SEASON,
        "training_rmse":    best["train_rmse"],
        "val_rmse":         best["val_rmse"],
        "val_r2":           best["val_r2"],
        "gap_closed_pct":   round((BPR_RAW_RMSE - best["val_rmse"]) / GAP * 100, 1),
        "coefficients":     best["model"].coef_.tolist(),
        "intercept":        float(best["model"].intercept_),
    }
    meta_path = OUTPUT_DIR / "bpr_calibration_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    # Team aggregates CSV
    agg_path = OUTPUT_DIR / "team_bpr_aggregates_2022_2026.csv"
    merged_df.to_csv(agg_path, index=False)

    print(f"\n[SAVED] {model_path.name}")
    print(f"[SAVED] {meta_path.name}")
    print(f"[SAVED] {agg_path.name}  ({len(merged_df)} rows)")


# ── Integration stub ───────────────────────────────────────────────────────────

def apply_bpr_calibration(
    team_bpr_aggregates: dict,   # {team_bbref: {"bpr_top8": float, ...}}
    calibration_model,
    calibration_meta: dict,
) -> dict[str, float]:
    """
    Post-process team BPR aggregates → predicted wins using fitted calibration.

    Integration point in nba_retrodiction_2025_26.py:
      After aggregate_to_teams() (line 559), before score_metric() (line 587).
      Add BPR_cal column to team_df, then score it like any other metric.

    Usage:
      cal_model = pickle.load(open("metrics_output/bpr_calibration_model.pkl", "rb"))
      cal_meta  = json.load(open("metrics_output/bpr_calibration_meta.json"))
      pred_wins = apply_bpr_calibration(team_aggs, cal_model, cal_meta)
      team_df["BPR_cal"] = team_df["team"].map(pred_wins)
    """
    features = calibration_meta["features"]
    rows, teams = [], []
    for team, aggs in team_bpr_aggregates.items():
        rows.append([aggs.get(f, 0.0) for f in features])
        teams.append(team)
    preds = calibration_model.predict(np.array(rows))
    return dict(zip(teams, preds.tolist()))


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("BPR CALIBRATION — Team-Wins Calibration Layer")
    print("=" * 78)

    # ── 1. Load outcomes ───────────────────────────────────────────────────────
    print("\n[STEP 1] Loading team outcomes (wins + adj_net) from DB...")
    outcomes = load_team_outcomes(ALL_SEASONS)
    print(f"  Total rows: {len(outcomes)}")

    # ── 2. Build BPR aggregates ────────────────────────────────────────────────
    print("\n[STEP 2] Building team BPR aggregates from DB...")
    aggregates = build_team_bpr_aggregates(ALL_SEASONS)
    print(f"  Total rows: {len(aggregates)}")

    # ── 3. Merge ───────────────────────────────────────────────────────────────
    merged = aggregates.merge(outcomes, on=["season", "team"], how="inner")
    print(f"\n[STEP 3] Merged: {len(merged)} team-seasons "
          f"({merged['actual_wins'].isna().sum()} missing wins)")

    missing_teams = set(aggregates["team"]) - set(outcomes["team"])
    if missing_teams:
        print(f"  Agg teams not in outcomes: {sorted(missing_teams)}")

    # ── 4. Fit calibration models ──────────────────────────────────────────────
    print("\n[STEP 4] Fitting calibration models...")
    cal_results = fit_calibration_models(merged)

    # ── 5. Print comparison table ──────────────────────────────────────────────
    print_comparison_table(cal_results)

    # ── 6. Select best model ───────────────────────────────────────────────────
    best_name = select_best_model(cal_results)
    best = cal_results[best_name]
    print(f"\nBest model: {best_name}  (val_rmse={best['val_rmse']:.3f})")

    # ── 7. Per-team breakdown ──────────────────────────────────────────────────
    val_df = merged[merged["season"] == VAL_SEASON].dropna(subset=["actual_wins"]).copy()
    val_df = val_df.reset_index(drop=True)
    print_team_breakdown(best_name, best, val_df)

    # ── 8. Save artifacts ──────────────────────────────────────────────────────
    save_artifacts(best_name, best, merged)

    # ── 9. Final summary ───────────────────────────────────────────────────────
    gap_closed = (BPR_RAW_RMSE - best["val_rmse"]) / GAP * 100
    status = "DEPLOY" if best["val_rmse"] < 4.5 else ("ITERATE" if best["val_rmse"] < 5.3 else "INSUFFICIENT GAIN")

    print("\n" + "=" * 78)
    print("BPR CALIBRATION RESULTS")
    print("=" * 78)
    print(f"  Training seasons:        {TRAIN_SEASONS[0]}-{TRAIN_SEASONS[-1]} ({len(TRAIN_SEASONS)*30} team-seasons)")
    print(f"  Validation season:       {VAL_SEASON} (30 team-seasons)")
    print(f"  Best model:              {best_name}")
    print(f"  Features:                {best['features']}")
    if hasattr(best["model"], "alpha_"):
        print(f"  Ridge alpha selected:    {best['model'].alpha_}")
    print(f"  Coefficients:            {[round(c, 4) for c in best['model'].coef_.tolist()]}")
    print(f"  Intercept:               {best['model'].intercept_:.3f}")
    print(f"")
    print(f"  Uncalibrated BPR RMSE:   {BPR_RAW_RMSE:.3f}")
    print(f"  Calibrated BPR RMSE:     {best['val_rmse']:.3f}")
    print(f"  BPM benchmark RMSE:      {BPM_RMSE:.3f}")
    print(f"  Gap closed:              {gap_closed:.1f}% of {GAP:.3f}-win gap")
    print(f"")

    # Indiana and LAL errors
    ind_idx = next((i for i, t in enumerate(best["val_teams"]) if t == "IND"), None)
    lal_idx = next((i for i, t in enumerate(best["val_teams"]) if t == "LAL"), None)
    if ind_idx is not None:
        ind_err = best["val_pred"][ind_idx] - best["val_actual"][ind_idx]
        print(f"  Indiana error:           raw ≈ +15 → calibrated {ind_err:+.1f}")
    if lal_idx is not None:
        lal_err = best["val_pred"][lal_idx] - best["val_actual"][lal_idx]
        print(f"  LAL error:               raw ≈ -11 → calibrated {lal_err:+.1f}")
    print(f"")
    print(f"  Recommendation:          {status}")
    print("=" * 78)


if __name__ == "__main__":
    main()
