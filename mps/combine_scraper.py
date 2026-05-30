"""
mps/combine_scraper.py

Fetch official 2026 NBA Draft Combine anthropometric + athleticism measurements
from the NBA Stats API.  Results cached to mps/data/combine_2026.json (24-hr TTL).

Public API
----------
scrape_combine_measurements(season_year)  → {name: {height_in, wingspan_in, ...}}
scrape_combine_athleticism(season_year)   → {name: {max_vertical_in}}
get_full_combine_data(season_year)        → merged dict, cached
"""

from __future__ import annotations

import difflib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── Paths ──────────────────────────────────────────────────────────────────────

MPS_DIR    = Path(__file__).parent
DATA_DIR   = MPS_DIR / "data"
CACHE_FILE = DATA_DIR / "combine_2026.json"
CACHE_TTL  = 24 * 3600  # seconds

# ── Name overrides ─────────────────────────────────────────────────────────────
# Maps prospect display name → NBA combine API name when fuzzy matching fails.
# Add entries here when a player's legal/API name differs from their roster name.

COMBINE_NAME_OVERRIDES: dict[str, str] = {
    "AJ Dybantsa": "Anicet Dybantsa",  # legal name; API uses "Anicet Dybantsa"
}

# ── NBA Stats API ──────────────────────────────────────────────────────────────

_BASE = "https://stats.nba.com/stats"

