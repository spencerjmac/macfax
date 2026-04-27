"""
Management command: ingest_gamelogs
Fetches and stores game-level data for Division I men's basketball

Usage:
    python manage.py ingest_gamelogs --season 2026
    python manage.py ingest_gamelogs --season 2026 --start 2025-11-01 --end 2025-11-07
    python manage.py ingest_gamelogs --season 2026 --refresh
"""

import logging
import requests
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connection
from django.utils import timezone

from ncaa.models import Season, Team, Game, TeamGameStats, ScoringEvent, TeamExternalId
from ncaa.utils.team_mapping import TeamMapper
from ncaa.utils.ncaa_api import NCAAAPIClient, ESPNAPIClient, NCAAAPIError

logger = logging.getLogger(__name__)


def _init_worker():
    """Run once per worker process: ensure Django is set up (spawn) and do not reuse parent DB connection."""
    import os
    if os.environ.get("DJANGO_SETTINGS_MODULE"):
        import django
        django.setup()
    connection.close()


def process_game_job(
    game_data: Dict,
    season_year: int,
    source: str = "ncaa",
    refresh: bool = False,
    dry_run: bool = False,
) -> Dict:
    """
    Standalone job function for processing a single game in the job queue.
    This allows games to be processed in parallel by multiple workers.
    """
    try:
        # Get season
        season = Season.objects.get(year=season_year)

        # Initialize API client
        if source == "ncaa":
            api_client = NCAAAPIClient()
        else:
            api_client = ESPNAPIClient()

        # Build team mapper
        mapper = TeamMapper(source=source)

        # Create command instance to access _process_game method
        cmd = Command()

        # Process the game
        result = cmd._process_game(
            game_data=game_data,
            season=season,
            api_client=api_client,
            mapper=mapper,
            refresh=refresh,
            dry_run=dry_run,
            source=source,
        )

        return result

    except Exception as e:
        logger.error(f"Error in process_game_job: {e}", exc_info=True)
        return {
            "created": False,
            "updated": False,
            "team_stats": 0,
            "scoring_events": 0,
            "error": str(e),
        }


