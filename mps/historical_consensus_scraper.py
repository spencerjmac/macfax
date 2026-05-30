"""
mps/historical_consensus_scraper.py

Phase 1 of scout consensus integration.
Scrapes historical pre-draft big boards from NBADraft.net (primary)
and NBA Draft Network (secondary) for 2010-2019 and 2021 draft classes.

Run:
    backend/.venv/bin/python -m mps.historical_consensus_scraper
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent / "data"
CACHE_PATH = DATA_DIR / "historical_consensus.json"

TRAINING_YEARS = [2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021]

# Draft day dates (cutoff for pre-draft snapshots)
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
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nbadraft.net/",
    "Connection": "keep-alive",
}

REQUEST_DELAY_PRIMARY = 2.0
REQUEST_DELAY_WAYBACK = 1.5
MAX_REQUESTS = 28

_request_count = 0


def _get(url: str, delay: float = 0.0, timeout: int = 20) -> Optional[requests.Response]:
    global _request_count
    if _request_count >= MAX_REQUESTS:
        print(f"  [BUDGET] Request budget ({MAX_REQUESTS}) exhausted — skipping {url[:60]}")
        return None
    if delay > 0:
        time.sleep(delay)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        _request_count += 1
        print(f"  [req #{_request_count}] {resp.status_code} {url[:80]}")
        return resp
    except Exception as exc:
        _request_count += 1
        print(f"  [req #{_request_count}] ERROR {url[:80]}: {exc}")
        return None


# ── HTML Parsing ──────────────────────────────────────────────────────────────

def _clean_name(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # Remove common suffixes that appear as separate elements
    text = re.sub(r"\s*(PG|SG|SF|PF|C|G|F)\s*$", "", text, flags=re.IGNORECASE).strip()
    return text


def _parse_nbadraft_page(html: str) -> list[dict]:
    """
    Adaptive parser for NBADraft.net big board page.
    Tries multiple HTML patterns. Returns list of {rank, player_name, position}.
    """
    soup = BeautifulSoup(html, "lxml")
    players = []

    # Strategy 1: standard <table> with rows
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            # Try to find rank (integer) in first few cells
            rank_val = None
            name_val = None
            pos_val = None
            for i, cell in enumerate(cells[:3]):
                txt = cell.get_text(strip=True)
                if txt.isdigit() and rank_val is None:
                    rank_val = int(txt)
                elif rank_val is not None and name_val is None and len(txt) > 3:
                    name_val = _clean_name(txt)
                elif name_val is not None and pos_val is None and len(txt) <= 3:
                    pos_val = txt
            if rank_val and name_val:
                players.append({"rank": rank_val, "player_name": name_val, "position": pos_val})

    if len(players) >= 10:
        return players

    # Strategy 2: look for numbered list items or ranked divs
    players = []
    # Try pattern: element with class containing "rank" or "player"
    for tag in soup.find_all(["div", "li", "span"], class_=True):
        classes = " ".join(tag.get("class", []))
        if re.search(r"player.name|name.player|player-row|big.board", classes, re.I):
            txt = tag.get_text(strip=True)
            if len(txt) > 4:
                players.append({"rank": len(players) + 1, "player_name": _clean_name(txt), "position": None})

    if len(players) >= 10:
        return players

    # Strategy 3: any <td> that looks like a player name (2+ words, title case)
    players = []
    rank_counter = 0
    for td in soup.find_all("td"):
        txt = td.get_text(strip=True)
        if re.match(r"^[A-Z][a-z]+ [A-Z]", txt) and 5 < len(txt) < 40:
            rank_counter += 1
            players.append({"rank": rank_counter, "player_name": _clean_name(txt), "position": None})

    if len(players) >= 10:
        return players

    # Strategy 4: look for ranked anchor links with player names
    players = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        txt = a.get_text(strip=True)
        if "/nba-draft/" in href or "/player/" in href:
            if re.match(r"^[A-Z][a-z]", txt) and 5 < len(txt) < 40:
                players.append({"rank": len(players) + 1, "player_name": _clean_name(txt), "position": None})

    return players


# ── Wayback Machine ───────────────────────────────────────────────────────────

def _wayback_find_snapshot(year: int) -> Optional[str]:
    """Use CDX API to find best pre-draft snapshot timestamp."""
    draft_date = DRAFT_DATES[year]
    start_date = f"{year}0601"
    cdx_url = (
        f"http://web.archive.org/cdx/search/cdx"
        f"?url=nbadraft.net/ranking/bigboard/"
        f"&output=json&from={start_date}&to={draft_date}"
        f"&limit=10&fl=timestamp,statuscode&filter=statuscode:200"
    )
    resp = _get(cdx_url, delay=REQUEST_DELAY_WAYBACK)
    if resp is None or resp.status_code != 200:
        return None
    try:
        rows = resp.json()
        # rows[0] is header ["timestamp","statuscode"]
        snapshots = [r[0] for r in rows[1:] if len(r) >= 1]
        if not snapshots:
            return None
        # Take most recent (last) snapshot before draft day
        return snapshots[-1]
    except Exception as exc:
        print(f"    CDX parse error: {exc}")
        return None


def _wayback_fetch_year(year: int) -> tuple[list[dict], str]:
    """Fetch from Wayback Machine. Returns (players, source_description)."""
    ts = _wayback_find_snapshot(year)
    if not ts:
        return [], "wayback_no_snapshot"

    wayback_url = f"https://web.archive.org/web/{ts}/https://www.nbadraft.net/ranking/bigboard/"
    resp = _get(wayback_url, delay=REQUEST_DELAY_WAYBACK)
    if resp is None or resp.status_code != 200:
        return [], "wayback_fetch_failed"

    players = _parse_nbadraft_page(resp.text)
    snapshot_date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
    return players, f"wayback:{snapshot_date}"


# ── Phase 1A: Probe ───────────────────────────────────────────────────────────

def phase1a_probe() -> str:
    """Probe 2019 primary URL, identify HTML structure, return selector hint."""
    print("=" * 70)
    print("  Phase 1A: URL Probe — NBADraft.net 2019")
    print("=" * 70)

    url = "https://www.nbadraft.net/ranking/bigboard/?year-mock=2019"
    resp = _get(url, delay=0.0)

    if resp is None:
        print("  FAILED: No response")
        return "wayback"

    print(f"\n  HTTP status: {resp.status_code}")
    print(f"  Content-Type: {resp.headers.get('content-type', 'unknown')[:60]}")
    print(f"  Content length: {len(resp.text):,} bytes")

    soup = BeautifulSoup(resp.text, "lxml")

    # Detect SPA shell (empty body = React/Vue SSR missing)
    body_text = soup.get_text(strip=True)
    has_player_names = bool(re.search(r"Zion Williamson|Ja Morant|RJ Barrett", resp.text, re.I))

    print(f"\n  Known 2019 player names found in HTML: {has_player_names}")

    # Report HTML structure
    tables = soup.find_all("table")
    print(f"  <table> elements found: {len(tables)}")
    for i, t in enumerate(tables[:3]):
        print(f"    table[{i}]: class={t.get('class')} id={t.get('id')}")
        rows = t.find_all("tr")
        print(f"      rows={len(rows)}, sample: {t.get_text()[:100]!r}")

    divs_with_rank = soup.find_all(attrs={"class": re.compile(r"rank|player|board", re.I)})
    print(f"  Rank/player/board classed elements: {len(divs_with_rank)}")
    for el in divs_with_rank[:3]:
        print(f"    <{el.name} class={el.get('class')}> text={el.get_text(strip=True)[:60]!r}")

    players = _parse_nbadraft_page(resp.text)
    print(f"\n  Players parsed by adaptive parser: {len(players)}")
    if players:
        print(f"  Top 5:")
        for p in players[:5]:
            print(f"    #{p['rank']:>3}  {p['player_name']}")

    if len(players) >= 10:
        return "primary_works"
    if resp.status_code == 200 and len(body_text) < 500:
        print("\n  DIAGNOSIS: SPA shell — JavaScript-rendered content not in HTML")
        print("  → Will use Wayback Machine for all years")
        return "wayback_all"

    print("\n  DIAGNOSIS: Primary blocked or insufficient data → use Wayback fallback")
    return "wayback"


# ── Phase 1B: Scrape all years ────────────────────────────────────────────────

def phase1b_scrape_all(probe_result: str) -> dict[int, dict]:
    print("\n" + "=" * 70)
    print("  Phase 1B: Scrape All 11 Years")
    print("=" * 70)

    results: dict[int, dict] = {}

    for year in TRAINING_YEARS:
        print(f"\n  Year {year}:")
        players = []
        source = "none"

        if probe_result == "primary_works":
            url = f"https://www.nbadraft.net/ranking/bigboard/?year-mock={year}"
            resp = _get(url, delay=REQUEST_DELAY_PRIMARY if year != TRAINING_YEARS[0] else 0.5)
            if resp and resp.status_code == 200:
                players = _parse_nbadraft_page(resp.text)
                source = "nbadraft_net_primary"

        if len(players) < 10:
            if _request_count >= MAX_REQUESTS - 2:
                print(f"    Budget nearly exhausted — skipping Wayback for {year}")
            else:
                players, source = _wayback_fetch_year(year)

        top3 = ", ".join(p["player_name"] for p in players[:3])
        status = "✓" if len(players) >= 60 else ("⚠ sparse" if len(players) >= 10 else "✗ FAILED")
        print(f"    {status} | source={source} | n={len(players)} | top3: {top3}")

        if len(players) < 10:
            print(f"    WARNING: Fewer than 10 players found for {year}")

        results[year] = {
            "players": players,
            "source": source,
            "n": len(players),
        }

    return results


# ── Phase 1C: NBA Draft Network probe ────────────────────────────────────────

def phase1c_nbadraftnetwork() -> dict:
    print("\n" + "=" * 70)
    print("  Phase 1C: NBA Draft Network Probe")
    print("=" * 70)

    if _request_count >= MAX_REQUESTS - 1:
        print("  Budget exhausted — skipping NBA Draft Network")
        return {}

    url = "https://nbadraftnetwork.com/consensus-big-board"
    resp = _get(url, delay=1.0)
    if resp is None or resp.status_code != 200:
        print(f"  NBA Draft Network unavailable (status={getattr(resp,'status_code','N/A')})")
        return {}

    soup = BeautifulSoup(resp.text, "lxml")
    body_text = soup.get_text(strip=True)

    # Check for year selection (historical data indicator)
    year_selectors = soup.find_all(["select", "option", "button"],
                                    string=re.compile(r"201[0-9]|2021", re.I))
    has_historical = len(year_selectors) > 0

    players = _parse_nbadraft_page(resp.text)
    print(f"  Status: {resp.status_code} | players found: {len(players)} | historical available: {has_historical}")

    if not has_historical:
        print("  NBA Draft Network: current year only — historical data not available.")
        print("  Skipping as secondary source.")
        return {}

    print(f"  Historical data available — would need per-year scraping (skipping for budget)")
    return {}


# ── Phase 1E: Validation ──────────────────────────────────────────────────────

def phase1e_validate(results: dict[int, dict]) -> None:
    print("\n" + "=" * 70)
    print("  Phase 1E: Ground Truth Validation")
    print("=" * 70)

    print(f"\n  {'Year':>4}  {'Source':<30}  {'n':>4}  {'Scraped #1':<25}  {'Expected #1':<25}  Status")
    print("  " + "-" * 100)

    all_ok = True
    for year in TRAINING_YEARS:
        info = results.get(year, {})
        players = info.get("players", [])
        source = info.get("source", "none")[:30]
        n = info.get("n", 0)
        top1 = players[0]["player_name"] if players else "—"
        expected = KNOWN_TOP_PICKS[year]

        def _norm(s): return re.sub(r"[^a-z ]", "", s.lower()).strip()
        ok = _norm(top1) == _norm(expected) or _norm(expected) in _norm(top1) or _norm(top1) in _norm(expected)
        status = "✓ validated" if ok else "⚠ MISMATCH"
        if not ok:
            all_ok = False
        print(f"  {year:>4}  {source:<30}  {n:>4}  {top1:<25}  {expected:<25}  {status}")

    print()
    if all_ok:
        print("  All years validated against known #1 picks.")
    else:
        print("  WARNING: Some years failed validation. Review before proceeding to Phase 2.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Historical Consensus Scraper — NBADraft.net")
    print(f"Budget: {MAX_REQUESTS} requests max")
    print()

    probe_result = phase1a_probe()
    results = phase1b_scrape_all(probe_result)
    phase1c_nbadraftnetwork()
    phase1e_validate(results)

    # Build output structure
    output = {
        "fetched_at": datetime.utcnow().isoformat(),
        "total_requests": _request_count,
        "sources": {
            "nbadraft_net": {
                str(year): info["players"]
                for year, info in results.items()
                if info["n"] >= 5
            }
        },
        "metadata": {
            str(year): {"source": info["source"], "n": info["n"]}
            for year, info in results.items()
        },
    }

    CACHE_PATH.parent.mkdir(exist_ok=True)
    with CACHE_PATH.open("w") as f:
        json.dump(output, f, indent=2)

    print(f"\n  Saved to {CACHE_PATH}")
    print(f"  Total requests used: {_request_count}/{MAX_REQUESTS}")

    # Coverage summary
    print("\n  Coverage summary:")
    print(f"  {'Year':>4}  {'Source':<30}  {'n':>4}  Top 3")
    print("  " + "-" * 80)
    for year, info in results.items():
        players = info["players"]
        top3 = ", ".join(p["player_name"] for p in players[:3]) if players else "—"
        src = info["source"][:30]
        print(f"  {year:>4}  {src:<30}  {info['n']:>4}  {top3}")


if __name__ == "__main__":
    main()
