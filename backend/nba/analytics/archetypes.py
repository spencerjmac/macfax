"""
archetypes.py — NBA player role classification for Box BPR.

Six mutually exclusive buckets evaluated in priority order so a player
lands in the most specific matching archetype rather than "connector".

Priority (highest to lowest):
  1. creator      — high-usage initiators (guards/wings who run the offense)
  2. scorer       — high-usage volume scorers without creation
  3. interior     — big-man bucket (low 3PA, rim presence)
  4. three_and_d  — off-ball wings/guards with spacing + defensive value
  5. stretch      — moderate-volume shooters without strong defense signal
  6. connector    — everything else (versatile/hybrid, catch-all)

Archetypes are used as one-hot features in the Ridge regression and to
allow archetype-aware prior SDs in future stages.
"""

from __future__ import annotations

ARCHETYPE_CREATOR = "creator"
ARCHETYPE_SCORER = "scorer"
ARCHETYPE_INTERIOR = "interior"
ARCHETYPE_THREE_AND_D = "three_and_d"
ARCHETYPE_STRETCH = "stretch"
ARCHETYPE_CONNECTOR = "connector"

ALL_ARCHETYPES = [
    ARCHETYPE_CREATOR,
    ARCHETYPE_SCORER,
    ARCHETYPE_INTERIOR,
    ARCHETYPE_THREE_AND_D,
    ARCHETYPE_STRETCH,
    ARCHETYPE_CONNECTOR,
]


def classify_nba_archetype(
    usg_pct: float | None,
    ast_pct: float | None,
    fg3a_pg: float | None,
    oreb_pct: float | None,
    blk_pct: float | None,
    d_mpir: float | None,
) -> str:
    """
    Classify a player into one of six NBA archetypes.

    All inputs are nullable — missing data falls through to 'connector'.
    Thresholds are based on 2024-25 NBA leaderboard distributions.
    """
    u = usg_pct or 0.0
    a = ast_pct or 0.0
    fg3a = fg3a_pg or 0.0
    oreb = oreb_pct or 0.0
    blk = blk_pct or 0.0
    d = d_mpir or 0.0

    # usg_pct and ast_pct stored as decimals (0.0–1.0) from NBA.com

    # Creator: runs the offense at high volume
    if u >= 0.22 and a >= 0.20:
        return ARCHETYPE_CREATOR

    # Scorer: high usage but not a primary playmaker
    if u >= 0.22 and a < 0.20:
        return ARCHETYPE_SCORER

    # Interior: rim-anchored bigs (low perimeter shooting, high paint presence)
    # oreb_pct and blk_pct also stored as decimals
    if fg3a < 2.0 and (oreb >= 0.10 or blk >= 0.025):
        return ARCHETYPE_INTERIOR

    # 3-and-D: off-ball contributor with clear defensive value
    if fg3a >= 3.0 and u < 0.18 and d > 0.0:
        return ARCHETYPE_THREE_AND_D

    # Stretch: perimeter shooting without the strong defensive signal
    if fg3a >= 4.0:
        return ARCHETYPE_STRETCH

    return ARCHETYPE_CONNECTOR


def archetype_onehot(archetype: str) -> list[float]:
    """Return a 6-dim one-hot vector for the given archetype label."""
    return [1.0 if a == archetype else 0.0 for a in ALL_ARCHETYPES]
