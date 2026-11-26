"""
nba/rating_scale.py — the scale of a season's player ratings (task 5.10b).

native-1 seasons (nba_compute_native_bpr) store centred ratings: obpr / dbpr average
0 (minutes-weighted), so 0 is a league-average player, not "unknown". Consumers that
need a value for a player with no rating, or a replacement level, take it from here:

  unknown player  = (-centre_obpr, -centre_dbpr)   (raw 0 on the centred scale)
  replacement     = R = -1.918; offense 0.8 R, defense 0.2 R
  Wins Added      = (bpr - R) x minutes / 48 / 37.73

native_scale(season) returns a Scale only when the season has an NBASeasonRatingScale row
AND native-1 rows; otherwise None, and the caller keeps its earlier constants unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

NATIVE_MODEL = "native-1"
WA_REPLACEMENT = -1.918        # task 5.5c fit 2 on centred ratings
# Wins Added divisor D (2026-11-26 recalibration; was 37.73, task 5.5c fit 2). Set so team sums of
# Wins Added move one-for-one with schedule-neutral expected wins (G * k/4 * adj_net, k from each
# season's home-win logistic): leave-one-season-out slope-1 divisors over the 21 full native seasons
# 2006-2026, with season fixed effects (each season has its own replacement-level intercept), span
# 27.71-28.17; this is their median. Recompute stored rows with `nba_recompute_wins_added --all`.
WA_DIVISOR = 27.97
REPLACEMENT_OFFENSE_SHARE = 0.8


@dataclass(frozen=True)
class Scale:
    centre_obpr: float
    centre_dbpr: float
    wins_divisor: float = WA_DIVISOR
    replacement: float = WA_REPLACEMENT

    @property
    def unknown_obpr(self) -> float:
        return -self.centre_obpr

    @property
    def unknown_dbpr(self) -> float:
        return -self.centre_dbpr

    @property
    def unknown_bpr(self) -> float:
        return -self.centre_obpr - self.centre_dbpr

    @property
    def replacement_obpr(self) -> float:
        return REPLACEMENT_OFFENSE_SHARE * self.replacement

    @property
    def replacement_dbpr(self) -> float:
        return (1.0 - REPLACEMENT_OFFENSE_SHARE) * self.replacement


def native_scale(season) -> Scale | None:
    """Scale for a season (NBASeason, its pk via season_id=..., or a year int); None unless native."""
    from nba.models import NBAPlayerSeasonStats, NBASeasonRatingScale

    if season is None:
        return None
    if isinstance(season, int):
        q = {"season__year": season}
    else:
        q = {"season": season}
    row = NBASeasonRatingScale.objects.filter(bpr_model=NATIVE_MODEL, **q).first()
    if row is None:
        return None
    if not NBAPlayerSeasonStats.objects.filter(bpr_model=NATIVE_MODEL, season_type="regular",
                                               season_id=row.season_id).exists():
        return None
    return Scale(row.centre_obpr, row.centre_dbpr, row.wins_divisor, row.replacement)


def native_scale_by_season_id(season_id: int, cache: dict) -> Scale | None:
    """native_scale for an NBASeason pk, memoised in `cache` (one lookup per season per run)."""
    if season_id not in cache:
        from nba.models import NBASeason
        cache[season_id] = native_scale(NBASeason.objects.filter(pk=season_id).first())
    return cache[season_id]


def row_is_native(row) -> bool:
    """A stats row (model instance or values() dict) written by the native model."""
    model = row.get("bpr_model") if isinstance(row, dict) else getattr(row, "bpr_model", None)
    return model == NATIVE_MODEL
