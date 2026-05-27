"""
mps/scorer.py

MPS 2026 Draft Big Board — Score current prospects using the validated model.

Validated architecture (from backtest.py, Spearman ρ=0.325 on 2022 holdout):
    MPS_base = college_efficiency_pillar (49%)
             + age_x_production_pillar  (41%)
             + competition_ctx_pillar   ( 5%)
             + nba_fit_pillar           ( 5%)
    avail_mod = GP% penalty (0 to -8 pts; only when GP < 70% of team schedule)
    age_pen   = -10 pts if draft_age ≥ 23, else 0
    MPS       = clip(MPS_base + physical_adj + avail_mod + age_pen, 0, 100)

Normalization uses training-set params (2010-2021) loaded from
mps/data/mps_dataset_raw.csv at startup — ensures new prospects are scored
on the same scale as the backtest validation.

Run:
    cd /home/spencer/Workspace/macfax
    backend/.venv/bin/python -m mps.scorer
"""

from __future__ import annotations

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
from mps.combine_scraper import get_full_combine_data, lookup_player

# ── Paths ──────────────────────────────────────────────────────────────────────

MPS_DIR    = Path(__file__).parent
DATA_DIR   = MPS_DIR / "data"
OUTPUT_DIR = MPS_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

DATASET = DATA_DIR / "mps_dataset_raw.csv"

# ── Model constants (validated from backtest.py) ──────────────────────────────

DRAFT_DATE_2026 = date(2026, 6, 23)  # 2026 NBA Draft

# Optimized weights: grid-search + COBYLA, maximizing Spearman ρ on 2010-2021
OPTIMIZED_WEIGHTS = {
    "college_efficiency": 0.488,
    "age_x_production":   0.412,
    "competition_ctx":    0.050,
    "nba_fit":            0.050,
}

# Grade thresholds (training-set percentiles: top 8/25/45/65%)
GRADE_THRESHOLDS = {"S": 66.3, "A": 56.2, "B": 50.6, "C": 44.9}

# Efficiency pillar: correlation-proportional weights (from backtest Pearson r)
_EFF_FEATS = ["ts_pct", "stl_pct", "dws", "blk_pct", "ast_pct", "orb_pct"]
_EFF_CORR  = np.array([0.155, 0.149, 0.111, 0.105, 0.099, 0.081])
_EFF_WGTS  = _EFF_CORR / _EFF_CORR.sum()

_FIT_FEATS = ["three_par", "ft_pct", "ast_pct"]

# ── Manual stat overrides ─────────────────────────────────────────────────────
# Used when sports-reference CBB doesn't publish BPM (below games threshold)
# or when page data is missing.  Non-None values override scraped.
# None values fall through to scraper result or training-set imputation.

MANUAL_STATS: dict[str, dict] = {
    "Cameron Boozer": {
        # Source: BBRef/Yahoo Sports confirmed 17.8 (highest since Zion Williamson 2019).
        # BBRef withholds BPM display below a GP threshold but it is computed;
        # 17.8 is the correct BBRef-scale value, consistent with the training set.
        # (Previous value 20.1 was EvanMiya BPR — different metric, different scale.)
        "bpm_college":        17.8,
        "ts_pct":             0.653,
        "stl_pct":            0.032,
        "orb_pct":            0.125,
        "blk_pct":            0.038,
        "ast_pct":            0.264,
        "ft_pct":             0.790,
        "usg_pct":            30.5,
        "three_par":          None,   # imputed with training median
        "dws":                None,   # imputed with training median
        "school_name":        "Duke",
        "college_season_year": 2026,
        "games_played":       None,   # GP unknown; avail_mod = 0
    },
}

# ── 2026 Prospect List ────────────────────────────────────────────────────────
# Full 70-player official NBA Draft Combine invitee list (domestic only).
# birth_date: exact where confirmed (✓), approximate (YYYY-MM-01) where not.
# team_games: actual games in team schedule; default 33 if omitted.
# combine: populate from nbadraft.net/NBA.com after May 2026 combine.

_CBB = "https://www.sports-reference.com/cbb/players/{slug}.html"

