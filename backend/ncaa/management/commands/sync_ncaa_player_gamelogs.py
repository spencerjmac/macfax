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

    # Only games involving some teams (Team primary keys), e.g. after fixing their ESPN ids:
    python manage.py sync_ncaa_player_gamelogs --season 2026 --teams 27,28 --sleep 1.1
"""
import time
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from ncaa.models import Game, Player, PlayerGameStats, Team, TeamExternalId
from ncaa.seasons import resolve_season_year

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sync NCAA player game-level box scores from ESPN for a given season."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, default=None,
            help="Season year (ending year, e.g. 2025 for 2024-25) (default: the season in play)",
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
            help="Skip games that already have PlayerGameStats rows and a period_count",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete existing PlayerGameStats for each game before re-inserting",
        )
        parser.add_argument(
            "--teams",
            type=str,
            default=None,
            help="Comma-separated Team primary keys: only games where one of them is home or away.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Only process N games (for testing). 0 = all.",
        )

    def handle(self, *args, **options):
        season_year = resolve_season_year(options["season"])
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

        if options.get("teams"):
            team_pks = [int(x) for x in options["teams"].split(",") if x.strip()]
            games_qs = games_qs.filter(Q(home_team_id__in=team_pks) | Q(away_team_id__in=team_pks))

        if skip_done:
            done_game_ids = set(
                PlayerGameStats.objects.filter(
                    game__season_year=season_year,
                ).values_list("game_id", flat=True).distinct()
            )
            # A game with player rows but no period_count is not done: re-fetch it so its periods
            # get recorded (otherwise --skip-done would leave it NULL forever).
            games_qs = games_qs.exclude(id__in=done_game_ids, period_count__isnull=False)

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
        periods_set = 0

        team_by_espn = {k: v.pk for k, v in espn_team_map.items()}
        for game_id, _ in game_list:
            rows = fetched.get(game_id, [])
            if not rows:
                skipped += 1
                continue
            n_players, n_stats, n_period = write_player_rows(game_id, rows, team_by_espn, force=force)
            total_players += n_players
            total_stats += n_stats
            periods_set += n_period

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. New players: {total_players} | "
                f"New game rows: {total_stats} | "
                f"Games with no data: {skipped} | "
                f"period_count set: {periods_set}"
            )
        )


def write_player_rows(game_id: int, rows: list, team_by_espn: dict, force: bool = False):
    """Upsert Player and PlayerGameStats rows for one game from ESPNAPIClient.parse_player_box_score rows,
    and record the game's periods into a NULL period_count.

    team_by_espn: ESPN team id -> Team pk (an unmapped team leaves the row's team NULL).
    Returns (new players, new PlayerGameStats rows, period_count set 0/1).
    """
    new_players = new_stats = period_set = 0
    if force:
        PlayerGameStats.objects.filter(game_id=game_id).delete()

    # Periods played, from the same ESPN summary. Nothing else sets Game.period_count at ingest
    # (fix_ncaa_stint_data backfills it from stints only), so games without stints stayed NULL.
    period = rows[0].get("game_period") if rows else None
    if isinstance(period, int) and period >= 2:
        period_set = Game.objects.filter(pk=game_id, period_count__isnull=True).update(
            period_count=period, went_to_ot=period > 2)

    with transaction.atomic():
        for row in rows:
            espn_athlete_id = row.get("espn_athlete_id", "")
            if not espn_athlete_id:
                continue
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
            new_players += int(created)
            _, created = PlayerGameStats.objects.update_or_create(
                player=player,
                game_id=game_id,
                defaults={
                    "team_id": team_by_espn.get(row["espn_team_id"]),
                    **{k: row[k] for k in (
                        "starter", "did_not_play", "minutes", "points", "fg_made", "fg_attempted",
                        "fg3_made", "fg3_attempted", "ft_made", "ft_attempted", "rebounds",
                        "offensive_rebounds", "defensive_rebounds", "assists", "turnovers",
                        "steals", "blocks", "fouls")},
                },
            )
            new_stats += int(created)
    return new_players, new_stats, period_set
