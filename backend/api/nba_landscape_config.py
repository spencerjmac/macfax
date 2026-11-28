"""
NBA Efficiency Landscape tier lines.

Each line marks a rank: it is drawn halfway between the adj_net of the Nth and the (N+1)th team of the
season, so exactly the top N teams sit above it.

Calibration (2026-11-27; runs and data in macfax-runs/nba-landscape/, compare_methods.py):
  sample   prod regular-season final ratings 2005-2026: 22 seasons, 660 team-seasons, 22 champions,
           88 conference finalists (champion, runner-up and both conference-finals losers),
           352 playoff teams (play-in losers count as missing the playoffs). Outcomes come from the
           playoff series in NBAGame.
  Champion   top 7   smallest rank that has every champion (22/22); two champions were 7th
                     (2011 DAL, 2023 DEN)
  Contender  top 10  81/88 conference finalists
  Playoff    top 15  loosest rank where at least 90% of the teams above made the playoffs
                     (302/330, 91.5%); below it: no champion, 2/88 conference finalists
                     (2023 LAL 18th, 2023 MIA 20th)

Why rank: our NBA adj_net is not centred on 0. The league mean drifts by season (-3.5 in 2020,
+7.3 in 2012; see services/ratings_engine.iterative_adjust), so a fixed net such as the old 0.0
Playoff line meant different things in different seasons. Ranks don't move with that drift. Gaps
below #1 or below the top-3 average don't move either, but they changed with the era: the cutoffs fit
on 2005-15 missed 2 of the 11 champions from 2016-26. Rank fit top 7 for champions in both eras.

The line uses unrounded adj_net, so it separates the Nth and (N+1)th teams' true values. If those two
are tied, the line passes through both. With N teams or fewer there is no (N+1)th team, and the line
is left out (None).
"""

from typing import Iterable, Optional

CHAMPION_RANK = 7
CONTENDER_RANK = 10
PLAYOFF_RANK = 15

LINE_RANKS = {
    "champion": CHAMPION_RANK,
    "contender": CONTENDER_RANK,
    "playoff": PLAYOFF_RANK,
}


def rank_line(nets: Iterable[float], n: int) -> Optional[float]:
    """Halfway between the Nth and (N+1)th highest net; None when there are N teams or fewer."""
    ordered = sorted(nets, reverse=True)
    if n < 1 or len(ordered) <= n:
        return None
    return (ordered[n - 1] + ordered[n]) / 2


def landscape_lines(nets: Iterable[float]) -> dict:
    """{key: {"n": N, "net": line or None}} for the three lines, from one season's adj_net values."""
    nets = list(nets)
    out = {}
    for key, n in LINE_RANKS.items():
        value = rank_line(nets, n)
        out[key] = {"n": n, "net": None if value is None else round(value, 3)}
    return out
