"""
nba_recency_backtest.py

Grid search over within-season half-life and cross-season decay values.

Three evaluations:
  1. Mid-season split  — train first-half of target season, predict second-half margins
  2. Season holdout    — train on prior seasons, predict all target-season game margins
  3. Retrodiction      — full-season RAPM vs actual team win totals (OLS R²/RMSE)

Results saved to metrics_output/recency_backtest_results.csv.

Usage:
    backend/.venv/bin/python nba_recency_backtest.py
    backend/.venv/bin/python nba_recency_backtest.py --half-lives None,60,90,120
    backend/.venv/bin/python nba_recency_backtest.py --half-lives None,90 --cross-decays 0.5,1.0
    backend/.venv/bin/python nba_recency_backtest.py --season 2025 --train-years 2022 2023 2024
    backend/.venv/bin/python nba_recency_backtest.py --lambda-override 1000 --skip-midseason
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import warnings
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402
django.setup()

from nba.analytics.rapm import build_nba_observations, fit_baseline_rapm  # noqa: E402

OUTPUT_DIR = SCRIPT_DIR / "metrics_output"
OUTPUT_DIR.mkdir(exist_ok=True)
RESULTS_CSV = OUTPUT_DIR / "recency_backtest_results.csv"


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NBA recency weighting backtest")
    p.add_argument("--season", type=int, default=2026,
                   help="Target season year (default 2026)")
    p.add_argument("--rapm-years", type=int, nargs="+", default=None,
                   help="Seasons to pool for mid-season/retrodiction evals "
                        "(default: season-2, season-1, season)")
    p.add_argument("--train-years", type=int, nargs="+", default=None,
                   help="Training seasons for holdout eval "
                        "(default: season-3, season-2, season-1)")
    p.add_argument("--half-lives", default="None,30,45,60,90,120,180",
                   help="Comma-separated within-season half-lives in days. "
                        "Use 'None' for no decay. (default: None,30,45,60,90,120,180)")
    p.add_argument("--cross-decays", default="0.25,0.33,0.5,0.67,0.75,1.0",
                   help="Comma-separated cross-season decay values "
                        "(default: 0.25,0.33,0.5,0.67,0.75,1.0)")
    p.add_argument("--lambda-override", type=float, default=None,
                   help="Fix lambda across all configs (skip baseline CV)")
    p.add_argument("--skip-midseason", action="store_true",
                   help="Skip mid-season split eval")
    p.add_argument("--skip-holdout", action="store_true",
                   help="Skip season holdout eval")
    p.add_argument("--skip-retro", action="store_true",
                   help="Skip retrodiction eval")
    return p.parse_args()


def _parse_half_lives(s: str) -> list[float | None]:
    out: list[float | None] = []
    for part in s.split(","):
        part = part.strip()
        out.append(None if part.lower() == "none" else float(part))
    return out


def _parse_floats(s: str) -> list[float]:
    return [float(x.strip()) for x in s.split(",")]


# ── Data helpers ───────────────────────────────────────────────────────────────

def _build_player_season_index(observations: list[dict]) -> tuple[dict, int]:
    all_ps: set[tuple[int, int]] = set()
    for obs in observations:
        yr = obs["season_year"]
        for pid in obs["home_player_ids"] + obs["away_player_ids"]:
            all_ps.add((pid, yr))
    index = {ps: i for i, ps in enumerate(sorted(all_ps))}
    return index, len(index)


def _build_team_rapm(
    result: dict,
    rapm_years: list[int],      # years present in result; use most recent per player
    stats_season_year: int,     # which season's roster/minutes to aggregate by
) -> dict[str, float]:
    """Minutes-weighted avg net RAPM per team. Uses most recent year's estimate per player."""
    from nba.models import NBAPlayerSeasonStats

    # Most-recent-year estimate per player across rapm_years
    obpr_by_pid: dict[int, float] = {}
    dbpr_by_pid: dict[int, float] = {}
    for yr in sorted(rapm_years):
        for (pid, season_yr), v in result["obpr"].items():
            if season_yr == yr:
                obpr_by_pid[pid] = v
        for (pid, season_yr), v in result["dbpr"].items():
            if season_yr == yr:
                dbpr_by_pid[pid] = v

    rows = list(
        NBAPlayerSeasonStats.objects.filter(
            season__year=stats_season_year,
            season_type="regular",
        ).select_related("player", "team").only(
            "player__player_id", "team__nba_team_id", "mpg", "gp"
        )
    )

    team_weighted: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        if row.team is None:
            continue
        pid = row.player.player_id
        mins = (row.mpg or 0.0) * (row.gp or 0)
        if mins <= 0 or pid not in obpr_by_pid:
            continue
        net = obpr_by_pid[pid] + dbpr_by_pid.get(pid, 0.0)
        team_weighted[str(row.team.nba_team_id)].append((net, mins))

    return {
        tid: sum(v * m for v, m in pairs) / sum(m for _, m in pairs)
        for tid, pairs in team_weighted.items()
        if sum(m for _, m in pairs) > 0
    }