NBA_HEADERS = {
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token":  "true",
    "Referer":            "https://www.nba.com/",
    "User-Agent":         (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":             "application/json, text/plain, */*",
    "Accept-Language":    "en-US,en;q=0.9",
    "Origin":             "https://www.nba.com",
}

TIMEOUT = 20  # seconds


# ── Internal helpers ───────────────────────────────────────────────────────────

def _nba_fetch(endpoint: str, params: dict) -> list[dict]:
    """
    GET one NBA Stats endpoint.  Returns list of row-dicts from resultSets[0].
    Returns [] on error or empty rowSet.
    """
    url = f"{_BASE}/{endpoint}"
    try:
        r = requests.get(url, headers=NBA_HEADERS, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        rs = data.get("resultSets", data.get("resultSet", []))
        if not rs:
            return []
        rs0 = rs[0]
        headers = rs0.get("headers", [])
        rows    = rs0.get("rowSet", [])
        return [dict(zip(headers, row)) for row in rows]
    except Exception as exc:
        print(f"    [combine] {endpoint} fetch error: {exc}")
        return []


def _safe_float(val) -> float | None:
    """Convert to float; return None on blank/null."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ── Public scrapers ────────────────────────────────────────────────────────────

def scrape_combine_measurements(season_year: str = "2026-27") -> dict[str, dict]:
    """
    Fetch draftcombineplayeranthro endpoint for the given season year.

    Tries ``season_year`` first, then "2026" as fallback if rowSet is empty.

    Returns
    -------
    dict[str, dict]  —  {player_name: {height_in, wingspan_in,
                                        standing_reach_in, weight_lbs}}
    Empty dict on failure or blocked API.
    """
    params = {"LeagueID": "00", "SeasonYear": season_year}
    rows = _nba_fetch("draftcombineplayeranthro", params)

    # Retry with alternate season-year format
    # NBA uses one-year-forward convention: combine for 2026 draft → "2026-27"
    if not rows and season_year == "2026-27":
        params["SeasonYear"] = "2026"
        rows = _nba_fetch("draftcombineplayeranthro", params)

    result: dict[str, dict] = {}
    for row in rows:
        name = row.get("PLAYER_NAME", "").strip()
        if not name:
            continue
        result[name] = {
            "height_in":         _safe_float(row.get("HEIGHT_WO_SHOES")),
            "wingspan_in":       _safe_float(row.get("WINGSPAN")),
            "standing_reach_in": _safe_float(row.get("STANDING_REACH")),
            "weight_lbs":        _safe_float(row.get("WEIGHT")),
        }
    return result


def scrape_combine_athleticism(season_year: str = "2026-27") -> dict[str, dict]:
    """
    Fetch draftcombinedrillresults endpoint for the given season year.

    Returns
    -------
    dict[str, dict]  —  {player_name: {max_vertical_in}}
    Empty dict on failure.
    """
    params = {"LeagueID": "00", "SeasonYear": season_year}
    rows = _nba_fetch("draftcombinedrillresults", params)

    if not rows and season_year == "2026-27":
        params["SeasonYear"] = "2026"
        rows = _nba_fetch("draftcombinedrillresults", params)

    result: dict[str, dict] = {}
    for row in rows:
        name = row.get("PLAYER_NAME", "").strip()
        if not name:
            continue
        result[name] = {
            "max_vertical_in":  _safe_float(row.get("MAX_VERTICAL_LEAP")),
            "lane_agility_sec": _safe_float(row.get("LANE_AGILITY_TIME")),
            "shuttle_run_sec":  _safe_float(row.get("SHUTTLE_RUN")),
            "sprint_sec":       _safe_float(row.get("THREE_QUARTER_SPRINT")),
        }
    return result


# ── Fallback scraper (babcockhoops.com) ───────────────────────────────────────

_BABCOCK_URL = "https://www.babcockhoops.com/combineresults"

# Expected column header substrings (case-insensitive) we try to match
_BABCOCK_COL_MAP = {
    "height":    "height_in",
    "wingspan":  "wingspan_in",
    "reach":     "standing_reach_in",
    "weight":    "weight_lbs",
    "vertical":  "max_vertical_in",
}


def _scrape_babcock() -> dict[str, dict]:
    """
    Attempt to parse combine measurements from babcockhoops.com.
    Returns {} on failure.
    """
    try:
        r = requests.get(
            _BABCOCK_URL,
            headers={"User-Agent": NBA_HEADERS["User-Agent"]},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
    except Exception as exc:
        print(f"    [combine] babcockhoops fetch error: {exc}")
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        print("    [combine] babcockhoops: no tables found")
        return {}

    result: dict[str, dict] = {}

    for table in tables:
        # Find header row
        header_cells = table.find_all("th")
        if not header_cells:
            continue
        col_names = [c.get_text(strip=True).lower() for c in header_cells]

        # Map column index → field name
        col_map: dict[int, str] = {}
        for idx, col in enumerate(col_names):
            for kw, field in _BABCOCK_COL_MAP.items():
                if kw in col:
                    col_map[idx] = field
                    break

        # Need at least wingspan/height to be useful
        fields_found = set(col_map.values())
        if "wingspan_in" not in fields_found and "height_in" not in fields_found:
            continue

        # Identify name column (first column usually)
        name_idx = 0
        for idx, col in enumerate(col_names):
            if "name" in col or "player" in col:
                name_idx = idx
                break

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= name_idx:
                continue
            name = cells[name_idx].get_text(strip=True)
            if not name or name.lower() in ("player", "name", ""):
                continue
            entry: dict = {}
            for col_idx, field in col_map.items():
                if col_idx < len(cells):
                    entry[field] = _safe_float(cells[col_idx].get_text(strip=True))
            if entry:
                result[name] = entry

    if result:
        print(f"    [combine] babcockhoops: {len(result)} players scraped (fallback)")
    else:
        print("    [combine] babcockhoops: parsed but no usable rows")
    return result


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _load_cache(cache_path: Path) -> dict[str, dict] | None:
    """Return cached players dict if cache exists and is fresh; None otherwise."""
    if not cache_path.exists():
        return None
    try:
        with cache_path.open() as f:
            obj = json.load(f)
        fetched_at_str = obj.get("fetched_at", "")
        if not fetched_at_str:
            return None
        fetched_at = datetime.fromisoformat(fetched_at_str)
        # Make both timezone-aware for comparison
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(tz=timezone.utc) - fetched_at).total_seconds()
        if age > CACHE_TTL:
            return None
        players = obj.get("players", {})
        print(f"    [combine] cache hit ({len(players)} players, "
              f"age {age/3600:.1f}h)")
        return players
    except Exception as exc:
        print(f"    [combine] cache read error: {exc}")
        return None


def _write_cache(players: dict[str, dict], cache_path: Path) -> None:
    """Write players dict to cache file with current timestamp."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    obj = {
        "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
        "players":    players,
    }
    try:
        with cache_path.open("w") as f:
            json.dump(obj, f, indent=2)
        print(f"    [combine] cache written → {cache_path}")
    except Exception as exc:
        print(f"    [combine] cache write error: {exc}")


# ── Main public function ───────────────────────────────────────────────────────

def get_full_combine_data(
    season_year: str = "2026-27",
    cache_path: Path | None = None,
) -> dict[str, dict]:
    """
    Return full combine data for all measured prospects.

    Data sources (in priority order):
      1. Fresh cache (24-hr TTL)  →  return immediately
      2. NBA Stats API (anthro + drill results)
      3. babcockhoops.com (fallback if NBA API blocked)

    Returns
    -------
    dict[str, dict]
        Keys are player names as returned by the data source.
        Values contain any subset of:
            height_in, wingspan_in, standing_reach_in,
            weight_lbs, max_vertical_in,
            lane_agility_sec, shuttle_run_sec, sprint_sec
        May be empty dict if all sources fail.
    """
    if cache_path is None:
        cache_path = CACHE_FILE

    # 1 — Try cache
    cached = _load_cache(cache_path)
    if cached is not None:
        return cached

    # 2 — NBA Stats API
    # NBA combine SeasonYear convention: "2026-27" = combine for 2026 draft
    print(f"    [combine] fetching NBA Stats API (season={season_year})...")
    anthro = scrape_combine_measurements(season_year)
    time.sleep(1)
    athletic = scrape_combine_athleticism(season_year)

    if anthro or athletic:
        # Merge: start with anthro, add athletic fields
        players: dict[str, dict] = {}
        all_names = set(anthro) | set(athletic)
        for name in all_names:
            entry = {**anthro.get(name, {}), **athletic.get(name, {})}
            players[name] = entry
        print(f"    [combine] NBA API: {len(players)} players "
              f"({len(anthro)} anthro, {len(athletic)} athletic)")
        _write_cache(players, cache_path)
        return players

    # 3 — Fallback: babcockhoops.com
    print("    [combine] NBA API returned no data — trying babcockhoops.com fallback...")
    players = _scrape_babcock()
    if players:
        _write_cache(players, cache_path)
    else:
        print("    [combine] all sources failed — physical adj = 0.0 for all players")

    return players


# ── Per-player lookup (for use by scorer) ─────────────────────────────────────

def lookup_player(data: dict[str, dict], name: str) -> dict:
    """
    Look up a prospect by name in the combine data dict.

    Resolution order:
      1. ``COMBINE_NAME_OVERRIDES[name]`` → exact lookup using mapped API name
      2. Exact match on ``name``
      3. ``difflib.get_close_matches(name, ...)`` with cutoff=0.8

    Returns {} on miss.
    """
    if not data:
        return {}
    # 1 — Override table (handles legal-name / nickname mismatches)
    api_name = COMBINE_NAME_OVERRIDES.get(name)
    if api_name and api_name in data:
        return data[api_name]
    # 2 — Exact
    if name in data:
        return data[name]
    # 3 — Fuzzy
    matches = difflib.get_close_matches(name, data.keys(), n=1, cutoff=0.8)
    if matches:
        return data[matches[0]]
    return {}


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    data = get_full_combine_data()
    print(f"\nTotal players: {len(data)}")
    for name, vals in sorted(data.items()):
        h = vals.get("height_in")
        w = vals.get("wingspan_in")
        ratio = f"{w/h:.3f}" if h and w else "N/A"
        print(f"  {name:<28}  H={h}  W={w}  ratio={ratio}")
