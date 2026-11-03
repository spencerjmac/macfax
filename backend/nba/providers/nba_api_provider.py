"""
NBA.com data provider — wraps nba_api (v1.9+).

This is the ONLY place nba_api response shapes are allowed to exist.
All callers receive normalized dataclasses from providers/base.py.

Resilience notes (based on nba_api release history):
  - Late 2025: nba_api updated request headers. Headers are managed by the
    package internally — keep nba-api pinned to >=1.9.0 in pyproject.toml.
  - PlayByPlayV2 / ScoreboardV2 deprecated \u2192 only V3 endpoints used here.
  - TeamGameLog was briefly deprecated then restored (Nov 2025).
  - LeagueGameLog is preferred for season ingestion (one call vs 30 calls).
  - All endpoint calls go through _call_with_retry() for uniform handling.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .base import (
    NBADataProvider,
    ProviderHealthResult,
    RawLeagueGameLog,
    RawGameResult,
    RawPlayerBoxScore,
    RawPlayerInfo,
    RawRosterEntry,
    RawTeamBoxScore,
)

logger = logging.getLogger(__name__)

# Raw PlayByPlayV3 / GameRotation responses, one file per game and endpoint
# (gitignored). Project-root data/nba in a checkout, /data/nba in Docker.
PBP_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "nba" / "pbp_cache"
GAME_FETCH_TRIES = 8              # these endpoints' HTTP 500s are often transient
GAME_FETCH_MAX_BACKOFF = 30.0     # seconds


class FetchSkipped(RuntimeError):
    """An earlier run already gave up on this game's endpoint; not retried."""


try:
    import nba_api  # noqa: F401
    NBA_API_AVAILABLE = True
except ImportError:
    NBA_API_AVAILABLE = False
    logger.warning(
        "nba_api is not installed. Run: pip install nba-api"
    )


# ── Season string helpers ─────────────────────────────────────────────────────

def _season_str(year: int) -> str:
    """2026 \u2192 '2025-26'"""
    return f"{year - 1}-{str(year)[2:]}"


def _season_type_str(season_type: str) -> str:
    mapping = {
        "regular": "Regular Season",
        "Regular Season": "Regular Season",
        "preseason": "Pre Season",
        "Pre Season": "Pre Season",
        "play_in": "PlayIn",
        "PlayIn": "PlayIn",
        "playoffs": "Playoffs",
        "Playoffs": "Playoffs",
    }
    return mapping.get(season_type, "Regular Season")


# ─────────────────────────────────────────────────────────────────────────────
# Concrete provider
# ─────────────────────────────────────────────────────────────────────────────


