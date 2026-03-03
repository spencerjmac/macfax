"""
NCAA API Client
Interfaces with self-hosted henrygd/ncaa-api (Docker) for game data
Includes rate limiting, retry logic, and caching
"""

import logging
import time
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class NCAAAPIError(Exception):
    """Base exception for NCAA API errors"""

    pass


class NCAAAPIClient:
    """
    Client for NCAA Stats API
    Connects to self-hosted henrygd/ncaa-api instance
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 90,
        rate_limit_delay: float = 1.0,
    ):
        """
        Args:
            base_url: Base URL of NCAA API (default: public demo API)
            timeout: Request timeout in seconds (increased to 90s for slow endpoints)
            rate_limit_delay: Delay between requests in seconds (1.0s = max 1 req/sec to stay under 5 req/sec limit with margin)
        """
        self.base_url = base_url or getattr(
            settings, "NCAA_API_BASE_URL", "https://ncaa-api.henrygd.me"
        )
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0

        # Setup session with retry logic
        # Note: Removed 502 from retry list - better to fail fast and continue with next game
        self.session = requests.Session()
        retry_strategy = Retry(
            total=2,  # Reduced from 3 to fail faster
            backoff_factor=0.5,  # Reduced from 1 for faster retries
            status_forcelist=[
                428,
                429,
                500,
                503,
                504,
            ],  # Include 428 Precondition Required
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(
            {
                "User-Agent": "CBB-Analytics-Dashboard/1.0",
                "Accept": "application/json",
            }
        )

    def _rate_limit(self):
        """Enforce rate limiting between requests"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        cache_key: Optional[str] = None,
        cache_ttl: int = 3600,
    ) -> Dict[str, Any]:
        """
        Make HTTP GET request to NCAA API

        Args:
            endpoint: API endpoint path
            params: Query parameters
            cache_key: Optional cache key for response
            cache_ttl: Cache time-to-live in seconds

        Returns:
            JSON response as dict

        Raises:
            NCAAAPIError: If request fails
        """
        # Check cache first
        if cache_key:
            cached = cache.get(cache_key)
            if cached:
                logger.debug(f"Cache hit: {cache_key}")
                return cached

        # Rate limit
        self._rate_limit()

        # Build URL
        url = urljoin(self.base_url, endpoint)

        try:
            logger.debug(f"GET {url} params={params}")
            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 428:
                # Some proxies require precondition headers for cache validation
                logger.warning(
                    f"428 Precondition Required for {url}. Retrying with precondition headers."
                )
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                    headers={
                        "If-None-Match": "*",
                        "If-Modified-Since": "Thu, 01 Jan 1970 00:00:00 GMT",
                    },
                )
            response.raise_for_status()

            data = response.json()

            # Cache successful response
            if cache_key and data:
                cache.set(cache_key, data, cache_ttl)

            return data

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error for {url}: {e}")
            raise NCAAAPIError(f"HTTP {e.response.status_code}: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            raise NCAAAPIError(f"Request failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error for {url}: {e}")
            raise NCAAAPIError(f"Unexpected error: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(NCAAAPIError),
    )
    def get_scoreboard(
        self,
        game_date: date,
        division: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Get all games for a specific date

        Args:
            game_date: Date to fetch scores for
            division: NCAA division (1, 2, or 3)

        Returns:
            List of normalized game data dictionaries
        """
        # Format: /scoreboard/basketball-men/d{division}/YYYY/MM/DD
        endpoint = f"/scoreboard/basketball-men/d{division}/{game_date.year}/{game_date.month:02d}/{game_date.day:02d}"
        cache_key = f'ncaa:scoreboard:{division}:{game_date.strftime("%Y%m%d")}'

        logger.info(f"Fetching NCAA scoreboard for {game_date}")

        try:
            response = self._make_request(
                endpoint, cache_key=cache_key, cache_ttl=3600  # Cache for 1 hour
            )
        except NCAAAPIError as e:
            # If the API is returning 428s, skip this date to avoid blocking the entire run
            if "428" in str(e):
                logger.warning(f"Skipping {game_date} due to repeated 428 responses.")
                return []
            raise

        # Normalize NCAA response to our expected format
        games = []
        for game_wrapper in response.get("games", []):
            game_data = game_wrapper.get("game", {})
            if not game_data:
                continue

            normalized = {
                "id": game_data.get("gameID"),
                "date": game_data.get("startDate"),
                "status": self._map_game_state(game_data.get("gameState")),
                "neutral_site": False,  # NCAA doesn't always provide this
                "venue": None,
                "home": {
                    "id": f"{game_data.get('gameID')}_home",  # Use unique ID per team
                    "name": game_data.get("home", {}).get("names", {}).get("short"),
                    "score": game_data.get("home", {}).get("score"),
                },
                "away": {
                    "id": f"{game_data.get('gameID')}_away",  # Use unique ID per team
                    "name": game_data.get("away", {}).get("names", {}).get("short"),
                    "score": game_data.get("away", {}).get("score"),
                },
                "_raw": game_data,
            }
            games.append(normalized)

        logger.info(f"Found {len(games)} NCAA D{division} games on {game_date}")
        return games

    def _map_game_state(self, state: str) -> str:
        """Map NCAA game state to our status enum"""
        state_map = {
            "final": "final",
            "live": "in_progress",
            "pre": "scheduled",
        }
        return state_map.get(state, "scheduled")

    def get_game_details(
        self,
        game_id: str,
    ) -> Dict[str, Any]:
        """
        Get detailed game information including box scores and play-by-play

        Note: No retry decorator - let calling code handle timeouts gracefully

        Args:
            game_id: NCAA game ID

        Returns:
            Detailed game data with normalized stats
        """
        # Fetch team stats using boxscore endpoint (more reliable than team-stats)
        # Note: According to NCAA API docs, team-stats may not work for some seasons
        endpoint = f"/game/{game_id}/boxscore"
        cache_key = f"ncaa:game:boxscore:{game_id}"

        logger.info(f"Fetching NCAA game boxscore for {game_id}")

        try:
            stats_data = self._make_request(
                endpoint, cache_key=cache_key, cache_ttl=7200  # Cache for 2 hours
            )
        except NCAAAPIError as e:
            logger.warning(f"Boxscore not available for game {game_id}: {e}")
            # Return minimal structure if boxscore unavailable
            return {"id": game_id, "home": {}, "away": {}, "scoringPlays": []}
        except Exception as e:
            logger.error(f"Unexpected error fetching boxscore for game {game_id}: {e}")
            # Return minimal structure on any error
            return {"id": game_id, "home": {}, "away": {}, "scoringPlays": []}

        # Parse team stats
        result = {"id": game_id, "home": {}, "away": {}}

        for team_box in stats_data.get("teamBoxscore", []):
            team_id = str(team_box.get("teamId"))
            team_stats = team_box.get("teamStats", {})

            # Normalize stats to match our schema
            normalized_stats = {
                "fieldGoalsMade": self._parse_int(team_stats.get("fieldGoalsMade")),
                "fieldGoalsAttempted": self._parse_int(
                    team_stats.get("fieldGoalsAttempted")
                ),
                "threePointFieldGoalsMade": self._parse_int(
                    team_stats.get("threePointsMade")
                ),
                "threePointFieldGoalsAttempted": self._parse_int(
                    team_stats.get("threePointsAttempted")
                ),
                "freeThrowsMade": self._parse_int(team_stats.get("freeThrowsMade")),
                "freeThrowsAttempted": self._parse_int(
                    team_stats.get("freeThrowsAttempted")
                ),
                "offensiveRebounds": self._parse_int(
                    team_stats.get("offensiveRebounds")
                ),
                "defensiveRebounds": self._parse_int(team_stats.get("totalRebounds", 0))
                - self._parse_int(team_stats.get("offensiveRebounds", 0)),
                "totalRebounds": self._parse_int(team_stats.get("totalRebounds")),
                "assists": self._parse_int(team_stats.get("assists")),
                "steals": self._parse_int(team_stats.get("steals")),
                "blocks": self._parse_int(team_stats.get("blockedShots")),
                "turnovers": self._parse_int(team_stats.get("turnovers")),
                "fouls": self._parse_int(team_stats.get("personalFouls")),
            }

            # Calculate points from field goals and free throws
            points = (
                normalized_stats["fieldGoalsMade"] * 2
                + normalized_stats[
                    "threePointFieldGoalsMade"
                ]  # Already counted in FGM, so add the extra point
                + normalized_stats["freeThrowsMade"]
            )
            normalized_stats["points"] = points

            # Find matching team (home/away) from the teams array
            teams = stats_data.get("teams", [])
            is_home = next(
                (t.get("isHome") for t in teams if str(t.get("teamId")) == team_id),
                None,
            )

            key = "home" if is_home else "away"
            result[key] = {
                "id": team_id,
                "stats": normalized_stats,
            }

        # Try to fetch play-by-play for scoring sequence (optional)
        # TEMPORARILY DISABLED - Play-by-play endpoint is very slow and causes timeouts
        # TODO: Re-enable with separate caching/timeout strategy
        # try:
        #     pbp_endpoint = f'/game/{game_id}/play-by-play'
        #     pbp_data = self._make_request(pbp_endpoint, cache_ttl=7200)
        #     result['scoringPlays'] = self._extract_scoring_plays(pbp_data, result)
        # except Exception as e:
        #     logger.warning(f"Could not fetch play-by-play for game {game_id}: {e}")
        #     result['scoringPlays'] = []

        result["scoringPlays"] = []  # Skip play-by-play for now

        return result

    @staticmethod
    def _parse_int(value, default=0):
        """Parse integer from string or number"""
        if value is None:
            return default
        try:
            # Remove percentage signs and commas
            if isinstance(value, str):
                value = value.replace("%", "").replace(",", "")
            return int(float(value))
        except (ValueError, TypeError):
            return default

    def _extract_scoring_plays(self, pbp_data: Dict, game_data: Dict) -> List[Dict]:
        """Extract scoring plays from play-by-play data"""
        # NCAA play-by-play structure varies, implement when needed
        # For now, return empty list
        return []

    def get_team_box_score(self, game_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract team box score totals from game data

        Args:
            game_data: Full game details response

        Returns:
            Dict with home/away team stats
        """
        # Parse structure based on henrygd/ncaa-api format
        # This is a placeholder - adjust based on actual API response

        box_scores = {
            "home": {},
            "away": {},
        }

        # Extract team totals
        # TODO: Implement based on actual NCAA API response structure

        return box_scores

    def get_scoring_sequence(self, game_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract ordered scoring events from game data

        Args:
            game_data: Full game details response

        Returns:
            List of scoring events in chronological order
        """
        scoring_events = []

        # Parse play-by-play or scoring summary
        # TODO: Implement based on actual NCAA API response structure

        return scoring_events

    def get_season_calendar(
        self,
        season_year: int,
        division: int = 1,
    ) -> Dict[str, Any]:
        """
        Get season calendar/schedule information

        Args:
            season_year: Ending year of season (e.g., 2026)
            division: NCAA division

        Returns:
            Calendar data
        """
        endpoint = f"/calendar/basketball-men/d{division}/{season_year}"
        cache_key = f"ncaa:calendar:{division}:{season_year}"

        logger.info(f"Fetching season calendar for {season_year}")

        data = self._make_request(
            endpoint, cache_key=cache_key, cache_ttl=86400  # Cache for 24 hours
        )

        return data


class ESPNAPIClient:
    """
    Fallback client for ESPN scoreboard API
    Used only when NCAA API data is missing
    """

    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"

    def __init__(self, timeout: int = 30, rate_limit_delay: float = 1.0):
        """
        Args:
            timeout: Request timeout in seconds
            rate_limit_delay: Delay between requests (ESPN has stricter limits)
        """
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0

        self.session = requests.Session()
        retry_strategy = Retry(
            total=2,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def _rate_limit(self):
        """More conservative rate limiting for ESPN"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def get_scoreboard(self, game_date: date) -> List[Dict[str, Any]]:
        """
        Get scoreboard from ESPN for a specific date

        Args:
            game_date: Date to fetch

        Returns:
            List of games in normalized format
        """
        self._rate_limit()

        date_str = game_date.strftime("%Y%m%d")
        url = f"{self.BASE_URL}/scoreboard"
        params = {"dates": date_str}

        try:
            logger.info(f"Fetching ESPN scoreboard for {game_date}")
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            events = data.get("events", [])

            # Normalize to our expected format
            normalized_games = []
            for event in events:
                normalized = self._normalize_game(event)
                if normalized:
                    normalized_games.append(normalized)

            logger.info(f"Found {len(normalized_games)} ESPN games on {game_date}")
            return normalized_games

        except Exception as e:
            logger.error(f"ESPN API error: {e}")
            return []

    def get_game_details(self, game_id: str) -> Dict[str, Any]:
        """
        Get detailed game data including box score and play-by-play

        Args:
            game_id: ESPN game ID

        Returns:
            Full game details with box score and plays
        """
        self._rate_limit()

        url = f"{self.BASE_URL}/summary"
        params = {"event": game_id}

        try:
            logger.info(f"Fetching ESPN game details for {game_id}")
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            return self._normalize_game_details(data)

        except Exception as e:
            logger.error(f"ESPN game details error: {e}")
            return {}

    def _normalize_game(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize ESPN event data to our expected format

        Args:
            event: Raw ESPN event object

        Returns:
            Normalized game dict
        """
        try:
            game_id = event.get("id")
            competitions = event.get("competitions", [])
            if not competitions:
                return None

            comp = competitions[0]
            competitors = comp.get("competitors", [])

            # Find home/away teams
            home_team = next(
                (c for c in competitors if c.get("homeAway") == "home"), None
            )
            away_team = next(
                (c for c in competitors if c.get("homeAway") == "away"), None
            )

            if not home_team or not away_team:
                return None

            status = comp.get("status", {}).get("type", {}).get("state", "pre")
            status_map = {
                "pre": "scheduled",
                "in": "in_progress",
                "post": "final",
            }

            return {
                "id": game_id,
                "date": event.get("date"),
                "status": status_map.get(status, "scheduled"),
                "neutral_site": comp.get("neutralSite", False),
                "venue": comp.get("venue", {}).get("fullName"),
                "home": {
                    "id": home_team.get("team", {}).get("id"),
                    "name": home_team.get("team", {}).get("displayName"),
                    "score": home_team.get("score"),
                },
                "away": {
                    "id": away_team.get("team", {}).get("id"),
                    "name": away_team.get("team", {}).get("displayName"),
                    "score": away_team.get("score"),
                },
                "_raw": event,
            }

        except Exception as e:
            logger.warning(f"Error normalizing ESPN event: {e}")
            return None

    def _normalize_game_details(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize ESPN summary data with box scores and play-by-play

        Args:
            data: Raw ESPN summary response

        Returns:
            Normalized game details
        """
        result = {}

        # Get basic game info
        header = data.get("header", {})
        competitions = header.get("competitions", [])
        if competitions:
            comp = competitions[0]
            competitors = comp.get("competitors", [])

            home_team = next(
                (c for c in competitors if c.get("homeAway") == "home"), None
            )
            away_team = next(
                (c for c in competitors if c.get("homeAway") == "away"), None
            )

            result["id"] = header.get("id")
            result["status"] = (
                comp.get("status", {}).get("type", {}).get("state", "pre")
            )
            result["neutral_site"] = comp.get("neutralSite", False)

            # Parse box scores
            box_score = data.get("boxscore", {})
            teams = box_score.get("teams", [])

            for team_data in teams:
                team_id = team_data.get("team", {}).get("id")
                is_home = home_team and str(home_team.get("team", {}).get("id")) == str(
                    team_id
                )

                stats = {}
                for stat in team_data.get("statistics", []):
                    stat_name = stat.get("name", "").lower().replace(" ", "")
                    stat_val = stat.get("displayValue", "0")

                    # Map ESPN stat names to our schema
                    stat_map = {
                        "fieldgoalsmade": "fieldGoalsMade",
                        "fieldgoals": "fieldGoalsMade",
                        "fieldgoalsattempted": "fieldGoalsAttempted",
                        "fieldgoalspct": "fieldGoalPct",
                        "threepointers": "threePointFieldGoalsMade",
                        "threepointfieldgoalsmade": "threePointFieldGoalsMade",
                        "threepointfieldgoalsattempted": "threePointFieldGoalsAttempted",
                        "freethrows": "freeThrowsMade",
                        "freethrowsmade": "freeThrowsMade",
                        "freethrowsattempted": "freeThrowsAttempted",
                        "totalrebounds": "totalRebounds",
                        "offensiverebounds": "offensiveRebounds",
                        "defensiverebounds": "defensiveRebounds",
                        "assists": "assists",
                        "steals": "steals",
                        "blocks": "blocks",
                        "turnovers": "turnovers",
                        "fouls": "fouls",
                        "totalfouls": "fouls",
                    }

                    if stat_name in stat_map:
                        # Handle "X-Y" format for made-attempted stats
                        if "-" in str(stat_val) and "pct" not in stat_name:
                            made, attempted = str(stat_val).split("-")
                            base_key = (
                                stat_map[stat_name]
                                .replace("Made", "")
                                .replace("Made", "")
                            )
                            stats[f"{base_key}Made"] = (
                                int(made) if made.isdigit() else 0
                            )
                            stats[f"{base_key}Attempted"] = (
                                int(attempted) if attempted.isdigit() else 0
                            )
                        else:
                            try:
                                stats[stat_map[stat_name]] = (
                                    int(stat_val)
                                    if stat_val.replace("-", "").isdigit()
                                    else 0
                                )
                            except:
                                pass

                # Add score
                if is_home and home_team:
                    stats["points"] = int(home_team.get("score", 0))
                elif away_team:
                    stats["points"] = int(away_team.get("score", 0))

                key = "home" if is_home else "away"
                result[key] = {
                    "id": team_id,
                    "name": team_data.get("team", {}).get("displayName"),
                    "stats": stats,
                }

            # Parse play-by-play for scoring events
            plays = data.get("plays", [])
            scoring_plays = []

            for play in plays:
                if play.get("scoringPlay", False):
                    scoring_plays.append(
                        {
                            "teamId": play.get("team", {}).get("id"),
                            "period": play.get("period", {}).get("number", 1),
                            "clock": play.get("clock", {}).get("displayValue", "0:00"),
                            "text": play.get("text", ""),
                            "homeScore": play.get("homeScore"),
                            "awayScore": play.get("awayScore"),
                            "scoreValue": play.get("scoreValue", 0),
                        }
                    )

            result["scoringPlays"] = scoring_plays

        return result
