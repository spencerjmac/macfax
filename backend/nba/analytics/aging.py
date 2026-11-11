"""
aging.py: a quadratic aging curve learned from a rating chain's own history.

For each player rated in both season s-1 and season s, his change in rating
(s minus s-1) is regressed on a quadratic in his age at s (age on Feb 1 of
season-ending year s), weighted by the smaller of his two seasons'
possessions. Offense and defense are fitted separately by the caller.

Only the seasons passed in are used: the caller decides which seasons are
history (nba_experiment_final_bpr --age-mult passes seasons up to Y-1 for Y).
"""

from __future__ import annotations

from datetime import date

import numpy as np

MIN_AGE_PAIRS = 30   # fewer pairs than this: no curve (no adjustment)


def age_at(dob: date | None, season: int) -> float | None:
    """Age in years on Feb 1 of season-ending year `season` (mid-season)."""
    if dob is None:
        return None
    return (date(season, 2, 1) - dob).days / 365.25


def aging_pairs(hist: dict[int, dict[int, float]], poss: dict[int, dict[int, float]],
                dobs: dict[int, date], upto: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    (ages, changes, weights) over every season s <= upto with s-1 also in hist: players
    rated in both, with a birth date; change = rating(s) - rating(s-1), age at s,
    weight = min(possessions in s-1, possessions in s).
    """
    ages, deltas, weights = [], [], []
    for s in sorted(hist):
        if s > upto or (s - 1) not in hist:
            continue
        prev, cur = hist[s - 1], hist[s]
        for pid in prev.keys() & cur.keys():
            a = age_at(dobs.get(pid), s)
            w = min(poss.get(s - 1, {}).get(pid, 0.0), poss.get(s, {}).get(pid, 0.0))
            if a is None or w <= 0:
                continue
            ages.append(a); deltas.append(cur[pid] - prev[pid]); weights.append(w)
    return np.array(ages), np.array(deltas), np.array(weights)


def fit_aging_curve(ages: np.ndarray, deltas: np.ndarray, weights: np.ndarray,
                    min_pairs: int = MIN_AGE_PAIRS) -> tuple[float, float, float] | None:
    """Weighted least squares of change on [1, age, age^2]; None with too few pairs."""
    if len(ages) < min_pairs:
        return None
    X = np.column_stack([np.ones_like(ages), ages, ages ** 2])
    sw = np.sqrt(weights)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], deltas * sw, rcond=None)
    return float(beta[0]), float(beta[1]), float(beta[2])


def curve_value(coefs: tuple[float, float, float] | None, age: float | None) -> float:
    """Expected change at `age` (0 without a curve or an age)."""
    if coefs is None or age is None:
        return 0.0
    c0, c1, c2 = coefs
    return c0 + c1 * age + c2 * age * age
