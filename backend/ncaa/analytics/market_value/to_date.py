"""
W.Add to date — the NCAA player-table figure built on PlayerMarketValue.

compute_market_values stores marginal_wins as a full-season rate (wins above
replacement over a season at the player's current per-minute impact and minutes).
The table shows the share earned so far: marginal_wins × GP / SEASON_GAMES.

Kept out of constants.py on purpose: that module's constant set is hashed into
every PlayerMarketValue row (constants_hash), and this display scaling is not part
of the valuation chain.
"""

SEASON_GAMES = 30  # approved scaling basis (Spencer, 2026-11-25)

# PlayerMarketValue.minutes_share = mpg / 40 of the row it was computed from
_SHARE_TOLERANCE = 1e-6


def wins_added_to_date(marginal_wins: float | None, gp: int | None) -> float | None:
    """marginal_wins × GP / SEASON_GAMES (None when either input is missing)."""
    if marginal_wins is None or gp is None:
        return None
    return marginal_wins * gp / SEASON_GAMES


def is_valued_row(minutes_share: float | None, mpg: float | None) -> bool:
    """
    True when a PlayerSeasonStats row is the one its PlayerMarketValue was computed from.

    A player who changed teams mid-season has one stats row per team but one value row
    (built from the highest-minutes team row). Matching mpg / 40 picks that row, so the
    other team's row shows no W.Add instead of a value scaled by the wrong games.
    """
    if minutes_share is None:
        return False
    return abs(minutes_share - (mpg or 0.0) / 40.0) < _SHARE_TOLERANCE
