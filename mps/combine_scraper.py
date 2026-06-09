"""
mps/combine_scraper.py

Fetch official 2026 NBA Draft Combine data from the NBA Stats API.
Results cached to mps/data/combine_2026.json (24-hr TTL).

Primary source: draftcombinestats (single endpoint — anthro + athletic + all shooting spots)
Fallbacks:      draftcombineplayeranthro + draftcombinedrillresults (anthro/athletic only)
                babcockhoops.com (anthro/athletic only)

Public API
----------
scrape_combine_stats(season_year)         → full dict from draftcombinestats
scrape_combine_measurements(season_year)  → anthro fallback dict
scrape_combine_athleticism(season_year)   → athletic fallback dict
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
    """GET one NBA Stats endpoint. Returns list of row-dicts from resultSets[0]."""
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


def _parse_makes_att(val) -> tuple[int, int] | tuple[None, None]:
    """
    Parse NBA combine shooting cell (e.g. "12-25") → (makes, attempts).
    Returns (None, None) on blank/null.
    """
    if val is None or val == "":
        return None, None
    s = str(val).strip()
    if "-" in s:
        parts = s.split("-", 1)
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    return None, None


def _agg_spots(row: dict, cols: list[str]) -> tuple[int | None, int | None]:
    """
    Sum makes and attempts across multiple shooting spot columns.
    Returns (total_makes, total_att) or (None, None) if all null.
    """
    total_makes = 0
    total_att   = 0
    any_data    = False
    for col in cols:
        m, a = _parse_makes_att(row.get(col))
        if m is not None and a is not None:
            total_makes += m
            total_att   += a
            any_data     = True
    if not any_data:
        return None, None
    return total_makes, total_att


# ── Shooting column groups ─────────────────────────────────────────────────────

_SPOT_15FT_COLS = [
    "SPOT_FIFTEEN_CORNER_LEFT", "SPOT_FIFTEEN_BREAK_LEFT", "SPOT_FIFTEEN_TOP_KEY",
    "SPOT_FIFTEEN_BREAK_RIGHT", "SPOT_FIFTEEN_CORNER_RIGHT",
]
_SPOT_COLLEGE3_COLS = [
    "SPOT_COLLEGE_CORNER_LEFT", "SPOT_COLLEGE_BREAK_LEFT", "SPOT_COLLEGE_TOP_KEY",
    "SPOT_COLLEGE_BREAK_RIGHT", "SPOT_COLLEGE_CORNER_RIGHT",
]
_SPOT_NBA3_COLS = [
    "SPOT_NBA_CORNER_LEFT", "SPOT_NBA_BREAK_LEFT", "SPOT_NBA_TOP_KEY",
    "SPOT_NBA_BREAK_RIGHT", "SPOT_NBA_CORNER_RIGHT",
]
_OFF_DRIB_15FT_COLS = [
    "OFF_DRIB_FIFTEEN_BREAK_LEFT", "OFF_DRIB_FIFTEEN_TOP_KEY", "OFF_DRIB_FIFTEEN_BREAK_RIGHT",
]
_OFF_DRIB_COLLEGE3_COLS = [
    "OFF_DRIB_COLLEGE_BREAK_LEFT", "OFF_DRIB_COLLEGE_TOP_KEY", "OFF_DRIB_COLLEGE_BREAK_RIGHT",
]


def _shooting_entry(row: dict) -> dict:
    """Build shooting sub-dict from a draftcombinestats row."""
    entry: dict = {}

    groups = [
        ("spot_15ft",          _SPOT_15FT_COLS),
        ("spot_college3",      _SPOT_COLLEGE3_COLS),
        ("spot_nba3",          _SPOT_NBA3_COLS),
        ("off_drib_15ft",      _OFF_DRIB_15FT_COLS),
        ("off_drib_college3",  _OFF_DRIB_COLLEGE3_COLS),
    ]
    for key, cols in groups:
        m, a = _agg_spots(row, cols)
        entry[f"{key}_makes"] = m
        entry[f"{key}_att"]   = a
        if m is not None and a and a > 0:
            entry[f"{key}_pct"] = round(m / a, 3)
        else:
            entry[f"{key}_pct"] = None

    # Single-spot on-move drills
    for col, key in [("ON_MOVE_FIFTEEN", "on_move_15ft"), ("ON_MOVE_COLLEGE", "on_move_college3")]:
        m, a = _parse_makes_att(row.get(col))
        entry[f"{key}_makes"] = m
        entry[f"{key}_att"]   = a
        if m is not None and a and a > 0:
            entry[f"{key}_pct"] = round(m / a, 3)
        else:
            entry[f"{key}_pct"] = None

    return entry


# ── Public scrapers ────────────────────────────────────────────────────────────

def scrape_combine_stats(season_year: str = "2026-27") -> dict[str, dict]:
    """
    Fetch draftcombinestats endpoint — returns anthro, athletic, and all
    shooting spots in a single API call.

    Returns
    -------
    dict[str, dict]  —  {player_name: {
        # Anthropometric
        height_in, height_w_shoes_in, wingspan_in, standing_reach_in,
        weight_lbs, body_fat_pct, hand_length_in, hand_width_in,
        # Athletic
        max_vertical_in, no_step_vertical_in,
        lane_agility_sec, modified_lane_agility_sec, sprint_sec, bench_press,
        # Shooting (aggregated by zone, each as _makes/_att/_pct)
        spot_15ft_*, spot_college3_*, spot_nba3_*,
        off_drib_15ft_*, off_drib_college3_*,
        on_move_15ft_*, on_move_college3_*,
    }}
    """
    params = {"LeagueID": "00", "SeasonYear": season_year}
    rows = _nba_fetch("draftcombinestats", params)

    if not rows and season_year == "2026-27":
        params["SeasonYear"] = "2026"
        rows = _nba_fetch("draftcombinestats", params)

    result: dict[str, dict] = {}
    for row in rows:
        name = row.get("PLAYER_NAME", "").strip()
        if not name:
            continue
        entry: dict = {
            # Anthropometric
            "height_in":               _safe_float(row.get("HEIGHT_WO_SHOES")),
            "height_w_shoes_in":        _safe_float(row.get("HEIGHT_W_SHOES")),
            "wingspan_in":              _safe_float(row.get("WINGSPAN")),
            "standing_reach_in":        _safe_float(row.get("STANDING_REACH")),
            "weight_lbs":               _safe_float(row.get("WEIGHT")),
            "body_fat_pct":             _safe_float(row.get("BODY_FAT_PCT")),
            "hand_length_in":           _safe_float(row.get("HAND_LENGTH")),
            "hand_width_in":            _safe_float(row.get("HAND_WIDTH")),
            # Athletic
            "max_vertical_in":          _safe_float(row.get("MAX_VERTICAL_LEAP")),
            "no_step_vertical_in":      _safe_float(row.get("STANDING_VERTICAL_LEAP")),
            "lane_agility_sec":         _safe_float(row.get("LANE_AGILITY_TIME")),
            "modified_lane_agility_sec":_safe_float(row.get("MODIFIED_LANE_AGILITY_TIME")),
            "sprint_sec":               _safe_float(row.get("THREE_QUARTER_SPRINT")),
            "bench_press":              _safe_float(row.get("BENCH_PRESS")),
        }
        entry.update(_shooting_entry(row))
        result[name] = entry

    return result


def scrape_combine_measurements(season_year: str = "2026-27") -> dict[str, dict]:
    """
    Fetch draftcombineplayeranthro endpoint (fallback when draftcombinestats unavailable).

    Returns
    -------
    dict[str, dict]  —  {player_name: {height_in, wingspan_in,
                                        standing_reach_in, weight_lbs,
                                        hand_length_in, hand_width_in}}
    """
    params = {"LeagueID": "00", "SeasonYear": season_year}
    rows = _nba_fetch("draftcombineplayeranthro", params)

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
            "hand_length_in":    _safe_float(row.get("HAND_LENGTH")),
            "hand_width_in":     _safe_float(row.get("HAND_WIDTH")),
        }
    return result


def scrape_combine_athleticism(season_year: str = "2026-27") -> dict[str, dict]:
    """
    Fetch draftcombinedrillresults endpoint (fallback when draftcombinestats unavailable).

    Returns
    -------
    dict[str, dict]  —  {player_name: {max_vertical_in, no_step_vertical_in,
                                        lane_agility_sec, shuttle_run_sec, sprint_sec}}
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
            "max_vertical_in":     _safe_float(row.get("MAX_VERTICAL_LEAP")),
            "no_step_vertical_in": _safe_float(row.get("NO_STEP_VERTICAL_LEAP")),
            "lane_agility_sec":    _safe_float(row.get("LANE_AGILITY_TIME")),
            "shuttle_run_sec":     _safe_float(row.get("SHUTTLE_RUN")),
            "sprint_sec":          _safe_float(row.get("THREE_QUARTER_SPRINT")),
        }
    return result


