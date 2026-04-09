"""
nba_sync_team_logs — ingest per-player box scores for a season.

Calls BoxScoreTraditionalV3 for each completed game that has no player stats
yet. Upserts NBAPlayer rows and creates NBAPlayerGameStats rows.

After this command, run nba_compute_player_stats to roll up season averages.

Usage:
    uv run python manage.py nba_sync_team_logs --season 2026
    uv run python manage.py nba_sync_team_logs --season 2026 --workers 4
    uv run python manage.py nba_sync_team_logs --season 2026 --limit 10 --workers 4
    uv run python manage.py nba_sync_team_logs --season 2026 --dry-run
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nba.models import NBASeason, NBATeam, NBAGame, NBAPlayer, NBAPlayerGameStats
from nba.providers.nba_api_provider import NBAApiProvider

logger = logging.getLogger(__name__)


def _parse_seconds(clock: str) -> "int | None":
    """Convert 'MM:SS' clock string to integer seconds. Returns None on failure."""
    if not clock:
        return None
    try:
        parts = clock.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(float(parts[1]))
        return None
    except (ValueError, AttributeError):
        return None


def _fetch_game(game, sleep: float):
    """
    Fetch player box score for one game. Runs in a thread pool.
    Returns (game, player_scores) on success or (game, exception) on failure.
    """
    provider = NBAApiProvider()  # each thread gets its own provider/session
    try:
        time.sleep(sleep)
        _, player_scores = provider.get_box_score_traditional(game.game_id)
        return game, player_scores
    except Exception as exc:  # noqa: BLE001
        return game, exc


class Command(BaseCommand):
    help = "Sync per-player box scores via BoxScoreTraditionalV3 for a season."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True,
                            help="Ending season year (e.g., 2026)")
        parser.add_argument("--limit", type=int, default=None,
                            help="Cap number of games to process (for testing)")
        parser.add_argument("--workers", type=int, default=1,
                            help="Parallel fetch threads (default 1). "
                                 "3-5 is a safe range for NBA.com rate limits.")
        parser.add_argument("--sleep", type=float, default=0.8,
                            help="Seconds to sleep between requests PER WORKER "
                                 "(default 0.8). With 4 workers and 0.8s sleep "
                                 "you get ~5 req/s total.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Fetch data but do not write to database")

    def handle(self, *args, **options):
        season_year: int = options["season"]
        limit = options["limit"]
        workers: int = max(1, options["workers"])
        sleep: float = options["sleep"]
        dry_run: bool = options["dry_run"]

        try:
            season = NBASeason.objects.get(year=season_year)
        except NBASeason.DoesNotExist:
            raise CommandError(
                f"Season {season_year} not found. Run nba_sync_teams first."
            )

        # Games that are finished but have no player stats yet
        synced_game_ids = set(
            NBAPlayerGameStats.objects.filter(
                game__season=season
            ).values_list("game__game_id", flat=True).distinct()
        )

        games_qs = (
            NBAGame.objects.filter(season=season, status="Final")
            .select_related("home_team", "away_team")
            .order_by("date")
        )
        pending = [g for g in games_qs if g.game_id not in synced_game_ids]

        if limit:
            pending = pending[:limit]

        total = len(pending)
        self.stdout.write(
            f"Season {season.display_name}: {total} games need player stats"
            + (f"  [workers={workers}]" if workers > 1 else "")
            + (" [DRY RUN]" if dry_run else "")
        )

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        team_map: dict = {t.nba_team_id: t for t in NBATeam.objects.all()}

        # ── Phase 1: fetch all box scores in parallel ─────────────────────────
        self.stdout.write(f"  Fetching {total} box scores with {workers} worker(s)...")
        results: dict = {}  # game_id → (game, player_scores | exception)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_fetch_game, game, sleep): game for game in pending}
            completed = 0
            for future in as_completed(futures):
                game_obj, outcome = future.result()
                results[game_obj.game_id] = (game_obj, outcome)
                completed += 1
                if completed % 10 == 0 or completed == total:
                    self.stdout.write(f"    fetched {completed}/{total}...")

        # ── Phase 2: write results serially ──────────────────────────────────
        created_players = 0
        created_stats = 0
        errors = 0

        for idx, game in enumerate(pending, 1):
            game_obj, outcome = results[game.game_id]

            if isinstance(outcome, Exception):
                logger.warning("BoxScore fetch failed game_id=%s: %s", game.game_id, outcome)
                self.stdout.write(self.style.WARNING(
                    f"  [{idx}/{total}] SKIP {game.game_id} — {outcome}"
                ))
                errors += 1
                continue

            player_scores = outcome
            if not player_scores:
                self.stdout.write(self.style.WARNING(
                    f"  [{idx}/{total}] SKIP {game.game_id} — no player rows returned"
                ))
                errors += 1
                continue

            if dry_run:
                self.stdout.write(f"  [{idx}/{total}] {game.game_id}: {len(player_scores)} rows (dry run)")
                continue

            with transaction.atomic():
                for ps in player_scores:
                    team = team_map.get(ps.team_id)
                    player, created = NBAPlayer.objects.update_or_create(
                        player_id=ps.player_id,
                        defaults={"current_team": team, "is_active": True},
                    )
                    if created or not player.name:
                        player.name = f"Player #{ps.player_id}"
                        player.save(update_fields=["name"])
                        created_players += 1

                    NBAPlayerGameStats.objects.update_or_create(
                        game=game_obj,
                        player=player,
                        defaults={
                            "team": team,
                            "seconds_played": _parse_seconds(ps.minutes_clock),
                            "pts": ps.pts,
                            "reb": ps.reb,
                            "ast": ps.ast,
                            "stl": ps.stl,
                            "blk": ps.blk,
                            "tov": ps.tov,
                            "fgm": ps.fgm,
                            "fga": ps.fga,
                            "fg3m": ps.fg3m,
                            "fg3a": ps.fg3a,
                            "ftm": ps.ftm,
                            "fta": ps.fta,
                            "plus_minus": ps.plus_minus,
                        },
                    )
                    created_stats += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. games={total}  new_players={created_players}  "
                f"stat_rows={created_stats}  errors={errors}"
            )
        )
        if errors:
            self.stdout.write(
                self.style.WARNING(f"  {errors} games failed — re-run to retry")
            )

        # ── Backfill player names ─────────────────────────────────────────────
        stubs = NBAPlayer.objects.filter(name__startswith="Player #")
        if stubs.exists() and not dry_run:
            self.stdout.write(f"\nBackfilling names for {stubs.count()} players...")
            provider = NBAApiProvider()
            try:
                all_players = provider.get_all_players(season_year)
                name_map = {p.player_id: p.name for p in all_players}
                updated = 0
                for player in stubs:
                    real_name = name_map.get(player.player_id)
                    if real_name:
                        player.name = real_name
                        player.save(update_fields=["name"])
                        updated += 1
                self.stdout.write(self.style.SUCCESS(f"  Names updated: {updated}"))
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(self.style.WARNING(f"  Name backfill failed: {exc}"))
