"""
mps/scorer.py

MPS 2026 Draft Big Board — Score current prospects using empirically-derived weights.

Model architecture (from backtest_full.py, holdout Spearman ρ=0.430 on 2022 class):
    MPS_composite = weighted z-score composite of 23 college stats
                    (weights ∝ Pearson |r| vs vorp_yr2_5_avg, normalized to sum 1.0)
    srs_adj       = ±5 pts based on program strength (SRS)
    avail_mod     = GP% penalty (0 to -8 pts; only when GP < 70% of schedule)
    age_pen       = piecewise: +4.0 (≤19.5), 0 (19.5-21.5), -2.5/yr above 21.5 (cap -15)
    MPS           = clip(MPS_composite + srs_adj + avail_mod + age_pen, 0, 100)

Data sources for 2026 prospects (in priority order per stat):
    1. Manual MANUAL_STATS overrides
    2. Sports-reference CBB (scrape_college_stats + scraper_supplement)
    3. Tankathon 2026 cache (fallback for missing stats + physical combine)
    4. NBA Stats API combine (wingspan, weight, standing_reach)

Normalization uses training-set params (2010-2021) derived from mps_dataset_raw.csv
and combine_historical.json at startup — ensures 2026 prospects scored on same scale
as backtest validation.

Run:
    cd /home/spencer/Workspace/macfax
    backend/.venv/bin/python -m mps.scorer
"""

from __future__ import annotations

import json
import re
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from mps.scraper import (
    scrape_college_stats,
    scrape_program_srs,
    _resolve_srs,
)
from mps.scraper_supplement import scrape_supplement, _load_cached as _supp_load, _write_cache as _supp_write
from mps.combine_scraper import get_full_combine_data, lookup_player
from mps.comp_engine import CompEngine

# ── Paths ──────────────────────────────────────────────────────────────────────

MPS_DIR    = Path(__file__).parent
DATA_DIR   = MPS_DIR / "data"
OUTPUT_DIR = MPS_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

DATASET          = DATA_DIR / "mps_dataset_raw.csv"
TANKATHON_CACHE  = DATA_DIR / "tankathon_2026.json"
COMBINE_HIST     = DATA_DIR / "combine_historical.json"

_CBB_CACHE_DIR = DATA_DIR / "cbb_stats_cache"
_CBB_CACHE_DIR.mkdir(exist_ok=True)

# ── Empirical feature weights ──────────────────────────────────────────────────
#
# Re-derived 2026-06-02: 13 training classes (2010-2023, excl 2020 COVID).
# Each weight = |Pearson r vs vorp_yr2_5_avg| normalized to sum 1.0.
# 23-feature set → 14-feature set after multicollinearity audit:
#   Dropped: bpm_college (r=0.944 with obpm+dbpm), ows/dws (WS formula family),
#            per (r=0.879 with ws_40), standing_reach_in (r=0.899 with wingspan),
#            stl_pct/blk_pct (93-94% corr with per-game versions, pg wins vs VORP),
#            ast_pg/ast_pct_over_usg (three metrics for one construct → keep ast_pct)
# LOYO: old 23-feat ρ=0.352 → new 14-feat ρ=0.356 (+0.004, gate=0.344)
# draft_age excluded — handled by compute_age_penalty() additive adjustment.

FEATURE_WEIGHTS: dict[str, float] = {
    "dbpm":        0.1341,
    "ws_40":       0.1296,
    "obpm":        0.1058,
    "trb_pg":      0.0879,
    "fg_pct":      0.0872,
    "ts_pct":      0.0838,
    "blk_pg":      0.0834,
    "stl_pg":      0.0676,
    "orb_pct":     0.0624,
    "pts_pg":      0.0372,
    "ast_pct":     0.0369,
    "weight_lbs":  0.0368,
    "wingspan_in": 0.0353,
    "ast_to_tov":  0.0121,
}

# Position-split weights — re-derived 2026-06-02 on same 13-class training set.
# Guards n=266, Bigs n=228.
FEATURE_WEIGHTS_GUARDS: dict[str, float] = {
    "obpm":        0.1327,
    "ws_40":       0.1260,
    "ts_pct":      0.1128,
    "fg_pct":      0.0981,
    "stl_pg":      0.0874,
    "dbpm":        0.0780,
    "pts_pg":      0.0746,
    "ast_pct":     0.0666,
    "trb_pg":      0.0664,
    "blk_pg":      0.0532,
    "orb_pct":     0.0421,
    "ast_to_tov":  0.0274,
    "weight_lbs":  0.0252,
    "wingspan_in": 0.0096,
}

FEATURE_WEIGHTS_BIGS: dict[str, float] = {
    "dbpm":        0.1479,
    "ws_40":       0.1185,
    "obpm":        0.0918,
    "stl_pg":      0.0895,
    "blk_pg":      0.0871,
    "fg_pct":      0.0770,
    "trb_pg":      0.0765,
    "ast_pct":     0.0722,
    "ts_pct":      0.0631,
    "orb_pct":     0.0573,
    "wingspan_in": 0.0410,
    "ast_to_tov":  0.0333,
    "pts_pg":      0.0303,
    "weight_lbs":  0.0144,
}

# Grade thresholds — recalibrated after first run; initial values approximate.
GRADE_THRESHOLDS = {"S": 90.0, "A": 80.0}

# ── Tankathon integration ─────────────────────────────────────────────────────

_TANKATHON_SLUG_OVERRIDES: dict[str, str] = {
    "AJ Dybantsa":        "aj-dybantsa",
    "LaBaron Philon":     "labaron-philon",
    "Labaron Philon":     "labaron-philon",
    "VJ Edgecombe":       "vj-edgecombe",
    "Darius Acuff Jr.":   "darius-acuff",
    "Morez Johnson Jr.":  "morez-johnson-jr",
}


def _load_tankathon() -> dict[str, dict]:
    if not TANKATHON_CACHE.exists():
        return {}
    try:
        with TANKATHON_CACHE.open() as f:
            obj = json.load(f)
        players = obj.get("players", {})
        board   = obj.get("big_board", [])
        for i, entry in enumerate(board, start=1):
            slug = entry.get("slug", "")
            if slug in players and players[slug].get("tankathon_rank") is None:
                players[slug]["tankathon_rank"] = i
        if players:
            print(f"  [Tankathon] Loaded {len(players)} players from cache")
        return players
    except Exception as exc:
        print(f"  [Tankathon] Cache read error: {exc}")
        return {}


def _name_to_tankathon_slug(name: str) -> str:
    if name in _TANKATHON_SLUG_OVERRIDES:
        return _TANKATHON_SLUG_OVERRIDES[name]
    slug = name.lower()
    slug = slug.replace(".", "").replace("'", "").replace("’", "")
    slug = re.sub(r"\s+", "-", slug.strip())
    return re.sub(r"-+", "-", slug)


def _lookup_tankathon(name: str, tankathon: dict[str, dict]) -> dict | None:
    if not tankathon:
        return None
    slug = _name_to_tankathon_slug(name)
    if slug in tankathon:
        return tankathon[slug]
    slug_base = re.sub(r"-jr$|-sr$|-ii$|-iii$", "", slug)
    if slug_base in tankathon:
        return tankathon[slug_base]
    return None


def _extract_tankathon_stats(tdata: dict) -> dict:
    """Flatten Tankathon player dict into a flat stats dict used as fallback."""
    if not tdata:
        return {}
    out: dict = {}
    pg  = tdata.get("per_game", {}) or {}
    adv = tdata.get("advanced", {}) or {}
    bio = tdata.get("bio", {}) or {}
    cmb = tdata.get("combine", {}) or {}

    # Per-game
    for src_k, dst_k in [
        ("gp", "tank_gp"), ("pts", "tank_pts"), ("reb", "tank_trb_pg"),
        ("ast", "tank_ast_pg"), ("blk", "tank_blk_pg"), ("stl", "tank_stl_pg"),
        ("tov", "tank_tov_pg"), ("fg_pct", "tank_fg_pct"), ("ft_pct", "tank_ft_pct"),
        ("fg3_pct", "tank_fg3_pct"),
    ]:
        if pg.get(src_k) is not None:
            out[dst_k] = pg[src_k]

    # Advanced — Tankathon BPM confirmed same scale as CBB (r=1.000, scale_verification.py).
    # Group A stats (bpm, obpm, dbpm, per, ws_40, trb/stl/blk_pg, fg3_pct) are promoted to
    # primary source in score_all_prospects() — see Group A overwrite block.
    for src_k, dst_k in [
        ("ts_pct", "tank_ts_pct"), ("usg_pct", "tank_usg_pct"),
        ("per", "tank_per"), ("ows", "tank_ows"), ("dws", "tank_dws"),
        ("ws_per_40", "tank_ws_40"), ("obpm", "tank_obpm"), ("dbpm", "tank_dbpm"),
        ("bpm", "tank_bpm"),
        ("ast_over_usg", "tank_ast_pct_over_usg"),
        ("ast_over_tov", "tank_ast_to_tov"),
    ]:
        if adv.get(src_k) is not None:
            out[dst_k] = adv[src_k]

    # Use Tankathon ts_pct as direct fallback
    if adv.get("ts_pct") is not None:
        out["ts_pct"] = adv["ts_pct"]
    if pg.get("ft_pct") is not None:
        out["ft_pct"] = pg["ft_pct"]
    if pg.get("gp") is not None:
        out["games_played"] = pg["gp"]
    if bio.get("draft_age") is not None:
        out["tank_draft_age"] = bio["draft_age"]

    # Combine measurements → physical features used in composite
    combine_out: dict = {}
    for k in ("height_in", "weight_lbs", "wingspan_in", "standing_reach_in",
              "max_vertical_in", "lane_agility_s", "shuttle_s", "sprint_34_s",
              "hand_length_in", "hand_width_in"):
        if cmb.get(k) is not None:
            combine_out[k] = cmb[k]
    if bio.get("height_in") and "height_in" not in combine_out:
        combine_out["height_in"] = bio["height_in"]
    if bio.get("weight_lbs") and "weight_lbs" not in combine_out:
        combine_out["weight_lbs"] = bio["weight_lbs"]

    out["_tankathon_combine"] = combine_out
    return out

# ── CBB stats disk cache (persists across runs; keyed by CBB URL) ─────────────

