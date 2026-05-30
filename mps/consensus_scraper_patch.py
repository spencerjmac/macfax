"""
mps/consensus_scraper_patch.py

Patches historical_consensus.json:
  1. Filters school names out of years with data (2010, 2015 have mixed-in schools)
  2. Retries failed years (2011, 2014, 2018, 2019) with longer timeout + alt URL patterns
  3. Fixes 2021 (wrong parse — schools instead of players)

Run:
    backend/.venv/bin/python -m mps.consensus_scraper_patch
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

DATA_DIR   = Path(__file__).parent / "data"
CACHE_PATH = DATA_DIR / "historical_consensus.json"

DRAFT_DATES = {
    2010: "20100624", 2011: "20110623", 2012: "20120628",
    2013: "20130627", 2014: "20140626", 2015: "20150625",
    2016: "20160623", 2017: "20170622", 2018: "20180621",
    2019: "20190620", 2021: "20210729",
}

KNOWN_TOP_PICKS = {
    2010: "John Wall",      2011: "Kyrie Irving",    2012: "Anthony Davis",
    2013: "Anthony Bennett",2014: "Andrew Wiggins",  2015: "Karl-Anthony Towns",
    2016: "Ben Simmons",    2017: "Markelle Fultz",  2018: "Deandre Ayton",
    2019: "Zion Williamson",2021: "Cade Cunningham",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nbadraft.net/",
}

MAX_REQUESTS = 25
_req_count   = 0


def _get(url: str, delay: float = 0.0, timeout: int = 35) -> Optional[requests.Response]:
    global _req_count
    if _req_count >= MAX_REQUESTS:
        print(f"  [BUDGET] max requests reached")
        return None
    if delay > 0:
        time.sleep(delay)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        _req_count += 1
        print(f"  [req #{_req_count}] {resp.status_code}  {url[:90]}")
        return resp
    except Exception as exc:
        _req_count += 1
        print(f"  [req #{_req_count}] ERROR: {type(exc).__name__}: {str(exc)[:80]}  {url[:60]}")
        return None


# ── School-name filter ────────────────────────────────────────────────────────

# Words that appear in college/school names but not player names
_SCHOOL_WORDS = {
    "state", "university", "college", "tech", "institute",
    "western", "eastern", "northern", "southern", "central",
    "ohio", "michigan", "indiana", "virginia", "carolina",
    "florida", "georgia", "texas", "kansas", "kentucky",
    "maryland", "arizona", "oklahoma", "illinois", "wisconsin",
    "minnesota", "tennessee", "missouri", "arkansas", "colorado",
    "connecticut", "vanderbilt", "marquette", "gonzaga", "villanova",
    "duke", "memphis", "louisiana", "mississippi", "alabama", "iowa",
    "oregon", "washington", "california", "penn", "nevada",
    "dayton", "butler", "xavier", "creighton", "providence",
    "seton", "hall", "boston", "pittsburgh", "houston", "cincinnati",
    "georgia", "pitt", "usc", "ucla", "uconn", "vcu",
    "madrid", "barcelona", "milan", "soccerbet", "mega", "cedevita",
    "cska", "zalgiris", "efes", "shawnee", "liberty",
    "montverde", "IMG", "prep", "academy",
}


def _is_school_name(name: str) -> bool:
    words = re.sub(r"[^a-z ]", "", name.lower()).split()
    return any(w in _SCHOOL_WORDS for w in words)


def _looks_like_person(name: str) -> bool:
    """True if name looks like FirstName LastName (optionally with Jr./II/III)."""
    # 2-4 words, each starting with uppercase, no school words
    words = name.strip().split()
    if len(words) < 2 or len(words) > 5:
        return False
    # Each word should be capitalized and contain only letters/hyphens/periods
    for w in words:
        if not re.match(r"^[A-Z][A-Za-z\-'\.]+$", w):
            return False
    if _is_school_name(name):
        return False
    return True


def filter_players(players: list[dict]) -> list[dict]:
    """Remove school names, renumber ranks."""
    clean = [p for p in players if _looks_like_person(p["player_name"])]
    # Renumber
    for i, p in enumerate(clean, 1):
        p["rank"] = i
    return clean


# ── CDX snapshot finder ───────────────────────────────────────────────────────

_CDX_URL_PATTERNS = [
    "nbadraft.net/ranking/bigboard/",
    "www.nbadraft.net/ranking/bigboard/",
    "nbadraft.net/nba-big-board/",
    "nbadraft.net/nba-draft-rankings/",
    "nbadraft.net/nba-draft-big-board/",
    "nbadraft.net/bigboard/",
]


def _cdx_find_snapshot(year: int, url_pattern: str = "nbadraft.net/ranking/bigboard/") -> Optional[str]:
    draft_date = DRAFT_DATES[year]
    start = f"{year}0601"
    cdx_url = (
        f"https://web.archive.org/cdx/search/cdx"
        f"?url={url_pattern}"
        f"&output=json&from={start}&to={draft_date}"
        f"&limit=10&fl=timestamp,statuscode&filter=statuscode:200"
    )
    resp = _get(cdx_url, delay=1.0, timeout=35)
    if resp is None or resp.status_code != 200:
        return None
    try:
        rows = resp.json()
        snapshots = [r[0] for r in rows[1:] if len(r) >= 1]
        return snapshots[-1] if snapshots else None
    except Exception:
        return None


def _wayback_fetch(ts: str) -> Optional[requests.Response]:
    url = f"https://web.archive.org/web/{ts}/https://www.nbadraft.net/ranking/bigboard/"
    return _get(url, delay=1.5, timeout=35)


# ── Parser (same as main scraper but with filtering) ─────────────────────────

def _clean_name(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*(PG|SG|SF|PF|C|G|F)\s*$", "", text, flags=re.IGNORECASE).strip()
    return text


def _parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    players = []

    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            rank_val = None
            name_val = None
            for cell in cells[:4]:
                txt = cell.get_text(strip=True)
                if txt.isdigit() and rank_val is None:
                    rank_val = int(txt)
                elif rank_val is not None and name_val is None and len(txt) > 3:
                    candidate = _clean_name(txt)
                    if _looks_like_person(candidate):
                        name_val = candidate
                        break  # stop after first valid name
            if rank_val and name_val:
                players.append({"rank": rank_val, "player_name": name_val, "position": None})

    if len(players) >= 10:
        return players

    # Fallback: anchors with player profile paths
    players = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        txt = a.get_text(strip=True)
        if ("/nba-draft/" in href or "/player/" in href or "/players/" in href):
            if _looks_like_person(txt):
                players.append({"rank": len(players) + 1, "player_name": _clean_name(txt), "position": None})

    if len(players) >= 10:
        return players

    # Fallback: all td with person-name-looking text
    players = []
    for td in soup.find_all("td"):
        txt = td.get_text(strip=True)
        if _looks_like_person(txt):
            players.append({"rank": len(players) + 1, "player_name": _clean_name(txt), "position": None})

    return players


# ── Fix step 1: Filter school names from existing data ────────────────────────

def step1_filter_existing(data: dict) -> dict:
    print("=" * 70)
    print("  Step 1: Filter school names from existing year data")
    print("=" * 70)

    for year_str, players in data["sources"]["nbadraft_net"].items():
        before = len(players)
        cleaned = filter_players(players)
        after = len(cleaned)
        removed = before - after
        data["sources"]["nbadraft_net"][year_str] = cleaned
        data["metadata"][year_str]["n"] = after
        if removed:
            print(f"  {year_str}: removed {removed} school/invalid names → {after} players remain")
        else:
            print(f"  {year_str}: no school names found → {after} players")

    return data


# ── Fix step 2: Retry failed years ───────────────────────────────────────────

def step2_retry_failed(data: dict) -> dict:
    print("\n" + "=" * 70)
    print("  Step 2: Retry failed years")
    print("=" * 70)

    failed_years = [
        year for year_str, meta in data["metadata"].items()
        if meta["n"] < 10
        for year in [int(year_str)]
    ]
    print(f"  Failed years: {failed_years}")

    for year in failed_years:
        print(f"\n  Retrying {year}:")
        ts = None

        # Try all known URL patterns for CDX
        for pattern in _CDX_URL_PATTERNS:
            if _req_count >= MAX_REQUESTS - 2:
                print(f"    Budget low — stopping retries")
                break
            ts = _cdx_find_snapshot(year, pattern)
            if ts:
                print(f"    Found snapshot {ts} via pattern: {pattern}")
                break
            time.sleep(0.5)

        if not ts:
            print(f"    No snapshot found for {year} across all patterns")
            continue

        resp = _wayback_fetch(ts)
        if resp is None or resp.status_code != 200:
            print(f"    Fetch failed")
            continue

        players = _parse_page(resp.text)
        players = filter_players(players)
        snap_date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"

        if len(players) < 10:
            print(f"    Only {len(players)} valid players found — insufficient")
            # Store what we have anyway
            if players:
                data["sources"]["nbadraft_net"][str(year)] = players
                data["metadata"][str(year)] = {"source": f"wayback:{snap_date}", "n": len(players)}
            continue

        data["sources"]["nbadraft_net"][str(year)] = players
        data["metadata"][str(year)] = {"source": f"wayback:{snap_date}", "n": len(players)}
        top3 = ", ".join(p["player_name"] for p in players[:3])
        print(f"    ✓ {len(players)} players | top3: {top3}")

    return data


# ── Fix step 3: Fix 2021 with deeper Wayback search ──────────────────────────

def step3_fix_2021(data: dict) -> dict:
    print("\n" + "=" * 70)
    print("  Step 3: Fix 2021 (earlier snapshot or alternative URL)")
    print("=" * 70)

    # 2021 snapshot from July 21 had college names — try earlier dates
    # Also try alternative URL patterns for 2021
    early_2021_patterns = [
        ("nbadraft.net/ranking/bigboard/", "20210601", "20210728"),
        ("www.nbadraft.net/ranking/bigboard/", "20210601", "20210728"),
        ("nbadraft.net/nba-big-board/", "20210601", "20210728"),
    ]

    for url_pattern, start, end in early_2021_patterns:
        if _req_count >= MAX_REQUESTS - 2:
            break
        draft_date = end
        cdx_url = (
            f"https://web.archive.org/cdx/search/cdx"
            f"?url={url_pattern}"
            f"&output=json&from={start}&to={draft_date}"
            f"&limit=10&fl=timestamp,statuscode&filter=statuscode:200"
        )
        resp = _get(cdx_url, delay=1.0, timeout=35)
        if resp is None or resp.status_code != 200:
            continue
        try:
            rows = resp.json()
            snapshots = [r[0] for r in rows[1:] if len(r) >= 1]
            if not snapshots:
                continue
            # Try multiple snapshots for 2021 (site kept changing)
            for ts in reversed(snapshots[-5:]):
                if _req_count >= MAX_REQUESTS - 1:
                    break
                fetch_resp = _wayback_fetch(ts)
                if fetch_resp is None or fetch_resp.status_code != 200:
                    continue
                players = _parse_page(fetch_resp.text)
                players = filter_players(players)
                snap_date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
                if len(players) >= 20:
                    data["sources"]["nbadraft_net"]["2021"] = players
                    data["metadata"]["2021"] = {"source": f"wayback:{snap_date}", "n": len(players)}
                    top3 = ", ".join(p["player_name"] for p in players[:3])
                    print(f"  2021: ✓ {len(players)} players | top3: {top3}")
                    return data
                else:
                    print(f"  2021 snapshot {snap_date}: only {len(players)} valid players")
        except Exception as exc:
            print(f"  2021 CDX error: {exc}")
            continue

    print("  2021: Could not find clean snapshot — keeping current {n} players".format(
        n=data["metadata"].get("2021", {}).get("n", 0)
    ))
    return data


# ── Validation ────────────────────────────────────────────────────────────────

def validate(data: dict) -> None:
    print("\n" + "=" * 70)
    print("  Validation: Ground truth check + coverage summary")
    print("=" * 70)

    print(f"\n  {'Year':>4}  {'Source':<30}  {'n':>4}  {'#1 on board':<25}  {'Expected #1':<25}  Status")
    print("  " + "-" * 105)

    total = 0
    matched = 0
    for year in sorted(int(y) for y in data["metadata"]):
        meta = data["metadata"][str(year)]
        players = data["sources"]["nbadraft_net"].get(str(year), [])
        n = meta["n"]
        total += 1
        top1 = players[0]["player_name"] if players else "—"
        expected = KNOWN_TOP_PICKS.get(year, "?")
        source = meta["source"][:30]

        def _norm(s): return re.sub(r"[^a-z ]", "", s.lower()).strip()
        ok = (_norm(top1) == _norm(expected)
              or _norm(expected) in _norm(top1)
              or _norm(top1) in _norm(expected))
        status = "✓" if (ok or n == 0) else "⚠ MISMATCH"
        if n >= 10:
            matched += 1
        print(f"  {year:>4}  {source:<30}  {n:>4}  {top1:<25}  {expected:<25}  {status}")

    years_with_data = sum(1 for y in data["metadata"]
                          if data["metadata"][y]["n"] >= 10)
    print(f"\n  Years with ≥10 players: {years_with_data}/11")
    print(f"  Total requests used: {_req_count}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Consensus Scraper Patch")
    print()

    with CACHE_PATH.open() as f:
        data = json.load(f)

    data = step1_filter_existing(data)
    data = step2_retry_failed(data)
    data = step3_fix_2021(data)
    validate(data)

    with CACHE_PATH.open("w") as f:
        json.dump(data, f, indent=2)
    print(f"\n  Saved patched data to {CACHE_PATH}")


if __name__ == "__main__":
    main()
