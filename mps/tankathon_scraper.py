"""
mps/tankathon_scraper.py

Phase 3: Scrape Tankathon.com for 2026 draft prospect data.

Fetches:
  - Big board: https://www.tankathon.com/big_board
  - Player pages: https://www.tankathon.com/players/{slug}

Data captured per player:
  NBA Combine: height_in, weight_lbs, wingspan, standing_reach, max_vertical,
               lane_agility, shuttle, sprint_34, hand_length, hand_width
  Per Game:    gp, mp, fg_pct, fg3_pct, ft_pct, reb, ast, blk, stl, tov, pf, pts
  Per 36:      same normalized to 36 min
  Advanced I:  ts_pct, efg_pct, three_par, fta_rate, proj_nba_3p_pct,
               usg_pct, ast_over_usg, ast_over_tov
  Advanced II: per, ows, dws, ws_per_40, ortg, drtg, obpm, dbpm, bpm

Run:
    cd /home/spencer/Workspace/macfax
    backend/.venv/bin/python -m mps.tankathon_scraper

    # Debug a single player page:
    backend/.venv/bin/python -m mps.tankathon_scraper --debug cameron-boozer
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── Paths ──────────────────────────────────────────────────────────────────────

MPS_DIR    = Path(__file__).parent
DATA_DIR   = MPS_DIR / "data"
CACHE_FILE = DATA_DIR / "tankathon_2026.json"
CACHE_TTL  = 24 * 3600  # 24-hour TTL

DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── HTTP ───────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.tankathon.com/",
}

REQUEST_DELAY = 4.0


def _get(url: str) -> requests.Response | None:
    time.sleep(REQUEST_DELAY)
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            return r
        print(f"    [HTTP {r.status_code}] {url}")
        return None
    except Exception as exc:
        print(f"    [HTTP error] {url}: {exc}")
        return None


# ── Slug construction ──────────────────────────────────────────────────────────

# Manual overrides for players whose Wikipedia/name-based slug differs from Tankathon.
SLUG_OVERRIDES: dict[str, str] = {
    "AJ Dybantsa":          "aj-dybantsa",
    "A.J. Dybantsa":        "aj-dybantsa",
    "LaBaron Philon":       "labaron-philon",
    "VJ Edgecombe":         "vj-edgecombe",
    "V.J. Edgecombe":       "vj-edgecombe",
    "Tre Johnson":          "tre-johnson",
    "Ace Bailey":           "ace-bailey",
    "Dylan Harper":         "dylan-harper",
    "Kon Knueppel":         "kon-knueppel",
    "Cameron Boozer":       "cameron-boozer",
}


def _name_to_slug(player_name: str) -> str:
    if player_name in SLUG_OVERRIDES:
        return SLUG_OVERRIDES[player_name]
    slug = player_name.lower()
    slug = slug.replace(".", "").replace("'", "").replace("'", "")
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug


# ── Float helper ───────────────────────────────────────────────────────────────

def _f(val: str | None) -> float | None:
    if val is None or str(val).strip() in ("", "—", "-", "N/A", "n/a"):
        return None
    try:
        return float(str(val).replace("%", "").strip())
    except ValueError:
        return None


# ── Big board scraper ──────────────────────────────────────────────────────────

def scrape_big_board() -> list[dict]:
    """
    Fetch Tankathon big board.

    Returns list of {rank, player_name, slug, position, school, tankathon_rank}.
    """
    print("  [Tankathon] Fetching big board...")
    resp = _get("https://www.tankathon.com/big_board")
    if resp is None:
        return []

    soup    = BeautifulSoup(resp.text, "lxml")
    players: list[dict] = []
    seen_slugs: set[str] = set()

    # Player rows: <a href="/players/slug"> containing name + position + school
    # The anchor text is "Cameron BoozerPF | Duke" — need to split off position/school.
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("/players/"):
            continue
        slug = href.split("/players/")[-1].strip("/")
        # Filter non-player slugs (e.g. "compare")
        if not slug or "/" in slug or slug in ("compare",):
            continue
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Clean name: strip "PG | School" suffix
        raw_name = a.get_text(strip=True)
        # Split on common position abbreviations followed by " | "
        name = re.split(r"\s*(?:PG|SG|SF|PF|C|G|F|G/F|F/C|SG/PG|PG/SG|SF/PF|PF/SF|SG/SF|SF/SG|PG/SF|G/PF)\s*\|", raw_name)[0].strip()
        if not name:
            name = raw_name

        # Try to extract rank from a nearby element
        rank = None
        parent = a.parent
        for _ in range(5):
            if parent is None:
                break
            rank_text = parent.get_text(strip=True)
            # Look for a leading number
            m = re.match(r"^(\d{1,3})\b", rank_text)
            if m:
                try:
                    rank = int(m.group(1))
                    break
                except ValueError:
                    pass
            parent = parent.parent

        players.append({
            "player_name":    name,
            "slug":           slug,
            "tankathon_rank": rank,
        })

    print(f"  [Tankathon] Found {len(players)} players on big board")
    # Backfill rank using list position for players where rank extraction failed
    for i, p in enumerate(players, start=1):
        if p["tankathon_rank"] is None:
            p["tankathon_rank"] = i
    return players


# ── Inches conversion ─────────────────────────────────────────────────────────

def _inches(val: str | None) -> float | None:
    """Convert "6'9.5\"" or "9'0\"" or "7'1.5\"" to decimal inches."""
    if val is None:
        return None
    val = val.strip().rstrip('"').rstrip("'")
    # Feet-inches like "6'9.5" or "9'0"
    m = re.match(r"^(\d+)['\u2019](\d+(?:\.\d+)?)", val)
    if m:
        return float(m.group(1)) * 12 + float(m.group(2))
    # Plain decimal like "35.0" (inches)
    m = re.match(r"^([\d.]+)$", val)
    if m:
        return float(m.group(1))
    return None


# ── Player page parser ─────────────────────────────────────────────────────────

def _stat_row_to_dict(container_divs) -> dict[str, str]:
    """
    Parse a list of .stat-container divs into {label_lower: value}.
    Label uses the last <span> in .stat-label (the abbreviation, not full hover text).
    """
    out: dict[str, str] = {}
    for div in container_divs:
        label_el = div.find(class_="stat-label")
        value_el = div.find(class_="stat-data")
        if not (label_el and value_el):
            continue
        # Use last span = abbreviation (e.g. "TS%" not "True Shooting %TS%")
        spans = label_el.find_all("span")
        if spans:
            label = spans[-1].get_text(strip=True).lower()
        else:
            label = label_el.get_text(strip=True).lower()
        value = value_el.get_text(strip=True)
        if label:
            out[label] = value
    return out


def _parse_stat_sections(soup: BeautifulSoup, debug: bool = False) -> dict:
    """
    Parse all stat sections from a Tankathon player page.

    Layout:
      .stats-header  → section name ("PER GAME AVERAGES", "ADVANCED STATS I", etc.)
      .stats         → immediately follows, contains .stat-row > .stat-container divs
      .stats.combine → NBA combine, contains .combine-stat divs
      .measurable    → height/weight/draft-age in player bio
    """
    result: dict = {}

    # ── Collect all sections by header label ──────────────────────────────────
    sections: dict[str, dict[str, str]] = {}
    for hdr in soup.find_all(class_="stats-header"):
        section_name = hdr.get_text(strip=True).lower()
        stats_div    = hdr.find_next_sibling(class_="stats")
        if stats_div is None:
            continue
        containers = stats_div.find_all(class_="stat-container")
        sections[section_name] = _stat_row_to_dict(containers)

    if debug:
        for k, v in sections.items():
            print(f"  [debug] section '{k}': {v}")

    # ── Map sections to output ────────────────────────────────────────────────
    def _find_section(*hints: str) -> dict[str, str]:
        """Return first section whose name contains any of the hint strings."""
        for hint in hints:
            for name, data in sections.items():
                if hint in name:
                    return data
        return {}

    pg  = _find_section("per game")
    p36 = _find_section("per 36")
    adv1 = _find_section("advanced stats i", "advanced i")
    adv2 = _find_section("advanced stats ii", "advanced ii")

    # Fallback: combine advanced I + II into one lookup
    def _adv(key: str) -> float | None:
        return _f(adv1.get(key) or adv2.get(key))

    result["per_game"] = {
        "gp":      _f(pg.get("g") or pg.get("gp")),
        "mp":      _f(pg.get("mp") or pg.get("min")),
        "pts":     _f(pg.get("pts")),
        "reb":     _f(pg.get("reb") or pg.get("trb")),
        "ast":     _f(pg.get("ast")),
        "blk":     _f(pg.get("blk")),
        "stl":     _f(pg.get("stl")),
        "tov":     _f(pg.get("to") or pg.get("tov")),
        "pf":      _f(pg.get("pf")),
        "fg_pct":  _f(pg.get("fg%")),
        "fg3_pct": _f(pg.get("3p%")),
        "ft_pct":  _f(pg.get("ft%")),
    }

    result["per_36"] = {
        "pts":     _f(p36.get("pts")),
        "reb":     _f(p36.get("reb") or p36.get("trb")),
        "ast":     _f(p36.get("ast")),
        "blk":     _f(p36.get("blk")),
        "stl":     _f(p36.get("stl")),
        "tov":     _f(p36.get("to") or p36.get("tov")),
        "fg_pct":  _f(p36.get("fg%")),
        "fg3_pct": _f(p36.get("3p%")),
    }

    result["advanced"] = {
        "ts_pct":          _adv("ts%"),
        "efg_pct":         _adv("efg%"),
        "three_par":       _adv("3par"),
        "fta_rate":        _adv("ftar"),
        "proj_nba_3p_pct": _adv("nba 3p%") or _adv("proj nba 3p%"),
        "usg_pct":         _adv("usg%"),
        "ast_over_usg":    _adv("ast/usg"),
        "ast_over_tov":    _adv("ast/to") or _adv("ast/tov"),
        "per":             _adv("per"),
        "ows":             _adv("ows") or _f(adv2.get("ows/40")),
        "dws":             _adv("dws") or _f(adv2.get("dws/40")),
        "ws_per_40":       _adv("ws/40"),
        "ortg":            _adv("ortg"),
        "drtg":            _adv("drtg"),
        "obpm":            _adv("obpm"),
        "dbpm":            _adv("dbpm"),
        "bpm":             _adv("bpm"),
    }

    # ── NBA Combine ───────────────────────────────────────────────────────────
    combine_div = soup.find("div", class_=lambda c: c and "stats" in c and "combine" in c)
    combine_row: dict[str, str] = {}
    if combine_div:
        for stat in combine_div.find_all(class_="combine-stat"):
            label_el = stat.find(class_="combine-stat-label")
            value_el = stat.find(class_="combine-stat-value")
            if label_el and value_el:
                # Label has hidden desktop spans; get all text
                label = label_el.get_text(strip=True).lower()
                combine_row[label] = value_el.get_text(strip=True)

    if debug:
        print(f"  [debug] combine_row: {combine_row}")

    result["combine"] = {
        "max_vertical_in":   _inches(combine_row.get("maxvertical")),
        "lane_agility_s":    _f(combine_row.get("laneagility")),
        "shuttle_s":         _f(combine_row.get("shuttle")),
        "sprint_34_s":       _f(combine_row.get("3/4sprint")),
        "hand_length_in":    _inches(combine_row.get("handlenghtl") or combine_row.get("handlengthh")
                                     or combine_row.get("handlengthl")),
        "hand_width_in":     _inches(combine_row.get("handwidthw")),
        "standing_reach_in": _inches(combine_row.get("standingreach")),
        "wingspan_in":       _inches(combine_row.get("wingspan")),
    }

    # ── Bio measurables (height, weight, draft age) ───────────────────────────
    result["bio"] = {
        "height_in":  None,
        "weight_lbs": None,
        "draft_age":  None,
        "position":   None,
        "school":     None,
    }

    for m_div in soup.find_all(class_="measurable"):
        label_el = m_div.find(class_="label")
        value_el = m_div.find(class_="value")
        if not (label_el and value_el):
            continue
        label = label_el.get_text(strip=True).lower()
        value = value_el.get_text(strip=True)

        if "height" in label:
            result["bio"]["height_in"] = _inches(value)
        elif "weight" in label:
            m = re.search(r"(\d+)", value)
            if m:
                result["bio"]["weight_lbs"] = float(m.group(1))
        elif "age" in label:
            m = re.search(r"([\d.]+)", value)
            if m:
                result["bio"]["draft_age"] = float(m.group(1))

    return result


def scrape_player(slug: str, debug: bool = False) -> dict | None:
    """Fetch and parse a Tankathon player page. Returns structured stat dict."""
    url  = f"https://www.tankathon.com/players/{slug}"
    resp = _get(url)
    if resp is None:
        return None
    if resp.status_code == 404 or "404" in resp.url:
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    if debug:
        print(f"\n  [debug] URL: {url}")
        print(f"  [debug] Page title: {soup.title.get_text() if soup.title else 'N/A'}")

    stats = _parse_stat_sections(soup, debug=debug)
    stats["url"]       = url
    stats["slug"]      = slug
    stats["scraped_at"] = datetime.now(tz=timezone.utc).isoformat()
    return stats


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _load_cache() -> dict | None:
    if not CACHE_FILE.exists():
        return None
    try:
        with CACHE_FILE.open() as f:
            obj = json.load(f)
        fetched_at = datetime.fromisoformat(obj.get("fetched_at", ""))
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(tz=timezone.utc) - fetched_at).total_seconds()
        if age > CACHE_TTL:
            print(f"  [cache] stale ({age/3600:.1f}h) — re-fetching")
            return None
        n = len(obj.get("players", {}))
        print(f"  [cache] hit — {n} players (age {age/3600:.1f}h)")
        return obj
    except Exception as exc:
        print(f"  [cache] read error: {exc}")
        return None


def _write_cache(players: dict, board: list[dict]) -> None:
    obj = {
        "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
        "big_board":  board,
        "players":    players,
    }
    with CACHE_FILE.open("w") as f:
        json.dump(obj, f, indent=2)
    print(f"  [cache] written → {CACHE_FILE} ({len(players)} players)")


# ── Main ───────────────────────────────────────────────────────────────────────

def main(debug_slug: str | None = None) -> dict:
    """
    Scrape full Tankathon 2026 dataset.

    Returns {player_slug: stat_dict}.
    """
    print("=" * 66)
    print("  TANKATHON SCRAPER — 2026 Draft Prospects")
    print("=" * 66)

    # Debug mode: scrape single player, skip cache
    if debug_slug:
        print(f"\n  [debug] Scraping single player: {debug_slug}")
        result = scrape_player(debug_slug, debug=True)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print(f"  [debug] Failed to scrape {debug_slug}")
        return {debug_slug: result} if result else {}

    # Check cache
    cached = _load_cache()
    if cached is not None:
        return cached.get("players", {})

    # 1. Fetch big board
    board = scrape_big_board()
    if not board:
        print("  ERROR: Could not fetch big board. Check connection.")
        return {}

    # 2. Scrape each player
    players: dict[str, dict] = {}
    total = len(board)
    errors = 0

    for i, entry in enumerate(board):
        slug = entry["slug"]
        name = entry["player_name"]
        rank = entry.get("tankathon_rank", "NR")
        print(f"  [{i+1}/{total}] {name} (rank {rank}) — {slug}")

        try:
            data = scrape_player(slug)
            if data:
                data["player_name"]    = name
                data["tankathon_rank"] = rank
                players[slug]          = data
            else:
                print(f"    → No data returned")
                errors += 1
        except Exception as exc:
            print(f"    ERROR: {exc}")
            errors += 1

    print(f"\n  Scraped {len(players)}/{total} players  ({errors} errors)")
    _write_cache(players, board)
    return players


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tankathon 2026 scraper")
    parser.add_argument("--debug", metavar="SLUG", help="Debug single player slug")
    args = parser.parse_args()
    main(debug_slug=args.debug)