PROSPECTS_2026 = [
    # ── Youngest tier (born 2007) ─────────────────────────────────────────────
    {
        "player_name": "Cameron Boozer",
        "birth_date":  "2007-07-18",   # ✓ confirmed; youngest-ish, 18.93 at draft
        "position":    "PF",
        "college":     "Duke",
        "cbb_url":     _CBB.format(slug="cameron-boozer-3"),  # -1 is different player
        "team_games":  38,             # Duke ran deep in tournament
        "combine":     None,
    },
    {
        "player_name": "Jayden Quaintance",
        "birth_date":  "2007-07-11",   # ✓ confirmed; youngest in class, ~18.95
        "position":    "PF",
        "college":     "Kentucky",
        "cbb_url":     _CBB.format(slug="jayden-quaintance-1"),
        "combine":     None,
        "note":        "ACL injury (Mar 2025 at ASU) — Kentucky season severely limited; scraped GP/BPM may be accurate or incomplete",
    },
    {
        "player_name": "Keaton Wagler",
        "birth_date":  "2007-02-03",   # ✓ confirmed
        "position":    "PG",
        "college":     "Illinois",
        "cbb_url":     _CBB.format(slug="keaton-wagler-1"),
        "combine":     None,
    },
    {
        "player_name": "AJ Dybantsa",
        "birth_date":  "2007-01-29",   # ✓ confirmed
        "position":    "SF",
        "college":     "BYU",
        "cbb_url":     _CBB.format(slug="aj-dybantsa-1"),
        "team_games":  33,
        "combine":     None,
    },
    {
        "player_name": "Darryn Peterson",
        "birth_date":  "2007-01-17",   # ✓ confirmed
        "position":    "PG",
        "college":     "Kansas",
        "cbb_url":     _CBB.format(slug="darryn-peterson-1"),
        "team_games":  31,             # Kansas schedule; Peterson missed games (cramping)
        "combine":     None,
    },
    {
        "player_name": "Koa Peat",
        "birth_date":  "2007-01-20",   # ✓ confirmed
        "position":    "PF",
        "college":     "Arizona",
        "cbb_url":     _CBB.format(slug="koa-peat-1"),
        "combine":     None,
    },
    {
        "player_name": "Kingston Flemings",
        "birth_date":  "2007-01-03",   # ✓ confirmed
        "position":    "SG",
        "college":     "Houston",
        "cbb_url":     _CBB.format(slug="kingston-flemings-1"),
        "combine":     None,
    },
    # ── 2006-born tier ────────────────────────────────────────────────────────
    {
        "player_name": "Nate Ament",
        "birth_date":  "2006-12-10",   # ✓ confirmed
        "position":    "PF",
        "college":     "Tennessee",
        "cbb_url":     _CBB.format(slug="nate-ament-1"),
        "combine":     None,
    },
    {
        "player_name": "Darius Acuff Jr.",
        "birth_date":  "2006-11-16",   # ✓ confirmed; Arkansas, NOT EKU
        "position":    "PG",
        "college":     "Arkansas",
        "cbb_url":     _CBB.format(slug="darius-acuff-jr-1"),
        "combine":     None,
    },
    {
        "player_name": "Caleb Wilson",
        "birth_date":  "2006-07-18",   # ✓ confirmed
        "position":    "PF",
        "college":     "UNC",
        "cbb_url":     _CBB.format(slug="caleb-wilson-1"),
        "combine":     None,
    },
    {
        "player_name": "Mikel Brown Jr.",
        "birth_date":  "2006-04-03",   # ✓ confirmed
        "position":    "PG",
        "college":     "Louisville",
        "cbb_url":     _CBB.format(slug="mikel-brown-jr-1"),
        "combine":     None,
    },
    {
        "player_name": "Isaiah Evans",
        "birth_date":  "2006-06-01",   # ~ approximate
        "position":    "SG",
        "college":     "Duke",
        "cbb_url":     _CBB.format(slug="isaiah-evans-1"),
        "combine":     None,
    },
    {
        "player_name": "Christian Anderson",
        "birth_date":  "2006-06-01",   # ~ approximate
        "position":    "PG",
        "college":     "Texas Tech",
        "cbb_url":     _CBB.format(slug="christian-anderson-1"),
        "combine":     None,
    },
    {
        "player_name": "Meleek Thomas",
        "birth_date":  "2006-06-01",   # ~ approximate
        "position":    "SG",
        "college":     "Arkansas",
        "cbb_url":     _CBB.format(slug="meleek-thomas-1"),
        "combine":     None,
    },
    {
        "player_name": "Dailyn Swain",
        "birth_date":  "2005-07-15",   # ✓ confirmed; transferred Xavier→Texas
        "position":    "SF",
        "college":     "Texas",
        "cbb_url":     _CBB.format(slug="dailyn-swain-2"),  # -1 was Xavier page
        "combine":     None,
    },
    {
        "player_name": "Henri Veesaar",
        "birth_date":  "2006-01-01",   # ~ approximate
        "position":    "C",
        "college":     "North Carolina",
        "cbb_url":     _CBB.format(slug="henri-veesaar-1"),
        "combine":     None,
    },
    {
        "player_name": "Malachi Moreno",
        "birth_date":  "2006-01-01",   # ~ approximate
        "position":    "C",
        "college":     "Kentucky",
        "cbb_url":     _CBB.format(slug="malachi-moreno-1"),
        "combine":     None,
        "withdrew":    True,           # returning to Kentucky per CBS Sports May 2026
    },
    # ── 2005-born tier ────────────────────────────────────────────────────────
    {
        "player_name": "Flory Bidunga",
        "birth_date":  "2005-02-24",   # ✓ confirmed
        "position":    "C",
        "college":     "Kansas",
        "cbb_url":     _CBB.format(slug="flory-bidunga-1"),
        "combine":     None,
        "withdrew":    True,           # returning to Louisville per CBS Sports May 2026
    },
    {
        "player_name": "Labaron Philon",
        "birth_date":  "2005-11-24",   # ✓ confirmed
        "position":    "PG",
        "college":     "Alabama",
        "cbb_url":     _CBB.format(slug="labaron-philon-1"),
        "combine":     None,
    },
    {
        "player_name": "Brayden Burries",
        "birth_date":  "2005-09-18",   # ✓ confirmed
        "position":    "SG",
        "college":     "Arizona",
        "cbb_url":     _CBB.format(slug="brayden-burries-1"),
        "combine":     None,
    },
    {
        "player_name": "Aday Mara",
        "birth_date":  "2005-04-07",   # ✓ confirmed
        "position":    "C",
        "college":     "Michigan",
        "cbb_url":     _CBB.format(slug="aday-mara-2"),  # -1 was UCLA page; -2 is Michigan
        "combine":     None,
        "note":        "Model likely undervalues — elite physical profile (7'3\", 9'9\" standing reach) not captured by BPM-based scoring; physical adj formula penalizes elite-sized centers",
    },
    {
        "player_name": "Morez Johnson Jr.",
        "birth_date":  "2005-06-01",   # ~ approximate
        "position":    "PF",
        "college":     "Illinois",      # NOTE: official combine doc says Michigan;
                                        # if scraper returns Illinois 2026, use that.
        "cbb_url":     _CBB.format(slug="morez-johnson-jr-1"),
        "combine":     None,
    },
    {
        "player_name": "Amari Allen",
        "birth_date":  "2005-06-01",   # ~ approximate
        "position":    "PF",
        "college":     "Alabama",
        "cbb_url":     _CBB.format(slug="amari-allen-1"),
        "combine":     None,
        "withdrew":    True,           # returning to Alabama per CBS Sports May 2026
    },
    {
        "player_name": "Quadir Copeland",
        "birth_date":  "2005-06-01",   # ~ approximate
        "position":    "SG",
        "college":     "NC State",
        "cbb_url":     _CBB.format(slug="quadir-copeland-1"),
        "combine":     None,
    },
    {
        "player_name": "Chris Cenac Jr.",
        "birth_date":  "2005-06-01",   # ~ approximate
        "position":    "PF",
        "college":     "Houston",
        "cbb_url":     _CBB.format(slug="chris-cenac-jr-1"),
        "combine":     None,
    },
    {
        "player_name": "Rueben Chinyelu",
        "birth_date":  "2005-06-01",   # ~ approximate
        "position":    "C",
        "college":     "Florida",
        "cbb_url":     _CBB.format(slug="rueben-chinyelu-1"),
        "combine":     None,
        "withdrew":    True,           # returning to Florida per CBS Sports May 2026
    },
    {
        "player_name": "Ryan Conwell",
        "birth_date":  "2005-06-01",   # ~ approximate
        "position":    "SG",
        "college":     "Louisville",
        "cbb_url":     _CBB.format(slug="ryan-conwell-1"),
        "combine":     None,
    },
    {
        "player_name": "Ja'Kobi Gillespie",
        "birth_date":  "2005-06-01",   # ~ approximate
        "position":    "PG",
        "college":     "Tennessee",
        "cbb_url":     _CBB.format(slug="jakobi-gillespie-1"),
        "combine":     None,
    },
    {
        "player_name": "Tyler Nickel",
        "birth_date":  "2005-06-01",   # ~ approximate
        "position":    "SF",
        "college":     "Vanderbilt",
        "cbb_url":     _CBB.format(slug="tyler-nickel-1"),
        "combine":     None,
    },
    {
        "player_name": "Tyler Tanner",
        "birth_date":  "2005-06-01",   # ~ approximate
        "position":    "PG",           # was PF — confirmed 6'0" PG (Wikipedia, SR, every source)
        "college":     "Vanderbilt",
        "cbb_url":     _CBB.format(slug="tyler-tanner-1"),
        "combine":     None,
        "withdrew":    False,
        "note":        "Model overranks — 6'0\" height limits NBA viability despite elite BPM/wingspan ratio; not reflected in scoring formula",
    },
    {
        "player_name": "Emanuel Sharp",
        "birth_date":  "2005-01-01",   # ~ approximate
        "position":    "SG",
        "college":     "Houston",
        "cbb_url":     _CBB.format(slug="emanuel-sharp-1"),
        "combine":     None,
    },
    {
        "player_name": "Izaiyah Nelson",
        "birth_date":  "2005-01-01",   # ~ approximate
        "position":    "PG",
        "college":     "South Florida",
        "cbb_url":     _CBB.format(slug="izaiyah-nelson-1"),
        "combine":     None,
        "note":        "Low-major program (South Florida) — BPM may be inflated by competition level despite SRS adjustment; late 2nd round consensus",
    },
    {
        "player_name": "Sergio De Larrea",
        "birth_date":  "2005-01-01",   # ~ approximate
        "position":    "C",
        "college":     "International",
        "cbb_url":     None,
        "combine":     None,
    },
    # ── 2004-born tier ────────────────────────────────────────────────────────
    {
        "player_name": "Milan Momcilovic",
        "birth_date":  "2004-09-22",   # ✓ confirmed (was 2004-08-09 — corrected)
        "position":    "SF",
        "college":     "Iowa State",
        "cbb_url":     _CBB.format(slug="milan-momcilovic-2"),  # 3rd-year junior; -1 was old page
        "combine":     None,
        "withdrew":    False,
        "note":        "Projected late 1st/2nd round; model ranks slightly above consensus",
    },
    {
        "player_name": "Cameron Carr",
        "birth_date":  "2004-12-01",   # ~ approximate
        "position":    "SF",
        "college":     "Baylor",
        "cbb_url":     _CBB.format(slug="cameron-carr-1"),
        "combine":     None,
    },
    {
        "player_name": "Kylan Boswell",
        "birth_date":  "2004-06-01",   # ~ approximate
        "position":    "PG",
        "college":     "Illinois",
        "cbb_url":     _CBB.format(slug="kylan-boswell-1"),
        "combine":     None,
    },
    {
        "player_name": "Zuby Ejiofor",
        "birth_date":  "2004-06-01",   # ~ approximate
        "position":    "PF",
        "college":     "St. John's",
        "cbb_url":     _CBB.format(slug="zuby-ejiofor-1"),
        "combine":     None,
    },
    {
        "player_name": "Bruce Thornton",
        "birth_date":  "2004-06-01",   # ~ approximate
        "position":    "PG",
        "college":     "Ohio State",
        "cbb_url":     _CBB.format(slug="bruce-thornton-1"),
        "combine":     None,
    },
    {
        "player_name": "Otega Oweh",
        "birth_date":  "2004-01-01",   # ~ approximate
        "position":    "SG",
        "college":     "Kentucky",
        "cbb_url":     _CBB.format(slug="otega-oweh-1"),
        "combine":     None,
    },
    {
        "player_name": "Keyshawn Hall",
        "birth_date":  "2004-01-01",   # ~ approximate
        "position":    "SF",
        "college":     "Auburn",
        "cbb_url":     _CBB.format(slug="keyshawn-hall-1"),
        "combine":     None,
    },
    {
        "player_name": "Baba Miller",
        "birth_date":  "2004-01-01",   # ~ approximate
        "position":    "PF",
        "college":     "Cincinnati",
        "cbb_url":     _CBB.format(slug="baba-miller-1"),
        "combine":     None,
    },
    {
        "player_name": "Braden Smith",
        "birth_date":  "2004-01-01",   # ~ approximate
        "position":    "PG",
        "college":     "Purdue",
        "cbb_url":     _CBB.format(slug="braden-smith-1"),
        "combine":     None,
    },
    {
        "player_name": "Ebuka Okorie",   # legal name; was "Okpara" on some rosters
        "birth_date":  "2004-01-01",   # ~ approximate
        "position":    "C",
        "college":     "Stanford",
        "cbb_url":     _CBB.format(slug="ebuka-okorie-1"),
        "combine":     None,
    },
    {
        "player_name": "Ugonna Onyenso",
        "birth_date":  "2004-01-01",   # ~ approximate
        "position":    "C",
        "college":     "Virginia",
        "cbb_url":     _CBB.format(slug="ugonna-onyenso-1"),
        "combine":     None,
    },
    {
        "player_name": "Tounde Yessoufou",
        "birth_date":  "2004-01-01",   # ~ approximate
        "position":    "SF",
        "college":     "Baylor",
        "cbb_url":     _CBB.format(slug="tounde-yessoufou-1"),
        "combine":     None,
    },
    {
        "player_name": "Felix Okpara",
        "birth_date":  "2004-01-01",   # ~ approximate
        "position":    "C",
        "college":     "Tennessee",
        "cbb_url":     _CBB.format(slug="felix-okpara-1"),
        "combine":     None,
    },
    {
        "player_name": "Karim Lopez",
        "birth_date":  "2005-01-01",   # ~ approximate
        "position":    "C",
        "college":     "International",
        "cbb_url":     None,
        "combine":     None,
    },
    # ── 2003-born tier (20.x–22.x at draft) ──────────────────────────────────
    {
        "player_name": "Joshua Jefferson",
        "birth_date":  "2003-09-01",   # ~ approximate
        "position":    "PF",
        "college":     "Iowa State",
        "cbb_url":     _CBB.format(slug="joshua-jefferson-1"),
        "combine":     None,
    },
    {
        "player_name": "Jaden Bradley",
        "birth_date":  "2003-09-01",   # ~ approximate
        "position":    "PG",
        "college":     "Arizona",
        "cbb_url":     _CBB.format(slug="jaden-bradley-1"),
        "combine":     None,
    },
    {
        "player_name": "Maliq Brown",
        "birth_date":  "2003-09-01",   # ~ approximate
        "position":    "SF",
        "college":     "Duke",
        "cbb_url":     _CBB.format(slug="maliq-brown-1"),
        "combine":     None,
    },
    {
        "player_name": "Malik Reneau",
        "birth_date":  "2003-09-01",   # ~ approximate
        "position":    "PF",
        "college":     "Miami FL",
        "cbb_url":     _CBB.format(slug="malik-reneau-1"),
        "combine":     None,
    },
    {
        "player_name": "Tyler Bilodeau",
        "birth_date":  "2003-12-01",   # ~ approximate
        "position":    "PF",
        "college":     "UCLA",
        "cbb_url":     _CBB.format(slug="tyler-bilodeau-1"),
        "combine":     None,
    },
    {
        "player_name": "Nate Bittle",
        "birth_date":  "2003-12-01",   # ~ approximate
        "position":    "C",
        "college":     "Oregon",
        "cbb_url":     _CBB.format(slug="nate-bittle-1"),
        "combine":     None,
    },
    {
        "player_name": "Tarris Reed Jr.",
        "birth_date":  "2003-12-01",   # ~ approximate
        "position":    "C",
        "college":     "UConn",
        "cbb_url":     _CBB.format(slug="tarris-reed-jr-1"),
        "combine":     None,
    },
    {
        "player_name": "Allen Graves",
        "birth_date":  "2003-12-01",   # ~ approximate
        "position":    "PF",
        "college":     "Santa Clara",
        "cbb_url":     _CBB.format(slug="allen-graves-1"),
        "combine":     None,
    },
    {
        "player_name": "Jaden Henley",
        "birth_date":  "2003-12-01",   # ~ approximate
        "position":    "SG",
        "college":     "Grand Canyon",
        "cbb_url":     _CBB.format(slug="jaden-henley-1"),
        "combine":     None,
    },
    {
        "player_name": "Tamin Lipsey",
        "birth_date":  "2003-12-01",   # ~ approximate
        "position":    "PG",
        "college":     "Iowa State",
        "cbb_url":     _CBB.format(slug="tamin-lipsey-1"),
        "combine":     None,
        "note":        "G League combine only — not invited to NBA Draft Combine; no official measurements",
    },
    {
        "player_name": "Nick Martinelli",
        "birth_date":  "2003-12-01",   # ~ approximate
        "position":    "PG",
        "college":     "Northwestern",
        "cbb_url":     _CBB.format(slug="nick-martinelli-1"),
        "combine":     None,
    },
    {
        "player_name": "Hannes Steinbach",
        "birth_date":  "2003-12-01",   # ~ approximate
        "position":    "SF",
        "college":     "Washington",
        "cbb_url":     _CBB.format(slug="hannes-steinbach-1"),
        "combine":     None,
    },
    {
        "player_name": "Bennett Stirtz",
        "birth_date":  "2003-12-01",   # ~ approximate
        "position":    "PG",
        "college":     "Iowa",
        "cbb_url":     _CBB.format(slug="bennett-stirtz-1"),
        "combine":     None,
    },
    {
        "player_name": "Peter Suder",
        "birth_date":  "2003-12-01",   # ~ approximate
        "position":    "C",
        "college":     "Miami OH",
        "cbb_url":     _CBB.format(slug="peter-suder-1"),
        "combine":     None,
    },
    # ── 23+ tier (⚠️ -10 age penalty) ────────────────────────────────────────
    {
        "player_name": "Alex Karaban",
        "birth_date":  "2003-03-01",   # ~ approximate; ~23.3 at draft
        "position":    "PF",
        "college":     "UConn",
        "cbb_url":     _CBB.format(slug="alex-karaban-1"),
        "combine":     None,
    },
    {
        "player_name": "Trey Kaufman-Renn",
        "birth_date":  "2003-03-01",   # ~ approximate; ~23.3 at draft
        "position":    "PF",
        "college":     "Purdue",
        "cbb_url":     _CBB.format(slug="trey-kaufman-renn-1"),
        "combine":     None,
    },
    {
        "player_name": "Milos Uzan",
        "birth_date":  "2003-03-01",   # ~ approximate; ~23.3 at draft
        "position":    "PG",
        "college":     "Houston",
        "cbb_url":     _CBB.format(slug="milos-uzan-1"),
        "combine":     None,
    },
    {
        "player_name": "Darrion Williams",
        "birth_date":  "2003-03-01",   # ✓ confirmed; ~23.3 at draft
        "position":    "SF",
        "college":     "NC State",
        "cbb_url":     _CBB.format(slug="darrion-williams-1"),
        "combine":     None,
    },
    {
        "player_name": "Rafael Castro",
        "birth_date":  "2003-03-01",   # ~ approximate; ~23.3 at draft
        "position":    "C",
        "college":     "George Washington",
        "cbb_url":     _CBB.format(slug="rafael-castro-1"),
        "combine":     None,
    },
    {
        "player_name": "Yaxel Lendeborg",
        "birth_date":  "2002-09-30",   # ✓ confirmed; 23.73 at draft
        "position":    "PF",
        "college":     "Michigan",
        "cbb_url":     _CBB.format(slug="yaxel-lendeborg-1"),
        "combine":     None,
    },
    {
        "player_name": "Trevon Brazile",
        "birth_date":  "2002-07-04",   # ✓ confirmed; 24.0 at draft
        "position":    "PF",
        "college":     "Arkansas",
        "cbb_url":     _CBB.format(slug="trevon-brazile-1"),
        "combine":     None,
    },
    {
        "player_name": "Oscar Cluff",
        "birth_date":  "2002-01-01",   # ~ approximate; ~24.5 at draft
        "position":    "C",
        "college":     "Purdue",
        "cbb_url":     _CBB.format(slug="oscar-cluff-1"),
        "combine":     None,
    },
    {
        "player_name": "Richie Saunders",
        "birth_date":  "2001-06-01",   # ~ approximate; ~25.1 at draft
        "position":    "SF",
        "college":     "BYU",
        "cbb_url":     _CBB.format(slug="richie-saunders-1"),
        "combine":     None,
    },
]


