"""
Calendar rules shared by the NBA and NCAA season helpers (no DB access).

Both leagues label a season by its ending year (2026 = 2025-26) and both
start playing in the autumn, so the "season in play" rolls over on the same
date. Each league's active window (the dates games are normally played) is
kept here so the daily job and its tests share one definition.
"""

from datetime import date

# First month of a new season year: from Oct 1 the season in play is the one
# ending next calendar year (Oct 2026 -> 2027), until Sep 30 of the next year.
SEASON_ROLLOVER_MONTH = 10

# (month, day) inclusive start / end of the dates games are normally played.
# A window whose start is after its end wraps the new year.
NBA_WINDOW = ((10, 1), (6, 30))     # preseason/opening night -> Finals
NCAA_WINDOW = ((11, 1), (4, 15))    # opening week -> national championship


def season_in_play(today: date | None = None) -> int:
    """Ending year of the season currently being played, or just finished."""
    today = today or date.today()
    return today.year + 1 if today.month >= SEASON_ROLLOVER_MONTH else today.year


def in_window(window: tuple[tuple[int, int], tuple[int, int]], today: date | None = None) -> bool:
    """True if today's (month, day) falls inside a possibly year-wrapping window."""
    today = today or date.today()
    start, end = window
    md = (today.month, today.day)
    if start <= end:
        return start <= md <= end
    return md >= start or md <= end
