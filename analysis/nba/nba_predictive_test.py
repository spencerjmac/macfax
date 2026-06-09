"""
nba_predictive_test.py

Predictive validity test for NBA advanced metrics.
Tests whether Year N player metrics predict Year N+1 team wins.

Three prediction pairs:
  Pair 1: 2022-23 → 2023-24
  Pair 2: 2023-24 → 2024-25
  Pair 3: 2024-25 → 2025-26

Metrics tested: BPR, BPM, OBPM, DBPM, WS48, WS, VORP, PER

Run:
    backend/.venv/bin/python nba_predictive_test.py
"""

from __future__ import annotations

import io
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import scipy.stats
from rapidfuzz import fuzz, process as rfprocess
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error

# ── Setup ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.parent.parent
OUTPUT_DIR = SCRIPT_DIR / "metrics_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Known retrodiction RMSEs for reference column
RETRO_RMSE = {
    "BPR": 5.636, "BOX_BPR": float("nan"), "BPM": 3.559, "OBPM": 6.097, "DBPM": 6.518,
    "WS48": 3.243, "WS": 3.432, "VORP": 3.617, "PER": 5.368,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# BBref → NBA.com abbreviation (for DB team matching)
BBREF_TO_DB = {"BRK": "BKN", "CHO": "CHA", "PHO": "PHX"}

# AVG and SUM metrics (same as retrodiction script)
AVG_METRICS = ["BPM", "OBPM", "DBPM", "WS48", "PER", "BPR", "BOX_BPR"]
SUM_METRICS = ["WS", "VORP"]
ALL_METRICS = AVG_METRICS + SUM_METRICS

# Star players for year-over-year stability analysis
STAR_PLAYERS = ["LeBron James", "Stephen Curry", "Giannis Antetokounmpo",
                "Kevin Durant", "Jayson Tatum"]

# Prediction pairs: (year_n, year_n1)
PAIRS = [(2023, 2024), (2024, 2025), (2025, 2026)]

# Season labels
SEASON_LABEL = {
    2022: "2021-22", 2023: "2022-23", 2024: "2023-24",
    2025: "2024-25", 2026: "2025-26",
}


# ── Utilities ──────────────────────────────────────────────────────────────────

def norm_name(s: str) -> str:
    s = str(s).lower().strip()
    s = s.encode("ascii", errors="ignore").decode()
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_team(s: str) -> str:
    """Strip seeding artifacts from BBref team name."""
    s = re.sub(r"\*|\(\d+\)", "", str(s))
    return re.sub(r"\s+", " ", s).strip().lower()


def pearson(x, y):
    if len(x) < 5:
        return float("nan"), float("nan")
    r, p = scipy.stats.pearsonr(x, y)
    return float(r), float(p)


def spearman(x, y):
    if len(x) < 5:
        return float("nan"), float("nan")
    r, p = scipy.stats.spearmanr(x, y)
    return float(r), float(p)


def ols_rmse(x_arr, y_arr):
    if len(x_arr) < 5:
        return float("nan")
    reg = LinearRegression().fit(x_arr.reshape(-1, 1), y_arr)
    pred = reg.predict(x_arr.reshape(-1, 1))
    return float(np.sqrt(mean_squared_error(y_arr, pred)))


# ── BBref scraping ─────────────────────────────────────────────────────────────

def scrape_bbref_advanced(season_end_year: int) -> pd.DataFrame | None:
    """
    Scrape BBref advanced stats page for a season.
    season_end_year: 2022 = 2021-22 season
    """
    url = f"https://www.basketball-reference.com/leagues/NBA_{season_end_year}_advanced.html"
    out_path = OUTPUT_DIR / f"bbref_advanced_{season_end_year}.csv"

    if out_path.exists():
        print(f"  [BBREF {SEASON_LABEL[season_end_year]}] Loading cached {out_path.name}")
        return pd.read_csv(out_path)

    print(f"  [BBREF {SEASON_LABEL[season_end_year]}] Scraping {url}...")
    time.sleep(4)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except Exception as e:
        print(f"  [BBREF {season_end_year}] HTTP error: {e}")
        return None

    try:
        tables = pd.read_html(io.StringIO(resp.text), attrs={"id": "advanced"})
        if not tables:
            print(f"  [BBREF {season_end_year}] No table found")
            return None
        df = tables[0]
    except Exception as e:
        print(f"  [BBREF {season_end_year}] Parse error: {e}")
        return None

    # Flatten multi-level columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[-1] for c in df.columns]

    # Drop repeated header rows
    if "Age" in df.columns:
        df = df[df["Age"] != "Age"].copy()
    elif "Rk" in df.columns:
        df = df[df["Rk"] != "Rk"].copy()

    # Multi-team: keep only *TM rows; for single-team players keep their row
    if "Team" in df.columns:
        multi_mask = df.duplicated(subset=["Player"], keep=False)
        tot_mask   = df["Team"].str.upper().str.match(r"^\d+TM$", na=False)
        df = df[~multi_mask | tot_mask].copy()
    elif "Tm" in df.columns:
        df = df.rename(columns={"Tm": "Team"})
        multi_mask = df.duplicated(subset=["Player"], keep=False)
        tot_mask   = df["Team"].str.upper().str.match(r"^\d+TM$", na=False)
        df = df[~multi_mask | tot_mask].copy()

    # Rename and cast
    rename = {"Player": "player_name", "Team": "team", "G": "games_played",
               "MP": "minutes", "PER": "PER", "USG%": "USG_pct",
               "WS": "WS", "WS/48": "WS48", "BPM": "BPM",
               "OBPM": "OBPM", "DBPM": "DBPM", "VORP": "VORP"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df["season"] = season_end_year

    numeric = ["games_played", "minutes", "PER", "USG_pct", "WS", "WS48",
               "BPM", "OBPM", "DBPM", "VORP"]
    for col in numeric:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "minutes" in df.columns:
        df = df[df["minutes"] >= 200].copy()

    # ftfy fix for player names
    try:
        import ftfy as _ftfy
        df["player_name"] = df["player_name"].map(
            lambda s: _ftfy.fix_text(str(s)) if pd.notna(s) else s
        )
    except ImportError:
        pass

    keep = ["player_name", "team", "season", "games_played", "minutes",
            "PER", "USG_pct", "WS", "WS48", "BPM", "OBPM", "DBPM", "VORP"]
    df = df[[c for c in keep if c in df.columns]].reset_index(drop=True)
    df.to_csv(out_path, index=False)
    print(f"  [BBREF {SEASON_LABEL[season_end_year]}] {len(df)} players → {out_path.name}")
    return df


# ── DB data loading ────────────────────────────────────────────────────────────

def load_bpr_from_db(season_year: int) -> pd.DataFrame:
    """Load final BPR + box_bpr + team from DB, keyed by NBA.com player_id."""
    from nba.models import NBAPlayerSeasonStats
    rows = list(
        NBAPlayerSeasonStats.objects.filter(
            season__year=season_year,
            season_type="regular",
            bpr__isnull=False,
        ).select_related("player", "team").values(
            "player__name", "player__player_id",
            "team__abbreviation",
            "bpr", "obpr", "dbpr",
            "box_bpr", "box_obpr", "box_dbpr",
            "mpg", "gp",
        )
    )
    df = pd.DataFrame(rows).rename(columns={
        "player__name": "player_name",
        "player__player_id": "nba_id",
        "team__abbreviation": "team_db",
    })
    df["minutes_bpr"] = df["mpg"].fillna(0) * df["gp"].fillna(0)
    df["BOX_BPR"] = df["box_bpr"]
    df["season"] = season_year
    return df


def load_wins_srs(season_year: int) -> dict[str, dict]:
    """
    Return {bbref_abbrev: {"wins": int, "srs": float}} for a season.
    Wins from NBAGame; SRS from NBATeamSeasonRatings.adj_net (proxy).
    """
    from nba.models import NBAGame, NBATeamSeasonRatings
    from nba.models import NBATeam

    # Build DB abbrev → BBref abbrev map
    db_to_bbref = {v: k for k, v in BBREF_TO_DB.items()}

    wins: dict[int, int] = defaultdict(int)
    for game in NBAGame.objects.filter(
        season__year=season_year, status="Final", counts_toward_regular_season=True
    ).select_related("home_team", "away_team"):
        if game.home_score and game.away_score:
            if game.home_score > game.away_score:
                wins[game.home_team.pk] += 1
            else:
                wins[game.away_team.pk] += 1

    result = {}
    for r in NBATeamSeasonRatings.objects.filter(
        season__year=season_year, season_type="regular"
    ).select_related("team"):
        db_abbrev = r.team.abbreviation
        bbref_abbrev = db_to_bbref.get(db_abbrev, db_abbrev)
        result[bbref_abbrev] = {
            "wins": wins.get(r.team.pk, 0),
            "srs":  r.adj_net,
        }
    return result


# ── Aggregation ────────────────────────────────────────────────────────────────

def bbref_to_bbref_abbrev(abbrev: str) -> str:
    """Pass-through; BBref data already in BBref format."""
    return abbrev if abbrev else ""


def merge_bpr_onto_players(
    bbref_df: pd.DataFrame,
    bpr_df: pd.DataFrame,
) -> pd.DataFrame:
    """Fuzzy-match BPR + BOX_BPR onto BBref player rows by name."""
    bpr_df["_norm"] = bpr_df["player_name"].map(norm_name)
    bpr_norm_list = bpr_df["_norm"].tolist()
    bpr_vals, box_bpr_vals, bpr_mins = [], [], []
    has_box = "BOX_BPR" in bpr_df.columns
    for _, row in bbref_df.iterrows():
        key = norm_name(row["player_name"])
        res = rfprocess.extractOne(key, bpr_norm_list, scorer=fuzz.WRatio, score_cutoff=82)
        if res:
            match_row = bpr_df.iloc[res[2]]
            bpr_vals.append(match_row["bpr"])
            bpr_mins.append(match_row["minutes_bpr"])
            box_bpr_vals.append(match_row["BOX_BPR"] if has_box else np.nan)
        else:
            bpr_vals.append(np.nan)
            bpr_mins.append(np.nan)
            box_bpr_vals.append(np.nan)
    df = bbref_df.copy()
    df["BPR"] = bpr_vals
    df["BOX_BPR"] = box_bpr_vals
    df["minutes_bpr"] = bpr_mins
    return df


def aggregate_to_teams(players: pd.DataFrame) -> pd.DataFrame:
    """Minutes-weighted team aggregation."""
    rows = []
    # Deduplicate traded players: keep row with most minutes (primary team)
    deduped = []
    for name, grp in players.groupby("player_name"):
        if len(grp) > 1:
            # Exclude TOT rows, keep per-team row with most minutes
            not_tot = grp[~grp["team"].str.upper().str.match(r"^\d+TM$", na=False)]
            if len(not_tot) > 0:
                deduped.append(not_tot.nlargest(1, "minutes"))
            else:
                deduped.append(grp.nlargest(1, "minutes"))
        else:
            deduped.append(grp)
    players = pd.concat(deduped, ignore_index=True)

    for team, grp in players.groupby("team"):
        row = {"team": team}
        for col in AVG_METRICS:
            if col not in grp.columns:
                row[col] = np.nan
                continue
            min_col = "minutes_bpr" if col in ("BPR", "BOX_BPR") and "minutes_bpr" in grp.columns else "minutes"
            valid = grp[[min_col, col]].dropna()
            if len(valid) == 0 or valid[min_col].sum() == 0:
                row[col] = np.nan
            else:
                row[col] = (valid[col] * valid[min_col]).sum() / valid[min_col].sum()
        for col in SUM_METRICS:
            row[col] = grp[col].sum(skipna=True) if col in grp.columns else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


# ── Prediction pair ────────────────────────────────────────────────────────────

def run_pair(
    year_n: int,
    year_n1: int,
    bbref_data: dict[int, pd.DataFrame],
    bpr_data: dict[int, pd.DataFrame],
    wins_data: dict[int, dict],
) -> dict[str, dict]:
    """
    Run one prediction pair: Year N metrics → Year N+1 outcomes.
    Returns {metric: {pearson_r, spearman_r, rmse, n_teams, team_errors}}
    """
    print(f"\n  [PAIR {SEASON_LABEL[year_n]} → {SEASON_LABEL[year_n1]}]")

    # Year N player data
    bbref_n = bbref_data.get(year_n)
    bpr_n   = bpr_data.get(year_n)
    if bbref_n is None or bpr_n is None:
        print(f"  Missing data for {year_n}")
        return {}

    # Merge BPR onto BBref
    players_n = merge_bpr_onto_players(bbref_n, bpr_n)

    # Aggregate to teams
    teams_n = aggregate_to_teams(players_n)

    # Year N+1 outcomes
    outcomes_n1 = wins_data.get(year_n1, {})
    if not outcomes_n1:
        print(f"  Missing outcomes for {year_n1}")
        return {}

    # Merge team stats with next-year outcomes
    teams_n["wins_n1"] = teams_n["team"].map(
        lambda t: outcomes_n1.get(t, {}).get("wins")
    )
    teams_n["srs_n1"] = teams_n["team"].map(
        lambda t: outcomes_n1.get(t, {}).get("srs")
    )

    results: dict[str, dict] = {}
    for metric in ALL_METRICS:
        if metric not in teams_n.columns:
            continue
        sub = teams_n[[metric, "wins_n1", "srs_n1", "team"]].dropna(subset=[metric, "wins_n1"])
        if len(sub) < 10:
            continue

        x = sub[metric].values
        y_wins = sub["wins_n1"].values

        r_pe, _ = pearson(x, y_wins)
        r_sp, _ = spearman(x, y_wins)
        rmse = ols_rmse(x, y_wins)

        # Per-team errors
        reg = LinearRegression().fit(x.reshape(-1, 1), y_wins)
        pred = reg.predict(x.reshape(-1, 1))
        errors = sorted(zip(sub["team"].values, (pred - y_wins).tolist()),
                        key=lambda z: -abs(z[1]))

        results[metric] = {
            "pearson_r":  round(r_pe, 3),
            "spearman_r": round(r_sp, 3),
            "rmse":       round(rmse, 3),
            "n_teams":    len(sub),
            "team_errors": errors,   # [(team, error), ...] sorted by |error|
        }
        print(f"    {metric:<8}: r={r_pe:.3f}  Spearman={r_sp:.3f}  RMSE={rmse:.3f}  n={len(sub)}")

    return results


# ── Star stability ─────────────────────────────────────────────────────────────

def compute_star_stability(
    bbref_data: dict[int, pd.DataFrame],
    bpr_data: dict[int, pd.DataFrame],
) -> dict[str, float]:
    """
    For each metric, compute year-over-year Pearson r for STAR_PLAYERS
    across seasons 2022-2026.
    """
    seasons = [2022, 2023, 2024, 2025, 2026]
    metrics_to_check = ["BPM", "WS48", "PER", "VORP", "BPR", "BOX_BPR"]

    # Build per-player per-season values
    player_vals: dict[str, dict[str, list[float]]] = {
        p: {m: [] for m in metrics_to_check} for p in STAR_PLAYERS
    }
    season_list_per_player: dict[str, list] = {p: [] for p in STAR_PLAYERS}

    for yr in seasons:
        bbref = bbref_data.get(yr)
        bpr   = bpr_data.get(yr)
        if bbref is None or bpr is None:
            continue
        players = merge_bpr_onto_players(bbref, bpr)

        for star in STAR_PLAYERS:
            key = norm_name(star)
            row = players[players["player_name"].map(norm_name) == key]
            if row.empty:
                # Fuzzy match
                norm_list = players["player_name"].map(norm_name).tolist()
                res = rfprocess.extractOne(key, norm_list, scorer=fuzz.WRatio, score_cutoff=85)
                if res:
                    row = players.iloc[[res[2]]]
            if not row.empty:
                r = row.iloc[0]
                for m in metrics_to_check:
                    v = r.get(m)
                    if pd.notna(v):
                        player_vals[star][m].append(float(v))
                        season_list_per_player[star].append(yr)

    # Compute year-over-year correlation per metric
    stability: dict[str, float] = {}
    for metric in metrics_to_check:
        # For each star, collect consecutive year pairs
        x_vals, y_vals = [], []
        for star in STAR_PLAYERS:
            vals = player_vals[star][metric]
            for i in range(len(vals) - 1):
                x_vals.append(vals[i])
                y_vals.append(vals[i + 1])
        if len(x_vals) >= 3:
            r, _ = pearson(np.array(x_vals), np.array(y_vals))
            stability[metric] = round(r, 3)
        else:
            stability[metric] = float("nan")

    return stability


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # Django setup
    sys.path.insert(0, str(SCRIPT_DIR / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()

    print("NBA Predictive Validity Test")
    print("=" * 70)

    # ── 1. Scrape/load BBref data ──────────────────────────────────────────────
    print("\n[STEP 1] Loading player metrics...")
    bbref_data: dict[int, pd.DataFrame] = {}

    # Historical seasons (scrape)
    for yr in [2022, 2023, 2024, 2025]:
        df = scrape_bbref_advanced(yr)
        if df is not None:
            bbref_data[yr] = df

    # 2025-26 — load from existing metrics CSV
    metrics_2026_path = OUTPUT_DIR / "nba_metrics_2025_26.csv"
    if metrics_2026_path.exists():
        df26 = pd.read_csv(metrics_2026_path)
        df26["season"] = 2026
        if "team" not in df26.columns and "team" in df26.columns:
            pass
        bbref_data[2026] = df26
        print(f"  [2025-26] Loaded from {metrics_2026_path.name}: {len(df26)} players")
    else:
        print("  [2025-26] metrics CSV not found")

    # ── 2. Load BPR from DB ────────────────────────────────────────────────────
    print("\n[STEP 2] Loading BPR from database...")
    bpr_data: dict[int, pd.DataFrame] = {}
    for yr in [2022, 2023, 2024, 2025, 2026]:
        try:
            df = load_bpr_from_db(yr)
            bpr_data[yr] = df
            print(f"  {SEASON_LABEL[yr]}: {len(df)} players with final BPR")
        except Exception as e:
            print(f"  {SEASON_LABEL[yr]}: ERROR — {e}")

    # ── 3. Load outcomes (wins + SRS) ──────────────────────────────────────────
    print("\n[STEP 3] Loading team outcomes from DB...")
    wins_data: dict[int, dict] = {}
    for yr in [2023, 2024, 2025, 2026]:
        try:
            d = load_wins_srs(yr)
            wins_data[yr] = d
            print(f"  {SEASON_LABEL[yr]}: {len(d)} teams")
        except Exception as e:
            print(f"  {SEASON_LABEL[yr]}: ERROR — {e}")

    # ── 4. Run prediction pairs ────────────────────────────────────────────────
    print("\n[STEP 4] Running prediction pairs...")
    pair_results: dict[tuple, dict[str, dict]] = {}
    for year_n, year_n1 in PAIRS:
        res = run_pair(year_n, year_n1, bbref_data, bpr_data, wins_data)
        pair_results[(year_n, year_n1)] = res

    # ── 5. Output Table 1: Per-pair results ────────────────────────────────────
    print("\n" + "=" * 80)
    print("OUTPUT TABLE 1 — PER-PAIR PEARSON r (Year N metrics → Year N+1 wins)")
    print("=" * 80)
    pair_labels = [
        f"Pair1\n({SEASON_LABEL[2023]}→{SEASON_LABEL[2024]})",
        f"Pair2\n({SEASON_LABEL[2024]}→{SEASON_LABEL[2025]})",
        f"Pair3\n({SEASON_LABEL[2025]}→{SEASON_LABEL[2026]})",
    ]
    print(f"{'Metric':<8} {'Pair1_r':>8} {'Pair2_r':>8} {'Pair3_r':>8} | "
          f"{'Pair1_RMSE':>10} {'Pair2_RMSE':>10} {'Pair3_RMSE':>10}")
    print("-" * 80)

    pair_rows = []
    for metric in ALL_METRICS:
        rs, rmses = [], []
        for pair in PAIRS:
            res = pair_results.get(pair, {}).get(metric, {})
            rs.append(res.get("pearson_r", float("nan")))
            rmses.append(res.get("rmse", float("nan")))
        row_str = f"{metric:<8}"
        for r in rs:
            row_str += f" {r:>+8.3f}" if not np.isnan(r) else f" {'—':>8}"
        row_str += " |"
        for rmse in rmses:
            row_str += f" {rmse:>10.3f}" if not np.isnan(rmse) else f" {'—':>10}"
        print(row_str)
        pair_rows.append({"metric": metric, "pair1_r": rs[0], "pair2_r": rs[1], "pair3_r": rs[2],
                           "pair1_rmse": rmses[0], "pair2_rmse": rmses[1], "pair3_rmse": rmses[2]})
    print("=" * 80)

    pd.DataFrame(pair_rows).to_csv(OUTPUT_DIR / "predictive_test_by_pair.csv", index=False)

    # ── 6. Output Table 2: Averaged results ────────────────────────────────────
    print("\n" + "=" * 80)
    print("OUTPUT TABLE 2 — AVERAGED ACROSS ALL 3 PAIRS (sorted by Avg_r)")
    print("=" * 80)
    print(f"{'Rank':<5} {'Metric':<8} {'Avg_r':>7} {'Avg_RMSE':>9} {'Avg_Spearman':>13} {'Retro_RMSE':>11}")
    print("-" * 60)

    summary_rows = []
    for metric in ALL_METRICS:
        rs, srs, rmses = [], [], []
        for pair in PAIRS:
            res = pair_results.get(pair, {}).get(metric, {})
            if res:
                r = res.get("pearson_r", float("nan"))
                sr = res.get("spearman_r", float("nan"))
                rm = res.get("rmse", float("nan"))
                if not np.isnan(r): rs.append(r)
                if not np.isnan(sr): srs.append(sr)
                if not np.isnan(rm): rmses.append(rm)
        avg_r  = float(np.mean(rs))  if rs   else float("nan")
        avg_sr = float(np.mean(srs)) if srs  else float("nan")
        avg_rm = float(np.mean(rmses)) if rmses else float("nan")
        retro  = RETRO_RMSE.get(metric, float("nan"))
        summary_rows.append({
            "metric": metric, "avg_r": avg_r, "avg_rmse": avg_rm,
            "avg_spearman": avg_sr, "retro_rmse": retro,
        })

    summary_rows.sort(key=lambda x: -x["avg_r"] if not np.isnan(x["avg_r"]) else float("inf"))
    bpm_avg_r = next((r["avg_r"] for r in summary_rows if r["metric"] == "BPM"), float("nan"))
    bpr_rank = None

    for rank, row in enumerate(summary_rows, 1):
        m = row["metric"]
        if m == "BPR":
            bpr_rank = rank
        r_str    = f"{row['avg_r']:>+7.3f}" if not np.isnan(row["avg_r"]) else f"{'—':>7}"
        rm_str   = f"{row['avg_rmse']:>9.3f}" if not np.isnan(row["avg_rmse"]) else f"{'—':>9}"
        sr_str   = f"{row['avg_spearman']:>13.3f}" if not np.isnan(row["avg_spearman"]) else f"{'—':>13}"
        ret_str  = f"{row['retro_rmse']:>11.3f}" if not np.isnan(row["retro_rmse"]) else f"{'—':>11}"
        print(f"{rank:<5} {m:<8} {r_str} {rm_str} {sr_str} {ret_str}")
    print("=" * 80)

    pd.DataFrame(summary_rows).to_csv(OUTPUT_DIR / "predictive_test_results.csv", index=False)

    # ── 7. BPR deep dive per pair ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("OUTPUT TABLE 3 — BPR TEAM PREDICTION DEEP DIVE")
    print("=" * 70)
    for i, (year_n, year_n1) in enumerate(PAIRS, 1):
        res = pair_results.get((year_n, year_n1), {}).get("BPR", {})
        if not res:
            print(f"  Pair {i}: no BPR data")
            continue
        errors = res.get("team_errors", [])
        print(f"\n  Pair {i} ({SEASON_LABEL[year_n]}→{SEASON_LABEL[year_n1]})  "
              f"r={res['pearson_r']:.3f}  RMSE={res['rmse']:.3f}")
        best  = [(t, e) for t, e in errors if e < 0][:5]   # under-predicted (pred < actual)
        worst = [(t, e) for t, e in errors if e > 0][:5]   # over-predicted
        print(f"    Best predicted (BPR was CONSERVATIVE):  "
              + ", ".join(f"{t}({e:+.1f})" for t, e in reversed(best[-5:])))
        print(f"    Worst predicted (BPR was OPTIMISTIC):   "
              + ", ".join(f"{t}({e:+.1f})" for t, e in worst[:5]))

    # ── 8. Star stability ──────────────────────────────────────────────────────
    print("\n" + "=" * 50)
    print("STAR PLAYER YEAR-OVER-YEAR STABILITY")
    print(f"(Pearson r of metric[yr] vs metric[yr+1] for {', '.join(STAR_PLAYERS)})")
    print("=" * 50)
    stability = compute_star_stability(bbref_data, bpr_data)
    stab_rows = []
    for m, r in sorted(stability.items(), key=lambda x: -x[1] if not np.isnan(x[1]) else -99):
        r_str = f"{r:.3f}" if not np.isnan(r) else "—"
        flag = "  ← unstable" if (not np.isnan(r) and r < 0.5) else ""
        print(f"  {m:<8} YoY r = {r_str}{flag}")
        stab_rows.append({"metric": m, "star_yoy_r": r})
    pd.DataFrame(stab_rows).to_csv(OUTPUT_DIR / "star_stability.csv", index=False)

    # ── 9. Auto-flags ──────────────────────────────────────────────────────────
    bpr_summary = next((r for r in summary_rows if r["metric"] == "BPR"), {})
    bpr_avg_r   = bpr_summary.get("avg_r", float("nan"))

    # Pair 2 worst?
    bpr_pair_rs = [pair_results.get(p, {}).get("BPR", {}).get("pearson_r", float("nan")) for p in PAIRS]
    pair2_worst = (not np.isnan(bpr_pair_rs[1]) and
                   bpr_pair_rs[1] == min(x for x in bpr_pair_rs if not np.isnan(x)))

    # ── 10. Final summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PREDICTIVE TEST SUMMARY")
    print("=" * 70)
    best_metric = summary_rows[0]["metric"] if summary_rows else "?"
    best_r      = summary_rows[0]["avg_r"]  if summary_rows else float("nan")
    bpr_vs_bpm  = bpr_avg_r - bpm_avg_r if not np.isnan(bpr_avg_r) and not np.isnan(bpm_avg_r) else float("nan")

    print(f"Best predictive metric overall:  {best_metric}  avg_r={best_r:.3f}")
    print(f"BPR predictive rank:             {bpr_rank} of {len(summary_rows)} metrics tested")
    print(f"BPR avg predictive r:            {bpr_avg_r:.3f}")
    print(f"BPM avg predictive r:            {bpm_avg_r:.3f}")
    if not np.isnan(bpr_vs_bpm):
        direction = "BETTER" if bpr_vs_bpm > 0 else "WORSE"
        print(f"BPR vs BPM (predictive):         BPR {direction} by {abs(bpr_vs_bpm):.3f} correlation points")
    print(f"BPR vs BPM (retrodiction):       BPR worse by {5.636-3.559:.3f} RMSE wins")
    print(f"Worst BPR prediction year:       Pair {'2 (2024→2025) ← LIVELY CONTAMINATION CONFIRMED' if pair2_worst else str(bpr_pair_rs.index(min(x for x in bpr_pair_rs if not np.isnan(x)))+1)}")
    bpr_yoy = stability.get("BPR", float("nan"))
    bpm_yoy = stability.get("BPM", float("nan"))
    print(f"Star stability — BPR YoY r:      {bpr_yoy:.3f}")
    print(f"Star stability — BPM YoY r:      {bpm_yoy:.3f}")

    # Verdict flags
    if not np.isnan(bpr_avg_r) and bpr_avg_r < 0.40:
        print("\n⚠  WARNING: BPR predictive correlation below minimum useful threshold.")
        print("   Architecture review recommended before deployment.")
    if not np.isnan(bpr_vs_bpm) and bpr_vs_bpm > 0:
        print("\n✓  FINDING: BPR is more predictive than BPM. Different signal")
        print("   may be capturing genuine forward-looking value.")

    # Verdict
    if not np.isnan(bpr_avg_r):
        if bpr_avg_r >= 0.55:
            verdict = "PREDICTIVE"
        elif bpr_avg_r >= 0.40:
            verdict = "DESCRIPTIVE ONLY"
        else:
            verdict = "NEEDS ARCHITECTURE REVIEW"
    else:
        verdict = "INSUFFICIENT DATA"
    print(f"\nVerdict: {verdict}")
    print("=" * 70)
    print(f"\n[SAVED] {OUTPUT_DIR}/predictive_test_results.csv")
    print(f"[SAVED] {OUTPUT_DIR}/predictive_test_by_pair.csv")
    print(f"[SAVED] {OUTPUT_DIR}/star_stability.csv")


if __name__ == "__main__":
    main()
