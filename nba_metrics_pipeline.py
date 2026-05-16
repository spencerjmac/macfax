"""
nba_metrics_pipeline.py

Collects NBA advanced player metrics for 2025-26 from multiple public sources,
merges by player name, and saves CSV files for BPR comparison analysis.

Run:
    backend/.venv/bin/python nba_metrics_pipeline.py

Sources:
    1. Basketball-Reference — BPM, OBPM, DBPM, WS, WS/48, PER, VORP, USG%
    2. NBA.com Stats API (via nba_api) — PIE
    3. FiveThirtyEight RAPTOR (archived) — RAPTOR_O, RAPTOR_D, RAPTOR_total, WAR
    4. EPM / DunksAndThrees — attempt, skip gracefully if blocked
    5. RPM / ESPN — attempt, skip gracefully if blocked
    6. LEBRON — load from lebron-data-2026.csv (already on disk)
"""

from __future__ import annotations

import io
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from rapidfuzz import process as rfprocess, fuzz

# ── Constants ──────────────────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).parent
OUTPUT_DIR   = SCRIPT_DIR / "metrics_output"
LEBRON_CSV   = SCRIPT_DIR / "lebron-data-2026.csv"
MERGE_LOG    = OUTPUT_DIR / "merge_log.txt"

MIN_MINUTES  = 200
FUZZY_CUTOFF = 85   # rapidfuzz score 0-100
REQUEST_DELAY = 4   # seconds between HTTP calls

BBREF_URL  = "https://www.basketball-reference.com/leagues/NBA_2026_advanced.html"
RAPTOR_URL = "https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-raptor/modern_RAPTOR_by_player.csv"
EPM_URL    = "https://dunksandthrees.com/epm"
RPM_URL    = "https://www.espn.com/nba/stats/player/_/stat/rpm"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

OUTPUT_DIR.mkdir(exist_ok=True)
_log_lines: list[str] = []


# ── Utilities ──────────────────────────────────────────────────────────────────

def norm_name(s: str) -> str:
    """Lowercase, strip punctuation/accents, collapse whitespace."""
    s = str(s).lower().strip()
    s = s.encode("ascii", errors="ignore").decode()   # drop accents
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def log(msg: str) -> None:
    print(msg)
    _log_lines.append(msg)


def save_log() -> None:
    MERGE_LOG.write_text("\n".join(_log_lines), encoding="utf-8")


def fuzzy_merge(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_key: str,
    right_key: str,
    cols: list[str],
    cutoff: int = FUZZY_CUTOFF,
) -> pd.DataFrame:
    """
    Left-join right onto left using rapidfuzz name matching.
    Adds cols from right (renamed to their original names) to left.
    Logs unmatched rows from both sides.
    """
    right_norm = right[right_key].map(norm_name)
    right_norm_list = right_norm.tolist()

    matched_left: set[int] = set()
    matched_right: set[int] = set()
    col_data: dict[str, list] = {c: [] for c in cols}

    for li, lname in enumerate(left[left_key].map(norm_name)):
        result = rfprocess.extractOne(
            lname, right_norm_list, scorer=fuzz.WRatio, score_cutoff=cutoff
        )
        if result:
            _, _, ri = result
            for c in cols:
                col_data[c].append(right.iloc[ri][c])
            matched_left.add(li)
            matched_right.add(ri)
        else:
            for c in cols:
                col_data[c].append(None)

    # Log unmatched from left
    for li, lname in enumerate(left[left_key]):
        if li not in matched_left:
            log(f"  [UNMATCHED LEFT] {lname!r} not found in right source")

    # Log unmatched from right
    for ri, rname in enumerate(right[right_key]):
        if ri not in matched_right:
            log(f"  [UNMATCHED RIGHT] {rname!r} not found in spine")

    result_df = left.copy()
    for c in cols:
        result_df[c] = col_data[c]
    return result_df


# ── Source collectors ──────────────────────────────────────────────────────────

