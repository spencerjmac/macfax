"""
Abstract NBA data provider interface.

Any concrete provider must implement this interface so the rest of the
codebase is decoupled from nba_api response shapes.

When nba_api has endpoint churn (as it did in late 2025), you fix it
in exactly one file — the concrete provider — not scattered across the app.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Provider output dataclasses — these are the shapes the app trusts
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RawGameResult:
    """One game result as returned by LeagueGameLog or TeamGameLog."""

    game_id: str
    date: str               # ISO date string YYYY-MM-DD
    season_year: int        # ending year
    home_team_id: int
    away_team_id: int
    home_score: Optional[int]
    away_score: Optional[int]
    home_abbreviation: str
    away_abbreviation: str
    arena: str = ""
    season_type: str = "regular"
    status: str = "Final"


@dataclass
class RawLeagueGameLog:
    """
    One row from LeagueGameLog — game metadata + team box score in a single call.
    One row = one team's half of one game.
    Pair two rows by game_id (one with is_home=True, one with is_home=False) to get
    the full game.
    """

    game_id: str
    date: str               # ISO date string YYYY-MM-DD
    season_id: str          # e.g. "22025" — encodes season type + year
    team_id: int            # NBA.com team ID
    team_abbreviation: str
    is_home: bool           # True if MATCHUP contains " vs. "

    # Scoring
    pts: Optional[int]      # None for future/scheduled games

    # Box score (used for four factors + possession calculation)
    fgm: Optional[int]
    fga: Optional[int]
    fg3m: Optional[int]
    fg3a: Optional[int]
    ftm: Optional[int]
    fta: Optional[int]
    oreb: Optional[int]
    dreb: Optional[int]
    tov: Optional[int]

    # Game result
    wl: str                 # 'W', 'L', or '' for scheduled games

    @property
    def is_final(self) -> bool:
        return self.wl in ('W', 'L')

    @property
    def season_type(self) -> str:
        """Derive season type from SEASON_ID prefix digit."""
        prefix = self.season_id[:1] if self.season_id else '2'
        return {
            '1': 'preseason',
            '2': 'regular',
            '4': 'playoffs',
            '5': 'play_in',
        }.get(prefix, 'regular')


@dataclass
class RawTeamBoxScore:
    """Team-level box score from BoxScoreTraditionalV3."""

    game_id: str
    team_id: int
    is_home: bool
    pts: int
    fgm: int
    fga: int
    fg3m: int
    fg3a: int
    ftm: int
    fta: int
    oreb: int
    dreb: int
    tov: int


@dataclass
class RawPlayerBoxScore:
    """Player-level box score from BoxScoreTraditionalV3."""

    game_id: str
    player_id: int
    team_id: int
    minutes_clock: str      # raw clock string e.g. "34:21" — seconds_played computed by caller
    pts: int
    reb: int
    ast: int
    stl: int
    blk: int
    tov: int
    fgm: int
    fga: int
    fg3m: int
    fg3a: int
    ftm: int
    fta: int
    plus_minus: Optional[int] = None


@dataclass
class RawPlayerInfo:
    """Player identity from CommonAllPlayers."""

    player_id: int
    name: str
    is_active: bool
    team_id: Optional[int] = None


@dataclass
class RawRosterEntry:
    """One roster entry from CommonTeamRoster."""

    player_id: int
    team_id: int
    name: str
    jersey_number: str = ""
    position: str = ""


@dataclass
class ProviderHealthResult:
    """Result of a provider health check on a single endpoint family."""

    endpoint: str
    ok: bool
    error: Optional[str] = None
    latency_ms: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# Abstract provider
# ─────────────────────────────────────────────────────────────────────────────


class NBADataProvider(ABC):
    """
    Abstract interface for NBA data retrieval.

    Implement this class to add a new data source (e.g., a future Sportradar
    adapter) without touching any ingestion or model code.
    """

    @abstractmethod
    def get_league_game_log(
        self,
        season_year: int,
        season_type: str = "Regular Season",
    ) -> list[RawLeagueGameLog]:
        """
        Returns one row per team per game via LeagueGameLog.

        Prefer this over per-team calls — one request covers the whole season.
        Pair rows by game_id to reconstruct full games.
        """

    @abstractmethod
    def get_team_game_log(
        self,
        team_id: int,
        season_year: int,
        season_type: str = "Regular Season",
    ) -> list[RawGameResult]:
        """Per-team game log — use when you need one team's schedule quickly."""

    @abstractmethod
    def get_box_score_traditional(
        self,
        game_id: str,
    ) -> tuple[list[RawTeamBoxScore], list[RawPlayerBoxScore]]:
        """
        Box score for a single game.
        Returns (team_box_scores, player_box_scores).
        """

    @abstractmethod
    def get_team_roster(
        self,
        team_id: int,
        season_year: int,
    ) -> list[RawRosterEntry]:
        """Current roster for a team from CommonTeamRoster."""

    @abstractmethod
    def get_all_players(
        self,
        season_year: int,
        is_only_current_season: bool = True,
    ) -> list[RawPlayerInfo]:
        """All active players from CommonAllPlayers."""

    @abstractmethod
    def health_check(self) -> list[ProviderHealthResult]:
        """
        Probe each endpoint family and return a list of health results.
        Used by GET /api/nba/health/.
        """
