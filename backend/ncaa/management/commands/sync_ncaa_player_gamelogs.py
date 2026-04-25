"""
Fetch per-player box scores from the ESPN summary API for every finished
game in a season, then upsert Player and PlayerGameStats rows.

Works with both ESPN-sourced games (use source_game_id directly) and
NCAA-sourced games (look up ESPN event IDs via scoreboard by matching team IDs).

Usage:
    # Fetch current season (2025-26 = year 2026):
    python manage.py sync_ncaa_player_gamelogs --season 2026

    # Parallel workers (safe: 3-6):
    python manage.py sync_ncaa_player_gamelogs --season 2026 --workers 4

    # Only games without existing player stats (incremental):
    python manage.py sync_ncaa_player_gamelogs --season 2026 --skip-done

    # Re-fetch everything (full overwrite):
    python manage.py sync_ncaa_player_gamelogs --season 2026 --force
"""
import time
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand
from django.db import transaction

from ncaa.models import Game, Player, PlayerGameStats, Team, TeamExternalId

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sync NCAA player game-level box scores from ESPN for a given season."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            default=2025,
            help="Season year (ending year, e.g. 2025 for 2024-25)",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            help="Number of parallel HTTP fetch workers (default 1; safe up to 4-6)",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=0.5,
            help="Per-worker sleep between requests (seconds, default 0.5)",
        )
        parser.add_argument(
            "--skip-done",
            action="store_true",
            help="Skip games that already have PlayerGameStats rows",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete existing PlayerGameStats for each game before re-inserting",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Only process N games (for testing). 0 = all.",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        workers = options["workers"]
        sleep_secs = options["sleep"]
        skip_done = options["skip_done"]
        force = options["force"]
        limit = options["limit"]

        from ncaa.utils.ncaa_api import ESPNAPIClient

        # --- Build ESPN team_id → Team lookup ---
        espn_team_map = {}
        for ext in TeamExternalId.objects.filter(source="espn").select_related("team"):
            espn_team_map[ext.external_id] = ext.team

        # Build Team pk → ESPN team id (reverse lookup for ncaa-sourced games)
        team_pk_to_espn_id = {v.pk: k for k, v in espn_team_map.items()}

        # --- Gather all finished games for the season ---
        games_qs = Game.objects.filter(
            season_year=season_year,
            status="final",
        ).select_related("home_team", "away_team").order_by("game_date")

        if skip_done:
            done_game_ids = set(
                PlayerGameStats.objects.filter(
                    game__season_year=season_year,
                ).values_list("game_id", flat=True).distinct()
            )
            games_qs = games_qs.exclude(id__in=done_game_ids)

        all_games = list(games_qs)
        if limit:
            all_games = all_games[:limit]

        # --- Separate by source and resolve ESPN event IDs ---
        # game_id → espn_event_id
        game_espn_map: dict[int, str] = {}

        espn_direct = [g for g in all_games if g.source == "espn"]
        ncaa_sourced = [g for g in all_games if g.source != "espn"]

        for g in espn_direct:
            game_espn_map[g.pk] = g.source_game_id

        if ncaa_sourced:
            self.stdout.write(
                f"Resolving ESPN event IDs for {len(ncaa_sourced)} NCAA-sourced games..."
            )
            # Group by date → fetch scoreboard once per date
            by_date = defaultdict(list)
            for g in ncaa_sourced:
                by_date[g.game_date].append(g)

            client = ESPNAPIClient(rate_limit_delay=sleep_secs)
            resolved = 0
            for game_date, day_games in sorted(by_date.items()):
                date_str = game_date.strftime("%Y%m%d")
                try:
                    client._rate_limit()
                    import requests
                    url = f"{client.BASE_URL}/scoreboard"
                    resp = client.session.get(
                        url,
                        params={"dates": date_str, "groups": "50", "limit": "500"},
                        timeout=client.timeout,
                    )
                    resp.raise_for_status()
                    events = resp.json().get("events", [])
                except Exception as e:
                    logger.warning(f"Scoreboard fetch failed for {game_date}: {e}")
                    continue

                # Build lookup: frozenset({espn_team_id_a, espn_team_id_b}) → event_id
                event_lookup: dict[frozenset, str] = {}
                for event in events:
                    comp = event.get("competitions", [{}])[0]
                    team_ids = frozenset(
                        str(c.get("team", {}).get("id", ""))
                        for c in comp.get("competitors", [])
                    )
                    if team_ids:
                        event_lookup[team_ids] = event["id"]

                for g in day_games:
                    home_espn = team_pk_to_espn_id.get(g.home_team_id, "")
                    away_espn = team_pk_to_espn_id.get(g.away_team_id, "")
                    if not home_espn or not away_espn:
                        continue
                    key = frozenset({home_espn, away_espn})
                    espn_event_id = event_lookup.get(key)
                    if espn_event_id:
                        game_espn_map[g.pk] = espn_event_id
                        resolved += 1

            self.stdout.write(
                f"  Resolved {resolved}/{len(ncaa_sourced)} NCAA games to ESPN event IDs."
            )

        # game_list: list of (game_pk, espn_event_id)
        game_list = [(pk, eid) for pk, eid in game_espn_map.items()]
        total = len(game_list)

        self.stdout.write(
            f"[sync_ncaa_player_gamelogs] Season {season_year}: "
            f"{total} games to fetch (workers={workers})"
        )

        if total == 0:
            self.stdout.write("Nothing to do.")
            return

        # --- Fetch phase (parallel) ---
        def fetch_one(game_id, espn_game_id):
            c = ESPNAPIClient(rate_limit_delay=sleep_secs)
            rows = c.get_player_box_score(espn_game_id)
            return game_id, rows

        fetched = {}  # game_id → rows list

        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(fetch_one, gid, eid): gid
                    for gid, eid in game_list
                }
                done = 0
                for future in as_completed(futures):
                    gid, rows = future.result()
                    fetched[gid] = rows
                    done += 1
                    if done % 100 == 0 or done == total:
                        self.stdout.write(f"  Fetched {done}/{total}...")
        else:
            for idx, (gid, eid) in enumerate(game_list, 1):
                _, rows = fetch_one(gid, eid)
                fetched[gid] = rows
                if idx % 100 == 0 or idx == total:
                    self.stdout.write(f"  Fetched {idx}/{total}...")

        self.stdout.write("Fetch phase complete. Writing to database...")

        # --- Write phase (serial) ---
        total_players = 0
        total_stats = 0
        skipped = 0

        for game_id, _ in game_list:
            rows = fetched.get(game_id, [])
            if not rows:
                skipped += 1
                continue

            if force:
                PlayerGameStats.objects.filter(game_id=game_id).delete()

            with transaction.atomic():
                for row in rows:
                    espn_athlete_id = row.get("espn_athlete_id", "")
                    if not espn_athlete_id:
                        continue

                    # Upsert Player
                    player, created = Player.objects.update_or_create(
                        espn_athlete_id=espn_athlete_id,
                        defaults={
                            "display_name": row["display_name"],
                            "short_name": row["short_name"],
                            "jersey": row["jersey"],
                            "position": row["position"],
                            "headshot_url": row["headshot_url"],
                        },
                    )
                    if created:
                        total_players += 1

                    # Resolve team from ESPN team ID
                    team = espn_team_map.get(row["espn_team_id"])

                    # Upsert PlayerGameStats
                    _, created = PlayerGameStats.objects.update_or_create(
                        player=player,
                        game_id=game_id,
                        defaults={
                            "team": team,
                            "starter": row["starter"],
                            "did_not_play": row["did_not_play"],
                            "minutes": row["minutes"],
                            "points": row["points"],
                            "fg_made": row["fg_made"],
                            "fg_attempted": row["fg_attempted"],
                            "fg3_made": row["fg3_made"],
                            "fg3_attempted": row["fg3_attempted"],
                            "ft_made": row["ft_made"],
                            "ft_attempted": row["ft_attempted"],
                            "rebounds": row["rebounds"],
                            "offensive_rebounds": row["offensive_rebounds"],
                            "defensive_rebounds": row["defensive_rebounds"],
                            "assists": row["assists"],
                            "turnovers": row["turnovers"],
                            "steals": row["steals"],
                            "blocks": row["blocks"],
                            "fouls": row["fouls"],
                        },
                    )
                    if created:
                        total_stats += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. New players: {total_players} | "
                f"New game rows: {total_stats} | "
                f"Games with no data: {skipped}"
            )
        )