# ── Fallback scraper (babcockhoops.com) ───────────────────────────────────────

_BABCOCK_URL = "https://www.babcockhoops.com/combineresults"

_BABCOCK_COL_MAP = {
    "height":    "height_in",
    "wingspan":  "wingspan_in",
    "reach":     "standing_reach_in",
    "weight":    "weight_lbs",
    "vertical":  "max_vertical_in",
}


def _scrape_babcock() -> dict[str, dict]:
    """Attempt to parse combine measurements from babcockhoops.com. Returns {} on failure."""
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
        header_cells = table.find_all("th")
        if not header_cells:
            continue
        col_names = [c.get_text(strip=True).lower() for c in header_cells]

        col_map: dict[int, str] = {}
        for idx, col in enumerate(col_names):
            for kw, field in _BABCOCK_COL_MAP.items():
                if kw in col:
                    col_map[idx] = field
                    break

        fields_found = set(col_map.values())
        if "wingspan_in" not in fields_found and "height_in" not in fields_found:
            continue

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
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(tz=timezone.utc) - fetched_at).total_seconds()
        if age > CACHE_TTL:
            return None
        players = obj.get("players", {})
        print(f"    [combine] cache hit ({len(players)} players, age {age/3600:.1f}h)")
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
      1. Fresh cache (24-hr TTL)
      2. draftcombinestats  — anthro + athletic + all shooting spots in one call
      3. draftcombineplayeranthro + draftcombinedrillresults  — anthro/athletic only
      4. babcockhoops.com  — anthro/athletic only

    Returns
    -------
    dict[str, dict]
        Keys: player names as returned by the data source.
        Values: any subset of height_in, height_w_shoes_in, wingspan_in,
            standing_reach_in, weight_lbs, body_fat_pct,
            hand_length_in, hand_width_in,
            max_vertical_in, no_step_vertical_in,
            lane_agility_sec, modified_lane_agility_sec, sprint_sec, bench_press,
            spot_15ft_*/spot_college3_*/spot_nba3_*/_makes/_att/_pct,
            off_drib_15ft_*/off_drib_college3_*/_makes/_att/_pct,
            on_move_15ft_*/on_move_college3_*/_makes/_att/_pct
    """
    if cache_path is None:
        cache_path = CACHE_FILE

    # 1 — Try cache
    cached = _load_cache(cache_path)
    if cached is not None:
        return cached

    print(f"    [combine] fetching NBA Stats API (season={season_year})...")

    # 2 — draftcombinestats (everything in one call)
    players = scrape_combine_stats(season_year)
    if players:
        print(f"    [combine] draftcombinestats: {len(players)} players")
        _write_cache(players, cache_path)
        return players

    # 3 — Separate anthro + drill endpoints (no shooting data)
    print("    [combine] draftcombinestats empty — trying anthro + drill fallback...")
    anthro = scrape_combine_measurements(season_year)
    time.sleep(1)
    athletic = scrape_combine_athleticism(season_year)

    if anthro or athletic:
        players = {}
        for name in set(anthro) | set(athletic):
            players[name] = {**anthro.get(name, {}), **athletic.get(name, {})}
        print(f"    [combine] anthro+drill fallback: {len(players)} players "
              f"({len(anthro)} anthro, {len(athletic)} athletic)")
        _write_cache(players, cache_path)
        return players

    # 4 — babcockhoops.com
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
      1. COMBINE_NAME_OVERRIDES[name] → exact lookup using mapped API name
      2. Exact match on name
      3. difflib.get_close_matches with cutoff=0.8
    """
    if not data:
        return {}
    api_name = COMBINE_NAME_OVERRIDES.get(name)
    if api_name and api_name in data:
        return data[api_name]
    if name in data:
        return data[name]
    matches = difflib.get_close_matches(name, data.keys(), n=1, cutoff=0.8)
    if matches:
        return data[matches[0]]
    return {}


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    data = get_full_combine_data()
    print(f"\nTotal players: {len(data)}")
    for name, vals in sorted(data.items()):
        h  = vals.get("height_in")
        w  = vals.get("wingspan_in")
        hl = vals.get("hand_length_in")
        hw = vals.get("hand_width_in")
        mv = vals.get("max_vertical_in")
        ns = vals.get("no_step_vertical_in")
        c3 = vals.get("spot_college3_pct")
        ratio = f"{w/h:.3f}" if h and w else "N/A"
        print(
            f"  {name:<28}  H={h}  W={w}  ratio={ratio}"
            f"  hand={hl}x{hw}  vert={mv}/{ns}"
            f"  c3%={c3}"
        )