# ── Training normalization params ─────────────────────────────────────────────

class TrainingParams:
    """
    Normalization parameters derived from 2010-2021 training set.
    Ensures new prospects are scored on the same scale as the backtest.
    """

    def __init__(self, train_df: pd.DataFrame) -> None:
        bpm = train_df["bpm_college"].dropna()
        srs = train_df["program_srs"].dropna()

        # BPM normalization bounds (2nd/98th percentile — same as backtest)
        self.bpm_min = float(bpm.quantile(0.02))
        self.bpm_max = float(bpm.quantile(0.98))

        # SRS normalization bounds
        self.srs_min = float(srs.quantile(0.02))
        self.srs_max = float(srs.quantile(0.98))

        # Efficiency features: (mean, std, median) for z-scoring + imputation
        self.eff_stats: dict[str, tuple[float, float, float]] = {}
        for feat in _EFF_FEATS:
            col = train_df[feat].dropna()
            self.eff_stats[feat] = (
                float(col.mean()), float(col.std()), float(col.median())
            )

        # NBA fit features
        self.fit_stats: dict[str, tuple[float, float, float]] = {}
        for feat in _FIT_FEATS:
            col = train_df[feat].dropna()
            self.fit_stats[feat] = (
                float(col.mean()), float(col.std()), float(col.median())
            )

        print(f"  [Params] BPM range (2%-98%): [{self.bpm_min:.2f}, {self.bpm_max:.2f}]")
        print(f"  [Params] SRS range (2%-98%): [{self.srs_min:.2f}, {self.srs_max:.2f}]")


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _zscore_to_0_100(z: float) -> float:
    """Map z-score to 0-100 using ±3σ range (mirrors backtest.py)."""
    return float(np.clip((z + 3.0) / 6.0 * 100, 0, 100))


