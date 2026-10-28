"""
NCAA season helpers.

* ``get_current_season()`` -- the season the site DISPLAYS (``is_current``).
* ``season_in_play()`` -- the season the calendar says is being played; the
  data pipeline ingests this one.

``activate_latest_season()`` moves the displayed season forward once a newer
season has a final game, so rollover needs no manual flag edit.
"""

from datetime import date, timedelta

from django.db.models import Max

from config.season_calendar import NCAA_WINDOW, in_window, season_in_play
from ncaa.models import Game, Season

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
    """No Season rows exist yet (fresh database)."""


def get_current_season() -> Season:
    """The displayed season: the ``is_current`` row, else the latest year."""
    season = (
        Season.objects.filter(is_current=True).first()
        or Season.objects.order_by("-year").first()
    )
    if season is None:
        raise NoSeasonError("No NCAA seasons found. Run ingest_gamelogs --create-season first.")
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


def activate_latest_season() -> tuple[Season | None, Season] | None:
    """
    Make the newest season with a final game the displayed one.

    Returns ``(old_current, new_current)`` when the flag moved, else None. Never
    moves backward and never flips to a season without final games. Idempotent.
    """
    latest_year = Game.objects.filter(status="final").aggregate(y=Max("season_year"))["y"]
    if latest_year is None:
        return None
    latest = Season.objects.filter(year=latest_year).first()
    if latest is None:
        return None

    current = Season.objects.filter(is_current=True).first()
    if current is not None and latest.year <= current.year:
        return None

    latest.is_current = True
    latest.save(update_fields=["is_current"])  # model save() clears the old flag
    return current, latest


def has_recent_final_games(days: int = 14, today: date | None = None) -> bool:
    today = today or date.today()
    return Game.objects.filter(status="final", game_date__gte=today - timedelta(days=days)).exists()


def in_season_window(today: date | None = None) -> bool:
    return in_window(NCAA_WINDOW, today)
