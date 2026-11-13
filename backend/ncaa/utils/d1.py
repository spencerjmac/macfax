"""
Division I membership for a season: the one place code decides "is this team D1 in season Y".

Team.is_d1 means "D1 today". Season decisions read TeamSeasonMembership (one row per season and team;
is_d1, is_reclassifying). If a season has no membership rows at all, these helpers fall back to
Team.is_d1 and log a warning (once per season per process).

  d1_q(season, "team")                 Q for rows whose `team` FK is D1 that season
  d1_q(season, "opponent")             same for the opponent FK
  d1_q(season, "")                     Q on Team itself (pk)
  d1_team_ids(season)                  set of D1 team ids (for loops)
  exclude_reclassifying=True           drop teams in an NCAA transition (tournament eligibility); default off
"""

import logging

from django.db.models import Q

logger = logging.getLogger(__name__)
_warned: set = set()


def _year(season) -> int:
    return int(getattr(season, "year", season))


def has_membership(season) -> bool:
    from ncaa.models import TeamSeasonMembership

    year = _year(season)
    ok = TeamSeasonMembership.objects.filter(season__year=year).exists()
    if not ok and year not in _warned:
        _warned.add(year)
        logger.warning(f"No TeamSeasonMembership rows for {year}: falling back to Team.is_d1 (D1 today)")
    return ok


def _members(season, exclude_reclassifying: bool):
    from ncaa.models import TeamSeasonMembership

    qs = TeamSeasonMembership.objects.filter(season__year=_year(season), is_d1=True)
    if exclude_reclassifying:
        qs = qs.exclude(is_reclassifying=True)
    return qs.values("team_id")


def d1_q(season, team_field: str = "team", *, exclude_reclassifying: bool = False) -> Q:
    """Q selecting rows whose `team_field` FK is a D1 team in `season` (Season or year).

    team_field "" means the queryset is Team itself. With no membership rows for the season, falls back
    to Team.is_d1 (exclude_reclassifying cannot apply then).
    """
    prefix = f"{team_field}__" if team_field else ""
    if has_membership(season):
        return Q(**{f"{prefix}{'id' if team_field else 'pk'}__in": _members(season, exclude_reclassifying)})
    return Q(**{f"{prefix}is_d1": True})


def d1_team_ids(season, *, exclude_reclassifying: bool = False) -> set:
    """Ids of D1 teams in `season` (fallback: Team.is_d1)."""
    from ncaa.models import Team

    if has_membership(season):
        return set(_members(season, exclude_reclassifying).values_list("team_id", flat=True))
    return set(Team.objects.filter(is_d1=True).values_list("id", flat=True))


def is_d1(team_id: int, season) -> bool:
    return team_id in d1_team_ids(season)
