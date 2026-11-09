"""
native_prior.py — prior for a season's RAPM built only from our own ratings.

Blends a player's box-score rating for the season with last season's rating
shrunk toward zero (rho). Players with only one of the two get that one:
the box rating as is, or last season's rating shrunk by rho.

Inputs and output map nba_id -> rating. Pure function: no database.
"""

from __future__ import annotations


def native_prior(
    box: dict[int, float],
    prev: dict[int, float],
    w_box: float,
    rho: float,
) -> dict[int, float]:
    """
    Per player:
      both present -> w_box * box + (1 - w_box) * rho * prev
      box only     -> box
      prev only    -> rho * prev
    """
    prior: dict[int, float] = {}
    for nba_id in box.keys() | prev.keys():
        if nba_id in box and nba_id in prev:
            prior[nba_id] = w_box * box[nba_id] + (1 - w_box) * rho * prev[nba_id]
        elif nba_id in box:
            prior[nba_id] = box[nba_id]
        else:
            prior[nba_id] = rho * prev[nba_id]
    return prior
