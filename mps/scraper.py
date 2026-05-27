"""
mps/scraper.py

Builds the MPS backtest dataset by scraping:
  1. BBRef NBA draft pages (2010-2023) — draftee roster + BBRef/CBB URLs
  2. Sports-Reference CBB player pages — college advanced stats
  3. BBRef player pages — NBA career VORP/WS/BPM (years 2-5)
  4. Bart Torvik — program AdjEM per season (free KenPom equivalent)

Run:
    cd /home/spencer/Workspace/macfax
    backend/.venv/bin/python -m mps.scraper

Output:
    mps/data/torvik_{year}.json      — Torvik AdjEM cache per season
    mps/data/draft_{year}.csv        — per-year draftee rows (intermediate)
    mps/data/mps_dataset_raw.csv     — final merged dataset (~500-700 rows)
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup, Comment
from rapidfuzz import fuzz, process as rfprocess

# ── Constants ─────────────────────────────────────────────────────────────────

MPS_DIR       = Path(__file__).parent
DATA_DIR      = MPS_DIR / "data"
REQUEST_DELAY = 4.0          # seconds — matches nba_metrics_pipeline.py
FUZZY_CUTOFF  = 82           # rapidfuzz WRatio threshold for school name matching
DRAFT_YEARS   = range(2010, 2024)   # 2010 through 2023 inclusive

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Manual school name aliases: (BBRef college name) → (Torvik canonical name)
# Populated as mismatches are discovered during runs.
SCHOOL_ALIASES: dict[str, str] = {
    "UConn":                     "Connecticut",
    "UNC":                       "North Carolina",
    "USC":                       "Southern California",
    "UNLV":                      "Nevada-Las Vegas",
    "LSU":                       "Louisiana State",
    "TCU":                       "Texas Christian",
    "SMU":                       "Southern Methodist",
    "VCU":                       "Virginia Commonwealth",
    "UAB":                       "Alabama-Birmingham",
    "UTEP":                      "Texas-El Paso",
    "UCF":                       "Central Florida",
    "UCSB":                      "Santa Barbara",
    "FIU":                       "Florida International",
    "FAU":                       "Florida Atlantic",
    "UT Martin":                 "Tennessee-Martin",
    "SIU":                       "Southern Illinois",
    "NIU":                       "Northern Illinois",
    "EIU":                       "Eastern Illinois",
    "WIU":                       "Western Illinois",
    "Miami (FL)":                "Miami FL",
    "Miami (OH)":                "Miami OH",
    "Louisiana":                 "Louisiana Lafayette",
    "UL Monroe":                 "Louisiana Monroe",
    "Texas A&M-CC":              "Texas A&M Corpus Chris",
    "Loyola (IL)":               "Loyola Chicago",
    "Loyola (MD)":               "Loyola Maryland",
    "IUPUI":                     "IUPUI",
    "Saint Mary's (CA)":         "Saint Mary's",
    "St. John's (NY)":           "St. John's",
    "Hawai'i":                   "Hawaii",
    "BYU":                       "Brigham Young",
    "ETSU":                      "East Tennessee State",
    "UMBC":                      "Maryland-Baltimore County",
    "SFA":                       "Stephen F. Austin",
    "UIW":                       "Incarnate Word",
}

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _get(url: str, *, delay: bool = True, retries: int = 2) -> requests.Response:
    """GET with user-agent, optional delay, and retry on connection errors."""
    for attempt in range(retries + 1):
        if delay or attempt > 0:
            # Extra backoff on retry
            time.sleep(REQUEST_DELAY * (attempt + 1))
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.encoding = "utf-8"
            return resp
        except requests.exceptions.ConnectionError as e:
            if attempt < retries:
                print(f"    [HTTP] Connection error (attempt {attempt+1}/{retries+1}): {e}. Retrying...")
            else:
                raise


# ── Program quality (SRS) from sports-reference.com/cbb ──────────────────────

def scrape_program_srs(year: int) -> dict[str, float]:
    """
    Fetch sports-reference CBB team SRS (Simple Rating System) for a season.

    SRS is a reliable proxy for KenPom/Torvik AdjEM — both measure adjusted
    margin of victory against opponent quality. Correlation r > 0.95.

    `year` = end-year of season (e.g., 2015 = 2014-15 season).
    Returns {team_name: srs}.
    Caches to mps/data/cbb_srs_{year}.json.
    """
    cache_path = DATA_DIR / f"cbb_srs_{year}.json"
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)

    url = f"https://www.sports-reference.com/cbb/seasons/men/{year}-advanced-school-stats.html"
    print(f"  [SRS] Fetching program SRS for {year}: {url}")
    try:
        resp = _get(url)
        if resp.status_code != 200:
            print(f"  [SRS] HTTP {resp.status_code} for {year}")
            return {}

        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table", {"id": "adv_school_stats"})
        if table is None:
            table = _find_table_in_comments(soup, "adv_school_stats")
        if table is None:
            print(f"  [SRS] Table not found for {year}")
            return {}

        result: dict[str, float] = {}
        for tr in table.find_all("tr"):
            cells = {td.get("data-stat", ""): td.get_text(strip=True)
                     for td in tr.find_all(["td", "th"])}
            team_raw = cells.get("school_name", "").strip()
            srs_str = cells.get("srs", "")
            if not team_raw or team_raw in ("School", ""):
                continue
            # Strip "NCAA" suffix that sports-reference appends to tournament teams
            # e.g., "KentuckyNCAA" → "Kentucky"
            team = re.sub(r"NCAA$", "", team_raw).strip()
            try:
                srs_val = float(srs_str)
                # Keep the higher SRS value if both regular and NCAA rows exist
                if team not in result or srs_val > result[team]:
                    result[team] = srs_val
            except ValueError:
                pass

        if result:
            with open(cache_path, "w") as f:
                json.dump(result, f, indent=2)
            print(f"  [SRS] Cached {len(result)} teams for {year}")
        else:
            print(f"  [SRS] No data parsed for {year}")
    except Exception as e:
        print(f"  [SRS] Failed for {year}: {e}")
        result = {}
    return result


def _resolve_srs(school_name: str, srs_data: dict[str, float]) -> float | None:
    """
    Fuzzy-match a school name to sports-reference CBB team name.
    Returns SRS float or None if no match above threshold.
    """
    if not school_name or not srs_data:
        return None

    # Apply manual alias first
    resolved = SCHOOL_ALIASES.get(school_name, school_name)

    # Exact match
    if resolved in srs_data:
        return srs_data[resolved]

    # Fuzzy match
    match = rfprocess.extractOne(resolved, srs_data.keys(), scorer=fuzz.WRatio)
    if match and match[1] >= FUZZY_CUTOFF:
        return srs_data[match[0]]

    return None


# ── Draft class scraper ───────────────────────────────────────────────────────

def scrape_draft_class(year: int) -> list[dict]:
    """
    Scrape BBRef NBA draft page for a given year.

    Returns list of dicts with:
      player_name, bbref_url, cbb_url, college, pick, round, draft_age, position
    Only includes players with a listed college (filters out international/G-League).
    """
    url = f"https://www.basketball-reference.com/draft/NBA_{year}.html"
    print(f"  [Draft] Scraping {year} class: {url}")
    resp = _get(url)
    if resp.status_code != 200:
        print(f"  [Draft] HTTP {resp.status_code} for {year}, skipping")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", {"id": "stats"})
    if table is None:
        print(f"  [Draft] No #stats table found for {year}")
        return []

    players = []
    tbody = table.find("tbody")
    if tbody is None:
        return []

    for tr in tbody.find_all("tr"):
        # Skip header rows injected mid-table
        if tr.get("class") and "thead" in tr.get("class"):
            continue

        cells = tr.find_all(["td", "th"])
        if len(cells) < 8:
            continue

        def cell_text(td) -> str:
            return td.get_text(strip=True)

        def cell_href(td) -> str | None:
            a = td.find("a")
            return a["href"] if a and a.get("href") else None

        # BBRef draft table column order (2010+ consistent):
        # Rk | Tm | Rd | Pk | Player | Nationality | College/HS | Yrs | G | MP | ...
        # But Rd/Pk/Player positions can shift — find by header or parse carefully.
        # Use data-stat attributes for reliability.

        row_data: dict[str, str | None] = {}
        for td in cells:
            stat = td.get("data-stat", "")
            row_data[stat] = cell_text(td)
            if stat in ("player", "college_name"):
                row_data[f"{stat}_href"] = cell_href(td)

        player_name = row_data.get("player", "").strip()
        if not player_name or player_name in ("Player", "Rk"):
            continue  # header row or empty

        college = row_data.get("college_name", "").strip()
        if not college:
            continue  # no college → international / G-League → skip

        # Draft position
        pick_str = row_data.get("pick_overall", row_data.get("pk", ""))
        try:
            pick = int(pick_str) if pick_str else None
        except ValueError:
            pick = None

        # Derive round from pick number (BBRef draft page doesn't expose round as data-stat)
        if pick is not None:
            draft_round = 1 if pick <= 30 else 2
        else:
            draft_round = None

        # Age and position: not available in draft table — will be extracted from player pages
        draft_age = None
        position = ""

        # BBRef player URL (reliable — draft page always has this link)
        bbref_url = row_data.get("player_href")   # e.g. /players/j/jamesle01.html

        # cbb_url: NOT reliable from draft page (links to school, not player).
        # Will be extracted from BBRef player page in scrape_nba_career().
        # Set to None here; populated later in build_dataset().
        cbb_url = None

        players.append({
            "player_name":  player_name,
            "draft_year":   year,
            "draft_pick":   pick,
            "draft_round":  draft_round,
            "draft_age":    draft_age,
            "position":     position,
            "college":      college,
            "bbref_url":    bbref_url,
            "cbb_url":      cbb_url,
        })

    print(f"  [Draft] {year}: {len(players)} college players found")
    return players


def _get_position_group(position: str) -> str:
    """Map raw position string → 'G', 'F', or 'BIG'.
    Handles both abbreviations (PG, C) and full names (Point Guard, Center).
    """
    pos = position.upper().strip()
    # Full names first
    if any(x in pos for x in ("POINT GUARD", "SHOOTING GUARD", "POINT-GUARD")):
        return "G"
    if any(x in pos for x in ("POWER FORWARD", "CENTER", "CENTRE")):
        return "BIG"
    if "SMALL FORWARD" in pos or "SMALL-FORWARD" in pos:
        return "F"
    # Abbreviations
    if pos in ("PG", "SG", "G", "PG-SG", "SG-PG", "G-F"):
        return "G"
    if pos in ("PF", "C", "C-PF", "PF-C", "F-C", "C-F"):
        return "BIG"
    if pos in ("SF", "F", "SF-SG", "SG-SF", "SF-PF", "PF-SF"):
        return "F"
    # Last resort: keyword in string
    if "GUARD" in pos:
        return "G"
    if "CENTER" in pos or "CENTRE" in pos:
        return "BIG"
    return "F"  # default: forward


# ── College stats scraper ─────────────────────────────────────────────────────

def scrape_college_stats(cbb_url: str) -> dict | None:
    """
    Scrape sports-reference.com/cbb player page for advanced college stats.

    Uses the player's FINAL college season (most NBA-relevant).
    Returns dict of college stat features, or None on failure.
    """
    print(f"    [CBB] {cbb_url}")
    resp = _get(cbb_url)
    if resp.status_code == 404:
        print(f"    [CBB] 404 — skipping")
        return None
    if resp.status_code != 200:
        print(f"    [CBB] HTTP {resp.status_code} — skipping")
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # ── Advanced stats table ──────────────────────────────────────────────────
    # Sports-reference wraps some tables in HTML comments for lazy loading.
    # Must parse comment blocks to find the actual table HTML.
    adv_table = soup.find("table", {"id": "players_advanced"})
    if adv_table is None:
        adv_table = _find_table_in_comments(soup, "players_advanced")
    if adv_table is None:
        print(f"    [CBB] No advanced table found")
        return None

    adv_rows = _parse_stats_table(adv_table)
    if not adv_rows:
        return None

    # Get final season row — keep only rows with a valid "YYYY-YY" season year.
    # Sports-reference appends per-school career summaries like "St. John's (NY) (3 Yrs)"
    # after the Career row; simple exclusion lists miss them.  Regex is robust.
    _SEASON_RE = re.compile(r"^\d{4}-\d{2,4}$")
    season_rows = [r for r in adv_rows
                   if _SEASON_RE.match(r.get("year_id", r.get("season", "")).strip())]
    if not season_rows:
        season_rows = adv_rows  # fallback: use whatever is there

    final_row = season_rows[-1]

    # ── Per-game table for FT% and GP/MP ─────────────────────────────────────
    pg_table = soup.find("table", {"id": "players_per_game"})
    if pg_table is None:
        pg_table = _find_table_in_comments(soup, "players_per_game")
    pg_rows = _parse_stats_table(pg_table) if pg_table else []
    # Same regex filter for per_game table — strips per-school career summaries.
    pg_season_rows = [r for r in pg_rows
                      if _SEASON_RE.match(r.get("year_id", r.get("season", "")).strip())]
    pg_final = pg_season_rows[-1] if pg_season_rows else {}

    def _f(d: dict, *keys) -> float | None:
        """Extract first matching key as float."""
        for k in keys:
            v = d.get(k)
            if v not in (None, "", "—"):
                try:
                    return float(str(v).replace("%", "").strip())
                except ValueError:
                    continue
        return None

    # School name — CBB uses data-stat="team_name_abbr" (full school name despite field name)
    school = str(final_row.get("team_name_abbr", final_row.get("school_name", final_row.get("team", "")))).strip()

    # Season year — extract end-year from "2013-14" → 2014
    # CBB uses data-stat="year_id" for season column
    season_str = str(final_row.get("year_id", final_row.get("season", ""))).strip()
    college_season_year = None
    m = re.search(r"(\d{4})-(\d{2,4})", season_str)
    if m:
        year_part = m.group(2)
        if len(year_part) == 2:
            college_season_year = int(m.group(1)[:2] + year_part)
        else:
            college_season_year = int(year_part)

    return {
        "bpm_college":       _f(final_row, "bpm"),
        "stl_pct":           _f(final_row, "stl_pct"),
        "orb_pct":           _f(final_row, "orb_pct"),
        "blk_pct":           _f(final_row, "blk_pct"),
        "ast_pct":           _f(final_row, "ast_pct"),
        "ts_pct":            _f(final_row, "ts_pct"),
        "ft_pct":            _f(pg_final, "ft_pct") or _f(final_row, "ft_pct"),
        "three_par":         _f(final_row, "fg3a_per_fga_pct", "3par"),
        "usg_pct":           _f(final_row, "usg_pct"),
        "dws":               _f(final_row, "dws"),
        "games_played":      _f(pg_final, "g", "games"),
        "school_name":       school,
        "college_season_year": college_season_year,
    }


def _find_table_in_comments(soup: BeautifulSoup, table_id: str):
    """
    Sports-reference lazy-loads some tables by wrapping them in HTML comments.
    This function extracts and parses those comment blocks to find a table by id.
    """
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if table_id in comment:
            comment_soup = BeautifulSoup(comment, "lxml")
            table = comment_soup.find("table", {"id": table_id})
            if table:
                return table
    return None


def _parse_stats_table(table) -> list[dict]:
    """Parse a BeautifulSoup table element into list of dicts using data-stat attrs."""
    if table is None:
        return []
    rows = []
    for tr in table.find_all("tr"):
        if tr.get("class") and "thead" in tr.get("class"):
            continue
        row: dict[str, str] = {}
        for td in tr.find_all(["td", "th"]):
            stat = td.get("data-stat", "")
            if stat:
                row[stat] = td.get_text(strip=True)
        if row:
            rows.append(row)
    return rows


# ── NBA career stats scraper ──────────────────────────────────────────────────

def scrape_nba_career(bbref_url: str, draft_year: int) -> dict:
    """
    Scrape BBRef player page for NBA career advanced stats AND the CBB URL.

    Computes average VORP, WS/48, BPM for NBA years 2-5 post-draft.
    Year 1 = first NBA season (draft_year+1), Year 2 = draft_year+2, etc.
    Also extracts link to sports-reference.com/cbb player page if present.
    """
    if not bbref_url:
        return _empty_nba_career()

    url = f"https://www.basketball-reference.com{bbref_url}"
    print(f"    [NBA career] {url}")
    resp = _get(url)
    if resp.status_code != 200:
        print(f"    [NBA career] HTTP {resp.status_code}")
        return _empty_nba_career()

    soup = BeautifulSoup(resp.text, "lxml")

    # ── Extract CBB URL from player page ─────────────────────────────────────
    # BBRef player pages link to sports-reference.com/cbb/players/ in the
    # "College Statistics" section or in the info box.
    cbb_url: str | None = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "sports-reference.com/cbb/players/" in href:
            cbb_url = href
            break

    # ── Extract age at draft and position from player bio ─────────────────────
    # BBRef player profile div has birth date and position info.
    draft_age: float | None = None
    position: str = ""

    info_div = soup.find("div", {"id": "info"})
    if info_div:
        # Position: look for "Position:" label in any paragraph
        for p_tag in info_div.find_all("p"):
            text = p_tag.get_text(" ", strip=True)
            if "Position" in text:
                # Get everything after "Position:" up to next label or end
                pos_match = re.search(r"Position[s]?:\s*([^\n\r▪•]+)", text)
                if pos_match:
                    position = pos_match.group(1).split("▪")[0].split("•")[0].strip()
                    # BBRef sometimes shows "Point Guard and Shooting Guard" — take first
                    position = position.split(" and ")[0].strip()
                    break

        # Draft age: BBRef stores birth date in <span id="necro-birth" data-birth="YYYY-MM-DD">
        from datetime import datetime
        birth_span = soup.find("span", {"id": "necro-birth"})
        if birth_span:
            birth_str = birth_span.get("data-birth", "").strip()
            try:
                # data-birth attribute is always ISO format: "1995-11-15"
                birth_date = datetime.strptime(birth_str, "%Y-%m-%d")
                # NBA draft is typically late June; use June 25 as approximate date
                draft_date = datetime(draft_year, 6, 25)
                draft_age = round((draft_date - birth_date).days / 365.25, 1)
            except ValueError:
                pass

    # Advanced stats table
    adv_table = soup.find("table", {"id": "advanced"})
    if adv_table is None:
        result = _empty_nba_career()
        result["cbb_url"] = cbb_url
        return result

    rows = _parse_stats_table(adv_table)

    # BBRef uses data-stat="comp_name_abbr" for league (NBA/NCAA/etc.)
    # and data-stat="team_name_abbr" for team, "year_id" for season.
    # Filter to NBA seasons only; skip TOT (multi-team total) rows.
    nba_seasons: list[dict] = []
    for row in rows:
        lg = row.get("comp_name_abbr", row.get("lg", row.get("league", ""))).strip().upper()
        # Accept rows where league is NBA, or is blank (some BBRef formats omit league)
        # but skip rows that are clearly not NBA
        if lg and lg not in ("NBA",):
            continue
        season_str = row.get("year_id", row.get("season", "")).strip()
        if not season_str or season_str in ("Season", ""):
            continue
        # Only include rows that look like a season (have year pattern)
        if not re.search(r"\d{4}", season_str):
            continue
        tm = row.get("team_name_abbr", row.get("team_id", row.get("tm", ""))).strip().upper()
        if tm == "TOT":
            continue  # skip total rows; individual team rows follow
        nba_seasons.append({**row, "_season_str": season_str})

    # Deduplicate by season: if a season appears multiple times (multi-team), keep first.
    seen_seasons: set[str] = set()
    deduped: list[dict] = []
    for row in nba_seasons:
        s = row["_season_str"]
        if s not in seen_seasons:
            seen_seasons.add(s)
            deduped.append(row)

    # Map season string → NBA year number relative to draft
    # draft_year=2015, first NBA season = 2015-16, start_year=2015 → year 1
    def _season_to_nba_year(season_str: str) -> int | None:
        m = re.search(r"(\d{4})-(\d{2,4})", season_str)
        if not m:
            return None
        start_year = int(m.group(1))
        return start_year - draft_year + 1  # year 1 = draft_year season

    # Collect years 2-5
    vorp_vals, ws48_vals, bpm_vals = [], [], []
    for row in deduped:
        nba_yr = _season_to_nba_year(row["_season_str"])
        if nba_yr is None or nba_yr < 2 or nba_yr > 5:
            continue
        try:
            vorp = float(row.get("vorp", ""))
            vorp_vals.append(vorp)
        except (ValueError, TypeError):
            pass
        try:
            ws48 = float(row.get("ws_per_48", ""))
            ws48_vals.append(ws48)
        except (ValueError, TypeError):
            pass
        try:
            bpm = float(row.get("bpm", ""))
            bpm_vals.append(bpm)
        except (ValueError, TypeError):
            pass

    return {
        "vorp_yr2_5_avg": (sum(vorp_vals) / len(vorp_vals)) if vorp_vals else 0.0,
        "ws48_yr2_5_avg": (sum(ws48_vals) / len(ws48_vals)) if ws48_vals else 0.0,
        "bpm_yr2_5_avg":  (sum(bpm_vals) / len(bpm_vals)) if bpm_vals else 0.0,
        "years_available": max(len(vorp_vals), len(ws48_vals), len(bpm_vals)),
        "cbb_url":         cbb_url,
        "draft_age":       draft_age,
        "position":        position,
    }


def _empty_nba_career() -> dict:
    return {
        "vorp_yr2_5_avg": 0.0,
        "ws48_yr2_5_avg": 0.0,
        "bpm_yr2_5_avg":  0.0,
        "years_available": 0,
        "cbb_url":         None,
        "draft_age":       None,
        "position":        "",
    }


# ── Main dataset builder ──────────────────────────────────────────────────────

def build_dataset(years: range = DRAFT_YEARS, force_refresh: bool = False) -> pd.DataFrame:
    """
    Orchestrate full dataset build for all draft years.

    Caches per-year CSVs to mps/data/draft_{year}.csv.
    Final output: mps/data/mps_dataset_raw.csv
    """
    all_rows: list[dict] = []

    for year in years:
        year_cache = DATA_DIR / f"draft_{year}.csv"

        if year_cache.exists() and not force_refresh:
            print(f"\n[{year}] Loading cached: {year_cache}")
            df_cached = pd.read_csv(year_cache)
            all_rows.extend(df_cached.to_dict("records"))
            continue

        print(f"\n{'='*60}")
        print(f"[{year}] Building draft class...")

        # Step 1: Draft class roster
        draftees = scrape_draft_class(year)
        if not draftees:
            print(f"[{year}] No draftees found — skipping")
            continue

        # Step 2: Program SRS for this college season
        # Players drafted in `year` played final college season ending in `year`
        # e.g., 2015 draftees → 2014-15 season → sports-reference year = 2015
        torvik = scrape_program_srs(year)

        year_rows: list[dict] = []
        for p in draftees:
            print(f"\n  Player: {p['player_name']} (pick {p['draft_pick']})")
            row = {**p, "position_group": _get_position_group(p.get("position", ""))}

            # Step 4+5: NBA career outcomes (also extracts cbb_url, age, position from BBRef page)
            if p.get("bbref_url"):
                try:
                    nba = scrape_nba_career(p["bbref_url"], year)
                except Exception as e:
                    print(f"    [NBA career] Error: {e}")
                    nba = _empty_nba_career()
                # Unpack extras
                cbb_url_found = nba.pop("cbb_url", None)
                age_found     = nba.pop("draft_age", None)
                pos_found     = nba.pop("position", "")
                row.update(nba)
                row["cbb_url"]   = cbb_url_found
                row["draft_age"] = age_found
                if pos_found:
                    row["position"]       = pos_found  # override empty placeholder
                    row["position_group"] = _get_position_group(pos_found)  # recompute
            else:
                nba_empty = _empty_nba_career()
                for k in ("cbb_url", "draft_age", "position"):
                    nba_empty.pop(k, None)
                row.update(nba_empty)

            # Step 3: College advanced stats — use cbb_url from BBRef player page
            cbb_url = row.get("cbb_url")
            if cbb_url:
                try:
                    college_stats = scrape_college_stats(cbb_url)
                except Exception as e:
                    print(f"    [CBB] Error scraping {cbb_url}: {e}")
                    college_stats = None
                if college_stats:
                    row.update(college_stats)
                    # Step 4: AdjEM lookup using school from CBB page
                    school = college_stats.get("school_name", p.get("college", ""))
                    row["program_srs"] = _resolve_srs(school, torvik)
                else:
                    row["program_srs"] = _resolve_srs(p.get("college", ""), torvik)
            else:
                print(f"    [CBB] No CBB URL found — skipping college stats")
                row["program_srs"] = _resolve_srs(p.get("college", ""), torvik)

            year_rows.append(row)

        # Save per-year cache
        if year_rows:
            df_year = pd.DataFrame(year_rows)
            df_year.to_csv(year_cache, index=False)
            print(f"\n[{year}] Saved {len(year_rows)} rows → {year_cache}")
            all_rows.extend(year_rows)

    if not all_rows:
        print("\nNo data collected.")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)

    # ── Reorder columns for readability ──────────────────────────────────────
    id_cols    = ["player_name", "draft_year", "draft_pick", "draft_round",
                  "draft_age", "college", "position", "position_group"]
    stat_cols  = ["bpm_college", "stl_pct", "orb_pct", "blk_pct", "ast_pct",
                  "ts_pct", "ft_pct", "three_par", "usg_pct", "dws"]
    ctx_cols   = ["program_srs", "college_season_year"]
    nba_cols   = ["vorp_yr2_5_avg", "ws48_yr2_5_avg", "bpm_yr2_5_avg", "years_available"]
    meta_cols  = ["bbref_url", "cbb_url"]
    ordered    = [c for c in id_cols + stat_cols + ctx_cols + nba_cols + meta_cols
                  if c in df.columns]
    leftover   = [c for c in df.columns if c not in ordered]
    df = df[ordered + leftover]

    # ── Save final dataset ────────────────────────────────────────────────────
    output_path = DATA_DIR / "mps_dataset_raw.csv"
    df.to_csv(output_path, index=False)
    print(f"\n{'='*60}")
    print(f"Dataset saved: {output_path}")
    print(f"Total rows: {len(df)}")

    # ── Sanity checks ─────────────────────────────────────────────────────────
    print("\n── Null rates ──────────────────────────────────────────────────")
    key_cols = stat_cols + ["program_srs", "college_season_year"] + ["vorp_yr2_5_avg"]
    for col in key_cols:
        if col in df.columns:
            null_pct = df[col].isna().mean() * 100
            print(f"  {col:25s}  {null_pct:5.1f}% null")

    print("\n── Median VORP yr2-5 by draft round ────────────────────────────")
    if "draft_round" in df.columns and "vorp_yr2_5_avg" in df.columns:
        by_round = df.groupby("draft_round")["vorp_yr2_5_avg"].median()
        for rnd, med in by_round.items():
            print(f"  Round {rnd}: {med:.2f}")

    print("\n── Years with full yr2-5 data ──────────────────────────────────")
    if "years_available" in df.columns and "draft_year" in df.columns:
        avg_yrs = df.groupby("draft_year")["years_available"].mean()
        for yr, avg in avg_yrs.items():
            print(f"  {yr}: {avg:.1f} avg years available")

    return df


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="MPS Dataset Builder — scrapes BBRef + CBB + Torvik for NBA draft prospect backtest"
    )
    parser.add_argument(
        "--years",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        default=[2010, 2023],
        help="Draft year range inclusive (default: 2010 2023)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore cached per-year CSVs and re-scrape everything",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Scrape a single year only (overrides --years)",
    )
    args = parser.parse_args()

    if args.year:
        target_years = range(args.year, args.year + 1)
    else:
        target_years = range(args.years[0], args.years[1] + 1)

    print(f"MPS Dataset Builder")
    print(f"Years: {list(target_years)}")
    print(f"Output: {DATA_DIR}")
    print(f"Force refresh: {args.force}")
    print()

    df = build_dataset(years=target_years, force_refresh=args.force)
    print(f"\nDone. {len(df)} rows in final dataset.")
