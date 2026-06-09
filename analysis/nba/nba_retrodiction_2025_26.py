"""
nba_retrodiction_2025_26.py

Retrodiction test: how well does each NBA advanced metric explain
actual 2025-26 team performance (wins + SRS)?

Steps:
  1. Load player metrics + BPR, clean multi-team players
  2. Aggregate to 30-team level (minutes-weighted avg or raw sum)
  3. Scrape BBref standings for actual wins + SRS
  4. Linear regression: team metric → wins, score with RMSE/MAE/R²/SRS_r
  5. Print ranking table, team breakdown for top metrics + BPR
  6. Player-level divergence report: BPR vs consensus z-score

Run:
    backend/.venv/bin/python nba_retrodiction_2025_26.py
"""

from __future__ import annotations

import io
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import scipy.stats
from rapidfuzz import fuzz, process as rfprocess
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

# ── Constants ──────────────────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).parent.parent.parent
OUTPUT_DIR   = SCRIPT_DIR / "metrics_output"
METRICS_CSV  = OUTPUT_DIR / "nba_metrics_2025_26.csv"
BPR_CSV      = SCRIPT_DIR / "data" / "nba" / "bpr_2025_26.csv"

BBREF_STANDINGS_URL = "https://www.basketball-reference.com/leagues/NBA_2026.html"

# Set False to skip BPR entirely
INCLUDE_BPR     = BPR_CSV.exists()
NULL_THRESHOLD  = 0.30    # skip metric if >30% of team-level values are null
RAPTOR_YEAR     = None    # filled at runtime from data

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# BBref → NBA.com abbreviation differences (for BPR team matching)
BBREF_TO_NBACOM = {
    "BRK": "BKN", "CHO": "CHA", "PHO": "PHX",
}
NBACOM_TO_BBREF = {v: k for k, v in BBREF_TO_NBACOM.items()}

# Metrics aggregated by minutes-weighted average
AVG_METRICS = ["PER", "BPM", "OBPM", "DBPM", "WS48", "RAPTOR_total", "LEBRON", "BPR"]
# Metrics aggregated by raw sum (counting stats)
SUM_METRICS = ["WS", "VORP"]

ALL_METRICS = AVG_METRICS + SUM_METRICS

OUTPUT_DIR.mkdir(exist_ok=True)


# ── Utilities ──────────────────────────────────────────────────────────────────

def norm_name(s: str) -> str:
    s = str(s).lower().strip()
    s = s.encode("ascii", errors="ignore").decode()
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def bbref_abbrev(abbrev: str) -> str:
    """Normalise team abbreviation to BBref standard (BKN→BRK, CHA→CHO, PHX→PHO)."""
    return NBACOM_TO_BBREF.get(abbrev, abbrev)


def norm_team_name(s: str) -> str:
    """Canonical team name for matching: lowercase, strip * and ranking suffixes."""
    s = str(s)
    s = re.sub(r"\*", "", s)           # remove playoff marker
    s = re.sub(r"\(\d+\)", "", s)      # remove (1), (2) seeding
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()


# ── Data loading ───────────────────────────────────────────────────────────────

def load_player_metrics() -> pd.DataFrame:
    """
    Load nba_metrics_2025_26.csv.
    - Drop "2TM" combined rows (keep per-team rows only).
    - For traded players with multiple per-team rows, keep the row with
      the most minutes (primary team assignment).
    """
    df = pd.read_csv(METRICS_CSV)

    # Rows with team == "2TM" are season-total aggregates for traded players
    traded_names = df[df["team"] == "2TM"]["player_name"].unique()
    # Drop combined multi-team rows ("2TM", "3TM", "4TM", etc.) — keep only per-team rows
    multi_team_mask = df["team"].str.match(r"^\d+TM$", na=False)
    df_clean = df[~multi_team_mask].copy()

    # Deduplicate traded players: keep primary team (max minutes)
    reassigned = 0
    deduped = []
    for name, grp in df_clean.groupby("player_name"):
        if len(grp) > 1:
            deduped.append(grp.nlargest(1, "minutes"))
            reassigned += 1
        else:
            deduped.append(grp)
    df_clean = pd.concat(deduped, ignore_index=True)

    print(f"[METRICS] Loaded {len(df_clean)} players "
          f"({reassigned} traded players assigned to primary team)")

    # Normalise team abbreviation to BBref standard
    df_clean["team"] = df_clean["team"].map(bbref_abbrev)

    return df_clean


