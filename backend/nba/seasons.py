"""
NBA season helpers.

Two different questions, two different answers:

* ``get_current_season()`` -- the season the site DISPLAYS (the ``is_current``
  flag). Readers use this.
* ``season_in_play()`` -- the season the calendar says is being played. The
  data pipeline ingests THIS season, so a new season gets its first games even
  while the flag still points at the last one.

``activate_latest_season()`` closes the gap: once a newer season has a final
regular-season game it becomes the displayed season. Nothing needs editing at
rollover.
"""

from datetime import date, timedelta

from config.season_calendar import NBA_WINDOW, in_window, season_in_play
from nba.models import NBAGame, NBASeason

__all__ = [
    "NoSeasonError",
    "season_in_play",
    "get_current_season",
    "get_current_season_year",
    "resolve_season_year",
    "add_season_argument",
    "activate_latest_season",
    "has_recent_final_games",
    "in_season_window",
]


class NoSeasonError(LookupError):
    """No NBASeason rows exist yet (fresh database)."""


def get_current_season() -> NBASeason:
    """
    The displayed season: the ``is_current`` row, else the latest season that has
    games. Not simply the latest year -- empty future rows exist as outlook
    targets and must never be picked as a fallback.
    """
    season = (
        NBASeason.objects.filter(is_current=True).first()
        or NBASeason.objects.filter(games__isnull=False).order_by("-year").first()
        or NBASeason.objects.order_by("-year").first()
    )
    if season is None:
        raise NoSeasonError("No NBA seasons found. Run nba_sync_games first.")
    return season


def get_current_season_year() -> int:
    return get_current_season().year


def resolve_season_year(value: int | None) -> int:
    """Explicit ``--season`` wins; otherwise the season being played today."""
    return value if value is not None else season_in_play()


def add_season_argument(parser, help: str | None = None) -> None:
    """Optional ``--season`` that defaults to the season in play."""
    parser.add_argument(
        "--season",
        type=int,
        default=None,
        help=help or "Season ending year (default: the season in play, e.g. 2027 for 2026-27)",
    )


def _final_regular_season_games():
    return NBAGame.objects.filter(
        season_type="regular",
        counts_toward_regular_season=True,
        status__iexact="final",
    )


def activate_latest_season() -> tuple[NBASeason | None, NBASeason] | None:
    """
    Make the newest season with a final regular-season game the displayed one.

    Returns ``(old_current, new_current)`` when the flag moved, else None. Never
    moves backward and never flips to a season without final games, so a future
    row created for outlooks cannot become current by accident. Idempotent.
    """
    latest = (
        NBASeason.objects.filter(
            games__season_type="regular",
            games__counts_toward_regular_season=True,
            games__status__iexact="final",
        )
        .order_by("-year")
        .first()
    )
    if latest is None:
        return None

    current = NBASeason.objects.filter(is_current=True).first()
    if current is not None and latest.year <= current.year:
        return None

    latest.is_current = True
    latest.save(update_fields=["is_current"])  # model save() clears the old flag
    return current, latest


def has_recent_final_games(days: int = 14, today: date | None = None) -> bool:
    today = today or date.today()
    return _final_regular_season_games().filter(date__gte=today - timedelta(days=days)).exists()


def in_season_window(today: date | None = None) -> bool:
    return in_window(NBA_WINDOW, today)