def _age_modifier(age: float) -> float:
    """Age multiplier for age×production pillar (mirrors backtest.py)."""
    if age < 19:   return 1.20
    if age < 20:   return 1.10
    if age < 21:   return 1.00
    if age < 22:   return 0.90
    if age < 23:   return 0.75
    return 0.50


def grade_label(mps: float) -> str:
    if mps >= GRADE_THRESHOLDS["S"]: return "S"
    if mps >= GRADE_THRESHOLDS["A"]: return "A"
    if mps >= GRADE_THRESHOLDS["B"]: return "B"
    if mps >= GRADE_THRESHOLDS["C"]: return "C"
    return "D"


def compute_physical_adjustment(combine: dict | None, position: str = "") -> float:
    """
    ±10 pt adjustment from wingspan/height ratio.

    Baseline ratio:
      - Centers (position="C"): 1.03 — elite-sized centers structurally have lower
        ratios due to the physics of very tall frames; 1.06 unfairly penalizes them.
      - All other positions: 1.06 (NBA draft-class average).

    Each 0.008 above/below baseline = ±1 pt, capped at ±10.
    Returns 0.0 if combine is None or keys missing.

    Note: directionally correct; not backtested against this dataset.
    r=0.35-0.45 vs defensive outcomes from separate studies.
    """
    if not combine:
        return 0.0
    h = combine.get("height_in")
    w = combine.get("wingspan_in")
    if not h or not w or h <= 0:
        return 0.0
    baseline = 1.03 if str(position).upper() == "C" else 1.06
    ratio = w / h
    adj = (ratio - baseline) / 0.008
    return float(np.clip(adj, -10.0, 10.0))