def load_bpr() -> pd.DataFrame | None:
    """
    Load bpr_2025_26.csv.
    BPR values are identical across team rows for traded players —
    keep row with most games played (primary team).
    """
    if not INCLUDE_BPR:
        print("[BPR] bpr_2025_26.csv not found — BPR excluded")
        return None

    df = pd.read_csv(BPR_CSV)

    # Deduplicate by nba_id: keep row with highest gp
    df = df.sort_values("gp", ascending=False).drop_duplicates(subset=["nba_id"], keep="first")

    # Compute minutes proxy for weighting
    df["minutes_bpr"] = df["mpg"] * df["gp"]

    # Normalise team to BBref abbreviation
    df["team_bbref"] = df["team"].map(bbref_abbrev)

    print(f"[BPR] Loaded {len(df)} players")
    return df[["player_name", "nba_id", "team_bbref", "bpr", "minutes_bpr"]].copy()


def merge_bpr(players: pd.DataFrame, bpr: pd.DataFrame) -> pd.DataFrame:
    """Merge BPR onto player metrics using nba_id where possible, fuzzy name fallback."""
    if bpr is None:
        players["BPR"] = np.nan
        players["minutes_bpr"] = np.nan
        return players

    # Build lookup by normalised name for fuzzy fallback
    bpr["_norm"] = bpr["player_name"].map(norm_name)
    bpr_norm_list = bpr["_norm"].tolist()

    bpr_vals, bpr_mins, bpr_teams = [], [], []
    for _, row in players.iterrows():
        norm = norm_name(row["player_name"])
        result = rfprocess.extractOne(norm, bpr_norm_list, scorer=fuzz.WRatio, score_cutoff=82)
        if result:
            match_row = bpr.iloc[result[2]]
            bpr_vals.append(match_row["bpr"])
            bpr_mins.append(match_row["minutes_bpr"])
            bpr_teams.append(match_row["team_bbref"])
        else:
            bpr_vals.append(np.nan)
            bpr_mins.append(np.nan)
            bpr_teams.append(None)

    players = players.copy()
    players["BPR"] = bpr_vals
    players["minutes_bpr"] = bpr_mins
    n_matched = sum(v is not None and not np.isnan(v) for v in bpr_vals)
    print(f"[BPR] Matched {n_matched}/{len(players)} players to BPR data")
    return players


# ── Team aggregation ───────────────────────────────────────────────────────────