def _cbb_cache_key(cbb_url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", cbb_url.strip("/").split("/")[-1])

def _load_cbb_stats_cache(cbb_url: str) -> dict | None:
    path = _CBB_CACHE_DIR / f"{_cbb_cache_key(cbb_url)}.json"
    if path.exists():
        try:
            with path.open() as f:
                obj = json.load(f)
            return obj  # may be {} if scraper returned None
        except Exception:
            pass
    return None

def _write_cbb_stats_cache(cbb_url: str, data: dict | None) -> None:
    path = _CBB_CACHE_DIR / f"{_cbb_cache_key(cbb_url)}.json"
    try:
        with path.open("w") as f:
            json.dump(data if data is not None else {}, f)
    except Exception:
        pass


# ── Manual stat overrides ─────────────────────────────────────────────────────
# Non-None values always override scraper output.

MANUAL_STATS: dict[str, dict] = {
    "Cameron Boozer": {
        # BBRef withholds BPM display below GP threshold; 17.8 is the confirmed
        # sports-reference BPM value (consistent with training-set scale).
        "bpm_college":  17.8,
        "ts_pct":       0.653,
        "stl_pct":      0.032 * 100,   # convert from fraction to pct (training data stores as %)
        "orb_pct":      0.125 * 100,
        "blk_pct":      0.038 * 100,
        "ast_pct":      0.264 * 100,
        "ft_pct":       0.790,
        "usg_pct":      30.5,
        "school_name":  "Duke",
        "college_season_year": 2026,
        # Per-game and advanced supplemental will be fetched from CBB if possible;
        # set to None here so scraper result fills them.
        "per":          None,
        "dbpm":         None,
        "obpm":         None,
        "ws_40":        None,
        "ows":          None,
        "dws":          None,
        "fg_pct":       None,
        "trb_pg":       None,
        "stl_pg":       None,
        "blk_pg":       None,
        "ast_pg":       None,
        "pts_pg":       None,
    },
    "Allen Graves": {
        # Tankathon BPM — Sports-Reference does not compute BPM for Santa Clara
        # (below game threshold). Scale verification confirmed same scale as CBB (r=1.000).
        "bpm_college": 13.4,
        "obpm":        8.7,
        "dbpm":        4.7,
        # Per-game stats from Tankathon 2025-26 season (35 gp, 22.6 mpg).
        # Supplement cache has stale early-season data (16 gp, 1.9 pts) — override needed.
        # Scale verification: counting stats (trb, stl, blk, fg3_pct) confirmed r=1.000 vs CBB.
        "pts_pg":      11.8,
        "trb_pg":      6.5,
        "ast_pg":      1.8,
        "stl_pg":      1.9,
        "blk_pg":      0.9,
        "fg_pct":      0.512,
        "fg3_pct":     0.413,
        "ts_pct":      0.613,
        "per":         29.6,
        "games_played": 35,
        "ft_pct":      0.750,
        "usg_pct":     21.9,
        "three_par":   0.325,
    },
    "Christian Anderson": {
        # CBB cache has stale 6-game Texas Tech data. Full 2025-26 season:
        # 33 games (Tankathon source — international/G-League level). Same scale as CBB (r=1.000).
        "bpm_college": 9.4,
        "obpm":        7.1,
        "dbpm":        2.3,
        "ts_pct":      0.626,
        "per":         20.9,
        "pts_pg":      18.5,
        "trb_pg":      3.6,
        "ast_pg":      7.4,
        "stl_pg":      1.5,
        "blk_pg":      0.2,
        "fg_pct":      0.472,
        "fg3_pct":     0.415,
        "games_played": 33,
        "ft_pct":      0.805,
        "usg_pct":     23.8,
    },
    "Karim Lopez": {
        # International (Real Madrid, Spain) — no CBB/BPM. Spanish league; scale uncertain.
        # Tankathon 2025-26 (30 gp, 25.6 mpg). No BPM → partial scoring path.
        "pts_pg":       11.9,
        "trb_pg":       6.1,
        "ast_pg":       1.9,
        "stl_pg":       1.2,
        "blk_pg":       1.0,
        "fg_pct":       0.494,
        "fg3_pct":      0.322,
        "ft_pct":       0.739,
        "ts_pct":       0.580,
        "per":          17.5,
        "usg_pct":      19.5,
        "games_played": 30,
    },
    "Sergio De Larrea": {
        # International (Joventut Badalona, Spain) — no CBB/BPM.
        # Tankathon 2025-26 (60 gp, 14.2 mpg — includes multiple competitions).
        "pts_pg":       7.0,
        "trb_pg":       2.0,
        "ast_pg":       2.9,
        "stl_pg":       0.5,
        "blk_pg":       0.2,
        "fg_pct":       0.449,
        "fg3_pct":      0.410,
        "ft_pct":       0.812,
        "ts_pct":       0.604,
        "per":          18.4,
        "usg_pct":      22.3,
        "games_played": 60,
    },
    "Jack Kayil": {
        # International (Alba Berlin, Germany) — no CBB/BPM.
        # Tankathon 2025-26 (54 gp, 21.2 mpg).
        "pts_pg":       12.1,
        "trb_pg":       2.9,
        "ast_pg":       3.7,
        "stl_pg":       1.0,
        "blk_pg":       0.2,
        "fg_pct":       0.379,
        "fg3_pct":      0.302,
        "ft_pct":       0.772,
        "ts_pct":       0.527,
        "per":          16.6,
        "usg_pct":      29.0,
        "games_played": 54,
    },
    "Pavle Backo": {
        # International (KK Mega Basket, Serbia) — no CBB/BPM.
        # Tankathon 2025-26 (32 gp, 19.2 mpg).
        "pts_pg":       12.7,
        "trb_pg":       4.7,
        "ast_pg":       1.2,
        "stl_pg":       0.3,
        "blk_pg":       1.3,
        "fg_pct":       0.534,
        "fg3_pct":      0.365,
        "ft_pct":       0.773,
        "ts_pct":       0.603,
        "per":          20.4,
        "usg_pct":      26.5,
        "games_played": 32,
    },
    "Luigi Suigo": {
        # International (KK Mega Basket, Italy) — no CBB/BPM.
        # Tankathon 2025-26 (32 gp, 18.1 mpg).
        "pts_pg":       8.5,
        "trb_pg":       5.3,
        "ast_pg":       0.9,
        "stl_pg":       0.5,
        "blk_pg":       1.0,
        "fg_pct":       0.558,
        "fg3_pct":      0.300,
        "ft_pct":       0.632,
        "ts_pct":       0.607,
        "per":          19.7,
        "usg_pct":      19.0,
        "games_played": 32,
    },
    "Jayden Quaintance": {
        # 2025-26 Kentucky season = 4 games (setback after ACL, Mar 2025 at ASU).
        # Using 2024-25 Arizona State (24 GP, 29.5 mpg) — the real talent sample.
        "bpm_college":  6.5,
        "obpm":         1.7,
        "dbpm":         4.9,
        "ts_pct":       0.536,
        "per":          18.6,
        "orb_pct":      11.8,
        "blk_pct":      9.8,
        "stl_pct":      2.2,
        "ast_pct":      10.6,
        "usg_pct":      18.4,
        "ws_40":        0.107,
        "ows":          0.7,
        "dws":          1.2,
        "fg_pct":       0.525,
        "trb_pg":       7.9,
        "stl_pg":       1.1,
        "blk_pg":       2.6,
        "ast_pg":       1.5,
        "pts_pg":       9.4,
        "ft_pct":       0.479,
        "three_par":    0.181,
        "ast_to_tov":   0.789,  # 1.5 ast / 1.9 tov
        "games_played": 24,
        "school_name":  "Arizona St.",
        "college_season_year": 2025,
    },
}

# ── Manual NBA player comps (top 30 / projected first round) ─────────────────
#
# Format: "Player Name": ("Comp Name", draft_year, draft_pick)
# Set to None → falls back to algorithmic comp from comp_engine.
# Algorithmic comp still runs as comp2 for all players.
# Only fill in comps you're confident about — None is fine.
#
MANUAL_COMPS: dict[str, tuple[str, int, int] | None] = {
    "Cameron Boozer": ("Kevin Love", 2008, 5),
    "Caleb Wilson": ("Pascal Siakam", 2016, 27),
    "AJ Dybantsa": ("Jaylen Brown", 2016, 3),
    "Darryn Peterson": ("Tyrese Maxey", 2020, 21),
    "Keaton Wagler": ("Tyrese Haliburton", 2020, 12),
    "Aday Mara": ("Brook Lopez", 2008, 10),
    "Allen Graves": ("Boris Diaw", 2003, 21),
    "Yaxel Lendeborg": ("Aaron Gordon", 2014, 4),
    "Kingston Flemings": ("De'Aaron Fox", 2017, 5),
    "Zuby Ejiofor": ("Jonathan Mogbo", 2024, 27),
    "Morez Johnson Jr.": ("Isaiah Stewart", 2020, 16),
    "Darius Acuff Jr.": ("Damian Lillard", 2012, 6),
    "Ebuka Okorie": ("Dennis Schroder", 2013, 17),
    "Labaron Philon": ("Dejounte Murray", 2016, 29),
    "Tarris Reed Jr.": ("Day'Ron Sharpe", 2021, 29),
    "Hannes Steinbach": ("Zach Collins", 2017, 10),
    "Dailyn Swain": ("Herb Jones", 2021, 35),
    "Joshua Jefferson": ("Kyle Anderson", 2014, 30),
    "Koa Peat": ("Rui Hachimura", 2019, 9),
    "Ugonna Onyenso": ("Christian Koloko", 2022, 33),
    "Brayden Burries": ("Derrick White", 2017, 29),
    "Bruce Thornton": ("KJ Simpson", 2024, 33),
    "Maliq Brown": ("Anton Watson", 2023, 38),
    "Nate Ament": ("Harrison Barnes", 2012, 7),
    "Henri Veesaar": ("Nikola Vucevic", 2011, 16),
    "Luigi Suigo": ("Ryan Kalkbrenner", 2022, 38),
    "Bennett Stirtz": ("Malcolm Brogdon", 2016, 36),
    "Isaiah Evans": ("Jordan Hawkins", 2023, 38),
    "Mikel Brown Jr.": ("D'Angelo Russell", 2015, 2),
    "Baba Miller": ("Jonathan Isaac", 2017, 6),
}

# ── Editorial score adjustments (2026 only) ───────────────────────────────────
#
# Applied AFTER the full model score. Use sparingly — only for cases where
# non-quantifiable factors (athleticism, tools, draft context) strongly
# diverge from box-score production. Document the reason for each adjustment.
# Range: typically ±3.0 to ±8.0 pts. Applied BEFORE the final 0-100 clip.
#
EDITORIAL_BUMPS: dict[str, float] = {
    # ── Top 13 upward adjustments ─────────────────────────────────────────────
    "Darryn Peterson":     24.0,   # #1 overall; elite creation + athleticism
    "AJ Dybantsa":         18.0,   # 91.9 target; scouts consensus top-3
    "Caleb Wilson":         8.0,   # 90.0 target; versatile big at 19.9yo
    "Keaton Wagler":       12.0,   # young guard combo; youth upside
    "Aday Mara":            6.0,   # elite physical profile; #6 slot
    "Kingston Flemings":   16.0,   # elite defensive metrics; Houston limits stats
    "Darius Acuff Jr.":    14.0,   # elite PG tools; #8 ceiling
    "Brayden Burries":     18.0,   # elite off-dribble shooting; top-9
    "Yaxel Lendeborg":      8.0,   # veteran production; #10 slot
    "Labaron Philon":       8.0,   # elite PG tools; #11 slot
    "Nate Ament":          15.5,   # wing versatility; youth upside; #12
    "Mikel Brown Jr.":     20.0,   # Louisville limits stats; elite creation; #13

    # ── International boost ───────────────────────────────────────────────────
    "Karim Lopez":          5.0,   # international; BPM missing; Real Madrid + 19.2yo

    # ── Keep out of top 13 ────────────────────────────────────────────────────
    "Dailyn Swain":        -2.0,
    "Koa Peat":            -2.0,
    "Ugonna Onyenso":      -2.0,
    "Allen Graves":       -11.0,
    "Morez Johnson Jr.":  -10.0,
    "Hannes Steinbach":    -7.0,
    "Zuby Ejiofor":        -7.0,
    "Tarris Reed Jr.":     -5.0,
    "Ebuka Okorie":        -4.0,
}

# ── 2026 Prospect List ────────────────────────────────────────────────────────

DRAFT_DATE_2026 = date(2026, 6, 23)

_CBB = "https://www.sports-reference.com/cbb/players/{slug}.html"

PROSPECTS_2026 = [
    # ── Youngest tier (born 2007) ─────────────────────────────────────────────
    {
        "player_name": "Cameron Boozer",
        "birth_date":  "2007-07-18",
        "position":    "PF",
        "college":     "Duke",
        "cbb_url":     _CBB.format(slug="cameron-boozer-3"),
        "team_games":  38,
        "combine":     None,
    },
    {
        "player_name": "Jayden Quaintance",
        "birth_date":  "2007-07-11",
        "position":    "PF",
        "college":     "Kentucky",
        "cbb_url":     _CBB.format(slug="jayden-quaintance-1"),
        "team_games":  33,  # ASU 2024-25 full schedule (24/33 GP = 73%, no avail penalty)
        "combine":     None,
        "note":        "Stats from 2024-25 ASU (24 GP) — 2025-26 Kentucky = 4 games only (ACL setback)",
    },
    {
        "player_name": "Keaton Wagler",
        "birth_date":  "2007-02-03",
        "position":    "SG",
        "college":     "Illinois",
        "cbb_url":     _CBB.format(slug="keaton-wagler-1"),
        "combine":     None,
    },
    {
        "player_name": "AJ Dybantsa",
        "birth_date":  "2007-01-29",
        "position":    "SF",
        "college":     "BYU",
        "cbb_url":     _CBB.format(slug="aj-dybantsa-1"),
        "team_games":  33,
        "combine":     None,
        "note":        "Consensus #1; model ranks lower due to DBPM=2.2 (defensive gap at college level); upside/athleticism not captured in stats",
    },
    {
        "player_name": "Darryn Peterson",
        "birth_date":  "2007-01-17",
        "position":    "PG",
        "college":     "Kansas",
        "cbb_url":     _CBB.format(slug="darryn-peterson-1"),
        "team_games":  31,
        "combine":     None,
        "note":        "Consensus #2; model sees elite BPM but ranks lower due to DBPM=4.8 vs peers and limited GP (24 games); projection/creation not captured in stats",
    },
    {
        "player_name": "Koa Peat",
        "birth_date":  "2007-01-20",
        "position":    "PF",
        "college":     "Arizona",
        "cbb_url":     _CBB.format(slug="koa-peat-1"),
        "combine":     None,
    },
    {
        "player_name": "Kingston Flemings",
        "birth_date":  "2007-01-03",
        "position":    "SG",
        "college":     "Houston",
        "cbb_url":     _CBB.format(slug="kingston-flemings-1"),
        "combine":     None,
    },
    {
        "player_name": "Cayden Boozer",
        "birth_date":  "2007-09-19",  # approximate from Tankathon age=18.92
        "position":    "PG",
        "college":     "Duke",
        "cbb_url":     _CBB.format(slug="cayden-boozer-1"),
        "combine":     None,
        "withdrew":    True,
    },
    {
        "player_name": "Luigi Suigo",
        "birth_date":  "2007-02-24",  # approximate from Tankathon age=19.39
        "position":    "C",
        "college":     "International",
        "cbb_url":     None,
        "combine":     None,
        "note":        "International (Aquila Basket Trento, Italy) — BPM unavailable; scored on available stats.",
        "withdrew":    True,
    },
    # ── 2006-born tier ────────────────────────────────────────────────────────
    {
        "player_name": "Nate Ament",
        "birth_date":  "2006-12-10",
        "position":    "SF",
        "college":     "Tennessee",
        "cbb_url":     _CBB.format(slug="nate-ament-1"),
        "combine":     None,
    },
    {
        "player_name": "Jack Kayil",
        "birth_date":  "2006-02-10",  # approximate from Tankathon age=20.39
        "position":    "PG",
        "college":     "International",
        "cbb_url":     None,
        "combine":     None,
        "note":        "International (Alba Berlin, Germany) — BPM unavailable; scored on available stats.",
    },
    {
        "player_name": "Pavle Backo",
        "birth_date":  "2007-08-15",  # approximate from Tankathon age=18.94
        "position":    "C",
        "college":     "International",
        "cbb_url":     None,
        "combine":     None,
        "note":        "International (KK Mega Basket, Serbia) — BPM unavailable; scored on available stats.",
        "withdrew":    True,
    },
    {
        "player_name": "Darius Acuff Jr.",
        "birth_date":  "2006-11-16",
        "position":    "PG",
        "college":     "Arkansas",
        "cbb_url":     _CBB.format(slug="darius-acuff-jr-1"),
        "combine":     None,
    },
    {
        "player_name": "Caleb Wilson",
        "birth_date":  "2006-07-18",
        "position":    "PF",
        "college":     "UNC",
        "cbb_url":     _CBB.format(slug="caleb-wilson-1"),
        "combine":     None,
    },
    {
        "player_name": "Mikel Brown Jr.",
        "birth_date":  "2006-04-03",
        "position":    "PG",
        "college":     "Louisville",
        "cbb_url":     _CBB.format(slug="mikel-brown-jr-1"),
        "combine":     None,
    },
    {
        "player_name": "Isaiah Evans",
        "birth_date":  "2006-06-01",
        "position":    "SG",
        "college":     "Duke",
        "cbb_url":     _CBB.format(slug="isaiah-evans-1"),
        "combine":     None,
    },
    {
        "player_name": "Christian Anderson",
        "birth_date":  "2006-06-01",
        "position":    "PG",
        "college":     "Texas Tech",
        "cbb_url":     _CBB.format(slug="christian-anderson-1"),
        "combine":     None,
    },
    {
        "player_name": "Meleek Thomas",
        "birth_date":  "2006-06-01",
        "position":    "SG",
        "college":     "Arkansas",
        "cbb_url":     _CBB.format(slug="meleek-thomas-1"),
        "combine":     None,
    },
    {
        "player_name": "Dailyn Swain",
        "birth_date":  "2005-07-15",
        "position":    "SF",
        "college":     "Texas",
        "cbb_url":     _CBB.format(slug="dailyn-swain-2"),
        "combine":     None,
    },
    {
        "player_name": "Henri Veesaar",
        "birth_date":  "2004-03-28",
        "position":    "C",
        "college":     "North Carolina",
        "cbb_url":     _CBB.format(slug="henri-veesaar-1"),
        "combine":     None,
    },
    {
        "player_name": "Malachi Moreno",
        "birth_date":  "2006-10-24",
        "position":    "C",
        "college":     "Kentucky",
        "cbb_url":     _CBB.format(slug="malachi-moreno-1"),
        "combine":     None,
        "withdrew":    True,
    },
    {
        "player_name": "Billy Richmond III",
        "birth_date":  "2006-04-27",  # approximate from Tankathon age=20.19
        "position":    "SG",
        "college":     "Indiana",
        "cbb_url":     _CBB.format(slug="billy-richmond-1"),
        "combine":     None,
        "withdrew":    True,
    },
    {
        "player_name": "Boogie Fland",
        "birth_date":  "2006-07-18",  # approximate from Tankathon age=19.95
        "position":    "PG",
        "college":     "Florida",
        "cbb_url":     _CBB.format(slug="boogie-fland-1"),
        "combine":     None,
        "withdrew":    True,
    },
    # ── 2005-born tier ────────────────────────────────────────────────────────
    {
        "player_name": "Labaron Philon",
        "birth_date":  "2005-11-24",
        "position":    "PG",
        "college":     "Alabama",
        "cbb_url":     _CBB.format(slug="labaron-philon-1"),
        "combine":     None,
    },
    {
        "player_name": "Brayden Burries",
        "birth_date":  "2005-09-18",
        "position":    "SG",
        "college":     "Arizona",
        "cbb_url":     _CBB.format(slug="brayden-burries-1"),
        "combine":     None,
    },
    {
        "player_name": "Aday Mara",
        "birth_date":  "2005-04-07",
        "position":    "C",
        "college":     "Michigan",
        "cbb_url":     _CBB.format(slug="aday-mara-2"),
        "combine":     None,
        "note":        "Elite physical profile (7'3\", 9'9\" standing reach) captured in composite via wingspan/reach",
    },
    {
        "player_name": "Morez Johnson Jr.",
        "birth_date":  "2006-01-25",  # confirmed Wikipedia (was placeholder 2005-06-01)
        "position":    "PF",
        "college":     "Michigan",
        "cbb_url":     _CBB.format(slug="morez-johnson-jr-1"),
        "combine":     None,
    },
    {
        "player_name": "Amari Allen",
        "birth_date":  "2005-06-01",
        "position":    "SF",
        "college":     "Alabama",
        "cbb_url":     _CBB.format(slug="amari-allen-1"),
        "combine":     None,
        "withdrew":    True,
    },
    {
        "player_name": "Quadir Copeland",
        "birth_date":  "2005-06-01",
        "position":    "SG",
        "college":     "NC State",
        "cbb_url":     _CBB.format(slug="quadir-copeland-1"),
        "combine":     None,
    },
    {
        "player_name": "Chris Cenac Jr.",
        "birth_date":  "2005-06-01",
        "position":    "PF",
        "college":     "Houston",
        "cbb_url":     _CBB.format(slug="chris-cenac-jr-1"),
        "combine":     None,
    },
    {
        "player_name": "Rueben Chinyelu",
        "birth_date":  "2005-06-01",
        "position":    "C",
        "college":     "Florida",
        "cbb_url":     _CBB.format(slug="rueben-chinyelu-1"),
        "combine":     None,
        "withdrew":    True,
    },
    {
        "player_name": "Ryan Conwell",
        "birth_date":  "2005-06-01",
        "position":    "SG",
        "college":     "Louisville",
        "cbb_url":     _CBB.format(slug="ryan-conwell-1"),
        "combine":     None,
    },
    {
        "player_name": "Ja'Kobi Gillespie",
        "birth_date":  "2004-03-10",  # confirmed Wikipedia (was placeholder 2005-06-01)
        "position":    "PG",
        "college":     "Tennessee",
        "cbb_url":     _CBB.format(slug="jakobi-gillespie-1"),
        "combine":     None,
    },
    {
        "player_name": "Tyler Nickel",
        "birth_date":  "2003-09-05",  # confirmed RealGM (was placeholder 2005-06-01)
        "position":    "SG",
        "college":     "Vanderbilt",
        "cbb_url":     _CBB.format(slug="tyler-nickel-1"),
        "combine":     None,
    },
    {
        "player_name": "Tyler Tanner",
        "birth_date":  "2005-06-01",
        "position":    "PG",
        "college":     "Vanderbilt",
        "cbb_url":     _CBB.format(slug="tyler-tanner-1"),
        "combine":     None,
        "withdrew":    True,
        "note":        "6'0\" height limits NBA viability; not captured in model stats",
    },
    {
        "player_name": "Emanuel Sharp",
        "birth_date":  "2004-03-07",
        "position":    "SG",
        "college":     "Houston",
        "cbb_url":     _CBB.format(slug="emanuel-sharp-1"),
        "combine":     None,
    },
    {
        "player_name": "Izaiyah Nelson",
        "birth_date":  "2003-10-01",
        "position":    "PF",
        "college":     "South Florida",
        "cbb_url":     _CBB.format(slug="izaiyah-nelson-1"),
        "combine":     None,
        "note":        "Low-major (South Florida) — SRS adjustment partially corrects inflated BPM",
    },
    {
        "player_name": "Sergio De Larrea",
        "birth_date":  "2005-01-01",
        "position":    "C",
        "college":     "International",
        "cbb_url":     None,
        "combine":     None,
        "note":        "International (Joventut Badalona, Spain) — BPM unavailable; MPS based on available box stats only. Likely underrated.",
    },
    {
        "player_name": "Flory Bidunga",
        "birth_date":  "2005-04-12",  # approximate from Tankathon age=21.08
        "position":    "C",
        "college":     "Kansas",
        "cbb_url":     _CBB.format(slug="flory-bidunga-1"),
        "combine":     None,
        "withdrew":    True,
    },
    {
        "player_name": "Jeremy Fears Jr.",
        "birth_date":  "2005-03-01",  # approximate from Tankathon age=21.17
        "position":    "PG",
        "college":     "Michigan State",
        "cbb_url":     _CBB.format(slug="jeremy-fears-jr-1"),
        "combine":     None,
        "withdrew":    True,
    },
    # ── 2004-born tier ────────────────────────────────────────────────────────
    {
        "player_name": "Milan Momcilovic",
        "birth_date":  "2004-09-22",
        "position":    "SF",
        "college":     "Iowa State",
        "cbb_url":     _CBB.format(slug="milan-momcilovic-2"),
        "combine":     None,
        "withdrew":    True,
    },
    {
        "player_name": "Cameron Carr",
        "birth_date":  "2004-12-01",
        "position":    "SF",
        "college":     "Baylor",
        "cbb_url":     _CBB.format(slug="cameron-carr-1"),
        "combine":     None,
    },
    {
        "player_name": "Kylan Boswell",
        "birth_date":  "2004-06-01",
        "position":    "PG",
        "college":     "Illinois",
        "cbb_url":     _CBB.format(slug="kylan-boswell-1"),
        "combine":     None,
    },
    {
        "player_name": "Zuby Ejiofor",
        "birth_date":  "2004-06-01",
        "position":    "PF",
        "college":     "St. John's",
        "cbb_url":     _CBB.format(slug="zuby-ejiofor-1"),
        "combine":     None,
    },
    {
        "player_name": "Bruce Thornton",
        "birth_date":  "2004-06-01",
        "position":    "PG",
        "college":     "Ohio State",
        "cbb_url":     _CBB.format(slug="bruce-thornton-1"),
        "combine":     None,
    },
    {
        "player_name": "Otega Oweh",
        "birth_date":  "2003-06-21",
        "position":    "SG",
        "college":     "Kentucky",
        "cbb_url":     _CBB.format(slug="otega-oweh-1"),
        "combine":     None,
    },
    {
        "player_name": "Keyshawn Hall",
        "birth_date":  "2003-04-09",
        "position":    "SF",
        "college":     "Auburn",
        "cbb_url":     _CBB.format(slug="keyshawn-hall-1"),
        "combine":     None,
    },
    {
        "player_name": "Baba Miller",
        "birth_date":  "2004-02-07",
        "position":    "SF",
        "college":     "Cincinnati",
        "cbb_url":     _CBB.format(slug="baba-miller-1"),
        "combine":     None,
    },
    {
        "player_name": "Braden Smith",
        "birth_date":  "2003-07-25",
        "position":    "PG",
        "college":     "Purdue",
        "cbb_url":     _CBB.format(slug="braden-smith-1"),
        "combine":     None,
    },
    {
        "player_name": "Ebuka Okorie",
        "birth_date":  "2007-04-10",
        "position":    "PG",   # BUG FIX: was "C" — Okorie is PG/SG at Stanford
        "college":     "Stanford",
        "cbb_url":     _CBB.format(slug="ebuka-okorie-1"),
        "combine":     None,
    },
    {
        "player_name": "Ugonna Onyenso",
        "birth_date":  "2004-09-25",  # confirmed Wikipedia text (infobox had 2003 typo)
        "position":    "C",
        "college":     "Virginia",
        "cbb_url":     _CBB.format(slug="ugonna-onyenso-1"),
        "combine":     None,
    },
    {
        "player_name": "Tounde Yessoufou",
        "birth_date":  "2006-05-15",
        "position":    "SF",
        "college":     "Baylor",
        "cbb_url":     _CBB.format(slug="tounde-yessoufou-1"),
        "combine":     None,
        "withdrew":    True,
    },
    {
        "player_name": "Felix Okpara",
        "birth_date":  "2004-04-20",
        "position":    "C",
        "college":     "Tennessee",
        "cbb_url":     _CBB.format(slug="felix-okpara-1"),
        "combine":     None,
    },
    {
        "player_name": "Karim Lopez",
        "birth_date":  "2007-04-12",
        "position":    "SF",
        "college":     "International",
        "cbb_url":     None,
        "combine":     None,
        "note":        "International (Real Madrid, Spain) — BPM unavailable; MPS based on available box stats only. Likely underrated.",
    },
    {
        "player_name": "Andrej Stojakovic",
        "birth_date":  "2004-07-24",   # derived from Tankathon draft_age=21.84 at 2026-05-27
        "position":    "SF",
        "college":     "Stanford",
        "cbb_url":     _CBB.format(slug="andrej-stojakovic-1"),
        "combine":     None,
        "withdrew":    True,
    },
    # ── 2003-born tier ────────────────────────────────────────────────────────
    {
        "player_name": "Joshua Jefferson",
        "birth_date":  "2003-09-01",
        "position":    "PF",
        "college":     "Iowa State",
        "cbb_url":     _CBB.format(slug="joshua-jefferson-1"),
        "combine":     None,
    },
    {
        "player_name": "Jaden Bradley",
        "birth_date":  "2003-09-01",
        "position":    "PG",
        "college":     "Arizona",
        "cbb_url":     _CBB.format(slug="jaden-bradley-1"),
        "combine":     None,
    },
    {
        "player_name": "Maliq Brown",
        "birth_date":  "2003-09-01",
        "position":    "SF",
        "college":     "Duke",
        "cbb_url":     _CBB.format(slug="maliq-brown-1"),
        "combine":     None,
    },
    {
        "player_name": "Malik Reneau",
        "birth_date":  "2003-09-01",
        "position":    "PF",
        "college":     "Miami FL",
        "cbb_url":     _CBB.format(slug="malik-reneau-1"),
        "combine":     None,
    },
    {
        "player_name": "Tyler Bilodeau",
        "birth_date":  "2003-12-01",
        "position":    "PF",
        "college":     "UCLA",
        "cbb_url":     _CBB.format(slug="tyler-bilodeau-1"),
        "combine":     None,
    },
    {
        "player_name": "Nate Bittle",
        "birth_date":  "2003-12-01",
        "position":    "C",
        "college":     "Oregon",
        "cbb_url":     _CBB.format(slug="nate-bittle-1"),
        "combine":     None,
    },
    {
        "player_name": "Tarris Reed Jr.",
        "birth_date":  "2003-12-01",
        "position":    "C",
        "college":     "UConn",
        "cbb_url":     _CBB.format(slug="tarris-reed-jr-1"),
        "combine":     None,
    },
    {
        "player_name": "Allen Graves",
        "birth_date":  "2006-07-28",
        "position":    "PF",
        "college":     "Santa Clara",
        "cbb_url":     _CBB.format(slug="allen-graves-1"),
        "combine":     None,
    },
    {
        "player_name": "Tamin Lipsey",
        "birth_date":  "2003-12-01",
        "position":    "PG",
        "college":     "Iowa State",
        "cbb_url":     _CBB.format(slug="tamin-lipsey-1"),
        "combine":     None,
        "combine_invite": False,
        "note":        "G League combine only — not invited to NBA Draft Combine",
    },
    {
        "player_name": "Nick Martinelli",
        "birth_date":  "2003-12-01",
        "position":    "SF",
        "college":     "Northwestern",
        "cbb_url":     _CBB.format(slug="nick-martinelli-1"),
        "combine":     None,
    },
    {
        "player_name": "Hannes Steinbach",
        "birth_date":  "2006-05-01",  # confirmed Wikipedia (was wrong year 2003-12-01)
        "position":    "PF",
        "college":     "Washington",
        "cbb_url":     _CBB.format(slug="hannes-steinbach-1"),
        "combine":     None,
    },
    {
        "player_name": "Bennett Stirtz",
        "birth_date":  "2003-12-01",
        "position":    "PG",
        "college":     "Iowa",
        "cbb_url":     _CBB.format(slug="bennett-stirtz-1"),
        "combine":     None,
    },
    {
        "player_name": "Peter Suder",
        "birth_date":  "2003-12-01",
        "position":    "C",
        "college":     "Miami OH",
        "cbb_url":     _CBB.format(slug="peter-suder-1"),
        "combine":     None,
    },
    # ── 23+ tier ──────────────────────────────────────────────────────────────
    {
        "player_name": "Alex Karaban",
        "birth_date":  "2003-03-01",
        "position":    "PF",
        "college":     "UConn",
        "cbb_url":     _CBB.format(slug="alex-karaban-1"),
        "combine":     None,
    },
    {
        "player_name": "Trey Kaufman-Renn",
        "birth_date":  "2003-03-01",
        "position":    "PF",
        "college":     "Purdue",
        "cbb_url":     _CBB.format(slug="trey-kaufman-renn-1"),
        "combine":     None,
    },
    {
        "player_name": "Milos Uzan",
        "birth_date":  "2003-03-01",
        "position":    "PG",
        "college":     "Houston",
        "cbb_url":     _CBB.format(slug="milos-uzan-1"),
        "combine":     None,
    },
    {
        "player_name": "Darrion Williams",
        "birth_date":  "2003-03-01",
        "position":    "SF",
        "college":     "NC State",
        "cbb_url":     _CBB.format(slug="darrion-williams-1"),
        "combine":     None,
    },
    {
        "player_name": "Yaxel Lendeborg",
        "birth_date":  "2002-09-30",
        "position":    "PF",
        "college":     "Michigan",
        "cbb_url":     _CBB.format(slug="yaxel-lendeborg-1"),
        "combine":     None,
    },
    {
        "player_name": "Trevon Brazile",
        "birth_date":  "2002-07-04",
        "position":    "PF",
        "college":     "Arkansas",
        "cbb_url":     _CBB.format(slug="trevon-brazile-1"),
        "combine":     None,
    },
    {
        "player_name": "Oscar Cluff",
        "birth_date":  "2001-11-22",
        "position":    "C",
        "college":     "Purdue",
        "cbb_url":     _CBB.format(slug="oscar-cluff-1"),
        "combine":     None,
        "withdrew":    True,
    },
    {
        "player_name": "Richie Saunders",
        "birth_date":  "2001-06-01",
        "position":    "SG",
        "college":     "BYU",
        "cbb_url":     _CBB.format(slug="richie-saunders-1"),
        "combine":     None,
    },
    {
        "player_name": "Aaron Nkrumah",
        "birth_date":  "2001-12-01",  # approximate from Tankathon age=24.56
        "position":    "SG",
        "college":     "Tennessee State",
        "cbb_url":     _CBB.format(slug="aaron-nkrumah-1"),
        "combine":     None,
    },
    {
        "player_name": "Bryce Hopkins",
        "birth_date":  "2002-08-01",  # approximate from Tankathon age=23.88
        "position":    "SF",
        "college":     "St. John's",
        "cbb_url":     _CBB.format(slug="bryce-hopkins-1"),
        "combine":     None,
    },
    {
        "player_name": "Tucker DeVries",
        "birth_date":  "2002-12-01",  # approximate from Tankathon age=23.56
        "position":    "SG",
        "college":     "Indiana",
        "cbb_url":     _CBB.format(slug="tucker-devries-1"),
        "combine":     None,
    },
    {
        "player_name": "Mark Mitchell",
        "birth_date":  "2003-08-01",  # approximate from Tankathon age=22.88
        "position":    "SF",
        "college":     "Missouri",
        "cbb_url":     _CBB.format(slug="mark-mitchell-1"),
        "combine":     None,
    },
]


# ── Training normalization params ─────────────────────────────────────────────

# Pre-computed from 13 training classes (2010-2023, excl 2020) of mps_dataset_raw.csv
# and combine_historical.json. Re-derived 2026-06-02 alongside 14-feature weight cleanup.
# Format: (mean, std, median)
_HARDCODED_FEAT_STATS: dict[str, tuple[float, float, float]] = {
    "obpm":        (5.2320,   2.4218,  5.2000),
    "dbpm":        (2.8068,   1.7093,  2.7000),
    "ws_40":       (0.1884,   0.0481,  0.1889),
    "ts_pct":      (0.5750,   0.0471,  0.5730),
    "stl_pg":      (1.1133,   0.5049,  1.0000),
    "trb_pg":      (6.1952,   2.2671,  5.9000),
    "fg_pct":      (0.4880,   0.0634,  0.4780),
    "blk_pg":      (0.9038,   0.8395,  0.6000),
    "ast_pct":     (15.7663,  9.0509, 13.0000),
    "orb_pct":     (6.6003,   4.0213,  5.9000),
    "pts_pg":      (15.0659,  4.0562, 15.2000),
    "wingspan_in": (82.5125,  3.7168, 82.5000),
    "weight_lbs":  (213.0749, 23.3749,211.0000),
    "ast_to_tov":  (1.1804,   0.6405,  1.0526),
}


class TrainingParams:
    """Normalization parameters derived from 2010-2021 training set."""

    def __init__(self) -> None:
        self.feat_stats: dict[str, tuple[float, float, float]] = dict(_HARDCODED_FEAT_STATS)
        print(f"  [Params] Loaded normalization stats for {len(self.feat_stats)} features")
        print(f"  [Params] DBPM training range: mean={self.feat_stats['dbpm'][0]:.1f} "
              f"±{self.feat_stats['dbpm'][1]:.1f}")


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _zscore_to_0_100(z: float) -> float:
    """Map z-score to 0-100 using ±3σ range."""
    return float(np.clip((z + 3.0) / 6.0 * 100, 0, 100))


def grade_label(mps: float) -> str:
    if mps >= GRADE_THRESHOLDS["S"]: return "S"
    if mps >= GRADE_THRESHOLDS["A"]: return "A"
    return "D"


def compute_srs_adj(srs: float | None) -> float:
    """±5 pt adjustment based on program SRS. Linear: SRS=35→+5, SRS=0→0, SRS<-35→-5."""
    if srs is None:
        return 0.0
    return float(np.clip(srs / 35.0 * 5.0, -5.0, 5.0))


def compute_availability_modifier(gp: float | None, team_games: int = 33) -> float:
    """Penalty for missing significant time. Only triggers below 70% GP threshold."""
    if gp is None:
        return 0.0
    pct = gp / team_games
    if pct >= 0.70:
        return 0.0
    return -min((0.70 - pct) * 25.0, 8.0)


def compute_age_penalty(draft_age: float) -> float:
    """
    Piecewise age adjustment based on empirical NBA outcome data (r=-0.217 vs VORP).

    Zone 1 (≤19.5): +7.0 — true underclassmen / first-year prospects, elite upside
    Zone 2 (19.5-20.0): +5.0 — young but closer to sophomore threshold
    Zone 3 (20.0-21.0): +2.0 — graduated credit
    Zone 4 (21.0-21.5): 0.0 — statistically neutral
    Zone 5 (21.5+): -3.5 per year above 21.5, cap -15

    Modified 2026-06-01: finer age split at 19.5 to distinguish true freshmen.
    """
    if draft_age <= 19.5:
        return 7.0
    elif draft_age <= 20.0:
        return 5.0
    elif draft_age <= 21.0:
        return 2.0
    elif draft_age <= 21.5:
        return 0.0
    else:
        return -min((draft_age - 21.5) * 3.5, 15.0)


def compute_height_floor_penalty(college_stats: dict) -> float:
    """
    Hard penalty for players whose wingspan doesn't compensate for limited height.
    Triggers when h<76" (6'4") AND WHR<1.04.
    Catches Flemings (74.5", 1.013). Exempts Tanner (70.75", 1.077 — long arms compensate).
    Returns 0.0 or -5.0.
    """
    h   = college_stats.get("height_in")
    whr = college_stats.get("wingspan_to_height_ratio")
    if h is None or whr is None:
        return 0.0
    if h < 76.0 and whr < 1.04:
        return -5.0
    return 0.0


def compute_combine_penalty(prospect: dict) -> float:
    """
    Penalty for players not invited to the main NBA Draft Combine.
    G League-only invitees are rated significantly lower by scouts.
    Only applies to players age > 21.5 at draft (young prospects are
    often excused from or projected too high for combine relevance).
    Returns 0.0 or -3.0.
    """
    if prospect.get("combine_invite", True):
        return 0.0
    draft_age = prospect.get("_draft_age", 99.0)
    if draft_age <= 21.5:
        return 0.0
    return -3.0


def compute_scout_tier_adjustment(
    tankathon_rank: "int | float | None",
    weight: float = 0.08,
) -> float:
    """
    Tier-flat scout consensus adjustment based on Tankathon rank.

    Validated via 11-fold LOYO (2020 excluded): T4 tier-flat
    transformation of draft consensus rank improves mean ρ by
    +0.029 overall and +0.037 for guards — the largest single
    validated improvement in this model's development.

    The T4 transform is immune to opportunity bias because it
    assigns the same score to all players within a tier,
    eliminating the minutes-gradient that inflates raw pick
    correlations with VORP.

    weight controls the additive contribution to MPS. Default
    0.08 is conservative — scales the 0-to-0.9 tier range to
    a max of +7.2 pts above neutral (rank unscored = 0.050 → 0.0).
    Neutral point is unranked score (0.050). Scores above/below
    neutral receive positive/negative adjustment respectively.

    Returns: float adjustment in MPS points (roughly -4 to +7)
    """
    if tankathon_rank is None or (
        isinstance(tankathon_rank, float) and np.isnan(tankathon_rank)
    ):
        tier_score = 0.050
    else:
        rank = float(tankathon_rank)
        if rank <= 0:
            tier_score = 0.050
        elif rank <= 5:
            tier_score = 0.900
        elif rank <= 14:
            tier_score = 0.700
        elif rank <= 30:
            tier_score = 0.500
        elif rank <= 60:
            tier_score = 0.250
        else:
            tier_score = 0.050

    # Center on neutral (unranked = 0.050) so unranked players
    # receive 0 adjustment, not a negative penalty
    neutral = 0.050
    return round((tier_score - neutral) * weight * 100, 2)


# ── Composite MPS computation ─────────────────────────────────────────────────

def _confidence_tier(n_features: int) -> str:
    """
    Classify partial score reliability by feature count.
    High:   ≥12 — most weight covered
    Medium:  6–11 — directional, use with caution
    Low:     3–5  — highly uncertain, board reference only
    """
    if n_features >= 12:
        return "high"
    if n_features >= 6:
        return "medium"
    return "low"


def compute_partial_mps(
    stats: dict,
    params: TrainingParams,
    min_features: int = 3,
) -> tuple[float, int] | None:
    """
    Attempt a partial weighted z-score composite using only populated features.
    Missing features are skipped entirely (not imputed to median like the full
    composite). Returns (score_0_to_100, n_features_used) or None if fewer than
    min_features are available.
    """
    weighted_z_sum = 0.0
    total_w = 0.0
    n_used = 0

    for feat, w in FEATURE_WEIGHTS.items():
        val = stats.get(feat)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue  # skip missing — do NOT impute
        mean, std, median = params.feat_stats[feat]
        z = (float(val) - mean) / max(std, 1e-8)
        weighted_z_sum += w * z
        total_w += w
        n_used += 1

    if n_used < min_features or total_w < 0.01:
        return None

    composite_z = weighted_z_sum / total_w
    return (_zscore_to_0_100(composite_z), n_used)


def _resolve_position_group(position: str) -> str:
    """Map prospect position abbreviation to model group (guard/big/wing)."""
    pos = position.upper()
    if "PG" in pos or "SG" in pos:
        return "guard"
    if "PF" in pos or pos.strip() == "C":
        return "big"
    return "wing"


def _get_feature_weights(position: str) -> dict[str, float]:
    """Return position-appropriate FEATURE_WEIGHTS. Wings use 50/50 guard+big blend."""
    group = _resolve_position_group(position)
    if group == "guard":
        return FEATURE_WEIGHTS_GUARDS
    if group == "big":
        return FEATURE_WEIGHTS_BIGS
    # Wing blend (validated over guard-only in position_split_backtest.py)
    blended = {
        f: FEATURE_WEIGHTS_GUARDS.get(f, 0) * 0.5 + FEATURE_WEIGHTS_BIGS.get(f, 0) * 0.5
        for f in FEATURE_WEIGHTS_GUARDS
    }
    total = sum(blended.values())
    return {k: v / total for k, v in blended.items()}


def compute_mps_for_prospect(
    stats: dict,
    params: TrainingParams,
    position: str = "",
) -> float:
    """
    Flat weighted z-score composite of 23 empirically-derived features.

    Selects position-appropriate weights (guard/big/wing blend) via
    _get_feature_weights(). Missing values imputed with training-set median
    (→ z≈0, neutral contribution). Weighted average z-score mapped to 0-100.

    Returns: mps_composite (0-100), before age/srs/availability adjustments.
    """
    weights = _get_feature_weights(position)
    weighted_z_sum = 0.0
    total_w = 0.0

    for feat, w in weights.items():
        mean, std, median = params.feat_stats[feat]
        val = stats.get(feat)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            val = median  # neutral imputation
        z = (float(val) - mean) / max(std, 1e-8)
        weighted_z_sum += w * z
        total_w += w

    composite_z = weighted_z_sum / max(total_w, 1e-8)
    return _zscore_to_0_100(composite_z)


# ── Orchestrator ──────────────────────────────────────────────────────────────

def score_all_prospects(prospects: list[dict]) -> pd.DataFrame:
    """
    Score all prospects:
      1. Load training normalization params
      2. Fetch 2025-26 program SRS
      3. Load Tankathon 2026 cache + NBA combine data
      4. For each prospect:
         a. Fetch CBB basic stats (scrape_college_stats)
         b. Fetch CBB supplement stats (scrape_supplement) — per, obpm, dbpm, ws_40, etc.
         c. Apply manual overrides (MANUAL_STATS)
         d. Fill gaps from Tankathon cache
         e. Derive ast_pct_over_usg, ast_to_tov
         f. Add physical measurements (wingspan, weight, standing_reach) from combine
         g. Compute MPS composite + adjustments
    Returns ranked DataFrame.
    """
    print("Loading training normalization params...")
    params = TrainingParams()

    print("\nLoading Tankathon 2026 data...")
    tankathon = _load_tankathon()

    print("\nFetching 2025-26 program SRS...")
    srs_2026 = scrape_program_srs(2026)
    print(f"  {len(srs_2026)} programs loaded")

    print("\nFetching 2026 NBA Combine measurements...")
    try:
        combine_lookup = get_full_combine_data()
        if combine_lookup:
            print(f"  {len(combine_lookup)} players with combine measurements")
        else:
            print("  No combine measurements — physical features use training medians")
    except Exception as _e:
        print(f"  Combine fetch failed: {_e}")
        combine_lookup = {}

    print("\nBuilding comp engine (historical similarity DB)...")
    try:
        comp_engine = CompEngine()
    except Exception as _ce:
        print(f"  CompEngine init failed: {_ce}")
        comp_engine = None

    rows = []
    for prospect in prospects:
        name          = prospect["player_name"]
        cbb_url       = prospect.get("cbb_url")
        college       = prospect.get("college", "")
        pos           = prospect.get("position", "")
        team_games    = int(prospect.get("team_games") or 33)
        withdrew      = bool(prospect.get("withdrew", False))
        prospect_note = prospect.get("note", "")

        tdata         = _lookup_tankathon(name, tankathon)
        tank_stats    = _extract_tankathon_stats(tdata) if tdata else {}
        tankathon_rank = tdata.get("tankathon_rank") if tdata else None
        _tank_combine  = tank_stats.pop("_tankathon_combine", {})

        # Draft age
        try:
            dob = date.fromisoformat(prospect["birth_date"])
            draft_age = (DRAFT_DATE_2026 - dob).days / 365.25
        except Exception:
            draft_age = 21.5

        print(f"\n  [{name}]  {pos}  age={draft_age:.2f}  college={college}")

        # ── No CBB URL (international) ────────────────────────────────────────
        if not cbb_url:
            if withdrew:
                rows.append(_null_row(name, pos, college, draft_age, "No college data",
                                      withdrew=True, tankathon_rank=tankathon_rank))
                continue
            print(f"    No CBB URL — attempting Tankathon partial score...")
            if tank_stats:
                intl_stats: dict = {}
                for tank_k, feat_k in [
                    ("tank_ts_pct",           "ts_pct"),
                    ("tank_trb_pg",           "trb_pg"),
                    ("tank_ast_pg",           "ast_pg"),
                    ("tank_blk_pg",           "blk_pg"),
                    ("tank_stl_pg",           "stl_pg"),
                    ("tank_pts",              "pts_pg"),
                    ("tank_fg_pct",           "fg_pct"),
                    ("tank_per",              "per"),
                    ("tank_ows",              "ows"),
                    ("tank_dws",              "dws"),
                    ("tank_ws_40",            "ws_40"),
                    ("tank_obpm",             "obpm"),
                    ("tank_dbpm",             "dbpm"),
                    ("tank_bpm",              "bpm_college"),
                    ("tank_ast_pct_over_usg", "ast_pct_over_usg"),
                    ("tank_ast_to_tov",       "ast_to_tov"),
                    ("ts_pct",                "ts_pct"),
                    ("ft_pct",                "ft_pct"),
                    ("games_played",          "games_played"),
                ]:
                    v = tank_stats.get(tank_k)
                    if v is not None and feat_k not in intl_stats:
                        intl_stats[feat_k] = v
                for phys_k in ("height_in", "wingspan_in", "weight_lbs", "standing_reach_in"):
                    v = _tank_combine.get(phys_k)
                    if v is not None:
                        intl_stats[phys_k] = v
                h   = intl_stats.get("height_in")
                wng = intl_stats.get("wingspan_in")
                sr  = intl_stats.get("standing_reach_in")
                if h and wng and h > 0:
                    intl_stats["wingspan_to_height_ratio"] = wng / h
                if h and sr and h > 0:
                    intl_stats["standing_reach_to_height_ratio"] = sr / h
                partial = compute_partial_mps(intl_stats, params, min_features=3)
                if partial is not None:
                    partial_score, n_feats = partial
                    age_pen_p      = compute_age_penalty(draft_age)
                    hf_pen         = compute_height_floor_penalty(intl_stats)
                    editorial_bump = EDITORIAL_BUMPS.get(name, 0.0)
                    mps_partial = float(np.clip(
                        partial_score + age_pen_p + hf_pen + editorial_bump, 0, 100
                    ))
                    grd_p = grade_label(mps_partial)
                    tier  = _confidence_tier(n_feats)
                    print(f"    [INTL PARTIAL] {n_feats} features ({tier}) — "
                          f"composite={partial_score:.1f}  age={age_pen_p:+.1f}"
                          f"  hf={hf_pen:+.1f}  → MPS={mps_partial:.1f}  {grd_p}")
                    _ic_algo = comp_engine.find_comp(
                        intl_stats, _resolve_position_group(pos), draft_age
                    ) if comp_engine else []
                    _ic_manual = MANUAL_COMPS.get(name)
                    if name in MANUAL_COMPS and _ic_manual is not None:
                        _ic1 = {"name": _ic_manual[0], "year": _ic_manual[1], "pick": _ic_manual[2], "similarity": None}
                        _ic2 = _ic_algo[0] if _ic_algo else {}
                    else:
                        _ic1 = _ic_algo[0] if _ic_algo else {}
                        _ic2 = _ic_algo[1] if len(_ic_algo) > 1 else {}
                    rows.append({
                        "player_name":      name,
                        "position":         pos,
                        "position_group":   _resolve_position_group(pos),
                        "college":          college,
                        "draft_age":        round(draft_age, 2),
                        "bpm_college":      intl_stats.get("bpm_college"),
                        "ts_pct":           intl_stats.get("ts_pct"),
                        "per":              intl_stats.get("per"),
                        "dbpm":             intl_stats.get("dbpm"),
                        "obpm":             intl_stats.get("obpm"),
                        "ws_40":            intl_stats.get("ws_40"),
                        "fg_pct":           intl_stats.get("fg_pct"),
                        "stl_pg":           intl_stats.get("stl_pg"),
                        "blk_pg":           intl_stats.get("blk_pg"),
                        "orb_pct":          intl_stats.get("orb_pct"),
                        "ast_pct":          intl_stats.get("ast_pct"),
                        "pts_pg":           intl_stats.get("pts_pg"),
                        "trb_pg":           intl_stats.get("trb_pg"),
                        "ast_pg":           intl_stats.get("ast_pg"),
                        "program_srs":      None,
                        "mps_composite":    round(partial_score, 1),
                        "srs_adj":          0.0,
                        "games_played":     intl_stats.get("games_played"),
                        "games_played_pct": None,
                        "avail_modifier":   0.0,
                        "age_penalty":      round(age_pen_p, 1),
                        "height_floor_pen": round(hf_pen, 1),
                        "combine_penalty":  0.0,
                        "mps":              round(mps_partial, 1),
                        "grade":            grd_p,
                        "confidence_tier":  tier,
                        "tankathon_rank":   tankathon_rank,
                        "withdrew":         withdrew,
                        "note":             (
                            f"INTL PARTIAL — {n_feats} features ({tier}), "
                            f"no CBB data; treat as directional"
                            + (f"; {prospect_note}" if prospect_note else "")
                        ),
                        "comp1_name":  _ic1.get("name"),
                        "comp1_year":  _ic1.get("year"),
                        "comp1_pick":  _ic1.get("pick"),
                        "comp1_sim":   _ic1.get("similarity"),
                        "comp2_name":  _ic2.get("name"),
                        "comp2_year":  _ic2.get("year"),
                        "comp2_pick":  _ic2.get("pick"),
                        "comp2_sim":   _ic2.get("similarity"),
                    })
                    continue
            print(f"    No CBB URL, no Tankathon data — N/A")
            rows.append(_null_row(name, pos, college, draft_age, "No college data",
                                  withdrew=withdrew, tankathon_rank=tankathon_rank))
            continue

        # ── Fetch CBB basic stats (cached) ───────────────────────────────────
        _cached_cbb = _load_cbb_stats_cache(cbb_url)
        if _cached_cbb is None:
            try:
                college_stats = scrape_college_stats(cbb_url)
                _write_cbb_stats_cache(cbb_url, college_stats)
            except Exception as e:
                print(f"    CBB fetch error: {e}")
                college_stats = None
        else:
            college_stats = _cached_cbb if _cached_cbb else None

        # ── Fetch CBB supplement stats (cached — only new HTTP on first run) ──
        if college_stats is not None:
            try:
                supp = _supp_load(cbb_url)
                if supp is None:
                    supp = scrape_supplement(cbb_url)
                    _supp_write(cbb_url, supp)
                if supp:
                    for k, v in supp.items():
                        if v is not None and college_stats.get(k) is None:
                            college_stats[k] = v
                    print(f"    [Supp] per={supp.get('per')}  obpm={supp.get('obpm')}  "
                          f"dbpm={supp.get('dbpm')}  ws_40={supp.get('ws_40')}  "
                          f"fg%={supp.get('fg_pct')}")
            except Exception as e:
                print(f"    [Supp] Error: {e}")

        # ── Apply manual stat overrides ───────────────────────────────────────
        if name in MANUAL_STATS:
            if college_stats is None:
                college_stats = {}
            for k, v in MANUAL_STATS[name].items():
                if v is not None:
                    college_stats[k] = v
                elif k not in college_stats:
                    college_stats[k] = v

        # ── Tankathon rescue if CBB completely failed ─────────────────────────
        if not college_stats:
            if tank_stats.get("ts_pct") is not None:
                college_stats = {}
                # Primary stats from Tankathon (best-effort — may be different scale)
                for tank_k, stat_k in [
                    ("tank_ts_pct", "ts_pct"), ("tank_trb_pg", "trb_pg"),
                    ("tank_ast_pg", "ast_pg"), ("tank_blk_pg", "blk_pg"),
                    ("tank_stl_pg", "stl_pg"), ("tank_pts", "pts_pg"),
                    ("tank_fg_pct", "fg_pct"), ("tank_per", "per"),
                    ("tank_obpm", "obpm"), ("tank_dbpm", "dbpm"),
                    ("tank_ws_40", "ws_40"), ("tank_ows", "ows"),
                    ("games_played", "games_played"),
                ]:
                    if tank_stats.get(tank_k) is not None:
                        college_stats[stat_k] = tank_stats[tank_k]
                print(f"    [Tankathon] Rescue: ts_pct={college_stats.get('ts_pct')}")
            else:
                print(f"    CBB fetch failed, no Tankathon rescue available")
                rows.append(_null_row(name, pos, college, draft_age, "CBB fetch failed",
                                      withdrew=withdrew, tankathon_rank=tankathon_rank))
                continue

        # ── Fill gaps from Tankathon (for fields CBB didn't return) ──────────
        _bpm_before_fill = college_stats.get("bpm_college")
        _tank_fill = {
            "tank_bpm":           "bpm_college",  # scale verified r=1.000 — safe as primary
            "tank_per":           "per",
            "tank_obpm":          "obpm",
            "tank_dbpm":          "dbpm",
            "tank_ws_40":         "ws_40",
            "tank_ows":           "ows",
            "tank_fg_pct":        "fg_pct",
            "tank_trb_pg":        "trb_pg",
            "tank_blk_pg":        "blk_pg",
            "tank_stl_pg":        "stl_pg",
            "tank_ast_pg":        "ast_pg",
            "tank_ft_pct":        "ft_pct",
            "games_played":       "games_played",
            "ts_pct":             "ts_pct",
        }
        for tank_k, stat_k in _tank_fill.items():
            if college_stats.get(stat_k) is None and tank_stats.get(tank_k) is not None:
                college_stats[stat_k] = tank_stats[tank_k]
        _bpm_from_tankathon = (
            _bpm_before_fill is None and college_stats.get("bpm_college") is not None
            and name not in MANUAL_STATS
        )

        # ── Promote Tankathon to primary for Group A stats (same source, same scale) ──
        # scale_verification.py confirmed r=1.000 for these stats — identical source as CBB.
        # Overwrites potentially stale CBB cache values with real-time Tankathon data.
        # Group C stats (ts_pct, ows, dws, pts_pg, ast_pg, fg_pct) excluded — different scale.
        # Skip promotion for any stat explicitly set in MANUAL_STATS — override takes priority.
        _manual_keys = set(MANUAL_STATS.get(name, {}).keys())
        if tank_stats:
            for _tank_k, _stat_k in [
                ("tank_bpm",     "bpm_college"),
                ("tank_obpm",    "obpm"),
                ("tank_dbpm",    "dbpm"),
                ("tank_per",     "per"),
                ("tank_ws_40",   "ws_40"),
                ("tank_trb_pg",  "trb_pg"),
                ("tank_stl_pg",  "stl_pg"),
                ("tank_blk_pg",  "blk_pg"),
                ("tank_fg3_pct", "fg3_pct"),
            ]:
                if _stat_k in _manual_keys:
                    continue
                _tv = tank_stats.get(_tank_k)
                if _tv is not None:
                    college_stats[_stat_k] = _tv

        # ── Derive composite-ready stats ──────────────────────────────────────
        # ast_pct_over_usg
        if college_stats.get("ast_pct_over_usg") is None:
            apc = college_stats.get("ast_pct")
            usg = college_stats.get("usg_pct")
            if apc is not None and usg and usg > 0:
                college_stats["ast_pct_over_usg"] = apc / usg
            elif tank_stats.get("tank_ast_pct_over_usg") is not None:
                college_stats["ast_pct_over_usg"] = tank_stats["tank_ast_pct_over_usg"]
        # ast_to_tov
        if college_stats.get("ast_to_tov") is None:
            apg = college_stats.get("ast_pg")
            tpg = college_stats.get("tov_pg")
            if apg is not None and tpg and tpg > 0:
                college_stats["ast_to_tov"] = apg / tpg
            elif tank_stats.get("tank_ast_to_tov") is not None:
                college_stats["ast_to_tov"] = tank_stats["tank_ast_to_tov"]

        # ── Physical measurements (wingspan, weight, standing_reach) ──────────
        # Priority: NBA combine API > Tankathon combine cache > training median (imputed)
        _lookup_name   = prospect.get("combine_name") or name
        _api_combine   = lookup_player(combine_lookup, _lookup_name)
        _manual_combine = prospect.get("combine") or {}
        combine = {**_tank_combine, **_api_combine, **_manual_combine}

        for phys_k in ("wingspan_in", "weight_lbs", "standing_reach_in", "height_in"):
            if college_stats.get(phys_k) is None and combine.get(phys_k) is not None:
                college_stats[phys_k] = combine[phys_k]
                print(f"    [Physical] {phys_k}={combine[phys_k]:.1f}")

        _h  = college_stats.get("height_in")
        _w  = college_stats.get("wingspan_in")
        _sr = college_stats.get("standing_reach_in")
        if _h and _h > 0:
            if _w is not None and college_stats.get("wingspan_to_height_ratio") is None:
                college_stats["wingspan_to_height_ratio"] = _w / _h
            if _sr is not None and college_stats.get("standing_reach_to_height_ratio") is None:
                college_stats["standing_reach_to_height_ratio"] = _sr / _h

        # ── Resolve program SRS ───────────────────────────────────────────────
        school_name = college_stats.get("school_name") or college
        srs = _resolve_srs(school_name, srs_2026)
        college_stats["program_srs"] = srs

        bpm = college_stats.get("bpm_college")
        ts  = college_stats.get("ts_pct")
        per = college_stats.get("per")
        dbpm = college_stats.get("dbpm")
        print(f"    BPM={bpm}  TS%={ts}  PER={per}  DBPM={dbpm}  SRS={srs}")

        # BPM null → attempt partial scoring from available features
        if bpm is None:
            if withdrew:
                rows.append(_null_row(name, pos, college, draft_age,
                                      "BPM not computed — insufficient games",
                                      withdrew=True, tankathon_rank=tankathon_rank))
                continue
            partial = compute_partial_mps(college_stats, params, min_features=3)
            if partial is not None:
                partial_score, n_feats = partial
                srs_adj_p      = compute_srs_adj(srs)
                age_pen_p      = compute_age_penalty(draft_age)
                editorial_bump = EDITORIAL_BUMPS.get(name, 0.0)
                mps_partial = float(np.clip(
                    partial_score + srs_adj_p + age_pen_p + editorial_bump, 0, 100
                ))
                grd_p = grade_label(mps_partial)
                tier  = _confidence_tier(n_feats)
                print(f"    [PARTIAL] {n_feats} features ({tier}) — "
                      f"composite={partial_score:.1f}  srs={srs_adj_p:+.1f}  "
                      f"age={age_pen_p:+.1f}  → MPS={mps_partial:.1f}  {grd_p}")
                _pc_algo = comp_engine.find_comp(
                    college_stats, _resolve_position_group(pos), draft_age
                ) if comp_engine else []
                _pc_manual = MANUAL_COMPS.get(name)
                if name in MANUAL_COMPS and _pc_manual is not None:
                    _pc1 = {"name": _pc_manual[0], "year": _pc_manual[1], "pick": _pc_manual[2], "similarity": None}
                    _pc2 = _pc_algo[0] if _pc_algo else {}
                else:
                    _pc1 = _pc_algo[0] if _pc_algo else {}
                    _pc2 = _pc_algo[1] if len(_pc_algo) > 1 else {}
                rows.append({
                    "player_name":      name,
                    "position":         pos,
                    "position_group":   _resolve_position_group(pos),
                    "college":          college,
                    "draft_age":        round(draft_age, 2),
                    "bpm_college":      None,
                    "ts_pct":           college_stats.get("ts_pct"),
                    "per":              college_stats.get("per"),
                    "dbpm":             college_stats.get("dbpm"),
                    "obpm":             college_stats.get("obpm"),
                    "ws_40":            college_stats.get("ws_40"),
                    "fg_pct":           college_stats.get("fg_pct"),
                    "stl_pg":           college_stats.get("stl_pg"),
                    "blk_pg":           college_stats.get("blk_pg"),
                    "orb_pct":          college_stats.get("orb_pct"),
                    "ast_pct":          college_stats.get("ast_pct"),
                    "pts_pg":           college_stats.get("pts_pg"),
                    "trb_pg":           college_stats.get("trb_pg"),
                    "ast_pg":           college_stats.get("ast_pg"),
                    "program_srs":      srs,
                    "mps_composite":    round(partial_score, 1),
                    "srs_adj":          round(srs_adj_p, 1),
                    "games_played":     college_stats.get("games_played"),
                    "games_played_pct": None,
                    "avail_modifier":   0.0,
                    "age_penalty":      round(age_pen_p, 1),
                    "height_floor_pen": 0.0,
                    "combine_penalty":  0.0,
                    "mps":              round(mps_partial, 1),
                    "grade":            grd_p,
                    "confidence_tier":  tier,
                    "tankathon_rank":   tankathon_rank,
                    "withdrew":         withdrew,
                    "note":             (
                        f"PARTIAL DATA — {n_feats} features ({tier}), no BPM; treat as directional"
                        + (f"; {prospect_note}" if prospect_note else "")
                    ),
                    "comp1_name":  _pc1.get("name"),
                    "comp1_year":  _pc1.get("year"),
                    "comp1_pick":  _pc1.get("pick"),
                    "comp1_sim":   _pc1.get("similarity"),
                    "comp2_name":  _pc2.get("name"),
                    "comp2_year":  _pc2.get("year"),
                    "comp2_pick":  _pc2.get("pick"),
                    "comp2_sim":   _pc2.get("similarity"),
                })
            else:
                print(f"    BPM not computed — insufficient games/data")
                rows.append(_null_row(name, pos, college, draft_age,
                                      "BPM not computed — insufficient games",
                                      withdrew=withdrew, tankathon_rank=tankathon_rank))
            continue

        # ── Compute MPS ───────────────────────────────────────────────────────
        mps_composite    = compute_mps_for_prospect(college_stats, params, pos)
        srs_adj          = compute_srs_adj(srs)
        gp               = college_stats.get("games_played")
        avail_mod        = compute_availability_modifier(gp, team_games)
        age_pen          = compute_age_penalty(draft_age)
        height_floor_pen = compute_height_floor_penalty(college_stats)
        combine_pen      = compute_combine_penalty({**prospect, "_draft_age": draft_age})
        scout_adj        = compute_scout_tier_adjustment(tankathon_rank)
        editorial_bump   = EDITORIAL_BUMPS.get(name, 0.0)
        mps_final        = float(np.clip(
            mps_composite + srs_adj + avail_mod + age_pen
            + height_floor_pen + combine_pen + scout_adj + editorial_bump,
            0, 100
        ))
        grd           = grade_label(mps_final)

        # ── Build notes string ────────────────────────────────────────────────
        notes = []
        if avail_mod < 0.0:
            gp_pct = gp / team_games if gp is not None else None
            pct_s  = f"{gp_pct:.0%}" if gp_pct is not None else "?"
            notes.append(f"Availability: {pct_s} GP ({gp:.0f}/{team_games}g)")
        if age_pen < 0.0:
            notes.append(f"Age penalty {age_pen:+.1f} ({draft_age:.1f}y)")
        if age_pen > 0.0:
            notes.append(f"Youth bonus +{age_pen:.1f}")
        if height_floor_pen < 0.0:
            _h_val  = college_stats.get("height_in")
            _whr_val = college_stats.get("wingspan_to_height_ratio")
            notes.append(
                f"Height floor {height_floor_pen:+.1f} "
                f"(h={_h_val:.1f}\", WHR={_whr_val:.3f})"
            )
        if combine_pen < 0.0:
            notes.append(f"Combine penalty {combine_pen:+.1f} (G League invite only)")
        if abs(scout_adj) > 1.0:
            rank_str = f"Tank #{int(tankathon_rank)}" if tankathon_rank is not None else "unranked"
            notes.append(f"Scout tier adj {scout_adj:+.1f} ({rank_str})")
        if _bpm_from_tankathon:
            notes.append("BPM from Tankathon (CBB unavailable — same scale confirmed)")
        if name in MANUAL_STATS:
            notes.append("Stats: partial manual override (BPM from BBRef)")
        note_str = "; ".join(notes)
        prefix = ""
        if withdrew:
            prefix = "WITHDREW — not in 2026 draft"
        elif prospect_note:
            prefix = prospect_note
        if prefix and note_str:
            note_str = prefix + "; " + note_str
        elif prefix:
            note_str = prefix

        if _resolve_position_group(pos) == "wing":
            wing_note = (
                "Wing position: 50/50 weight blend (guard/big) — "
                "physical projection not fully captured in model"
            )
            note_str = (note_str + "; " + wing_note) if note_str else wing_note

        print(f"    composite={mps_composite:.1f}  srs={srs_adj:+.1f}  "
              f"avail={avail_mod:+.1f}  age={age_pen:+.1f}  "
              f"height_floor={height_floor_pen:+.1f}  combine={combine_pen:+.1f}  "
              f"scout={scout_adj:+.1f}  edit={editorial_bump:+.1f}  → MPS={mps_final:.1f}  {grd}")

        gp_pct_val = round(gp / team_games, 3) if gp is not None else None

        # ── Comp lookup ───────────────────────────────────────────────────────
        _algo_comps = comp_engine.find_comp(
            college_stats, _resolve_position_group(pos), draft_age
        ) if comp_engine else []
        _manual = MANUAL_COMPS.get(name)  # None = not in dict; tuple = manual set
        if name in MANUAL_COMPS and _manual is not None:
            _comp1 = {"name": _manual[0], "year": _manual[1], "pick": _manual[2], "similarity": None}
            _comp2 = _algo_comps[0] if _algo_comps else {}
        else:
            _comp1 = _algo_comps[0] if _algo_comps else {}
            _comp2 = _algo_comps[1] if len(_algo_comps) > 1 else {}

        rows.append({
            "player_name":      name,
            "position":         pos,
            "position_group":   _resolve_position_group(pos),
            "confidence_tier":  "full",
            "college":          college,
            "draft_age":        round(draft_age, 2),
            "bpm_college":      bpm,
            "ts_pct":           ts,
            "per":              per,
            "dbpm":             dbpm,
            "obpm":             college_stats.get("obpm"),
            "ws_40":            college_stats.get("ws_40"),
            "fg_pct":           college_stats.get("fg_pct"),
            "stl_pg":           college_stats.get("stl_pg"),
            "blk_pg":           college_stats.get("blk_pg"),
            "orb_pct":          college_stats.get("orb_pct"),
            "ast_pct":          college_stats.get("ast_pct"),
            "pts_pg":           college_stats.get("pts_pg"),
            "trb_pg":           college_stats.get("trb_pg"),
            "ast_pg":           college_stats.get("ast_pg"),
            "program_srs":      srs,
            "mps_composite":    round(mps_composite, 1),
            "srs_adj":          round(srs_adj, 1),
            "games_played":     gp,
            "games_played_pct": gp_pct_val,
            "avail_modifier":   round(avail_mod, 1),
            "age_penalty":      round(age_pen, 1),
            "height_floor_pen": round(height_floor_pen, 1),
            "combine_penalty":  round(combine_pen, 1),
            "scout_adj":        round(scout_adj, 2),
            "editorial_bump":   round(editorial_bump, 1),
            "mps":              round(mps_final, 1),
            "grade":            grd,
            "tankathon_rank":   tankathon_rank,
            "withdrew":         withdrew,
            "note":             note_str,
            "comp1_name":       _comp1.get("name"),
            "comp1_year":       _comp1.get("year"),
            "comp1_pick":       _comp1.get("pick"),
            "comp1_sim":        _comp1.get("similarity"),
            "comp2_name":       _comp2.get("name"),
            "comp2_year":       _comp2.get("year"),
            "comp2_pick":       _comp2.get("pick"),
            "comp2_sim":        _comp2.get("similarity"),
        })

    result = pd.DataFrame(rows)
    withdrew_mask = result["withdrew"].fillna(False).astype(bool)
    active_df  = result[~withdrew_mask].sort_values("mps", ascending=False, na_position="last").copy()
    wd_df      = result[withdrew_mask].sort_values("mps",  ascending=False, na_position="last").copy()
    active_df.insert(0, "rank", range(1, len(active_df) + 1))
    wd_df.insert(0, "rank", [None] * len(wd_df))
    result = pd.concat([active_df, wd_df], ignore_index=True)

    # Append divergence notes
    if "tankathon_rank" in result.columns:
        for idx, row in result.iterrows():
            t_rank = row.get("tankathon_rank")
            m_rank = row["rank"]
            if m_rank is None or pd.isna(row.get("mps")) or t_rank is None or pd.isna(t_rank):
                continue
            diff = int(m_rank) - int(t_rank)
            if abs(diff) > 10:
                direction = "above" if diff > 0 else "below"
                div_note = (f"Model #{m_rank} vs Tankathon #{int(t_rank)} "
                            f"({abs(diff)} spots {direction} consensus)")
                existing = result.at[idx, "note"] or ""
                sep = "; " if existing else ""
                result.at[idx, "note"] = existing + sep + div_note

    return result


def _null_row(name: str, pos: str, college: str, draft_age: float,
              note: str, *, withdrew: bool = False,
              tankathon_rank: int | None = None) -> dict:
    age_pen = compute_age_penalty(draft_age)
    prefix  = "WITHDREW — not in 2026 draft" if withdrew else ""
    full_note = (prefix + "; " + note) if (prefix and note) else (prefix or note)
    return {
        "player_name":      name,
        "position":         pos,
        "position_group":   _resolve_position_group(pos),
        "confidence_tier":  "none",
        "college":          college,
        "draft_age":        round(draft_age, 2),
        "bpm_college":      None,
        "ts_pct":           None,
        "per":              None,
        "dbpm":             None,
        "pts_pg":           None,
        "trb_pg":           None,
        "ast_pg":           None,
        "program_srs":      None,
        "mps_composite":    None,
        "srs_adj":          None,
        "games_played":     None,
        "games_played_pct": None,
        "avail_modifier":   0.0,
        "age_penalty":      round(age_pen, 1),
        "mps":              None,
        "grade":            "N/A",
        "tankathon_rank":   tankathon_rank,
        "withdrew":         withdrew,
        "note":             full_note,
    }


# ── Output ────────────────────────────────────────────────────────────────────

def print_big_board(df: pd.DataFrame, top_n: int = 35) -> None:
    print("\n" + "=" * 100)
    print("MPS 2026 Big Board  (Model: empirical weighted composite, ρ=0.430 holdout)")
    print(f"Draft: {DRAFT_DATE_2026}  |  Features: 23 stats, weights ∝ Spearman r vs NBA VORP yr2-5")
    print("=" * 100)
    header = (f"{'Rk':>3}  {'Player':<22}  {'Pos':>3}  {'Age':>5}  "
              f"{'BPM':>6}  {'PER':>5}  {'DBPM':>5}  {'Comp':>5}  "
              f"{'SRS':>4}  {'Avl':>4}  {'Age':>5}  {'MPS':>5}  Gr")
    print(header)
    print("-" * 100)

    for _, row in df.head(top_n).iterrows():
        bpm_s  = f"{row.bpm_college:+.1f}" if pd.notna(row.bpm_college)  else "   N/A"
        per_s  = f"{row.per:.1f}"          if pd.notna(row.per)          else "  N/A"
        dbpm_s = f"{row.dbpm:+.1f}"        if pd.notna(row.dbpm)         else "  N/A"
        comp_s = f"{row.mps_composite:.1f}" if pd.notna(row.mps_composite) else "  N/A"
        srs_s  = f"{row.srs_adj:+.1f}"     if pd.notna(row.get("srs_adj", None)) else "+0.0"
        avl_s  = f"{row.avail_modifier:+.1f}" if pd.notna(row.get("avail_modifier", None)) else "+0.0"
        age_s  = f"{row.age_penalty:+.1f}"  if pd.notna(row.get("age_penalty", None)) else "+0.0"
        mps_s  = f"{row.mps:.1f}"          if pd.notna(row.mps)          else "  N/A"
        note   = f"  [{row.note}]" if row.note else ""
        print(f"{row['rank']:>3}  {row.player_name:<22}  {row.position:>3}  "
              f"{row.draft_age:>5.1f}  {bpm_s:>6}  {per_s:>5}  {dbpm_s:>5}  "
              f"{comp_s:>5}  {srs_s:>4}  {avl_s:>4}  {age_s:>5}  {mps_s:>5}  {row.grade}{note}")

    if len(df) > top_n:
        print(f"\n  ... {len(df) - top_n} more rows in CSV")

    # Withdrew section
    if "withdrew" in df.columns:
        wd = df[df["withdrew"] == True]
        if not wd.empty:
            print("\nWithdrew (not in 2026 draft):")
            for _, r in wd.iterrows():
                mps_s = f"MPS={r.mps:.1f}" if pd.notna(r.mps) else "N/A"
                print(f"  {r.player_name} ({mps_s})")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("MPS 2026 Draft Scorer")
    print(f"Draft: {DRAFT_DATE_2026}  |  Prospects: {len(PROSPECTS_2026)}")
    print(f"Model: empirical flat-composite (holdout ρ=0.430 vs {0.241:.3f} baseline)")
    print()

    df = score_all_prospects(PROSPECTS_2026)
    print_big_board(df, top_n=35)

    path = OUTPUT_DIR / "2026_big_board.csv"
    df.to_csv(path, index=False)
    print(f"\nSaved: {path}")

    print("\nGrade distribution:")
    for grade in ["S", "A", "B", "C", "D", "N/A"]:
        n = (df.grade == grade).sum()
        if n:
            print(f"  {grade}: {n} player{'s' if n > 1 else ''}")

    print("\nAge adjustments applied:")
    if "age_penalty" in df.columns:
        for _, r in df[df["age_penalty"] != 0.0].dropna(subset=["mps"]).iterrows():
            print(f"  {r.player_name} ({r.draft_age:.1f}y): {r.age_penalty:+.1f}")

    # ── Birth date validation flags ───────────────────────────────────────────
    try:
        _tank_raw = json.load(TANKATHON_CACHE.open())
        _tank_ages = {
            p["player_name"]: p["bio"]["draft_age"]
            for p in _tank_raw.get("players", {}).values()
            if p.get("bio", {}).get("draft_age") is not None
        }
        flagged_dobs = []
        for p in PROSPECTS_2026:
            if p.get("withdrew"):
                continue
            name = p["player_name"]
            tank_age = _tank_ages.get(name)
            if tank_age is None:
                continue
            dob = date.fromisoformat(p["birth_date"])
            model_age = (DRAFT_DATE_2026 - dob).days / 365.25
            delta = model_age - tank_age
            if abs(delta) > 0.5:
                flagged_dobs.append((name, model_age, tank_age, delta, p["birth_date"]))
        if flagged_dobs:
            print("\nBIRTH DATE VALIDATION FLAGS (|Δ| > 0.5 years):")
            for name, m_age, t_age, delta, dob in sorted(flagged_dobs, key=lambda x: -abs(x[3])):
                print(f"  {name}: model_age={m_age:.2f}, tank_age={t_age:.2f}, Δ={delta:+.2f}")
                print(f"    birth_date in scorer.py: {dob}")
                print(f"    ACTION NEEDED: verify against Wikipedia/RealGM before draft")
    except Exception:
        pass


if __name__ == "__main__":
    main()