def _load_games(season_year: int) -> pd.DataFrame:
    from nba.models import NBAGame
    rows = []
    for g in NBAGame.objects.filter(
        season__year=season_year,
        status="Final",
        counts_toward_regular_season=True,
        pbp_quality_flag=False,
    ).select_related("home_team", "away_team").only(
        "game_id", "date", "home_score", "away_score",
        "home_team__nba_team_id", "away_team__nba_team_id",
    ):
        if g.home_score is None or g.away_score is None:
            continue
        rows.append({
            "game_id":      g.game_id,
            "date":         g.date,
            "home_team_id": str(g.home_team.nba_team_id),
            "away_team_id": str(g.away_team.nba_team_id),
            "margin":       g.home_score - g.away_score,
        })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _load_wins(season_year: int) -> dict[str, int]:
    from nba.models import NBAGame
    wins: dict[str, int] = defaultdict(int)
    for g in NBAGame.objects.filter(
        season__year=season_year, status="Final", counts_toward_regular_season=True,
    ).select_related("home_team", "away_team"):
        if g.home_score is not None and g.away_score is not None:
            if g.home_score > g.away_score:
                wins[str(g.home_team.nba_team_id)] += 1
            else:
                wins[str(g.away_team.nba_team_id)] += 1
    return dict(wins)


# ── Fitting ────────────────────────────────────────────────────────────────────

def _fit_config(
    observations: list[dict],
    player_season_index: dict,
    n_ps: int,
    target_year: int,
    within_hl: float | None,
    cross_decay: float,
    lambda_override: float | None,
    eval_date: date | None = None,
) -> dict:
    return fit_baseline_rapm(
        observations=observations,
        player_season_index=player_season_index,
        n_player_seasons=n_ps,
        run_cv=(lambda_override is None),
        lambda_override=lambda_override,
        target_season_year=target_year,
        cross_season_decay=cross_decay,
        within_season_half_life=within_hl,
        eval_date=eval_date,
    )


# ── Evaluation ─────────────────────────────────────────────────────────────────

def _predict_games(
    team_rapm: dict[str, float],
    games: pd.DataFrame,
    hca: float,
) -> dict:
    actual, predicted = [], []
    for _, row in games.iterrows():
        h, a = row["home_team_id"], row["away_team_id"]
        if h not in team_rapm or a not in team_rapm:
            continue
        actual.append(row["margin"])
        predicted.append(team_rapm[h] - team_rapm[a] + hca)
    if len(actual) < 5:
        return {"n": len(actual), "mae": float("nan"), "acc": float("nan")}
    act = np.array(actual)
    pred = np.array(predicted)
    return {
        "n":   len(actual),
        "mae": float(np.mean(np.abs(act - pred))),
        "acc": float(np.mean((act > 0) == (pred > 0))),
    }