def compute_availability_modifier(gp: float | None, team_games: int = 33) -> float:
    """
    Penalty for players who missed significant playing time.
    Only triggers when GP < 70% of team's schedule.
    Capped at -8 pts regardless of absences.

    Formula: -min((0.70 - gp/team_games) * 25, 8.0)
    """
    if gp is None:
        return 0.0
    pct = gp / team_games
    if pct >= 0.70:
        return 0.0
    return -min((0.70 - pct) * 25.0, 8.0)


def compute_age_penalty(draft_age: float) -> float:
    """
    Piecewise age adjustment based on empirical NBA outcome research.

    Zone 1 (≤19.5): +2.5 bonus — freshman one-and-dones
                     meaningfully outperform older prospects
    Zone 2 (19.5–21.5): neutral — sophomore/junior outcomes
                          are statistically indistinguishable
    Zone 3 (21.5+): linear decay at -2.0 pts per year above 21.5,
                     capped at -15 pts

    Examples:
      18.9 (Boozer)      → +2.5
      19.4 (Dybantsa)    → +2.5
      20.8 (Burries)     → 0.0
      21.1 (Morez)       → 0.0
      21.75 (Momcilovic) → -0.5
      22.1 (Ejiofor)     → -1.2
      22.56 (Stirtz)     → -2.1
      22.9 (Reed)        → -2.8
      23.73 (Lendeborg)  → -4.5
      25.06 (Saunders)   → -7.1
    """
    if draft_age <= 19.5:
        return 2.5
    elif draft_age <= 21.5:
        return 0.0
    else:
        penalty = (draft_age - 21.5) * 2.0
        return -min(penalty, 15.0)


