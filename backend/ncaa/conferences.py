"""
Conference registry and season-keyed membership (no DB access).

Membership changes every summer, so it lives in data files, one per season:

    ncaa/data/conferences/<season>.csv      e.g. 2027.csv = the 2026-27 season

Columns: slug, team, conference (display name, see CONFERENCES), plus
informational previous_conference, change, announced_future_move.

A season uses the newest file whose year is <= that season, so a new file is only
needed in a summer where something moves; 2028 reuses 2027.csv until a 2028.csv
exists. Seasons before the first file (<= 2026) use the frozen CONF_MAP in
conf_utils, so history is never rewritten.

Rollover next summer: add <next season>.csv (copy the last file, edit the rows
that moved, and add any new conference to CONFERENCES below).
"""

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data" / "conferences"


@dataclass(frozen=True)
class ConferenceDef:
    code: str   # stable id stored in Conference.code (max 10 chars)
    name: str   # full name stored in Conference.name
    csv_name: str  # how the season CSV spells it ("" = not used by any season file)


# Codes MUST match the keys used by the frozen CONF_MAP (conf_utils).
# MAAC and WAC stay for seasons <= 2026; their successors Metro and UAC are new
# codes (the UAC has different members than the old WAC).
CONFERENCES: tuple[ConferenceDef, ...] = (
    ConferenceDef("ACC", "Atlantic Coast Conference", "ACC"),
    ConferenceDef("AE", "America East", "America East"),
    ConferenceDef("Amer", "American Athletic Conference", "American"),
    ConferenceDef("A10", "Atlantic 10", "Atlantic 10"),
    ConferenceDef("ASun", "ASUN Conference", "ASUN"),
    ConferenceDef("B10", "Big Ten", "Big Ten"),
    ConferenceDef("B12", "Big 12", "Big 12"),
    ConferenceDef("BE", "Big East", "Big East"),
    ConferenceDef("BSky", "Big Sky", "Big Sky"),
    ConferenceDef("BSth", "Big South", "Big South"),
    ConferenceDef("BW", "Big West", "Big West"),
    ConferenceDef("CAA", "Colonial Athletic Association", "CAA"),
    ConferenceDef("CUSA", "Conference USA", "Conference USA"),
    ConferenceDef("Horz", "Horizon League", "Horizon League"),
    ConferenceDef("Ivy", "Ivy League", "Ivy League"),
    ConferenceDef("MAAC", "Metro Atlantic Athletic Conference", ""),   # renamed Metro in 2026-27
    ConferenceDef("MAC", "Mid-American Conference", "MAC"),
    ConferenceDef("MEAC", "Mid-Eastern Athletic Conference", "MEAC"),
    ConferenceDef("Metro", "Metro Conference", "Metro"),
    ConferenceDef("MVC", "Missouri Valley Conference", "Missouri Valley"),
    ConferenceDef("MWC", "Mountain West Conference", "Mountain West"),
    ConferenceDef("NEC", "Northeast Conference", "NEC"),
    ConferenceDef("OVC", "Ohio Valley Conference", "Ohio Valley"),
    ConferenceDef("P12", "Pac-12 Conference", "Pac-12"),
    ConferenceDef("Pat", "Patriot League", "Patriot League"),
    ConferenceDef("SB", "Sun Belt", "Sun Belt"),
    ConferenceDef("SC", "Southern Conference", "Southern"),
    ConferenceDef("SEC", "Southeastern Conference", "SEC"),
    ConferenceDef("Slnd", "Southland Conference", "Southland"),
    ConferenceDef("Sum", "Summit League", "Summit League"),
    ConferenceDef("SWAC", "Southwestern Athletic Conference", "SWAC"),
    ConferenceDef("UAC", "United Athletic Conference", "UAC"),
    ConferenceDef("WAC", "Western Athletic Conference", ""),           # became the UAC in 2026-27
    ConferenceDef("WCC", "West Coast Conference", "WCC"),
)

CODE_BY_CSV_NAME: dict[str, str] = {c.csv_name: c.code for c in CONFERENCES if c.csv_name}
NAME_BY_CODE: dict[str, str] = {c.code: c.name for c in CONFERENCES}


class ConferenceDataError(ValueError):
    """A season file names a conference that is not in CONFERENCES."""


def available_years() -> list[int]:
    """Season years that have a data file, ascending."""
    years = []
    for path in DATA_DIR.glob("*.csv"):
        if re.fullmatch(r"\d{4}", path.stem):
            years.append(int(path.stem))
    return sorted(years)


def file_year_for(season_year: int) -> int | None:
    """Year of the file that governs a season (newest <= season), or None for the frozen era."""
    usable = [y for y in available_years() if y <= season_year]
    return usable[-1] if usable else None


@lru_cache(maxsize=None)
def _load_file(file_year: int) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with open(DATA_DIR / f"{file_year}.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            slug = row["slug"].strip().lower()
            name = row["conference"].strip()
            try:
                mapping[slug] = CODE_BY_CSV_NAME[name]
            except KeyError:
                raise ConferenceDataError(
                    f"{file_year}.csv: unknown conference {name!r} for {row['team']!r}"
                ) from None
    return mapping


def season_conference_map(season_year: int) -> dict[str, str] | None:
    """{team slug: conference code} for a season, or None when the frozen CONF_MAP applies."""
    file_year = file_year_for(season_year)
    return None if file_year is None else _load_file(file_year)
