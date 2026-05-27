"""
mps/scraper_supplement.py

Phase 1 of the MPS rebuild: expand mps_dataset_raw.csv with per-game and
advanced stats that were not captured in the original scraper.

Fetches missing columns for each training row that has a cbb_url:
  From players_advanced: per, ows, obpm, dbpm, ortg, ws_40
  From players_per_game:  pts_pg, trb_pg, ast_pg, stl_pg, blk_pg,
                          tov_pg, fg_pct, fg3_pct, mp_pg, games_played

Caches per-player to mps/data/supplement_cache/{sanitized}.json.
Writes merged result to mps/data/mps_dataset_raw.csv (in-place, backup first).

Run:
    cd /home/spencer/Workspace/macfax
    backend/.venv/bin/python -m mps.scraper_supplement
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup, Comment

from mps.scraper import _get, _find_table_in_comments, _parse_stats_table

# ── Paths ──────────────────────────────────────────────────────────────────────

MPS_DIR    = Path(__file__).parent
DATA_DIR   = MPS_DIR / "data"
CACHE_DIR  = DATA_DIR / "supplement_cache"
CSV_PATH   = DATA_DIR / "mps_dataset_raw.csv"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── New columns this script adds ───────────────────────────────────────────────

NEW_COLS = [
    "per", "ows", "obpm", "dbpm", "ortg", "ws_40",
    "pts_pg", "trb_pg", "ast_pg", "stl_pg", "blk_pg",
    "tov_pg", "fg_pct", "fg3_pct", "mp_pg", "games_played",
]

# ── CBB page parser ────────────────────────────────────────────────────────────

_SEASON_RE = re.compile(r"^\d{4}-\d{2,4}$")


def _f(d: dict, *keys) -> float | None:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "—", "-"):
            try:
                return float(str(v).replace("%", "").strip())
            except ValueError:
                continue
    return None


def scrape_supplement(cbb_url: str) -> dict:
    """Fetch cbb_url and return the new supplemental stat columns."""
    resp = _get(cbb_url)
    if resp.status_code != 200:
        print(f"    [supp] HTTP {resp.status_code} — {cbb_url}")
        return {}

    soup = BeautifulSoup(resp.text, "lxml")

    # ── Advanced table ─────────────────────────────────────────────────────────
    adv_table = soup.find("table", {"id": "players_advanced"})
    if adv_table is None:
        adv_table = _find_table_in_comments(soup, "players_advanced")

    adv_final: dict = {}
    if adv_table:
        adv_rows = _parse_stats_table(adv_table)
        season_rows = [r for r in adv_rows
                       if _SEASON_RE.match(r.get("year_id", r.get("season", "")).strip())]
        if not season_rows:
            season_rows = adv_rows
        if season_rows:
            adv_final = season_rows[-1]

    # ── Per-game table ─────────────────────────────────────────────────────────
    pg_table = soup.find("table", {"id": "players_per_game"})
    if pg_table is None:
        pg_table = _find_table_in_comments(soup, "players_per_game")

    pg_final: dict = {}
    if pg_table:
        pg_rows = _parse_stats_table(pg_table)
        pg_season = [r for r in pg_rows
                     if _SEASON_RE.match(r.get("year_id", r.get("season", "")).strip())]
        if not pg_season:
            pg_season = pg_rows
        if pg_season:
            pg_final = pg_season[-1]

    # ── Compute ws_40 from total WS + total MP ─────────────────────────────────
    ws  = _f(adv_final, "ws")
    mp  = _f(adv_final, "mp")
    ws_40 = (ws / (mp / 40)) if (ws is not None and mp and mp > 0) else None

    return {
        "per":          _f(adv_final, "per"),
        "ows":          _f(adv_final, "ows"),
        "obpm":         _f(adv_final, "obpm"),
        "dbpm":         _f(adv_final, "dbpm"),
        "ortg":         _f(adv_final, "off_rtg", "ortg"),
        "ws_40":        ws_40,
        "pts_pg":       _f(pg_final, "pts_per_g", "pts"),
        "trb_pg":       _f(pg_final, "trb_per_g", "trb"),
        "ast_pg":       _f(pg_final, "ast_per_g", "ast"),
        "stl_pg":       _f(pg_final, "stl_per_g", "stl"),
        "blk_pg":       _f(pg_final, "blk_per_g", "blk"),
        "tov_pg":       _f(pg_final, "tov_per_g", "tov"),
        "fg_pct":       _f(pg_final, "fg_pct"),
        "fg3_pct":      _f(pg_final, "fg3_pct"),
        "mp_pg":        _f(pg_final, "mp_per_g", "mp"),
        "games_played": _f(pg_final, "g", "games"),
    }


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _cache_key(cbb_url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", cbb_url.strip("/").split("/")[-1])


def _load_cached(cbb_url: str) -> dict | None:
    path = CACHE_DIR / f"{_cache_key(cbb_url)}.json"
    if path.exists():
        try:
            with path.open() as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _write_cache(cbb_url: str, data: dict) -> None:
    path = CACHE_DIR / f"{_cache_key(cbb_url)}.json"
    try:
        with path.open("w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"    [supp cache] write error: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 64)
    print("  MPS SUPPLEMENT SCRAPER — Expand training CSV")
    print("=" * 64)

    df = pd.read_csv(CSV_PATH)
    print(f"\n  Loaded {len(df)} rows from {CSV_PATH.name}")

    # Determine which rows need supplementing
    # A row needs work if any new column is missing (NaN or not present)
    for col in NEW_COLS:
        if col not in df.columns:
            df[col] = float("nan")

    # Rows with a cbb_url
    has_url = df["cbb_url"].notna() & (df["cbb_url"].str.strip() != "")
    rows_with_url = df[has_url]
    print(f"  Rows with cbb_url: {len(rows_with_url)}")

    # Skip rows already fully supplemented (all new cols present + non-NaN BPM proxy)
    needs_work = df[has_url & df["per"].isna()].copy()
    from_cache = df[has_url & df["per"].notna()]
    print(f"  Already complete: {len(from_cache)}  |  Need fetching: {len(needs_work)}")

    if needs_work.empty:
        print("\n  Nothing to do — all rows already supplemented.")
        return

    total   = len(needs_work)
    fetched = 0
    cached  = 0
    errors  = 0

    updates: dict[int, dict] = {}  # row index → new stats

    for idx, (row_idx, row) in enumerate(needs_work.iterrows()):
        cbb_url = str(row["cbb_url"]).strip()
        name    = row.get("player_name", "?")
        year    = int(row.get("draft_year", 0))

        cached_data = _load_cached(cbb_url)
        if cached_data is not None:
            updates[row_idx] = cached_data
            cached += 1
            if (idx + 1) % 50 == 0:
                print(f"  [{idx+1}/{total}] {name} ({year}) — cache hit")
            continue

        print(f"  [{idx+1}/{total}] {name} ({year}) — {cbb_url}")
        try:
            data = scrape_supplement(cbb_url)
            _write_cache(cbb_url, data)
            updates[row_idx] = data
            fetched += 1
        except Exception as exc:
            print(f"    ERROR: {exc}")
            errors += 1

    # Apply updates
    for row_idx, data in updates.items():
        for col, val in data.items():
            if col in df.columns:
                df.at[row_idx, col] = val

    # Backup original then write
    backup = CSV_PATH.with_suffix(".csv.bak")
    shutil.copy2(CSV_PATH, backup)
    df.to_csv(CSV_PATH, index=False)

    print(f"\n  Done. Fetched: {fetched}  Cached: {cached}  Errors: {errors}")
    print(f"  Backup: {backup.name}")
    print(f"  Written: {CSV_PATH.name} ({len(df)} rows, {len(df.columns)} columns)")

    # Quick coverage report
    print("\n  Column coverage (non-null / total):")
    for col in NEW_COLS:
        n = df[col].notna().sum()
        print(f"    {col:<20}  {n}/{len(df)}")
    print("=" * 64)


if __name__ == "__main__":
    main()