# ── Single-player MPS computation ─────────────────────────────────────────────

def compute_mps_for_prospect(
    stats: dict,
    draft_age: float,
    params: TrainingParams,
) -> tuple[float, float, float, float, float]:
    """
    Compute 4 pillar scores and MPS_base for a single prospect.

    Uses training-set normalization params to stay on the same scale as the
    backtest — critical because BPM normalization is percentile-based.

    Returns:
        (pillar_efficiency, pillar_age_prod, pillar_comp, pillar_fit, mps_base)
        All values 0-100.
    """

    # ── Pillar 2: Age × Production ────────────────────────────────────────────
    # BPM normalized to [0,100] using training percentiles, then × age modifier
    bpm = stats.get("bpm_college")
    if bpm is None or (isinstance(bpm, float) and np.isnan(bpm)):
        bpm = params.bpm_min  # worst-case: missing → floor
    bpm_range = max(params.bpm_max - params.bpm_min, 1e-8)
    bpm_norm = float(np.clip((bpm - params.bpm_min) / bpm_range, 0, 1) * 100)
    pillar_age_prod = float(np.clip(bpm_norm * _age_modifier(draft_age), 0, 100))

    # ── Pillar 1: College Efficiency ──────────────────────────────────────────
    # Correlation-weighted z-scores of secondary stats (not BPM — already above)
    eff_z = 0.0
    total_w = 0.0
    for i, feat in enumerate(_EFF_FEATS):
        mean, std, median = params.eff_stats.get(feat, (0.0, 1.0, 0.0))
        val = stats.get(feat)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            val = median  # impute with training median → z ≈ 0
        z = (float(val) - mean) / max(std, 1e-8)
        eff_z    += _EFF_WGTS[i] * z
        total_w  += _EFF_WGTS[i]
    pillar_efficiency = _zscore_to_0_100(eff_z / max(total_w, 1e-8))

    # ── Pillar 3: Competition Context ─────────────────────────────────────────
    srs = stats.get("program_srs")
    if srs is None or (isinstance(srs, float) and np.isnan(srs)):
        srs = (params.srs_min + params.srs_max) / 2  # impute with midpoint
    srs_range = max(params.srs_max - params.srs_min, 1e-8)
    pillar_comp = float(np.clip((float(srs) - params.srs_min) / srs_range, 0, 1) * 100)

    # ── Pillar 4: NBA Fit ─────────────────────────────────────────────────────
    fit_z_sum, n_fit = 0.0, 0
    for feat in _FIT_FEATS:
        mean, std, median = params.fit_stats.get(feat, (0.0, 1.0, 0.0))
        val = stats.get(feat)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            val = median
        fit_z_sum += (float(val) - mean) / max(std, 1e-8)
        n_fit += 1
    pillar_fit = _zscore_to_0_100(fit_z_sum / max(n_fit, 1))

    # ── Weighted MPS ──────────────────────────────────────────────────────────
    w = OPTIMIZED_WEIGHTS
    mps_base = float(np.clip(
        pillar_efficiency  * w["college_efficiency"] +
        pillar_age_prod    * w["age_x_production"]   +
        pillar_comp        * w["competition_ctx"]    +
        pillar_fit         * w["nba_fit"],
        0, 100
    ))
    return pillar_efficiency, pillar_age_prod, pillar_comp, pillar_fit, mps_base


# ── Orchestrator ──────────────────────────────────────────────────────────────

