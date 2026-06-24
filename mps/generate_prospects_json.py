"""
mps/generate_prospects_json.py

Convert 2026_big_board.csv → web/src/data/prospects_2026.json
for the MacFacts Next.js web app.

Run:
    backend/.venv/bin/python -m mps.generate_prospects_json
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

CSV_PATH  = Path(__file__).parent / "output" / "2026_big_board.csv"
JSON_PATH = Path(__file__).parent.parent / "web" / "src" / "data" / "prospects_2026.json"
BACKEND_DIR = Path(__file__).parent.parent / "backend"

NBA_HEADERS = {
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Referer": "https://www.nba.com/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}
NBA_HEADSHOT_BASE = "https://cdn.nba.com/headshots/nba/latest/260x190"

# Pre-fetched from NBA draftcombineplayeranthro (2026-27) — update annually
_KNOWN_IDS: dict[str, int] = {
    "Matthew Able": 1643587, "Darius Acuff Jr.": 1643411, "Amari Allen": 1643533,
    "Nathaniel Ament": 1643417, "Christian Anderson": 1643515, "Tobe Awaka": 1643591,
    "Flory Bidunga": 1643540, "Tyler Bilodeau": 1643548, "John Blackwell": 1643612,
    "Cameron Boozer": 1643409, "Kylan Boswell": 1643573, "Nicholas Boyd": 1643592,
    "Jaden Bradley": 1643558, "Trevon Brazile": 1642350, "Maliq Brown": 1643576,
    "Christopher Brown Jr": 1643414, "Brayden Burries": 1643415, "Cameron Carr": 1643418,
    "Rafael Castro": 1643572, "Christopher Cenac Jr.": 1643416, "Rueben Chinyelu": 1642929,
    "Jacob Cofie": 1643618, "Ryan Conwell": 1643553, "Sergio De Larrea": 1643547,
    "Anicet Dybantsa": 1643407, "AJ Dybantsa": 1643407,
    "Zuby Ejiofor": 1643544, "Isaiah Evans": 1642912, "Jeremy Fears Jr.": 1643578,
    "Kingston Flemings": 1643412, "Ja'Kobi Gillespie": 1643551, "Allen Graves": 1643512,
    "Keyshawn Hall": 1643545, "Jaden Harris": 1643541, "Bryce Hopkins": 1643624,
    "Joshua Jefferson": 1643538, "Morez Johnson": 1643516, "Morez Johnson Jr.": 1643516,
    "Alex Karaban": 1642284, "Trey Kaufman-Renn": 1643626, "Jack Kayil": 1643583,
    "Tobi Lawal": 1643588, "Yaxel Lendeborg": 1642865, "Karim Lopez": 1643510,
    "Aday Mara": 1643530, "Nick Martinelli": 1643568, "Baba Miller": 1642394,
    "Dillon Mitchell": 1641759, "Milan Momcilovic": 1643521, "Malachi Moreno": 1643613,
    "Izaiyah Nelson": 1643593, "Tyler Nickel": 1643589, "Aaron Nkrumah": 1643635,
    "Ebuka Okorie": 1643536, "Felix Okpara": 1643590, "Ugonna Onyenso": 1642391,
    "Otega Oweh": 1642923, "Koa Peat": 1643520, "Darryn Peterson": 1643408,
    "Labaron Philon": 1642889, "Jayden Quaintance": 1643519, "Tarris Reed Jr.": 1643542,
    "Billy Richmond III": 1643586, "Richie Saunders": 1643563, "Emanuel Sharp": 1643567,
    "Braden Smith": 1643552, "Hannes Steinbach": 1643419, "Bennett Stirtz": 1642892,
    "Andrej Stojakovic": 1642887, "Peter Suder": 1643614, "Luigi Suigo": 1643543,
    "Dailyn Swain": 1643517, "Tyler Tanner": 1643535, "Meleek Thomas": 1643509,
    "Bruce Thornton": 1643570, "Milos Uzan": 1642870, "Henri Veesaar": 1643539,
    "Keaton Wagler": 1643413, "Caleb Wilson": 1643410, "Tounde Yessoufou": 1643537,
    # Additional names not in combine (partial coverage)
    "Nate Ament": 1643417, "Chris Cenac Jr.": 1643416, "Quadir Copeland": None,
    "Ja'Kobi Gillespie": 1643551, "Oscar Cluff": None, "Tamin Lipsey": None,
    "Darrion Williams": None, "Jaden Bradley": 1643558,
}


def _fetch_espn_headshots(names: list[str]) -> dict[str, str | None]:
    """Pull ESPN headshot URLs from the Django NCAA player DB."""
    try:
        sys.path.insert(0, str(BACKEND_DIR))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        import django
        django.setup()
        from ncaa.models.players import Player

        results: dict[str, str | None] = {}
        for name in names:
            parts = name.replace("Jr.", "").replace("Jr", "").strip().split()
            last  = parts[-1] if parts else name
            first = parts[0]  if len(parts) > 1 else ""
            qs = Player.objects.filter(
                display_name__icontains=last,
                headshot_url__isnull=False,
            ).exclude(headshot_url="")
            if first:
                qs = qs.filter(display_name__icontains=first)
            p = qs.first()
            results[name] = p.headshot_url if p else None

        found = sum(1 for v in results.values() if v)
        print(f"  ESPN headshots from DB: {found}/{len(names)} matched")
        return results
    except Exception as exc:
        print(f"  WARNING: could not fetch ESPN headshots from DB: {exc}")
        return {n: None for n in names}


def _fetch_player_ids() -> dict[str, int]:
    """Fetch NBA combine player IDs → {player_name: player_id}."""
    try:
        r = requests.get(
            "https://stats.nba.com/stats/draftcombineplayeranthro",
            headers=NBA_HEADERS,
            params={"LeagueID": "00", "SeasonYear": "2026-27"},
            timeout=20,
        )
        data = r.json()
        rs0 = data["resultSets"][0]
        headers = rs0["headers"]
        rows = rs0["rowSet"]
        result = {}
        for row in rows:
            d = dict(zip(headers, row))
            name = d.get("PLAYER_NAME", "").strip()
            pid = d.get("PLAYER_ID") or d.get("TEMP_PLAYER_ID")
            if name and pid:
                result[name] = int(pid)
        print(f"  Fetched {len(result)} NBA player IDs from combine")
        return result
    except Exception as exc:
        print(f"  WARNING: could not fetch player IDs: {exc}")
        return {}


def _match_id(csv_name: str, id_map: dict[str, int]) -> int | None:
    """Exact match first, then try name variants."""
    if csv_name in id_map:
        return id_map[csv_name]
    # Try without suffix (Jr., III, etc.)
    import re
    clean = re.sub(r"\s+(Jr\.|Sr\.|III|II|IV)$", "", csv_name).strip()
    if clean in id_map:
        return id_map[clean]
    # Reverse: check if csv_name is substring of any key
    for k, v in id_map.items():
        if csv_name.lower() in k.lower() or k.lower() in csv_name.lower():
            return v
    return None


def _safe(val, cast=None):
    """Return None for NaN/null, else optionally cast."""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    if cast is not None:
        try:
            return cast(val)
        except (ValueError, TypeError):
            return None
    return val


def _build_strengths_weaknesses(row: pd.Series) -> tuple[list[str], list[str]]:
    """Derive narrative strength/weakness bullets from scored prospect row."""
    strengths: list[str] = []
    weaknesses: list[str] = []

    bpm   = _safe(row.get("bpm_college"), float)
    dbpm  = _safe(row.get("dbpm"), float)
    ts    = _safe(row.get("ts_pct"), float)
    ppg   = _safe(row.get("pts_pg"), float)
    rpg   = _safe(row.get("trb_pg"), float)
    apg   = _safe(row.get("ast_pg"), float)
    age   = _safe(row.get("draft_age"), float)
    avail = _safe(row.get("avail_modifier"), float) or 0.0
    hf    = _safe(row.get("height_floor_pen"), float) or 0.0
    scout = _safe(row.get("scout_adj"), float) or 0.0

    # ── Strengths ──────────────────────────────────────────────────────────
    if bpm is not None:
        if bpm >= 14:  strengths.append("Elite overall producer (BPM)")
        elif bpm >= 10: strengths.append("High box-score value (BPM)")

    if dbpm is not None:
        if dbpm >= 5:   strengths.append("Elite college defender")
        elif dbpm >= 2: strengths.append("Positive defensive impact")

    if ts is not None:
        if ts >= 0.64:   strengths.append("Elite scoring efficiency (TS%)")
        elif ts >= 0.58: strengths.append("Above-average scorer efficiency")

    if ppg is not None:
        if ppg >= 20:    strengths.append("High-volume scorer")
        elif ppg >= 16:  strengths.append("Consistent scoring threat")

    if rpg is not None:
        if rpg >= 9:  strengths.append("Elite rebounder")
        elif rpg >= 7: strengths.append("Strong rebounder")

    if apg is not None:
        if apg >= 6:  strengths.append("Elite playmaker")
        elif apg >= 4: strengths.append("Capable playmaker")

    if age is not None:
        if age <= 19.5:  strengths.append("Top-tier youth upside")
        elif age <= 20.5: strengths.append("Strong projection runway")

    if scout >= 5.0:     strengths.append("Consensus top-5 pick")
    elif scout >= 3.0:   strengths.append("Lottery consensus prospect")

    # ── Weaknesses ─────────────────────────────────────────────────────────
    if dbpm is not None:
        if dbpm < 0:    weaknesses.append("Defensive liability at college level")
        elif dbpm < 1.5: weaknesses.append("Below-average college defender")

    if ts is not None:
        if ts < 0.53:   weaknesses.append("Below-average scoring efficiency")
        elif ts < 0.56: weaknesses.append("Inconsistent scoring efficiency")

    if bpm is not None and bpm < 7:
        weaknesses.append("Limited box-score production")

    if ppg is not None and ppg < 10:
        weaknesses.append("Low college scoring output")

    if age is not None:
        if age >= 23:   weaknesses.append("Age limits projection window")
        elif age >= 22: weaknesses.append("Age-based projection concern")

    if avail < -2.0:
        weaknesses.append("Injury/availability history")

    if hf < -2.0:
        weaknesses.append("Height/length below NBA threshold")

    return strengths, weaknesses


def main() -> None:
    df = pd.read_csv(CSV_PATH)

    # Filter: active only (not withdrew, has mps score)
    active = df[
        (df["withdrew"].isna() | (df["withdrew"] == False)) &
        df["mps"].notna()
    ].copy()

    print(f"Active prospects: {len(active)} (of {len(df)} total rows)")

    # Fetch ESPN headshots from Django NCAA player DB (same source as player stats pages)
    all_names = [str(r["player_name"]) for _, r in active.iterrows()]
    espn_headshots = _fetch_espn_headshots(all_names)

    prospects = []
    matched_photos = 0
    for _, row in active.iterrows():
        csv_name = str(row["player_name"])
        headshot = espn_headshots.get(csv_name)
        if headshot:
            matched_photos += 1
        strengths, weaknesses = _build_strengths_weaknesses(row)
        prospects.append({
            "rank":          int(row["rank"]),
            "name":          str(row["player_name"]),
            "position":      str(row["position"]),
            "positionGroup": str(row.get("position_group", "")),
            "college":       str(row.get("college", "")),
            "age":           round(float(row["draft_age"]), 2),
            "bpm":           _safe(row.get("bpm_college"), float),
            "dbpm":          _safe(row.get("dbpm"), float),
            "obpm":          _safe(row.get("obpm"), float),
            "per":           _safe(row.get("per"), float),
            "ts":            _safe(row.get("ts_pct"), float),
            "fgPct":         _safe(row.get("fg_pct"), float),
            "ws40":          _safe(row.get("ws_40"), float),
            "ppg":           _safe(row.get("pts_pg"), float),
            "rpg":           _safe(row.get("trb_pg"), float),
            "apg":           _safe(row.get("ast_pg"), float),
            "stlPg":         _safe(row.get("stl_pg"), float),
            "blkPg":         _safe(row.get("blk_pg"), float),
            "orbPct":        _safe(row.get("orb_pct"), float),
            "astPct":        _safe(row.get("ast_pct"), float),
            "mpsComposite":  round(float(row["mps_composite"]), 1),
            "srsAdj":        round(float(row.get("srs_adj", 0) or 0), 1),
            "ageAdj":        round(float(row.get("age_penalty", 0) or 0), 1),
            "scoutAdj":      round(_safe(row.get("scout_adj"), float) or 0.0, 1),
            "availAdj":      round(float(row.get("avail_modifier", 0) or 0), 1),
            "mps":           round(float(row["mps"]), 1),
            "grade":         str(row["grade"]),
            "tankRank":      _safe(row.get("tankathon_rank"), int),
            "tier":          str(row.get("confidence_tier", "full") or "full"),
            "note":          str(row.get("note", "") or ""),
            "heightFloor":   round(float(row.get("height_floor_pen", 0) or 0), 1),
            "combinePen":    round(float(row.get("combine_penalty", 0) or 0), 1),
            "headshot":      headshot,
            "strengths":     strengths,
            "weaknesses":    weaknesses,
            "comp1":         _safe(row.get("comp1_name"), str),
            "comp1Year":     _safe(row.get("comp1_year"), int),
            "comp1Pick":     _safe(row.get("comp1_pick"), int),
            "comp1Sim":      _safe(row.get("comp1_sim"), int),
            "comp2":         _safe(row.get("comp2_name"), str),
            "comp2Year":     _safe(row.get("comp2_year"), int),
            "comp2Pick":     _safe(row.get("comp2_pick"), int),
            "comp2Sim":      _safe(row.get("comp2_sim"), int),
        })

    # ── Apply consensus rank ordering ──────────────────────────────────────────
    # Override model rank with consensus ordering (avg of MF/Tank/Ring/ESPN).
    # Mara kept at #6 per editorial preference. Scores reassigned rank-order
    # so displayed MPS decreases monotonically with rank.
    CONSENSUS_ORDER = [
        "Darryn Peterson", "Cameron Boozer", "AJ Dybantsa", "Caleb Wilson", "Keaton Wagler",
        "Aday Mara", "Kingston Flemings", "Darius Acuff Jr.", "Brayden Burries", "Yaxel Lendeborg",
        "Mikel Brown Jr.", "Nate Ament", "Labaron Philon", "Hannes Steinbach", "Morez Johnson Jr.",
        "Jayden Quaintance", "Dailyn Swain", "Ebuka Okorie", "Allen Graves", "Cameron Carr",
        "Bennett Stirtz", "Karim Lopez", "Christian Anderson", "Koa Peat", "Joshua Jefferson",
        "Henri Veesaar", "Zuby Ejiofor", "Chris Cenac Jr.", "Tarris Reed Jr.", "Isaiah Evans",
        "Meleek Thomas", "Baba Miller", "Ryan Conwell", "Alex Karaban", "Richie Saunders",
        "Sergio De Larrea", "Ugonna Onyenso", "Bruce Thornton", "Maliq Brown", "Trevon Brazile",
        "Jack Kayil", "Emanuel Sharp", "Izaiyah Nelson", "Braden Smith", "Ja'Kobi Gillespie",
        "Jaden Bradley", "Nick Martinelli", "Felix Okpara", "Otega Oweh", "Tyler Nickel",
        "Quadir Copeland", "Bryce Hopkins", "Aaron Nkrumah", "Tyler Bilodeau", "Tamin Lipsey",
        "Kylan Boswell", "Nate Bittle", "Milos Uzan", "Trey Kaufman-Renn", "Keyshawn Hall",
        "Malik Reneau", "Mark Mitchell", "Peter Suder", "Darrion Williams", "Tucker DeVries",
    ]
    by_name = {p["name"]: p for p in prospects}
    known = [n for n in CONSENSUS_ORDER if n in by_name]
    remaining = [p for p in prospects if p["name"] not in set(known)]
    sorted_scores = sorted([p["mps"] for p in prospects], reverse=True)

    def _grade(mps: float) -> str:
        if mps >= 90.0: return "S"
        if mps >= 80.0: return "A"
        return "D"

    reordered = []
    score_idx = 0
    for name in known:
        p = dict(by_name[name])
        new_mps = round(sorted_scores[score_idx], 1)
        p["rank"] = score_idx + 1
        p["mps"] = new_mps
        p["grade"] = _grade(new_mps)
        reordered.append(p)
        score_idx += 1
    for p in remaining:
        p = dict(p)
        new_mps = round(sorted_scores[score_idx], 1) if score_idx < len(sorted_scores) else p["mps"]
        p["rank"] = score_idx + 1
        p["mps"] = new_mps
        p["grade"] = _grade(new_mps)
        reordered.append(p)
        score_idx += 1
    prospects = reordered

    output = {
        "updatedAt": "2026-05-30",
        "totalProspects": len(prospects),
        "prospects": prospects,
    }

    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(output, indent=2))
    print(f"Written: {JSON_PATH}")
    print(f"Headshots matched: {matched_photos}/{len(prospects)}")
    print(f"\nFirst 5 prospects:")
    for p in prospects[:5]:
        print(f"  #{p['rank']} {p['name']} — MPS {p['mps']} ({p['grade']}) headshot={'✓' if p['headshot'] else '✗'}")


if __name__ == "__main__":
    main()
