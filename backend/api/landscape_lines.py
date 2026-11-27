"""
Tier lines for the NCAA Efficiency Landscape.

Each line is a fixed distance below a reference: the average Adj EM of the top 3 D1 teams, taken
before any conference / tournament / top-N filter so the lines don't move with the filters.

Calibration (2026-11-27; runs and data in macfax-runs/landscape-lines/, landscape_compare.py):
  sample   prod Selection Sunday snapshots (is_pre_tournament=True), 2005-2026 without 2020:
           21 seasons, 21 champions, 84 Final Four teams
  exempt   UConn 2011 and 2014 (ranked 16th and 25th on Selection Sunday)
  Title Favorites  reference - 4.6   smallest distance that has every champion except the UConn
                                     pair above it (19/21; Duke 2015 sits exactly on it)
  Final 4          reference - 8.4   75% of Final Four teams above it (63/84)
  Hit or Miss      reference - 15.3  no champions and at most 5% of Final Four teams below it
                                     (80/84 above)

Rounding: the calibration used the API's 0.1-rounded Adj EM, and Duke 2015 is exactly 4.6 below
the reference in those units (33.8 - 29.2) but 4.64 below in unrounded ones. So the reference is
built from the same 0.1-rounded values the API returns as `net`, and each line is rounded UP to
the 0.1 grid. Every `net` is on that grid, so `net >= line` holds exactly when
`net >= reference - delta`, and floating-point noise can't push a team on the line out.
"""

import math
from typing import Iterable

REFERENCE_TOP_N = 3

TITLE_FAVORITES_DELTA = 4.6
FINAL_FOUR_DELTA = 8.4
HIT_OR_MISS_DELTA = 15.3

DELTAS = {
    "title": TITLE_FAVORITES_DELTA,
    "final4": FINAL_FOUR_DELTA,
    "hit_miss": HIT_OR_MISS_DELTA,
}


def _ceil_tenth(x: float) -> float:
    """Round up to the 0.1 grid, ignoring float noise (29.199999999999996 -> 29.2, not 29.3)."""
    return round(math.ceil(round(x * 10, 6)) / 10, 1)


def landscape_reference(adj_ems: Iterable[float]) -> float:
    """Average of the top 3 Adj EM values, each rounded to 0.1 as the API shows them."""
    nets = sorted((round(v, 1) for v in adj_ems), reverse=True)
    if not nets:
        raise ValueError("landscape_reference needs at least one team")
    top = nets[:REFERENCE_TOP_N]
    return sum(top) / len(top)


def landscape_lines(adj_ems: Iterable[float]) -> dict:
    """Reference and the three tier lines (Adj EM values) for one season's D1 teams."""
    reference = landscape_reference(adj_ems)
    return {
        "reference": reference,
        "lines": {key: _ceil_tenth(reference - delta) for key, delta in DELTAS.items()},
    }