def score_all_prospects(prospects: list[dict]) -> pd.DataFrame:
    """
    Score all prospects:
      1. Load training CSV → derive normalization params
      2. Fetch 2025-26 program SRS (one call, 365 programs)
      3. For each prospect: fetch CBB stats, apply manual overrides,
         compute MPS, apply physical/availability/age adjustments
    Returns fully ranked DataFrame (all rows, N/A last).
    """
    # Load training data for normalization
    print("Loading training set for normalization params...")
    df_train = pd.read_csv(DATASET)
    df_train = df_train[df_train.draft_year <= 2021].copy()
    params = TrainingParams(df_train)

    # Fetch 2025-26 program SRS
    print("\nFetching 2025-26 program SRS (sports-reference CBB)...")
    srs_2026 = scrape_program_srs(2026)
    print(f"  {len(srs_2026)} programs loaded")

    # Fetch 2026 NBA Combine measurements (cached 24h)
    print("\nFetching 2026 NBA Combine measurements...")
    try:
        combine_lookup = get_full_combine_data()
        if combine_lookup:
            print(f"  {len(combine_lookup)} players with combine measurements")
        else:
            print("  No combine measurements available — physical adj = 0.0 for all")
    except Exception as _e:
        print(f"  Combine fetch failed: {_e}; physical adj = 0.0 for all")
        combine_lookup = {}

    rows = []
    for prospect in prospects:
        name          = prospect["player_name"]
        cbb_url       = prospect.get("cbb_url")
        college       = prospect.get("college", "")
        pos           = prospect.get("position", "")
        team_games    = int(prospect.get("team_games") or 33)
        withdrew      = bool(prospect.get("withdrew", False))
        prospect_note = prospect.get("note", "")

        # Combine data: API lookup merged with prospect-level manual override
        # combine_name field overrides the lookup name (e.g. Ebuka Okpara → Okorie)
        # COMBINE_NAME_OVERRIDES in combine_scraper handles nickname/legal-name gaps
        # Prospect-level combine dict wins key-by-key over API data
        _lookup_name    = prospect.get("combine_name") or name
        _api_combine    = lookup_player(combine_lookup, _lookup_name)
        _manual_combine = prospect.get("combine") or {}
        combine         = {**_api_combine, **_manual_combine} or None

        # Draft age
        try:
            dob = date.fromisoformat(prospect["birth_date"])
            draft_age = (DRAFT_DATE_2026 - dob).days / 365.25
        except Exception:
            draft_age = 21.5  # fallback

        print(f"\n  [{name}]  {pos}  age={draft_age:.2f}  college={college}")

        # ── No CBB URL (international / no college stats) ─────────────────────
        if not cbb_url:
            print(f"    No CBB URL — international/no data")
            rows.append(_null_row(name, pos, college, draft_age,
                                  combine, "No college data", withdrew=withdrew))
            continue

        # ── Fetch CBB stats ───────────────────────────────────────────────────
        try:
            college_stats = scrape_college_stats(cbb_url)
        except Exception as e:
            print(f"    CBB fetch error: {e}")
            college_stats = None

        # ── Apply manual stat overrides ───────────────────────────────────────
        # Non-None values in MANUAL_STATS always win over scraped.
        # If entire scrape failed, build from scratch using manual data.
        if name in MANUAL_STATS:
            if college_stats is None:
                college_stats = {}
            manual = MANUAL_STATS[name]
            for k, v in manual.items():
                if v is not None:
                    college_stats[k] = v       # manual non-None always overrides
                elif k not in college_stats:
                    college_stats[k] = v       # manual None only fills missing keys

        if not college_stats:
            print(f"    CBB fetch failed (404 or missing tables)")
            rows.append(_null_row(name, pos, college, draft_age,
                                  combine, "CBB fetch failed", withdrew=withdrew))
            continue

        # ── Resolve program SRS ───────────────────────────────────────────────
        school_name = college_stats.get("school_name") or college
        srs = _resolve_srs(school_name, srs_2026)
        college_stats["program_srs"] = srs

        bpm = college_stats.get("bpm_college")
        ts  = college_stats.get("ts_pct")
        print(f"    BPM={bpm}  TS%={ts}  SRS={srs}")

        # ── BPM null → incomplete data, do not score ──────────────────────────
        # Sports-reference withholds BPM below a GP threshold.
        # Without BPM, age×production pillar (41%) collapses to floor.
        # Only reaches here if name NOT in MANUAL_STATS (Boozer is covered above).
        if bpm is None:
            print(f"    BPM not computed by source (insufficient games/data)")
            rows.append(_null_row(name, pos, college, draft_age,
                                  combine, "BPM not computed — insufficient games",
                                  withdrew=withdrew))
            continue

        # ── Compute base MPS pillars ──────────────────────────────────────────
        peff, page, pcomp, pfit, mps_base = compute_mps_for_prospect(
            college_stats, draft_age, params
        )

        # ── Apply adjustments ─────────────────────────────────────────────────
        phys_adj  = compute_physical_adjustment(combine, pos)
        gp        = college_stats.get("games_played")
        avail_mod = compute_availability_modifier(gp, team_games)
        age_pen   = compute_age_penalty(draft_age)
        mps_final = float(np.clip(mps_base + phys_adj + avail_mod + age_pen, 0, 100))
        grd       = grade_label(mps_final)

        # ── Build notes string ────────────────────────────────────────────────
        notes = []
        if avail_mod < 0.0:
            gp_pct = gp / team_games if gp is not None else None
            pct_s  = f"{gp_pct:.0%}" if gp_pct is not None else "?"
            notes.append(f"Availability: {pct_s} GP ({gp:.0f}/{team_games}g)")
        if age_pen < 0.0:
            notes.append(f"Age penalty -10 ({draft_age:.1f}y)")
        if name in MANUAL_STATS:
            notes.append("Stats: manual override (BBRef BPM)")
        note_str = "; ".join(notes)
        # Prepend withdrew flag or prospect-level note
        prefix = ""
        if withdrew:
            prefix = "WITHDREW — not in 2026 draft"
        elif prospect_note:
            prefix = prospect_note
        if prefix and note_str:
            note_str = prefix + "; " + note_str
        elif prefix:
            note_str = prefix

        print(f"    Pillars: eff={peff:.1f} age={page:.1f} comp={pcomp:.1f} fit={pfit:.1f}")
        print(f"    MPS base={mps_base:.1f}  phys={phys_adj:+.1f}  "
              f"avail={avail_mod:+.1f}  agepen={age_pen:+.1f}  "
              f"→ MPS={mps_final:.1f}  Grade={grd}")

        gp_pct_val = round(gp / team_games, 3) if gp is not None else None

        rows.append({
            "player_name":      name,
            "position":         pos,
            "college":          college,
            "draft_age":        round(draft_age, 2),
            "bpm_college":      bpm,
            "ts_pct":           ts,
            "program_srs":      srs,
            "pillar_eff":       round(peff,  1),
            "pillar_age":       round(page,  1),
            "pillar_comp":      round(pcomp, 1),
            "pillar_fit":       round(pfit,  1),
            "mps_base":         round(mps_base,  1),
            "physical_adj":     round(phys_adj,  1),
            "games_played":     gp,
            "games_played_pct": gp_pct_val,
            "avail_modifier":   round(avail_mod, 1),
            "age_penalty":      round(age_pen,   1),
            "mps":              round(mps_final, 1),
            "grade":            grd,
            "withdrew":         withdrew,
            "note":             note_str,
        })

    result = pd.DataFrame(rows)
    # Sort: scored players by MPS desc, N/A last
    result = result.sort_values("mps", ascending=False, na_position="last")
    result.insert(0, "rank", range(1, len(result) + 1))
    return result.reset_index(drop=True)