def collect_bbref() -> pd.DataFrame | None:
    """Basketball-Reference advanced stats — spine of the master file."""
    print("[BBREF] Fetching...")
    time.sleep(REQUEST_DELAY)
    try:
        resp = requests.get(BBREF_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"  # force UTF-8 decode (BBref serves UTF-8; auto-detect gets it wrong)
    except Exception as e:
        log(f"[BBREF] FAILED: {e}")
        return None

    try:
        tables = pd.read_html(io.StringIO(resp.text), attrs={"id": "advanced"})
        if not tables:
            log("[BBREF] FAILED: no table with id='advanced' found")
            return None
        df = tables[0]
    except Exception as e:
        log(f"[BBREF] FAILED parsing HTML: {e}")
        return None

    # Flatten multi-level columns if needed
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(str(c) for c in col).strip() for col in df.columns]

    # Drop repeated header rows (BBref inserts "Age" == "Age" rows mid-table)
    if "Age" in df.columns:
        df = df[df["Age"] != "Age"].copy()
    elif "Rk" in df.columns:
        df = df[df["Rk"] != "Rk"].copy()

    # Keep only season-total rows for multi-team players (Tm == "TOT" or "2TM"/"3TM" etc.)
    if "Tm" in df.columns:
        multi_mask = df.duplicated(subset=["Player"], keep=False)
        tot_mask   = df["Tm"].str.upper().isin(["TOT", "2TM", "3TM", "4TM", "5TM"])
        df = df[~multi_mask | tot_mask].copy()

    # Normalize column names
    rename = {
        "Player": "player_name",
        "Tm":     "team",
        "Team":   "team",   # BBref uses "Team" in 2026
        "G":      "games_played",
        "MP":     "minutes",
        "PER":    "PER",
        "USG%":   "USG_pct",
        "WS":     "WS",
        "WS/48":  "WS48",
        "BPM":    "BPM",
        "OBPM":   "OBPM",
        "DBPM":   "DBPM",
        "VORP":   "VORP",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Extract player_id_bbref from Player links — not available via read_html,
    # so we derive a slug from the name as a stand-in identifier
    df["player_id_bbref"] = df["player_name"].map(
        lambda n: re.sub(r"[^a-z]", "", norm_name(str(n)))[:8]
        + "01"
    )

    # Cast numeric columns
    numeric_cols = ["games_played", "minutes", "PER", "USG_pct", "WS", "WS48",
                    "BPM", "OBPM", "DBPM", "VORP"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Filter minimum minutes
    if "minutes" in df.columns:
        df = df[df["minutes"] >= MIN_MINUTES].copy()

    keep = ["player_name", "player_id_bbref", "team", "games_played", "minutes",
            "PER", "USG_pct", "WS", "WS48", "BPM", "OBPM", "DBPM", "VORP"]
    df = df[[c for c in keep if c in df.columns]].reset_index(drop=True)

    # Fix any residual mojibake in names (belt-and-suspenders after explicit UTF-8 decode)
    try:
        import ftfy as _ftfy
        df["player_name"] = df["player_name"].map(lambda s: _ftfy.fix_text(str(s)) if pd.notna(s) else s)
    except ImportError:
        pass

    out = OUTPUT_DIR / "bbref_advanced_2025_26.csv"
    df.to_csv(out, index=False)
    print(f"[BBREF] SUCCESS — {len(df)} players → {out.name}")
    return df


def collect_nba_dot_com() -> pd.DataFrame | None:
    """NBA.com advanced stats via nba_api — gets PIE and related metrics."""
    print("[NBA.COM] Fetching via nba_api...")
    time.sleep(REQUEST_DELAY)
    try:
        from nba_api.stats.endpoints import leaguedashplayerstats  # type: ignore
        endpoint = leaguedashplayerstats.LeagueDashPlayerStats(
            season="2025-26",
            season_type_all_star="Regular Season",
            per_mode_detailed="Totals",
            measure_type_detailed_defense="Advanced",
            timeout=30,
        )
        df = endpoint.get_data_frames()[0]
    except Exception as e:
        log(f"[NBA.COM] FAILED: {e}")
        return None

    rename = {
        "PLAYER_NAME": "player_name",
        "PLAYER_ID":   "nba_player_id",
        "TEAM_ABBREVIATION": "team_nba",
        "MIN":         "minutes_nba",
        "PIE":         "PIE",
        "E_OFF_RATING": "E_OFF_RATING",
        "E_DEF_RATING": "E_DEF_RATING",
        "E_NET_RATING": "E_NET_RATING",
        "E_USG_PCT":    "E_USG_PCT",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    if "minutes_nba" in df.columns:
        df["minutes_nba"] = pd.to_numeric(df["minutes_nba"], errors="coerce")
        df = df[df["minutes_nba"] >= MIN_MINUTES].copy()

    keep = ["player_name", "nba_player_id", "team_nba", "minutes_nba",
            "PIE", "E_OFF_RATING", "E_DEF_RATING", "E_NET_RATING", "E_USG_PCT"]
    df = df[[c for c in keep if c in df.columns]].reset_index(drop=True)

    out = OUTPUT_DIR / "nba_dot_com_2025_26.csv"
    df.to_csv(out, index=False)
    print(f"[NBA.COM] SUCCESS — {len(df)} players → {out.name}")
    return df


def collect_raptor() -> pd.DataFrame | None:
    """FiveThirtyEight RAPTOR (archived GitHub CSV) — most recent season available."""
    print("[RAPTOR] Fetching from GitHub...")
    time.sleep(REQUEST_DELAY)
    try:
        df = pd.read_csv(RAPTOR_URL, low_memory=False)
    except Exception as e:
        log(f"[RAPTOR] FAILED: {e}")
        return None

    # Keep most recent season in the file
    if "season" in df.columns:
        latest = df["season"].max()
        df = df[df["season"] == latest].copy()
        print(f"[RAPTOR] Most recent season in archive: {latest}")
    elif "season_type" in df.columns:
        df = df[df["season_type"] == "RS"].copy()

    # Aggregate multi-team players — sum mp, average numeric columns only
    if "player_name" in df.columns:
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        agg_cols = {
            c: ("sum" if c == "mp" else "mean")
            for c in numeric_cols
            if c not in ("player_name",)
        }
        if agg_cols:
            df = df.groupby("player_name", as_index=False).agg(agg_cols)

    rename = {
        "player_name":    "player_name",
        "raptor_offense": "RAPTOR_O",
        "raptor_defense": "RAPTOR_D",
        "raptor_total":   "RAPTOR_total",
        "war_total":      "RAPTOR_WAR",
        "mp":             "minutes_raptor",
        "season":         "RAPTOR_season",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    if "minutes_raptor" in df.columns:
        df["minutes_raptor"] = pd.to_numeric(df["minutes_raptor"], errors="coerce")
        df = df[df["minutes_raptor"] >= MIN_MINUTES].copy()

    keep = ["player_name", "RAPTOR_O", "RAPTOR_D", "RAPTOR_total", "RAPTOR_WAR",
            "RAPTOR_season", "minutes_raptor"]
    df = df[[c for c in keep if c in df.columns]].reset_index(drop=True)

    out = OUTPUT_DIR / "raptor_2025_26.csv"
    df.to_csv(out, index=False)
    print(f"[RAPTOR] SUCCESS — {len(df)} players → {out.name}")
    return df


def collect_epm() -> pd.DataFrame | None:
    """DunksAndThrees EPM — attempt scrape, skip gracefully if blocked."""
    print("[EPM] Attempting dunksandthrees.com scrape...")
    time.sleep(REQUEST_DELAY)
    try:
        from bs4 import BeautifulSoup  # type: ignore
        resp = requests.get(EPM_URL, headers=HEADERS, timeout=15)
        if resp.status_code in (403, 429, 503):
            log(f"[EPM] SKIPPED (HTTP {resp.status_code} — site requires JS rendering)")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        tables = pd.read_html(io.StringIO(str(soup)), flavor="html5lib")
        if not tables:
            log("[EPM] SKIPPED (no parseable table found — site likely JS-rendered)")
            return None

        df = tables[0]
        if "EPM" not in df.columns and "epm" not in str(df.columns).lower():
            log("[EPM] SKIPPED (table found but no EPM column — format changed)")
            return None

        df.columns = [str(c).strip() for c in df.columns]
        name_col = next((c for c in df.columns if "player" in c.lower() or "name" in c.lower()), None)
        epm_col  = next((c for c in df.columns if "epm" in c.lower()), None)
        if not name_col or not epm_col:
            log("[EPM] SKIPPED (cannot identify name/EPM columns)")
            return None

        df = df[[name_col, epm_col]].rename(columns={name_col: "player_name", epm_col: "EPM"})
        df["EPM"] = pd.to_numeric(df["EPM"], errors="coerce")
        print(f"[EPM] SUCCESS — {len(df)} players")
        return df

    except Exception as e:
        log(f"[EPM] SKIPPED ({type(e).__name__}: {e})")
        return None


def collect_rpm() -> pd.DataFrame | None:
    """ESPN RPM — attempt scrape, skip gracefully if blocked."""
    print("[RPM] Attempting ESPN scrape...")
    time.sleep(REQUEST_DELAY)
    try:
        resp = requests.get(RPM_URL, headers=HEADERS, timeout=15)
        if resp.status_code in (403, 429, 503):
            log(f"[RPM] SKIPPED (HTTP {resp.status_code} — ESPN blocks scraping)")
            return None

        tables = pd.read_html(io.StringIO(resp.text))
        if not tables:
            log("[RPM] SKIPPED (no table found — site likely JS-rendered)")
            return None

        df = tables[0]
        df.columns = [str(c).strip() for c in df.columns]

        name_col = next((c for c in df.columns if "name" in c.lower() or "player" in c.lower()), None)
        rpm_col  = next((c for c in df.columns if c.upper() in ("RPM", "REAL PLUS-MINUS")), None)
        if not name_col or not rpm_col:
            log("[RPM] SKIPPED (cannot identify name/RPM columns)")
            return None

        df = df[[name_col, rpm_col]].rename(columns={name_col: "player_name", rpm_col: "RPM"})
        df["RPM"] = pd.to_numeric(df["RPM"], errors="coerce")
        print(f"[RPM] SUCCESS — {len(df)} players")
        return df

    except Exception as e:
        log(f"[RPM] SKIPPED ({type(e).__name__}: {e})")
        return None


def load_lebron() -> pd.DataFrame:
    """Load LEBRON ratings from local CSV (lebron-data-2026.csv)."""
    print("[LEBRON] Loading from local file...")
    df = pd.read_csv(LEBRON_CSV)

    rename = {
        "Player":    "player_name",
        "nba_id":    "nba_id",
        "LEBRON":    "LEBRON",
        "O-LEBRON":  "O_LEBRON",
        "D-LEBRON":  "D_LEBRON",
        "WAR":       "LEBRON_WAR",
        "Team":      "team_lebron",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    keep = ["player_name", "nba_id", "LEBRON", "O_LEBRON", "D_LEBRON", "LEBRON_WAR"]
    df = df[[c for c in keep if c in df.columns]].copy()
    print(f"[LEBRON] Loaded {len(df)} players from {LEBRON_CSV.name}")
    return df


# ── Merge pipeline ─────────────────────────────────────────────────────────────

def merge_all(
    spine: pd.DataFrame,
    nba_com: pd.DataFrame | None,
    raptor: pd.DataFrame | None,
    lebron: pd.DataFrame,
    epm: pd.DataFrame | None,
    rpm: pd.DataFrame | None,
) -> pd.DataFrame:
    master = spine.copy()

    # NBA.com — PIE + E ratings
    if nba_com is not None:
        log("\n[MERGE] BBref ← NBA.com (PIE, E ratings):")
        nba_cols = [c for c in ["PIE", "E_OFF_RATING", "E_DEF_RATING", "E_NET_RATING", "E_USG_PCT"]
                    if c in nba_com.columns]
        master = fuzzy_merge(master, nba_com, "player_name", "player_name", nba_cols)
    else:
        for c in ["PIE", "E_OFF_RATING", "E_DEF_RATING", "E_NET_RATING"]:
            master[c] = None

    # RAPTOR
    if raptor is not None:
        log("\n[MERGE] BBref ← RAPTOR:")
        rap_cols = [c for c in ["RAPTOR_O", "RAPTOR_D", "RAPTOR_total", "RAPTOR_WAR", "RAPTOR_season"]
                    if c in raptor.columns]
        master = fuzzy_merge(master, raptor, "player_name", "player_name", rap_cols)
    else:
        for c in ["RAPTOR_O", "RAPTOR_D", "RAPTOR_total", "RAPTOR_WAR", "RAPTOR_season"]:
            master[c] = None

    # LEBRON — try nba_id first, fall back to fuzzy name
    log("\n[MERGE] BBref ← LEBRON:")
    leb_cols = [c for c in ["LEBRON", "O_LEBRON", "D_LEBRON", "LEBRON_WAR"] if c in lebron.columns]
    master = fuzzy_merge(master, lebron, "player_name", "player_name", leb_cols)

    # EPM
    if epm is not None:
        log("\n[MERGE] BBref ← EPM:")
        master = fuzzy_merge(master, epm, "player_name", "player_name", ["EPM"])
    else:
        master["EPM"] = None

    # RPM
    if rpm is not None:
        log("\n[MERGE] BBref ← RPM:")
        master = fuzzy_merge(master, rpm, "player_name", "player_name", ["RPM"])
    else:
        master["RPM"] = None

    return master


# ── Summary ────────────────────────────────────────────────────────────────────

def print_summary(master: pd.DataFrame) -> None:
    print("\n" + "=" * 65)
    print("PIPELINE SUMMARY")
    print("=" * 65)
    print(f"Total players in master file: {len(master)}")

    metric_cols = ["PER", "BPM", "OBPM", "DBPM", "WS", "WS48", "VORP", "USG_pct",
                   "PIE", "RAPTOR_total", "RAPTOR_O", "RAPTOR_D", "RAPTOR_WAR",
                   "EPM", "RPM", "LEBRON", "O_LEBRON", "D_LEBRON"]

    print("\nNull counts per metric:")
    for col in metric_cols:
        if col in master.columns:
            n_null = master[col].isna().sum()
            pct    = n_null / len(master) * 100
            flag   = " ← needs supplement" if pct > 50 else ""
            print(f"  {col:<16} {n_null:>4} null ({pct:5.1f}%){flag}")
        else:
            print(f"  {col:<16}  not collected")

    if "BPM" in master.columns:
        show_cols = [c for c in ["player_name", "team", "BPM", "OBPM", "DBPM", "LEBRON"]
                     if c in master.columns]
        top10 = master[master["BPM"].notna()].nlargest(10, "BPM")[show_cols]
        print("\nTop 10 by BPM:")
        print(top10.to_string(index=False))

    print("=" * 65)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("NBA Metrics Pipeline — 2025-26 Season")
    print("=" * 65)
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Min minutes filter: {MIN_MINUTES}")
    print()

    # Collect all sources
    bbref  = collect_bbref()
    if bbref is None:
        print("\n[ABORT] Basketball-Reference is the spine — cannot continue without it.")
        save_log()
        sys.exit(1)

    nba_com = collect_nba_dot_com()
    raptor  = collect_raptor()
    lebron  = load_lebron()
    epm     = collect_epm()
    rpm     = collect_rpm()

    # Merge
    print("\nMerging sources...")
    master = merge_all(bbref, nba_com, raptor, lebron, epm, rpm)

    # Save master
    out_path = OUTPUT_DIR / "nba_metrics_2025_26.csv"
    master.to_csv(out_path, index=False)
    print(f"\nMaster file saved: {out_path}")

    # Summary
    print_summary(master)

    # Save log
    save_log()
    print(f"\nMerge log saved: {MERGE_LOG}")


if __name__ == "__main__":
    main()
