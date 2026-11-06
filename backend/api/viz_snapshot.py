"""
Which TeamSeasonRatings / TeamSeasonMetrics rows the NCAA visualizations read.

Every team has two kinds of rows per season:
  is_pre_tournament=False  full-season ratings, recomputed by the daily pipeline
  is_pre_tournament=True   frozen snapshot taken once at Selection Sunday

The tournament-oriented charts (trapezoid, landscape, crystal ball, cinderella)
want the Selection Sunday snapshot so a season is judged on what was known
before the bracket. But the snapshot only exists from Selection Sunday on, so a
season in progress has none and those charts came back empty all regular
season. Rule: use the snapshot when the season has one, otherwise the
full-season rows.
"""

from ncaa.models import Season, TeamSeasonRatings


def use_pre_tournament_rows(season: Season) -> bool:
    """True if `season` has a Selection Sunday snapshot to show, else False."""
    return TeamSeasonRatings.all_objects.filter(
        season=season,
        is_pre_tournament=True,
        team__is_d1=True,
        games_played__gt=0,
    ).exists()