def aggregate_to_teams(players: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate player-level metrics to 30-team level.
    AVG_METRICS: minutes-weighted average.
    SUM_METRICS: raw sum.
    BPR uses its own minutes_bpr column when available.
    """
    rows = []
    for team, grp in players.groupby("team"):
        row: dict = {"team": team}

        for col in AVG_METRICS:
            if col == "BPR" and "minutes_bpr" in grp.columns:
                weight_col = "minutes_bpr"
            else:
                weight_col = "minutes"

            if col not in grp.columns:
                row[col] = np.nan
                continue
            valid = grp[[weight_col, col]].dropna()
            if len(valid) == 0 or valid[weight_col].sum() == 0:
                row[col] = np.nan
            else:
                row[col] = (valid[col] * valid[weight_col]).sum() / valid[weight_col].sum()

        for col in SUM_METRICS:
            if col not in grp.columns:
                row[col] = np.nan
            else:
                row[col] = grp[col].sum(skipna=True)

        rows.append(row)

    team_df = pd.DataFrame(rows)
    print(f"[AGG] Aggregated to {len(team_df)} teams")
    return team_df


# ── Standings scrape ───────────────────────────────────────────────────────────

def _abbrev_from_href(href: str) -> str | None:
    """Extract 'OKC' from '/teams/OKC/2026.html'."""
    m = re.search(r"/teams/([A-Z]{2,4})/", href)
    return m.group(1) if m else None


def scrape_bbref_standings() -> pd.DataFrame | None:
    """
    Scrape wins, losses, SRS from BBref season page.

    BBref embeds some tables in HTML comments for lazy-loading.
    Approach:
      1. Strip <!-- --> from raw HTML
      2. Use pd.read_html(attrs={"id": ...}) to pull each conference table
      3. Use BeautifulSoup on the stripped table to extract team abbreviations
         from <a href=/teams/XXX/...> links
      4. Join abbreviations to stats via row index (guaranteed same order)

    Returns DataFrame with columns: team_abbrev, wins, losses, SRS
    Team abbreviations are in BBref format (BRK/CHO/PHO) — matching player data.
    """
    print(f"[STANDINGS] Scraping {BBREF_STANDINGS_URL}...")
    time.sleep(4)
    try:
        resp = requests.get(BBREF_STANDINGS_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except Exception as e:
        print(f"[STANDINGS] HTTP error: {e}")
        return None

    try:
        from bs4 import BeautifulSoup

        # Strip HTML comments (BBref lazy-load pattern)
        raw_uncommented = resp.text.replace("<!--", "").replace("-->", "")

        soup = BeautifulSoup(raw_uncommented, "lxml")
        all_rows = []

        for conf in ("E", "W"):
            tid = f"confs_standings_{conf}"
            table_tag = soup.find("table", id=tid)
            if table_tag is None:
                print(f"[STANDINGS] Table {tid!r} not found after comment strip")
                continue

            # Build {norm_team_name → BBref_abbrev} from soup links
            # norm_team_name strips *, (1), (2) etc. before comparing
            norm_to_abbrev: dict[str, str] = {}
            tbody = table_tag.find("tbody")
            for tr in (tbody.find_all("tr") if tbody else []):
                team_cell = (
                    tr.find("td", attrs={"data-stat": "team_name"}) or
                    tr.find("th", attrs={"data-stat": "team_name"})
                )
                if not team_cell:
                    continue
                a = team_cell.find("a")
                href = a.get("href", "") if a else ""
                m = re.search(r"/teams/([A-Z]{2,4})/", href)
                if m:
                    norm_to_abbrev[norm_team_name(team_cell.get_text())] = m.group(1)

            # Read stats with pd.read_html on the full uncommented page
            # (more reliable than serialising the soup tag back to string)
            dfs = pd.read_html(io.StringIO(raw_uncommented), attrs={"id": tid})
            if not dfs:
                print(f"[STANDINGS] pd.read_html found no table for {tid!r}")
                continue
            df = dfs[0]

            # Flatten multi-level columns if needed
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[-1] for c in df.columns]

            # Keep only rows where W is numeric (drops division-header rows)
            df = df[pd.to_numeric(df.get("W"), errors="coerce").notna()].copy()

            # First column is the team name column
            name_col = df.columns[0]

            # Map team names → abbreviation via normalized lookup
            def _get_abbrev(raw: str) -> str:
                key = norm_team_name(raw)
                return norm_to_abbrev.get(key, "")

            df["team_abbrev"] = df[name_col].map(_get_abbrev)
            df["wins"]   = pd.to_numeric(df.get("W"),   errors="coerce")
            df["losses"] = pd.to_numeric(df.get("L"),   errors="coerce")
            df["SRS"]    = pd.to_numeric(df.get("SRS"), errors="coerce")

            matched = df[df["team_abbrev"] != ""]
            unmatched = df[df["team_abbrev"] == ""]
            if not unmatched.empty:
                print(f"[STANDINGS] {tid}: {len(unmatched)} unmatched teams: "
                      f"{unmatched[name_col].tolist()}")

            all_rows.append(matched[["team_abbrev", "wins", "losses", "SRS"]])

        if not all_rows:
            print("[STANDINGS] No data parsed from either conference table")
            return None

        result = pd.concat(all_rows, ignore_index=True)
        result = result.dropna(subset=["wins", "SRS"])

        # Abbreviations stay in BBref format (BRK, CHO, PHO) —
        # player team data is also BBref format, so the merge key matches.
        print(
            f"[STANDINGS] SUCCESS — {len(result)} teams  "
            f"SRS range [{result['SRS'].min():.2f}, {result['SRS'].max():.2f}]"
        )
        return result

    except Exception as e:
        import traceback
        print(f"[STANDINGS] Parse error: {e}")
        traceback.print_exc()
        return None


def standings_from_db() -> pd.DataFrame:
    """
    Fallback: compute wins from Django DB + use adj_net as SRS proxy.
    """
    print("[STANDINGS] Falling back to database...")
    import django, os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(SCRIPT_DIR / "backend"))
    django.setup()

    from collections import defaultdict
    from nba.models import NBAGame, NBATeam, NBATeamSeasonRatings

    team_wins: dict[int, int] = defaultdict(int)
    for game in NBAGame.objects.filter(
        season__year=2026, status="Final", counts_toward_regular_season=True
    ).select_related("home_team", "away_team"):
        if game.home_score is not None and game.away_score is not None:
            if game.home_score > game.away_score:
                team_wins[game.home_team.pk] += 1
            else:
                team_wins[game.away_team.pk] += 1

    rows = []
    for r in NBATeamSeasonRatings.objects.filter(
        season__year=2026, season_type="regular"
    ).select_related("team"):
        rows.append({
            # Convert NBA.com → BBref format to match player team data
            "team_abbrev": bbref_abbrev(r.team.abbreviation),
            "wins":        team_wins.get(r.team.pk, np.nan),
            "losses":      82 - team_wins.get(r.team.pk, 0),
            "SRS":         r.adj_net,   # adj_net proxy (not true BBref SRS)
        })

    df = pd.DataFrame(rows)
    print(f"[STANDINGS] DB fallback — {len(df)} teams (SRS = adj_net proxy)")
    return df


# ── Scoring ────────────────────────────────────────────────────────────────────

def score_metric(
    team_df: pd.DataFrame,
    metric: str,
    wins_col: str = "wins",
    srs_col: str = "SRS",
) -> dict | None:
    """
    Linear regression: team_metric → wins.
    Returns RMSE, MAE, R², Pearson-r vs SRS, or None if metric unusable.
    """
    sub = team_df[[metric, wins_col, srs_col]].dropna()
    if len(sub) < 10:
        return None

    null_rate = team_df[metric].isna().mean()
    if null_rate > NULL_THRESHOLD:
        print(f"[SKIP] {metric}: {null_rate:.0%} null at team level (threshold {NULL_THRESHOLD:.0%})")
        return None

    X = sub[[metric]].values
    y_wins = sub[wins_col].values
    y_srs  = sub[srs_col].values

    reg = LinearRegression().fit(X, y_wins)
    y_pred = reg.predict(X)

    rmse = float(np.sqrt(mean_squared_error(y_wins, y_pred)))
    mae  = float(mean_absolute_error(y_wins, y_pred))
    r2   = float(reg.score(X, y_wins))
    srs_r, _ = scipy.stats.pearsonr(sub[metric].values, y_srs)

    return {
        "metric": metric,
        "n_teams": len(sub),
        "RMSE": round(rmse, 3),
        "MAE":  round(mae, 3),
        "R2":   round(r2, 3),
        "SRS_r": round(float(srs_r), 3),
        "_reg": reg,
        "_sub": sub,
    }


def add_predictions(team_df: pd.DataFrame, metric: str, reg) -> pd.DataFrame:
    """Add predicted wins column for a given metric's fitted regression."""
    col = f"pred_{metric}"
    valid = team_df[metric].notna()
    team_df[col] = np.nan
    team_df.loc[valid, col] = reg.predict(team_df.loc[valid, [metric]].values)
    team_df[col] = team_df[col].round(1)
    return team_df


# ── Output formatting ──────────────────────────────────────────────────────────

def print_ranking_table(results: list[dict], raptor_year: int | None) -> None:
    print("\n" + "=" * 72)
    print("RETRODICTION RANKING — 2025-26 NBA Season")
    print("(lower RMSE = better; metrics sorted by RMSE vs actual wins)")
    print("=" * 72)

    sorted_r = sorted(results, key=lambda x: x["RMSE"])
    header = f"{'Rank':>4}  {'Metric':<16} {'RMSE':>6} {'MAE':>6} {'R²':>6} {'SRS_r':>7} {'N':>4}"
    print(header)
    print("-" * 56)
    for rank, res in enumerate(sorted_r, 1):
        label = res["metric"]
        if label == "RAPTOR_total" and raptor_year:
            label += f" ({raptor_year})"
        print(f"{rank:>4}  {label:<16} {res['RMSE']:>6.3f} {res['MAE']:>6.3f} "
              f"{res['R2']:>6.3f} {res['SRS_r']:>7.3f} {res['n_teams']:>4}")
    print("=" * 72)


def print_team_breakdown(team_df: pd.DataFrame, metric: str, wins_col: str = "wins") -> None:
    pred_col = f"pred_{metric}"
    if pred_col not in team_df.columns:
        return
    sub = team_df[["team", wins_col, pred_col]].dropna().copy()
    sub["error"] = (sub[pred_col] - sub[wins_col]).round(1)
    sub["abs_error"] = sub["error"].abs()
    sub = sub.sort_values("abs_error", ascending=False)

    print(f"\n  Team breakdown — {metric}:")
    print(f"  {'Team':<6} {'Actual':>7} {'Pred':>7} {'Error':>7}")
    print(f"  {'-'*30}")
    for _, row in sub.iterrows():
        flag = " ◀ worst" if row["abs_error"] == sub["abs_error"].max() else ""
        print(f"  {row['team']:<6} {row[wins_col]:>7.0f} {row[pred_col]:>7.1f} {row['error']:>+7.1f}{flag}")


# ── Divergence report ──────────────────────────────────────────────────────────

def build_divergence_report(players: pd.DataFrame) -> pd.DataFrame:
    """
    Flag players where BPR z-score diverges >1.5 SD from consensus
    (consensus = mean z-score across BPM, LEBRON, RAPTOR_total, PER).
    """
    if "BPR" not in players.columns or players["BPR"].isna().all():
        print("[DIVERGENCE] BPR not available — skipping divergence report")
        return pd.DataFrame()

    consensus_cols = [c for c in ["BPM", "LEBRON", "RAPTOR_total", "PER"] if c in players.columns]
    df = players.copy()

    # Z-score each metric
    for col in consensus_cols + ["BPR"]:
        mu, sigma = df[col].mean(), df[col].std()
        df[f"z_{col}"] = (df[col] - mu) / sigma if sigma > 0 else 0.0

    # Consensus z = mean of available z-scores
    z_cols = [f"z_{c}" for c in consensus_cols]
    df["consensus_z"] = df[z_cols].mean(axis=1)
    df["BPR_z"] = df["z_BPR"]
    df["divergence"] = (df["BPR_z"] - df["consensus_z"]).round(3)
    df["abs_div"] = df["divergence"].abs()

    threshold = 1.5
    flagged = df[df["abs_div"] >= threshold].copy()
    flagged = flagged.sort_values("abs_div", ascending=False)

    keep = ["player_name", "team", "minutes", "BPR_z", "consensus_z", "divergence",
            "BPR", "BPM", "LEBRON", "RAPTOR_total", "PER"]
    flagged = flagged[[c for c in keep if c in flagged.columns]].round(3)

    print(f"\n[DIVERGENCE] {len(flagged)} players with |BPR_z - consensus_z| ≥ {threshold}")
    print(f"\n  Top 5 divergent players (+ = BPR rates higher than consensus):")
    print(f"  {'Player':<28} {'Team':<5} {'BPR_z':>6} {'Con_z':>6} {'Div':>6}  {'BPR':>5} {'BPM':>5} {'LEBRON':>7}")
    print(f"  {'-'*75}")
    for _, row in flagged.head(10).iterrows():
        print(f"  {row['player_name']:<28} {row.get('team','?'):<5} "
              f"{row['BPR_z']:>6.2f} {row['consensus_z']:>6.2f} {row['divergence']:>+6.2f}  "
              f"{row.get('BPR', float('nan')):>5.2f} {row.get('BPM', float('nan')):>5.2f} "
              f"{row.get('LEBRON', float('nan')):>7.3f}")

    return flagged


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    global RAPTOR_YEAR

    print("NBA Retrodiction Analysis — 2025-26 Season")
    print("=" * 72)
    print(f"INCLUDE_BPR = {INCLUDE_BPR}")
    print()

    # ── 1. Load players ────────────────────────────────────────────────────────
    players = load_player_metrics()
    bpr_df  = load_bpr()
    players = merge_bpr(players, bpr_df)

    # Note RAPTOR data year
    if "RAPTOR_season" in players.columns:
        yr = players["RAPTOR_season"].dropna()
        RAPTOR_YEAR = int(yr.mode().iloc[0]) if not yr.empty else None
        if RAPTOR_YEAR:
            print(f"[RAPTOR] Data is from {RAPTOR_YEAR} season (3+ years old — caveat emptor)")

    # ── 2. Aggregate to team level ─────────────────────────────────────────────
    team_df = aggregate_to_teams(players)

    # ── 3. Standings ──────────────────────────────────────────────────────────
    standings = scrape_bbref_standings()
    if standings is None:
        standings = standings_from_db()

    # Pre-merge sanity: both sides must use BBref abbreviations
    print(f"[MERGE] team_df teams ({len(team_df)}): {sorted(team_df['team'].tolist())}")
    print(f"[MERGE] standings teams ({len(standings)}): {sorted(standings['team_abbrev'].tolist())}")
    missing = set(team_df["team"]) - set(standings["team_abbrev"])
    if missing:
        print(f"[MERGE WARN] {len(missing)} teams in player data not in standings: {sorted(missing)}")

    team_df = team_df.merge(standings, left_on="team", right_on="team_abbrev", how="left")
    n_unmatched = team_df["wins"].isna().sum()
    if n_unmatched > 0:
        print(f"[WARN] {n_unmatched} teams without standings data:")
        print(f"  {team_df[team_df['wins'].isna()]['team'].tolist()}")

    # ── 4. Score metrics ───────────────────────────────────────────────────────
    metrics_to_test = [m for m in ALL_METRICS if not (m == "BPR" and not INCLUDE_BPR)]
    results = []

    print("\n[SCORING] Running regressions...")
    for metric in metrics_to_test:
        if metric not in team_df.columns:
            continue
        res = score_metric(team_df, metric)
        if res is None:
            continue
        team_df = add_predictions(team_df, metric, res["_reg"])
        del res["_reg"], res["_sub"]   # don't need these in the results table
        results.append(res)
        print(f"  {metric:<16} RMSE={res['RMSE']:.3f}  R²={res['R2']:.3f}  SRS_r={res['SRS_r']:.3f}")

    # ── 5. Ranking table ───────────────────────────────────────────────────────
    print_ranking_table(results, RAPTOR_YEAR)

    # ── 6. Team breakdown for top 3 + BPR ─────────────────────────────────────
    sorted_metrics = sorted(results, key=lambda x: x["RMSE"])
    top3 = [r["metric"] for r in sorted_metrics[:3]]
    show = list(dict.fromkeys(top3 + (["BPR"] if INCLUDE_BPR and "BPR" not in top3 else [])))

    print("\n" + "=" * 72)
    print("TEAM BREAKDOWN — top metrics + BPR")
    print("=" * 72)
    for m in show:
        print_team_breakdown(team_df, m)

    # ── 7. Save team predictions ───────────────────────────────────────────────
    pred_cols = ["team", "wins", "losses", "SRS"] + [f"pred_{m}" for m in metrics_to_test if f"pred_{m}" in team_df.columns]
    team_out = team_df[[c for c in pred_cols if c in team_df.columns]].sort_values("wins", ascending=False)
    team_out.to_csv(OUTPUT_DIR / "team_predictions.csv", index=False)
    print(f"\n[SAVED] metrics_output/team_predictions.csv ({len(team_out)} teams)")

    # Save results table
    results_df = pd.DataFrame([{k: v for k, v in r.items()} for r in results])
    results_df = results_df.sort_values("RMSE")
    results_df.to_csv(OUTPUT_DIR / "retrodiction_results.csv", index=False)
    print(f"[SAVED] metrics_output/retrodiction_results.csv")

    # ── 8. Divergence report ───────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("BPR DIVERGENCE REPORT")
    print("=" * 72)
    flagged = build_divergence_report(players)
    if not flagged.empty:
        flagged.to_csv(OUTPUT_DIR / "bpr_divergence_report.csv", index=False)
        print(f"[SAVED] metrics_output/bpr_divergence_report.csv ({len(flagged)} players)")

    print("\nDone.")


if __name__ == "__main__":
    main()