class Command(BaseCommand):
    help = "Ingest game logs from NCAA API for a season"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            required=True,
            help="Season year (ending year, e.g., 2026 for 2025-26 season)",
        )
        parser.add_argument(
            "--start", type=str, help="Start date (YYYY-MM-DD). Default: season start"
        )
        parser.add_argument(
            "--end", type=str, help="End date (YYYY-MM-DD). Default: yesterday (skip today; games may be unplayed)"
        )
        parser.add_argument(
            "--refresh", action="store_true", help="Force refresh existing games"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Dry run mode (no DB writes)"
        )
        parser.add_argument(
            "--rebuild-mappings",
            action="store_true",
            help="Rebuild team mappings before ingesting",
        )
        parser.add_argument(
            "--source",
            type=str,
            default="ncaa",
            choices=["espn", "ncaa"],
            help="Data source (default: ncaa)",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            metavar="N",
            help="In-process parallel workers for game ingestion (default: 1). Use 2+ for multiprocessing.",
        )
        parser.add_argument(
            "--create-season",
            action="store_true",
            help="Auto-create Season object if it doesn't exist (useful for historical seasons)",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        refresh = options["refresh"]
        dry_run = options["dry_run"]
        rebuild_mappings = options["rebuild_mappings"]
        source = options.get("source", "ncaa")
        workers = max(1, int(options.get("workers", 1)))

        create_season = options.get("create_season", False)
        current_year = date.today().year

        # Get or create season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            if create_season:
                prev_year = season_year - 1
                display_name = f"{prev_year}-{str(season_year)[2:]}"
                is_current = (season_year == current_year) or (
                    season_year == current_year + 1 and date.today().month >= 10
                )
                season = Season.objects.create(
                    year=season_year,
                    display_name=display_name,
                    is_current=is_current,
                )
                self.stdout.write(
                    self.style.SUCCESS(f"Created season: {display_name}")
                )
            else:
                raise CommandError(
                    f"Season {season_year} not found. "
                    f"Run with --create-season to auto-create it."
                )

        # Determine date range
        start_date = self._parse_date(options.get("start"))
        end_date = self._parse_date(options.get("end"))

        if not start_date:
            # Default: start of season (November 1 of the prior calendar year)
            start_date = date(season_year - 1, 11, 1)

        if not end_date:
            # For past (completed) seasons default to April 15 of the ending year
            # so we don't loop through years of empty dates.
            # For the current/upcoming season default to yesterday.
            if season_year < date.today().year or (
                season_year == date.today().year and date.today().month > 8
            ):
                end_date = date(season_year, 4, 15)
            else:
                end_date = date.today() - timedelta(days=1)

        if start_date > end_date:
            raise CommandError("Start date must be before end date")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'='*60}\n"
                f"INGESTING GAME LOGS: {season.display_name}\n"
                f"Date Range: {start_date} to {end_date}\n"
                f"Source: {source.upper()} | Refresh: {refresh} | Dry Run: {dry_run}\n"
                f"{'='*60}\n"
            )
        )

        # Initialize API client based on source
        if source == "ncaa":
            api_client = NCAAAPIClient()
        else:
            api_client = ESPNAPIClient()

        # Step 1: Build/refresh team mappings
        mapper = self._build_team_mappings(
            source=source, rebuild=rebuild_mappings, dry_run=dry_run
        )

        # Step 2: Fetch and process games
        stats = self._ingest_games(
            season=season,
            start_date=start_date,
            end_date=end_date,
            api_client=api_client,
            mapper=mapper,
            refresh=refresh,
            dry_run=dry_run,
            source=source,
            workers=workers,
        )

        # Step 3: Summary
        self._print_summary(stats)

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date string to date object"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise CommandError(f"Invalid date format: {date_str}. Use YYYY-MM-DD")

    def _build_team_mappings(
        self, source: str = "ncaa", rebuild: bool = False, dry_run: bool = False
    ) -> TeamMapper:
        """Build TeamExternalId mappings"""
        self.stdout.write(f"\n[1/3] Building {source.upper()} team mappings...")

        mapper = TeamMapper(source=source)

        if rebuild:
            self.stdout.write("  Rebuilding all mappings from scratch...")
            # In a real scenario, we'd fetch all teams from NCAA API first
            # For now, we'll rely on incremental mapping during game ingestion

        existing_count = TeamExternalId.objects.filter(source=source).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"  OK - {existing_count} {source.upper()} team mappings loaded"
            )
        )

        return mapper

    def _ingest_games(
        self,
        season: Season,
        start_date: date,
        end_date: date,
        api_client,
        mapper: TeamMapper,
        refresh: bool,
        dry_run: bool,
        source: str = "ncaa",
        workers: int = 1,
    ) -> Dict[str, int]:
        """Main ingestion loop"""
        self.stdout.write("\n[2/3] Fetching games...")

        stats = {
            "dates_processed": 0,
            "games_found": 0,
            "games_created": 0,
            "games_updated": 0,
            "games_skipped": 0,
            "team_stats_created": 0,
            "scoring_events_created": 0,
            "errors": 0,
            "jobs_queued": 0,
        }

        if workers > 1:
            self.stdout.write(
                self.style.SUCCESS(
                    f"MULTIPROCESSING MODE - {workers} workers (no Redis required)\n"
                )
            )

        current_date = start_date

        while current_date <= end_date:
            self.stdout.write(f"\n  Processing {current_date}...")
            stats["dates_processed"] += 1

            try:
                # Fetch scoreboard for this date
                games = api_client.get_scoreboard(current_date)
                stats["games_found"] += len(games)

                self.stdout.write(f"    Found {len(games)} games")

                # Process each game (multiprocessing or serial)
                if workers > 1:
                    # In-process multiprocessing (no Redis)
                    with ProcessPoolExecutor(
                        max_workers=workers,
                        initializer=_init_worker,
                    ) as executor:
                        future_to_info = {
                            executor.submit(
                                process_game_job,
                                game_data=g,
                                season_year=season.year,
                                source=source,
                                refresh=refresh,
                                dry_run=dry_run,
                            ): (i, g)
                            for i, g in enumerate(games, 1)
                        }
                        for future in as_completed(future_to_info):
                            i, game_data = future_to_info[future]
                            game_id = str(
                                game_data.get("id")
                                or game_data.get("gameID", "unknown")
                            )
                            try:
                                result = future.result()
                                if result.get("error"):
                                    stats["errors"] += 1
                                    self.stdout.write(
                                        self.style.ERROR(
                                            f"    ✗ [{i}/{len(games)}] {game_id}: {result['error']}"
                                        )
                                    )
                                elif result["created"]:
                                    stats["games_created"] += 1
                                    stats["team_stats_created"] += result[
                                        "team_stats"
                                    ]
                                    stats["scoring_events_created"] += result[
                                        "scoring_events"
                                    ]
                                    self.stdout.write(
                                        f"    ✓ [{i}/{len(games)}] Created game {game_id}"
                                    )
                                elif result["updated"]:
                                    stats["games_updated"] += 1
                                    self.stdout.write(
                                        f"    ↻ [{i}/{len(games)}] Updated game {game_id}"
                                    )
                                else:
                                    stats["games_skipped"] += 1
                            except Exception as e:
                                stats["errors"] += 1
                                logger.error(
                                    f"Error processing game {game_id}: {e}",
                                    exc_info=True,
                                )
                                self.stdout.write(
                                    self.style.ERROR(
                                        f"    ✗ [{i}/{len(games)}] {game_id}: {e}"
                                    )
                                )
                else:
                    # Synchronous processing (original behavior)
                    for i, game_data in enumerate(games, 1):
                        game_id = str(
                            game_data.get("id")
                            or game_data.get("gameID", "unknown")
                        )
                        try:
                            result = self._process_game(
                                game_data=game_data,
                                season=season,
                                api_client=api_client,
                                mapper=mapper,
                                refresh=refresh,
                                dry_run=dry_run,
                                source=source,
                            )
                            if result["created"]:
                                stats["games_created"] += 1
                                stats["team_stats_created"] += result["team_stats"]
                                stats["scoring_events_created"] += result[
                                    "scoring_events"
                                ]
                                self.stdout.write(
                                    f"    ✓ [{i}/{len(games)}] Created game {game_id}"
                                )
                            elif result["updated"]:
                                stats["games_updated"] += 1
                                self.stdout.write(
                                    f"    ↻ [{i}/{len(games)}] Updated game {game_id}"
                                )
                            else:
                                stats["games_skipped"] += 1
                        except Exception as e:
                            stats["errors"] += 1
                            logger.error(
                                f"Error processing game {game_id}: {e}",
                                exc_info=True,
                            )
                            self.stdout.write(
                                self.style.ERROR(
                                    f"    ✗ [{i}/{len(games)}] Error processing game {game_id}: {e}"
                                )
                            )

            except NCAAAPIError as e:
                logger.error(f"NCAA API error for {current_date}: {e}")
                self.stdout.write(
                    self.style.WARNING(f"    ⚠ NCAA API error, skipping date")
                )

            # Move to next date
            current_date += timedelta(days=1)

        return stats

    def _process_game(
        self,
        game_data: Dict,
        season: Season,
        api_client,
        mapper: TeamMapper,
        refresh: bool,
        dry_run: bool,
        source: str = "ncaa",
    ) -> Dict[str, any]:
        """Process a single game"""
        # Extract basic game info
        game_id = str(game_data.get("id") or game_data.get("gameID"))
        home_team_data = game_data.get("home", {})
        away_team_data = game_data.get("away", {})

        home_name = home_team_data.get("name") or home_team_data.get("team", {}).get(
            "displayName"
        )
        away_name = away_team_data.get("name") or away_team_data.get("team", {}).get(
            "displayName"
        )
        home_id = str(
            home_team_data.get("id") or home_team_data.get("team", {}).get("id", "")
        )
        away_id = str(
            away_team_data.get("id") or away_team_data.get("team", {}).get("id", "")
        )

        # Map teams
        home_team = self._map_team(mapper, home_name, home_id, dry_run)
        away_team = self._map_team(mapper, away_name, away_id, dry_run)

        if not home_team or not away_team:
            logger.warning(f"Skipping game {game_id}: Unable to map teams")
            return {
                "created": False,
                "updated": False,
                "team_stats": 0,
                "scoring_events": 0,
            }

        # Check if game exists
        existing_game = Game.objects.filter(source_game_id=game_id).first()

        if existing_game and not refresh:
            # Smart skip: only skip if game is already final
            # This allows in-progress and scheduled games to be updated on subsequent runs
            if existing_game.status == "final":
                return {
                    "created": False,
                    "updated": False,
                    "team_stats": 0,
                    "scoring_events": 0,
                }
            # Game exists but isn't final - re-process it to get updated data

        if dry_run:
            self.stdout.write(f"    [DRY RUN] Would process: {away_name} @ {home_name}")
            return {
                "created": True,
                "updated": False,
                "team_stats": 2,
                "scoring_events": 0,
            }

        # Fetch full game details (box scores)
        try:
            game_details = api_client.get_game_details(game_id)
            # Merge carefully - preserve scores from scoreboard, add stats from details
            full_game_data = {**game_data}
            if "home" in game_details and "stats" in game_details["home"]:
                full_game_data["home"]["stats"] = game_details["home"]["stats"]
            if "away" in game_details and "stats" in game_details["away"]:
                full_game_data["away"]["stats"] = game_details["away"]["stats"]
            if "scoringPlays" in game_details:
                full_game_data["scoringPlays"] = game_details["scoringPlays"]
        except (TimeoutError, ConnectionError) as e:
            # Network/timeout errors - log and continue with scoreboard data only
            logger.warning(f"Timeout fetching details for game {game_id}: {e}")
            self.stdout.write(
                self.style.WARNING(
                    f"      ⏱ Timeout for game {game_id}, using scoreboard data only"
                )
            )
            full_game_data = game_data
        except requests.exceptions.Timeout as e:
            # Explicit timeout from requests library
            logger.warning(f"Requests timeout for game {game_id}: {e}")
            self.stdout.write(
                self.style.WARNING(
                    f"      ⏱ Timeout for game {game_id}, using scoreboard data only"
                )
            )
            full_game_data = game_data
        except requests.exceptions.RequestException as e:
            # Other requests errors
            logger.warning(f"Request error for game {game_id}: {e}")
            self.stdout.write(
                self.style.WARNING(
                    f"      ⚠ Network error for game {game_id}, using scoreboard data only"
                )
            )
            full_game_data = game_data
        except NCAAAPIError as e:
            # NCAA API specific errors (data not available, etc.)
            logger.warning(f"NCAA API error for game {game_id}: {e}")
            self.stdout.write(
                self.style.WARNING(
                    f"      ⚠ Data unavailable for game {game_id}, using scoreboard data only"
                )
            )
            full_game_data = game_data
        except Exception as e:
            # If details unavailable for any other reason, store what we have from scoreboard
            logger.warning(f"Could not fetch details for game {game_id}: {e}")
            full_game_data = game_data

        # Parse game metadata
        game_obj = self._upsert_game(
            game_id=game_id,
            game_data=full_game_data,
            season=season,
            home_team=home_team,
            away_team=away_team,
            source=source,
        )

        # Skip stat extraction if game doesn't have final scores
        if game_obj.home_score is None or game_obj.away_score is None:
            logger.info(f"Skipping stats for incomplete game: {game_id}")
            return {
                "created": existing_game is None,
                "updated": False,
                "team_stats": 0,
                "scoring_events": 0,
            }

        # Extract and store team stats
        team_stats_count = self._extract_team_stats(
            game=game_obj,
            game_data=full_game_data,
        )

        # Extract and store scoring events
        scoring_events_count = self._extract_scoring_events(
            game=game_obj,
            game_data=full_game_data,
        )

        is_new = existing_game is None

        return {
            "created": is_new,
            "updated": not is_new,
            "team_stats": team_stats_count,
            "scoring_events": scoring_events_count,
        }

    def _map_team(
        self, mapper: TeamMapper, team_name: str, team_id: str, dry_run: bool
    ) -> Optional[Team]:
        """Map external team to canonical Team"""
        # Filter out known non-D1 schools
        non_d1_indicators = ["JWU", "Johnson & Wales", "NAIA", "NCAA D2", "NCAA DIII"]
        if team_name and any(
            indicator.lower() in team_name.lower() for indicator in non_d1_indicators
        ):
            if not dry_run:
                print(f"Filtering out non-D1 school: '{team_name}'")
            return None

        # Check if already mapped
        existing = mapper.get_team_by_external_id(team_id)
        if existing:
            return existing

        # Create new mapping (allow non-D1 teams to be created as opponents)
        mapping = mapper.map_and_save(
            external_name=team_name,
            external_id=team_id,
            dry_run=dry_run,
            allow_non_d1=True,  # Allow creating non-D1 teams for opponents
        )

        return mapping.team if mapping else None

    def _upsert_game(
        self,
        game_id: str,
        game_data: Dict,
        season: Season,
        home_team: Team,
        away_team: Team,
        source: str = "ncaa",
    ) -> Game:
        """Create or update Game record"""
        # Parse game data
        status_map = {
            "final": "final",
            "completed": "final",
            "in_progress": "in_progress",
            "in progress": "in_progress",
            "scheduled": "scheduled",
            "postponed": "postponed",
            "canceled": "canceled",
        }

        # Handle both string status (NCAA normalized) and nested object (ESPN)
        status_raw = game_data.get("status", "scheduled")
        if isinstance(status_raw, dict):
            status_str = status_raw.get("type", {}).get("name", "scheduled").lower()
        else:
            status_str = status_raw.lower() if status_raw else "scheduled"

        status = status_map.get(status_str, "scheduled")

        # Parse game date (handle multiple formats)
        game_date_str = (
            game_data.get("date")
            or game_data.get("gameDate")
            or game_data.get("startDate")
        )
        if game_date_str:
            try:
                # Try MM/DD/YYYY format (NCAA with slashes)
                if "/" in game_date_str:
                    game_date = datetime.strptime(game_date_str, "%m/%d/%Y").date()
                # Try ISO format (ESPN)
                elif "T" in game_date_str or "Z" in game_date_str:
                    game_date = datetime.fromisoformat(
                        game_date_str.replace("Z", "+00:00")
                    ).date()
                # Try YYYY-MM-DD
                elif game_date_str[4:5] == "-":
                    game_date = datetime.strptime(game_date_str, "%Y-%m-%d").date()
                # Try MM-DD-YYYY (NCAA historical API returns dashes not slashes)
                else:
                    game_date = datetime.strptime(game_date_str, "%m-%d-%Y").date()
            except Exception as e:
                logger.warning(f"Could not parse date '{game_date_str}': {e}")
                game_date = date.today()
        else:
            game_date = date.today()

        home_score = game_data.get("home", {}).get("score")
        away_score = game_data.get("away", {}).get("score")

        # Convert scores to int, handle empty strings
        if home_score not in (None, "", " "):
            try:
                home_score = int(home_score)
            except (ValueError, TypeError):
                home_score = None
        else:
            home_score = None

        if away_score not in (None, "", " "):
            try:
                away_score = int(away_score)
            except (ValueError, TypeError):
                away_score = None
        else:
            away_score = None

        neutral = game_data.get("neutralSite", False) or game_data.get(
            "neutral_site", False
        )

        # Upsert
        game, created = Game.objects.update_or_create(
            source_game_id=game_id,
            defaults={
                "season_year": season.year,
                "game_date": game_date,
                "home_team": home_team,
                "away_team": away_team,
                "status": status,
                "home_score": home_score,
                "away_score": away_score,
                "neutral_site": neutral,
                "source": source,
                "raw_json": game_data,
            },
        )

        return game

    def _extract_team_stats(self, game: Game, game_data: Dict) -> int:
        """Extract and store TeamGameStats for both teams"""
        # Delete existing stats if re-processing
        TeamGameStats.objects.filter(game=game).delete()

        # Extract stats from merged game data
        # Check if we have detailed stats from get_game_details()
        home_stats = game_data.get("home", {}).get("stats", {})
        away_stats = game_data.get("away", {}).get("stats", {})

        # If no stats, skip (game might not have box score yet)
        if not home_stats and not away_stats:
            return 0

        stats_created = 0

        for team_data, team, opponent, location in [
            (
                home_stats,
                game.home_team,
                game.away_team,
                "H" if not game.neutral_site else "N",
            ),
            (
                away_stats,
                game.away_team,
                game.home_team,
                "A" if not game.neutral_site else "N",
            ),
        ]:
            if not team_data:
                continue

            TeamGameStats.objects.create(
                game=game,
                team=team,
                opponent=opponent,
                home_away=location,
                pts=self._safe_int(team_data.get("points", 0)),
                fgm=self._safe_int(team_data.get("fieldGoalsMade", 0)),
                fga=self._safe_int(team_data.get("fieldGoalsAttempted", 0)),
                fg3m=self._safe_int(team_data.get("threePointFieldGoalsMade", 0)),
                fg3a=self._safe_int(team_data.get("threePointFieldGoalsAttempted", 0)),
                ftm=self._safe_int(team_data.get("freeThrowsMade", 0)),
                fta=self._safe_int(team_data.get("freeThrowsAttempted", 0)),
                oreb=self._safe_int(team_data.get("offensiveRebounds", 0)),
                dreb=self._safe_int(team_data.get("defensiveRebounds", 0)),
                reb=self._safe_int(team_data.get("totalRebounds", 0)),
                ast=self._safe_int(team_data.get("assists", 0)),
                stl=self._safe_int(team_data.get("steals", 0)),
                blk=self._safe_int(team_data.get("blocks", 0)),
                tov=self._safe_int(team_data.get("turnovers", 0)),
                pf=self._safe_int(team_data.get("fouls", 0)),
                raw_json=team_data,
            )
            stats_created += 1

        return stats_created

    def _extract_scoring_events(self, game: Game, game_data: Dict) -> int:
        """Extract and store ScoringEvents from play-by-play"""
        # Delete existing events if re-processing
        ScoringEvent.objects.filter(game=game).delete()

        # Extract play-by-play or scoring summary
        # This is a placeholder - adjust based on actual API response
        plays = game_data.get("playByPlay", []) or game_data.get("scoringPlays", [])

        if not plays:
            return 0

        events_created = 0

        for idx, play in enumerate(plays):
            # Parse play data
            scoring_team_id = play.get("teamId")
            scoring_team = self._find_team_by_external_id(scoring_team_id)

            if not scoring_team:
                continue

            points = self._extract_points_from_play(play)
            if points == 0:
                continue

            ScoringEvent.objects.create(
                game=game,
                seq=idx + 1,
                period=play.get("period", 1),
                clock=play.get("clock", ""),
                scoring_team=scoring_team,
                points=points,
                home_score=play.get("homeScore"),
                away_score=play.get("awayScore"),
                raw_json=play,
            )
            events_created += 1

        return events_created

    @staticmethod
    def _safe_int(value, default=0) -> int:
        """Safely convert value to int"""
        try:
            return int(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _find_team_by_external_id(external_id: str) -> Optional[Team]:
        """Find team by NCAA external ID"""
        try:
            mapping = TeamExternalId.objects.select_related("team").get(
                source="ncaa", external_id=str(external_id)
            )
            return mapping.team
        except TeamExternalId.DoesNotExist:
            return None

    @staticmethod
    def _extract_points_from_play(play: Dict) -> int:
        """Extract points scored from a play"""
        # Look for scoring type
        scoring_type = play.get("scoringPlay", {}).get("type", "")

        if "three" in scoring_type.lower() or "3" in scoring_type:
            return 3
        elif "free" in scoring_type.lower() or "ft" in scoring_type.lower():
            return 1
        elif "field" in scoring_type.lower() or "made" in scoring_type.lower():
            return 2

        # Fallback: look for points explicitly
        return Command._safe_int(play.get("points", 0))

    def _print_summary(self, stats: Dict[str, int]):
        """Print ingestion summary"""
        summary_lines = [
            f"\n[3/3] Ingestion Complete!\n",
            f"{'='*60}\n",
            f"SUMMARY\n",
            f"{'='*60}\n",
            f"Dates Processed:      {stats['dates_processed']}\n",
            f"Games Found:          {stats['games_found']}\n",
        ]

        # Show jobs queued if in parallel mode
        if stats.get("jobs_queued", 0) > 0:
            summary_lines.append(f"Games Queued:         {stats['jobs_queued']}\n")
            summary_lines.append(f"(Waiting for workers to process...)\n")
        else:
            summary_lines.extend(
                [
                    f"Games Created:        {stats['games_created']}\n",
                    f"Games Updated:        {stats['games_updated']}\n",
                    f"Games Skipped:        {stats['games_skipped']}\n",
                    f"Team Stats Created:   {stats['team_stats_created']}\n",
                    f"Scoring Events:       {stats['scoring_events_created']}\n",
                ]
            )

        summary_lines.extend(
            [f"Errors:               {stats['errors']}\n", f"{'='*60}\n"]
        )

        self.stdout.write(self.style.SUCCESS("".join(summary_lines)))
