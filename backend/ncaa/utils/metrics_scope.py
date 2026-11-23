"""
Which TeamGameStats rows count toward a team's TeamSeasonMetrics.

Shared by compute_team_metrics (which stores the season totals) and the rankings
view (which sums final scores over the same games for PTS / OPP PTS), so the
two always cover the same games.
"""

from django.db.models import Q

from ncaa.utils.d1 import d1_q


def metrics_game_stats_q(season, is_pre_tournament: bool) -> Q:
    """Q over TeamGameStats: final games vs opponents that were D1 that season.

    Canceled games stored as 0-0 'final' are excluded. With is_pre_tournament,
    only games on or before Selection Sunday count.
    """
    q = Q(game__season_year=season.year, game__status="final") & d1_q(season, "opponent")
    q &= ~Q(game__home_score=0, game__away_score=0)
    if is_pre_tournament and season.selection_sunday_date:
        q &= Q(game__game_date__lte=season.selection_sunday_date)
    return q