def _null_row(name: str, pos: str, college: str,
              draft_age: float, combine: dict | None, note: str,
              *, withdrew: bool = False) -> dict:
    age_pen = compute_age_penalty(draft_age)
    prefix = "WITHDREW — not in 2026 draft" if withdrew else ""
    full_note = (prefix + "; " + note) if (prefix and note) else (prefix or note)
    return {
        "player_name":      name,
        "position":         pos,
        "college":          college,
        "draft_age":        round(draft_age, 2),
        "bpm_college":      None,
        "ts_pct":           None,
        "program_srs":      None,
        "pillar_eff":       None,
        "pillar_age":       None,
        "pillar_comp":      None,
        "pillar_fit":       None,
        "mps_base":         None,
        "physical_adj":     round(compute_physical_adjustment(combine, pos), 1),
        "games_played":     None,
        "games_played_pct": None,
        "avail_modifier":   0.0,
        "age_penalty":      round(age_pen, 1),
        "mps":              None,
        "grade":            "N/A",
        "withdrew":         withdrew,
        "note":             full_note,
    }


# ── Output ────────────────────────────────────────────────────────────────────

def print_big_board(df: pd.DataFrame, top_n: int = 30) -> None:
    """Print formatted ranked table (top N only; full board saved to CSV)."""
    print("\n" + "=" * 90)
    print("MPS 2026 Big Board")
    print(f"Draft: {DRAFT_DATE_2026}  |  Model: BPM×Age (90%) + Physical (±10)")
    print("=" * 90)
    header = (f"{'Rk':>3}  {'Player':<22}  {'Pos':>3}  {'Age':>5}  "
              f"{'BPM':>6}  {'Base':>5}  {'Phy':>5}  {'Avl':>5}  {'AgP':>5}  {'MPS':>5}  Grade")
    print(header)
    print("-" * 90)

    display_df = df.head(top_n)
    for _, row in display_df.iterrows():
        bpm_s  = f"{row.bpm_college:+.1f}" if pd.notna(row.bpm_college) else "   N/A"
        base_s = f"{row.mps_base:.1f}"     if pd.notna(row.mps_base)    else "  N/A"
        mps_s  = f"{row.mps:.1f}"          if pd.notna(row.mps)         else "  N/A"
        phys_s = f"{row.physical_adj:+.1f}" if pd.notna(row.get("physical_adj", None)) else " +0.0"
        avl_s  = f"{row.avail_modifier:+.1f}" if pd.notna(row.get("avail_modifier", None)) else " +0.0"
        agp_s  = f"{row.age_penalty:+.1f}"    if pd.notna(row.get("age_penalty",    None)) else " +0.0"
        note   = f"  [{row.note}]" if row.note else ""
        print(f"{row['rank']:>3}  {row.player_name:<22}  {row.position:>3}  "
              f"{row.draft_age:>5.1f}  {bpm_s:>6}  {base_s:>5}  "
              f"{phys_s:>5}  {avl_s:>5}  {agp_s:>5}  {mps_s:>5}  {row.grade}{note}")

    if len(df) > top_n:
        print(f"\n  ... {len(df) - top_n} more rows in CSV (full board saved)")

    # Withdrew section
    if "withdrew" in df.columns:
        wd = df[df["withdrew"] == True]
        if not wd.empty:
            print("\nWithdrew (not eligible for 2026 draft):")
            parts = []
            for _, r in wd.iterrows():
                mps_s = f"MPS={r.mps:.1f}" if pd.notna(r.mps) else "N/A"
                parts.append(f"  {r.player_name} ({mps_s})")
            print("\n".join(parts))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("MPS 2026 Draft Scorer")
    print(f"Draft: {DRAFT_DATE_2026}  |  Prospects: {len(PROSPECTS_2026)}")
    print()

    df = score_all_prospects(PROSPECTS_2026)
    print_big_board(df, top_n=30)

    # Save full 70-player board
    path = OUTPUT_DIR / "2026_big_board.csv"
    df.to_csv(path, index=False)
    print(f"\nSaved: {path}")

    # Grade distribution
    print("\nGrade distribution:")
    for grade in ["S", "A", "B", "C", "D", "N/A"]:
        n = (df.grade == grade).sum()
        if n:
            print(f"  {grade}: {n} player{'s' if n > 1 else ''}")

    # Age penalty summary
    penalized = df[(df.get("age_penalty") if "age_penalty" in df.columns else pd.Series(dtype=float)).lt(0)]
    if "age_penalty" in df.columns:
        penalized = df[df["age_penalty"] < 0]
        if not penalized.empty:
            print(f"\n23+ age penalty applied to {len(penalized)} players:")
            for _, r in penalized.iterrows():
                print(f"  {r.player_name} ({r.draft_age:.1f}y) — MPS={r.mps if pd.notna(r.mps) else 'N/A'}")

    # Availability penalty summary
    if "avail_modifier" in df.columns:
        avail_hit = df[df["avail_modifier"] < 0]
        if not avail_hit.empty:
            print(f"\nAvailability penalty applied to {len(avail_hit)} players:")
            for _, r in avail_hit.iterrows():
                print(f"  {r.player_name}: {r.avail_modifier:+.1f} pts "
                      f"({r.games_played_pct:.0%} GP)")

    print("\nNote: approximate DOBs (YYYY-MM-01) should be updated when confirmed.")
    print("⚠️  Boozer BPM=17.8 from BBRef (page withholds display below GP threshold; value confirmed via Yahoo Sports/SR).")


if __name__ == "__main__":
    main()