def _retrodiction_eval(
    team_rapm: dict[str, float],
    actual_wins: dict[str, int],
) -> dict:
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    pairs = [(team_rapm[tid], w) for tid, w in actual_wins.items() if tid in team_rapm]
    if len(pairs) < 5:
        return {"n": len(pairs), "r2": float("nan"), "rmse": float("nan"), "mae": float("nan")}

    X = np.array([x for x, _ in pairs]).reshape(-1, 1)
    y = np.array([w for _, w in pairs])
    reg = LinearRegression().fit(X, y)
    y_pred = reg.predict(X)
    return {
        "n":    len(pairs),
        "r2":   float(reg.score(X, y)),
        "rmse": float(np.sqrt(mean_squared_error(y, y_pred))),
        "mae":  float(mean_absolute_error(y, y_pred)),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    season_year   = args.season
    rapm_years    = args.rapm_years or [season_year - 2, season_year - 1, season_year]
    train_years   = args.train_years or [season_year - 3, season_year - 2, season_year - 1]
    half_lives    = _parse_half_lives(args.half_lives)
    cross_decays  = _parse_floats(args.cross_decays)
    lam_override  = args.lambda_override
    do_midseason  = not args.skip_midseason
    do_holdout    = not args.skip_holdout
    do_retro      = not args.skip_retro

    n_configs = len(half_lives) * len(cross_decays)
    evals = [e for e, flag in [("mid-season", do_midseason), ("holdout", do_holdout), ("retro", do_retro)] if flag]

    print(f"\n{'='*70}")
    print("NBA RECENCY WEIGHTING BACKTEST")
    print(f"  Target season : {season_year}")
    print(f"  RAPM pool     : {rapm_years}  (mid-season + retrodiction)")
    print(f"  Holdout train : {train_years}  → predict {season_year}")
    print(f"  Grid          : {len(half_lives)} half-lives × {len(cross_decays)} cross-decays = {n_configs} configs")
    print(f"  Evals         : {', '.join(evals)}")
    print(f"{'='*70}\n")

    # ── Load target-season games ────────────────────────────────────────────────
    print(f"Loading {season_year} game records...")
    all_games = _load_games(season_year)
    if len(all_games) == 0:
        print("ERROR: No games found.")
        return
    print(f"  {len(all_games)} completed games")

    # Mid-season split
    cutoff_date    = all_games["date"].median().date()
    train_game_ids = set(all_games[all_games["date"].dt.date <= cutoff_date]["game_id"])
    test_games     = all_games[all_games["date"].dt.date > cutoff_date].copy()
    print(f"  Mid-season split at {cutoff_date}: {len(train_game_ids)} train / {len(test_games)} test")

    actual_wins = _load_wins(season_year)
    print(f"  {len(actual_wins)} teams with win totals")

    # ── Load observations ───────────────────────────────────────────────────────
    print(f"\nLoading observations...")

    full_obs = None
    full_psi = None
    full_nps = None
    mid_obs  = None
    mid_psi  = None
    mid_nps  = None

    if do_midseason or do_retro:
        print(f"  Full-season pool {rapm_years}...")
        full_obs = build_nba_observations(season_year=season_year, rapm_years=rapm_years)
        full_psi, full_nps = _build_player_season_index(full_obs)
        print(f"    {len(full_obs)} observations  ({full_nps} player-seasons)")

    if do_midseason:
        mid_obs = [o for o in full_obs if o["game_id"] in train_game_ids]
        mid_psi, mid_nps = _build_player_season_index(mid_obs)
        print(f"  First-half only: {len(mid_obs)} observations  ({mid_nps} player-seasons)")

    holdout_obs = None
    holdout_psi = None
    holdout_nps = None

    if do_holdout:
        print(f"  Holdout train {train_years}...")
        holdout_obs = build_nba_observations(season_year=max(train_years), rapm_years=train_years)
        holdout_psi, holdout_nps = _build_player_season_index(holdout_obs)
        print(f"    {len(holdout_obs)} observations  ({holdout_nps} player-seasons)")

    # ── Baseline CV (runs once) ─────────────────────────────────────────────────
    fixed_lambda = lam_override
    baseline_hl, baseline_csd = None, 0.5

    if fixed_lambda is None:
        print(f"\nBaseline CV (hl=None, csd=0.5) to select lambda...")
        t0 = time.time()
        ref_obs = full_obs if full_obs is not None else holdout_obs
        ref_psi, ref_nps = (full_psi, full_nps) if full_obs is not None else (holdout_psi, holdout_nps)
        ref_year = season_year if full_obs is not None else max(train_years)
        cv_result = _fit_config(ref_obs, ref_psi, ref_nps, ref_year,
                                within_hl=None, cross_decay=0.5, lambda_override=None)
        fixed_lambda = cv_result["lambda"]
        print(f"  λ={fixed_lambda:.1f}  ({time.time()-t0:.1f}s)")
    else:
        print(f"\nUsing fixed λ={fixed_lambda:.1f} (--lambda-override)")

    # ── Column headers ──────────────────────────────────────────────────────────
    col_parts = ["Config"]
    if do_midseason: col_parts += ["[MID] MAE", "Acc%"]
    if do_holdout:   col_parts += ["[HOLD] MAE", "Acc%"]
    if do_retro:     col_parts += ["[RETRO] R²", "RMSE"]
    col_parts += ["time"]

    header = f"  {'Config':<26}"
    if do_midseason: header += f" {'[MID] MAE':>10} {'Acc%':>6}"
    if do_holdout:   header += f" {'[HOLD] MAE':>10} {'Acc%':>6}"
    if do_retro:     header += f" {'[RETRO] R²':>10} {'RMSE':>6}"
    header += f" {'t':>5}"

    print(f"\nGrid search  λ={fixed_lambda:.1f}")
    print(header)
    print("  " + "-" * (len(header) - 2))

    results: list[dict] = []

    for within_hl in half_lives:
        for cross_decay in cross_decays:
            label = f"hl={str(within_hl) if within_hl else 'None':>5}  csd={cross_decay:.2f}"
            is_baseline = (within_hl == baseline_hl and cross_decay == baseline_csd)
            t0 = time.time()
            row: dict = {
                "within_season_half_life": within_hl,
                "cross_season_decay":      cross_decay,
                "is_baseline":             is_baseline,
                "lambda":                  fixed_lambda,
            }

            # Mid-season
            mid_mae = mid_acc = float("nan")
            if do_midseason:
                mid_result = _fit_config(
                    mid_obs, mid_psi, mid_nps, season_year,
                    within_hl=within_hl, cross_decay=cross_decay,
                    lambda_override=fixed_lambda, eval_date=cutoff_date,
                )
                mid_rapm = _build_team_rapm(mid_result, [season_year], season_year)
                mp = _predict_games(mid_rapm, test_games, mid_result.get("hca", 0.0))
                mid_mae, mid_acc = mp["mae"], mp["acc"]
                row.update({"mid_n": mp["n"], "mid_mae": mid_mae, "mid_acc": mid_acc})

            # Season holdout
            hold_mae = hold_acc = float("nan")
            if do_holdout:
                hold_result = _fit_config(
                    holdout_obs, holdout_psi, holdout_nps, max(train_years),
                    within_hl=within_hl, cross_decay=cross_decay,
                    lambda_override=fixed_lambda,
                )
                hold_rapm = _build_team_rapm(hold_result, train_years, season_year)
                hp = _predict_games(hold_rapm, all_games, hold_result.get("hca", 0.0))
                hold_mae, hold_acc = hp["mae"], hp["acc"]
                row.update({"hold_n": hp["n"], "hold_mae": hold_mae, "hold_acc": hold_acc})

            # Retrodiction
            retro_r2 = retro_rmse = float("nan")
            if do_retro:
                full_result = _fit_config(
                    full_obs, full_psi, full_nps, season_year,
                    within_hl=within_hl, cross_decay=cross_decay,
                    lambda_override=fixed_lambda,
                )
                retro_rapm = _build_team_rapm(full_result, rapm_years, season_year)
                re = _retrodiction_eval(retro_rapm, actual_wins)
                retro_r2, retro_rmse = re["r2"], re["rmse"]
                row.update({"retro_n": re["n"], "retro_r2": retro_r2,
                            "retro_rmse": retro_rmse, "retro_mae": re["mae"]})

            elapsed = time.time() - t0
            row["elapsed_s"] = round(elapsed, 1)
            results.append(row)

            line = f"  {label:<26}"
            if do_midseason:
                line += f" {mid_mae:>10.2f} {mid_acc*100:>6.1f}" if not np.isnan(mid_mae) else f" {'nan':>10} {'nan':>6}"
            if do_holdout:
                line += f" {hold_mae:>10.2f} {hold_acc*100:>6.1f}" if not np.isnan(hold_mae) else f" {'nan':>10} {'nan':>6}"
            if do_retro:
                line += f" {retro_r2:>10.3f} {retro_rmse:>6.2f}" if not np.isnan(retro_r2) else f" {'nan':>10} {'nan':>6}"
            line += f" {elapsed:5.1f}s"
            if is_baseline:
                line += "  ← BASELINE"
            print(line)

    # ── Save + summary ──────────────────────────────────────────────────────────
    df = pd.DataFrame(results)
    df.to_csv(RESULTS_CSV, index=False)
    print(f"\n[SAVED] {RESULTS_CSV}")

    _print_summary(df, do_midseason, do_holdout, do_retro)


def _print_summary(df: pd.DataFrame, do_midseason: bool, do_holdout: bool, do_retro: bool) -> None:
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")

    base = df[df["is_baseline"]]
    if not base.empty:
        b = base.iloc[0]
        print("\n  Baseline (hl=None, csd=0.50):")
        if do_midseason and "mid_mae" in b: print(f"    Mid-season  MAE={b['mid_mae']:.3f}  Acc={b['mid_acc']*100:.1f}%")
        if do_holdout   and "hold_mae" in b: print(f"    Holdout     MAE={b['hold_mae']:.3f}  Acc={b['hold_acc']*100:.1f}%")
        if do_retro     and "retro_r2" in b: print(f"    Retrodiction R²={b['retro_r2']:.3f}  RMSE={b['retro_rmse']:.3f}")

    def _best(col: str, ascending: bool, label: str) -> None:
        sub = df.dropna(subset=[col])
        if sub.empty:
            return
        row = sub.loc[sub[col].idxmin() if ascending else sub[col].idxmax()]
        hl  = f"{int(row['within_season_half_life'])}d" if pd.notna(row["within_season_half_life"]) else "None"
        csd = row["cross_season_decay"]
        print(f"\n  Best {label}:  hl={hl}  csd={csd:.2f}")
        if do_midseason and "mid_mae" in row and not np.isnan(row["mid_mae"]):
            print(f"    Mid-season  MAE={row['mid_mae']:.3f}  Acc={row['mid_acc']*100:.1f}%")
        if do_holdout and "hold_mae" in row and not np.isnan(row.get("hold_mae", float("nan"))):
            print(f"    Holdout     MAE={row['hold_mae']:.3f}  Acc={row['hold_acc']*100:.1f}%")
        if do_retro and "retro_r2" in row and not np.isnan(row.get("retro_r2", float("nan"))):
            print(f"    Retrodiction R²={row['retro_r2']:.3f}  RMSE={row['retro_rmse']:.3f}")
        # delta vs baseline
        if not base.empty:
            b = base.iloc[0]
            if ascending and col in b and not np.isnan(b[col]):
                d = b[col] - row[col]
                print(f"    vs baseline: {'+' if d>=0 else ''}{d:.3f} ({col})")
            elif not ascending and col in b and not np.isnan(b[col]):
                d = row[col] - b[col]
                print(f"    vs baseline: {'+' if d>=0 else ''}{d:.3f} ({col})")

    if do_midseason:  _best("mid_mae",  ascending=True,  label="mid-season game pred (↓ MAE)")
    if do_holdout:    _best("hold_mae", ascending=True,  label="holdout game pred     (↓ MAE)")
    if do_retro:      _best("retro_r2", ascending=False, label="retrodiction          (↑ R²)")

    # Joint rank across available metrics
    rank_cols = []
    valid = df.copy()
    if do_midseason and "mid_mae" in valid:
        valid["_r_mid"]  = valid["mid_mae"].rank(ascending=True)
        rank_cols.append("_r_mid")
    if do_holdout and "hold_mae" in valid:
        valid["_r_hold"] = valid["hold_mae"].rank(ascending=True)
        rank_cols.append("_r_hold")
    if do_retro and "retro_r2" in valid:
        valid["_r_retro"] = valid["retro_r2"].rank(ascending=False)
        rank_cols.append("_r_retro")
    if rank_cols:
        valid["_joint"] = valid[rank_cols].sum(axis=1)
        best = valid.loc[valid["_joint"].idxmin()]
        hl  = f"{int(best['within_season_half_life'])}d" if pd.notna(best["within_season_half_life"]) else "None"
        print(f"\n  Best combined (joint rank across {len(rank_cols)} metric{'s' if len(rank_cols)>1 else ''}):")
        print(f"    hl={hl}  csd={best['cross_season_decay']:.2f}")

    print(f"\n{'='*70}")
    print(f"Full results: {RESULTS_CSV}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=UserWarning)
    main()