class NBAApiProvider(NBADataProvider):
    """
    Concrete provider backed by nba_api (NBA.com stats endpoints).

    Args:
        sleep_seconds: Minimum sleep between API calls (rate-limit buffer).
        max_retries: Retry attempts on transient failures.
        timeout: Request timeout in seconds.
        cache_dir: Raw play-by-play / rotation response cache (None disables).
    """

    def __init__(
        self,
        sleep_seconds: float = 0.6,
        max_retries: int = 3,
        timeout: int = 30,
        cache_dir: "Path | None" = PBP_CACHE_DIR,
    ):
        self.sleep_seconds = sleep_seconds
        self.max_retries = max_retries
        self.timeout = timeout
        self.cache_dir = cache_dir
        if not NBA_API_AVAILABLE:
            raise RuntimeError("nba_api is not installed. Run: pip install nba-api")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _call_with_retry(self, fn, *args, **kwargs):
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(self.sleep_seconds)
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("nba_api call failed (attempt %d/%d): %s", attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    # Timeout errors need much longer backoff — 0.8s retry after 60s timeout is useless
                    exc_str = str(exc).lower()
                    is_timeout = "timeout" in exc_str or "timed out" in exc_str
                    backoff = (20.0 * attempt) if is_timeout else (self.sleep_seconds * attempt)
                    logger.info("Backing off %.1fs before retry...", backoff)
                    time.sleep(backoff)
        raise RuntimeError(f"nba_api call failed after {self.max_retries} attempts") from last_exc

    def _fetch_game_endpoint(self, endpoint_cls, game_id: str):
        """
        One game's nba_api endpoint object with its data sets loaded.

        Reads the raw response from the cache when the file exists. Otherwise
        calls NBA.com up to GAME_FETCH_TRIES times with exponential backoff and
        caches the raw response. When every try fails, <game_id>_<endpoint>.failed
        records when, and later calls raise FetchSkipped instead of trying again
        (delete the file to retry).
        """
        from nba_api.stats.library.http import NBAStatsResponse

        name = f"{game_id}_{endpoint_cls.endpoint}"
        cached = self.cache_dir / f"{name}.json" if self.cache_dir else None
        failed = self.cache_dir / f"{name}.failed" if self.cache_dir else None

        if cached and cached.exists():
            ep = endpoint_cls(game_id=game_id, timeout=self.timeout, get_request=False)
            ep.nba_response = NBAStatsResponse(response=cached.read_text(), status_code=200, url=None)
            ep.load_response()
            return ep
        if failed and failed.exists():
            raise FetchSkipped(f"{name}: gave up earlier {failed.read_text().strip()}")

        last_exc: Optional[Exception] = None
        for attempt in range(1, GAME_FETCH_TRIES + 1):
            try:
                time.sleep(self.sleep_seconds)
                # Requests and loads; an empty HTTP 500 body raises while loading.
                ep = endpoint_cls(game_id=game_id, timeout=self.timeout)
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("%s failed (try %d/%d): %s", name, attempt, GAME_FETCH_TRIES, exc)
                if attempt < GAME_FETCH_TRIES:
                    time.sleep(min(GAME_FETCH_MAX_BACKOFF, 2.0 ** attempt))
        else:
            if failed:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                failed.write_text(json.dumps({
                    "failed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "tries": GAME_FETCH_TRIES,
                    "error": str(last_exc)[:300],
                }))
            raise RuntimeError(f"{name} failed after {GAME_FETCH_TRIES} tries") from last_exc

        if cached:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = cached.with_suffix(".tmp")
            tmp.write_text(ep.nba_response.get_response())
            tmp.replace(cached)
        return ep

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        try:
            return int(value) if value is not None and str(value).strip() not in ('', 'None', 'nan') else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_date(raw) -> str:
        """Parse various nba_api date formats to YYYY-MM-DD."""
        import pandas as pd
        try:
            return pd.to_datetime(str(raw)).strftime("%Y-%m-%d")
        except Exception:
            return str(raw)[:10]

    # ── get_league_game_log ───────────────────────────────────────────────────

    def get_league_game_log(
        self,
        season_year: int,
        season_type: str = "Regular Season",
    ) -> list[RawLeagueGameLog]:
        """
        Fetch all team-game rows for a season from LeagueGameLog.

        Returns one RawLeagueGameLog per team per game. The caller pairs rows
        by game_id (two rows per game: is_home=True and is_home=False).
        """
        from nba_api.stats.endpoints import leaguegamelog

        season = _season_str(season_year)
        season_type_s = _season_type_str(season_type)

        def _call():
            lg = leaguegamelog.LeagueGameLog(
                season=season,
                season_type_all_star=season_type_s,
                timeout=self.timeout,
            )
            return lg.get_data_frames()[0]

        df = self._call_with_retry(_call)

        if df is None or df.empty:
            logger.warning("LeagueGameLog returned empty for season %s %s", season, season_type_s)
            return []

        results: list[RawLeagueGameLog] = []
        for _, row in df.iterrows():
            try:
                matchup = str(row.get("MATCHUP", ""))
                is_home = " vs. " in matchup or " vs " in matchup
                wl = str(row.get("WL", "") or "").strip()

                results.append(
                    RawLeagueGameLog(
                        game_id=str(row["GAME_ID"]),
                        date=self._parse_date(row.get("GAME_DATE", "")),
                        season_id=str(row.get("SEASON_ID", "")),
                        team_id=int(row["TEAM_ID"]),
                        team_abbreviation=str(row.get("TEAM_ABBREVIATION", "")),
                        is_home=is_home,
                        matchup=matchup,
                        pts=self._safe_int(row.get("PTS")),
                        fgm=self._safe_int(row.get("FGM")),
                        fga=self._safe_int(row.get("FGA")),
                        fg3m=self._safe_int(row.get("FG3M")),
                        fg3a=self._safe_int(row.get("FG3A")),
                        ftm=self._safe_int(row.get("FTM")),
                        fta=self._safe_int(row.get("FTA")),
                        oreb=self._safe_int(row.get("OREB")),
                        dreb=self._safe_int(row.get("DREB")),
                        tov=self._safe_int(row.get("TOV")),
                        wl=wl,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not parse LeagueGameLog row: %s", exc)
                continue

        logger.info(
            "LeagueGameLog: %d rows for %s %s", len(results), season, season_type_s
        )
        return results

    # ── get_team_game_log ─────────────────────────────────────────────────────

    def get_team_game_log(
        self,
        team_id: int,
        season_year: int,
        season_type: str = "Regular Season",
    ) -> list[RawGameResult]:
        """Per-team fallback. Prefer get_league_game_log for full-season ingestion."""
        # TODO (Phase 2 enhancement): implement if needed as fallback
        logger.info("get_team_game_log: team=%s season=%s [not yet implemented]", team_id, season_year)
        return []

    # ── get_box_score_traditional ─────────────────────────────────────────────

    def get_box_score_traditional(
        self,
        game_id: str,
    ) -> tuple[list[RawTeamBoxScore], list[RawPlayerBoxScore]]:
        """
        Full BoxScoreTraditionalV3 for one game.
        Used in Phase 4 for player-level stats.
        Phase 2 uses LeagueGameLog for team-level stats instead.
        """
        from nba_api.stats.endpoints import boxscoretraditionalv3

        def _call():
            box = boxscoretraditionalv3.BoxScoreTraditionalV3(
                game_id=game_id,
                timeout=self.timeout,
            )
            return box.get_data_frames()

        dfs = self._call_with_retry(_call)

        # V3 returns camelCase column names (personId, teamId, points, etc.)
        # df[0] = player stats (has personId)
        # df[1] = starters/bench splits
        # df[2] = team totals (2 rows, no personId)
        player_df = None
        team_df = None
        for df in dfs:
            if df is None or df.empty:
                continue
            cols = set(df.columns)
            if "personId" in cols:
                player_df = df
            elif "teamId" in cols and "personId" not in cols and len(df) <= 2:
                team_df = df

        team_scores: list[RawTeamBoxScore] = []
        if team_df is not None:
            for _, row in team_df.iterrows():
                try:
                    team_scores.append(
                        RawTeamBoxScore(
                            game_id=game_id,
                            team_id=int(row["teamId"]),
                            is_home=False,  # caller must determine from game record
                            pts=self._safe_int(row.get("points")) or 0,
                            fgm=self._safe_int(row.get("fieldGoalsMade")) or 0,
                            fga=self._safe_int(row.get("fieldGoalsAttempted")) or 0,
                            fg3m=self._safe_int(row.get("threePointersMade")) or 0,
                            fg3a=self._safe_int(row.get("threePointersAttempted")) or 0,
                            ftm=self._safe_int(row.get("freeThrowsMade")) or 0,
                            fta=self._safe_int(row.get("freeThrowsAttempted")) or 0,
                            oreb=self._safe_int(row.get("reboundsOffensive")) or 0,
                            dreb=self._safe_int(row.get("reboundsDefensive")) or 0,
                            tov=self._safe_int(row.get("turnovers")) or 0,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not parse team box score row: %s", exc)

        player_scores: list[RawPlayerBoxScore] = []
        if player_df is not None:
            for _, row in player_df.iterrows():
                try:
                    player_id_val = row.get("personId") or row.get("playerId")
                    if not player_id_val:
                        continue
                    player_scores.append(
                        RawPlayerBoxScore(
                            game_id=game_id,
                            player_id=int(player_id_val),
                            team_id=int(row["teamId"]),
                            minutes_clock=str(row.get("minutes") or ""),
                            pts=self._safe_int(row.get("points")) or 0,
                            reb=self._safe_int(row.get("reboundsTotal")) or 0,
                            oreb=self._safe_int(row.get("reboundsOffensive")) or 0,
                            dreb=self._safe_int(row.get("reboundsDefensive")) or 0,
                            ast=self._safe_int(row.get("assists")) or 0,
                            stl=self._safe_int(row.get("steals")) or 0,
                            blk=self._safe_int(row.get("blocks")) or 0,
                            tov=self._safe_int(row.get("turnovers")) or 0,
                            fgm=self._safe_int(row.get("fieldGoalsMade")) or 0,
                            fga=self._safe_int(row.get("fieldGoalsAttempted")) or 0,
                            fg3m=self._safe_int(row.get("threePointersMade")) or 0,
                            fg3a=self._safe_int(row.get("threePointersAttempted")) or 0,
                            ftm=self._safe_int(row.get("freeThrowsMade")) or 0,
                            fta=self._safe_int(row.get("freeThrowsAttempted")) or 0,
                            plus_minus=self._safe_int(row.get("plusMinusPoints")),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not parse player box score row: %s", exc)

        return team_scores, player_scores

    # ── get_team_roster ───────────────────────────────────────────────────────

    def get_team_roster(
        self, team_id: int, season_year: int | None = None, *, season: str | None = None
    ) -> list[RawRosterEntry]:
        from nba_api.stats.endpoints import commonteamroster

        # Prefer an explicit NBA.com season key (e.g. "2026-27") so callers pass
        # the resolved string rather than relying on _season_str's year-1
        # arithmetic. Fall back to deriving it from a season-ending year.
        if season is None:
            if season_year is None:
                raise ValueError("get_team_roster requires season or season_year")
            season = _season_str(season_year)

        def _call():
            r = commonteamroster.CommonTeamRoster(
                team_id=team_id, season=season, timeout=self.timeout
            )
            return r.get_data_frames()[0]

        df = self._call_with_retry(_call)
        results: list[RawRosterEntry] = []
        for _, row in df.iterrows():
            try:
                results.append(
                    RawRosterEntry(
                        player_id=int(row["PLAYER_ID"]),
                        team_id=team_id,
                        name=str(row.get("PLAYER", "")),
                        jersey_number=str(row.get("NUM", "") or ""),
                        position=str(row.get("POSITION", "") or ""),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not parse roster row: %s", exc)
        return results

    # ── get_all_players ───────────────────────────────────────────────────────

    def get_all_players(
        self, season_year: int, is_only_current_season: bool = True
    ) -> list[RawPlayerInfo]:
        from nba_api.stats.endpoints import commonallplayers

        season = _season_str(season_year)
        flag = 1 if is_only_current_season else 0

        def _call():
            p = commonallplayers.CommonAllPlayers(
                is_only_current_season=flag, season=season, timeout=self.timeout
            )
            return p.get_data_frames()[0]

        df = self._call_with_retry(_call)
        results: list[RawPlayerInfo] = []
        for _, row in df.iterrows():
            try:
                results.append(
                    RawPlayerInfo(
                        player_id=int(row["PERSON_ID"]),
                        name=str(row.get("DISPLAY_FIRST_LAST", "")),
                        is_active=bool(int(row.get("ROSTERSTATUS", 0) or 0)),
                        team_id=self._safe_int(row.get("TEAM_ID")),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not parse player row: %s", exc)
        return results

    # ── get_play_by_play ──────────────────────────────────────────────────────

    def get_play_by_play(self, game_id: str) -> "list[RawPlayEvent]":
        """
        Fetch play-by-play events for one game via PlayByPlayV3.

        Returns events in chronological order (ascending orderNumber).
        clock format from API: "PT09M36.00S" → parsed to seconds remaining.
        """
        import re
        from nba_api.stats.endpoints.playbyplayv3 import PlayByPlayV3
        from .base import RawPlayEvent

        df = self._fetch_game_endpoint(PlayByPlayV3, game_id).play_by_play.get_data_frame()

        if df is None or df.empty:
            logger.warning("PlayByPlayV3 returned empty for game %s", game_id)
            return []

        def _parse_clock(clock: str) -> int:
            """PT09M36.00S → 576 seconds remaining in period."""
            m = re.match(r'PT(\d+)M([\d.]+)S', str(clock or ""))
            return int(m.group(1)) * 60 + int(float(m.group(2))) if m else 0

        def _safe_score(val) -> "int | None":
            try:
                return int(val) if val is not None and str(val).strip() not in ('', 'None', 'nan') else None
            except (ValueError, TypeError):
                return None

        results: list[RawPlayEvent] = []
        for _, row in df.iterrows():
            try:
                results.append(RawPlayEvent(
                    game_id=str(row.get("gameId", game_id)),
                    action_number=int(row.get("actionNumber", 0) or 0),
                    clock_secs=_parse_clock(row.get("clock", "")),
                    period=int(row.get("period", 1) or 1),
                    team_id=self._safe_int(row.get("teamId")),
                    person_id=self._safe_int(row.get("personId")),
                    action_type=str(row.get("actionType", "") or "").lower(),
                    sub_type=str(row.get("subType", "") or "").lower(),
                    shot_result=str(row.get("shotResult", "") or "") or None,
                    is_field_goal=bool(row.get("isFieldGoal", False)),
                    score_home=_safe_score(row.get("scoreHome")),
                    score_away=_safe_score(row.get("scoreAway")),
                    points_total=int(row.get("pointsTotal", 0) or 0),
                    description=str(row.get("description", "") or ""),
                    order_number=int(row.get("orderNumber", 0) or 0),
                ))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not parse PBP row for game %s: %s", game_id, exc)

        results.sort(key=lambda e: e.order_number)
        return results

    # ── get_game_rotation ─────────────────────────────────────────────────────

    def get_game_rotation(self, game_id: str) -> "list[RawRotationStint]":
        """
        Every player's on-court intervals for one game via GameRotation.

        IN_TIME_REAL / OUT_TIME_REAL are tenths of a second from tip-off.
        """
        from nba_api.stats.endpoints.gamerotation import GameRotation
        from .base import RawRotationStint

        ep = self._fetch_game_endpoint(GameRotation, game_id)

        results: list[RawRotationStint] = []
        for data_set in (ep.away_team, ep.home_team):
            table = data_set.get_dict()
            for raw in table["data"]:
                row = dict(zip(table["headers"], raw))
                if row.get("IN_TIME_REAL") is None or row.get("OUT_TIME_REAL") is None:
                    logger.warning("GameRotation row without times for game %s: %s", game_id, row)
                    continue
                results.append(RawRotationStint(
                    game_id=str(row.get("GAME_ID") or game_id),
                    team_id=self._safe_int(row.get("TEAM_ID")),
                    person_id=self._safe_int(row.get("PERSON_ID")),
                    player_name=f"{row.get('PLAYER_FIRST') or ''} {row.get('PLAYER_LAST') or ''}".strip(),
                    in_time=float(row["IN_TIME_REAL"]),
                    out_time=float(row["OUT_TIME_REAL"]),
                ))
        return results

    # ── health_check ──────────────────────────────────────────────────────────

    def health_check(self) -> list[ProviderHealthResult]:
        """Check that each endpoint module is importable (fast, no network call)."""
        endpoints = {
            "LeagueGameLog": "nba_api.stats.endpoints.leaguegamelog",
            "TeamGameLog": "nba_api.stats.endpoints.teamgamelog",
            "BoxScoreTraditionalV3": "nba_api.stats.endpoints.boxscoretraditionalv3",
            "CommonTeamRoster": "nba_api.stats.endpoints.commonteamroster",
            "CommonAllPlayers": "nba_api.stats.endpoints.commonallplayers",
            "PlayByPlayV3": "nba_api.stats.endpoints.playbyplayv3",
        }
        results = []
        for name, module_path in endpoints.items():
            start = time.time()
            try:
                import importlib
                importlib.import_module(module_path)
                results.append(
                    ProviderHealthResult(
                        endpoint=name,
                        ok=True,
                        latency_ms=(time.time() - start) * 1000,
                    )
                )
            except ImportError as exc:
                results.append(ProviderHealthResult(endpoint=name, ok=False, error=str(exc)))
        return results


# ── Utility: parse nba_api minute clock strings to integer seconds ────────────

def parse_minutes_to_seconds(minutes_str: str) -> Optional[int]:
    """
    "34:21"     \u2192 2061
    "34:21.00"  \u2192 2061  (BoxScoreTraditionalV3 format)
    ""          \u2192 None
    """
    if not minutes_str:
        return None
    try:
        clean = minutes_str.split(".")[0]
        parts = clean.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return None
    except (ValueError, AttributeError):
        return None


