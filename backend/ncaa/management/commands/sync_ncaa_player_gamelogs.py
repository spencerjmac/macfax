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

    # Historical backfill (2005-2014): D1-vs-D1 games only, one request per second:
    python manage.py sync_ncaa_player_gamelogs --season 2014 --d1-vs-d1 --sleep 1.0

Canceled 0-0 games are never fetched. Games stored with an ESPN event id (source 'espn', and every 2005-2008 game,
which the NCAA ingest stored with ESPN's event id and ESPN raw data) use it directly; only other NCAA-sourced games
are looked up on ESPN's scoreboard (by game_date, which is a UTC date for 2005-2008, so that lookup would miss them).
Box entries ESPN blanked (no athlete id, no stats) are counted per game and reported, not stored.
"""
import time
import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from ncaa.models import Game, Player, PlayerGameStats, Team, TeamExternalId
from ncaa.seasons import resolve_season_year
from ncaa.utils.d1 import d1_q

# Seasons whose NCAA-sourced games were stored with ESPN's event id as source_game_id (and ESPN raw data).
ESPN_ID_THROUGH_SEASON = 2008
PGS_FIELDS = ("starter", "did_not_play", "minutes", "points", "fg_made", "fg_attempted", "fg3_made", "fg3_attempted",
              "ft_made", "ft_attempted", "rebounds", "offensive_rebounds", "defensive_rebounds", "assists",
              "turnovers", "steals", "blocks", "fouls")
PLAYER_FIELDS = ("display_name", "short_name", "jersey", "position", "headshot_url")


def select_games(season_year: int, *, teams=None, d1_vs_d1: bool = False, skip_done: bool = False):
    """Finished games to fetch for a season (canceled 0-0 games never; optionally D1 vs D1 only)."""
    qs = Game.objects.filter(season_year=season_year, status="final").exclude(home_score=0, away_score=0)
    if d1_vs_d1:
        qs = qs.filter(d1_q(season_year, "home_team") & d1_q(season_year, "away_team"))
    if teams:
        qs = qs.filter(Q(home_team_id__in=teams) | Q(away_team_id__in=teams))
    if skip_done:
        done_game_ids = set(PlayerGameStats.objects.filter(game__season_year=season_year)
                            .values_list("game_id", flat=True).distinct())
        # A game with player rows but no period_count is not done: re-fetch it so its periods
        # get recorded (otherwise --skip-done would leave it NULL forever).
        qs = qs.exclude(id__in=done_game_ids, period_count__isnull=False)
    return list(qs.select_related("home_team", "away_team").order_by("game_date", "id"))


def has_espn_event_id(game) -> bool:
    return game.source == "espn" or (game.season_year <= ESPN_ID_THROUGH_SEASON and bool(game.source_game_id))

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
            "--d1-vs-d1",
            action="store_true",
            help="Only games between two teams that were D1 that season (TeamSeasonMembership)",
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

        # --- Gather finished games for the season ---
        team_pks = [int(x) for x in options["teams"].split(",") if x.strip()] if options.get("teams") else None
        all_games = select_games(season_year, teams=team_pks, d1_vs_d1=options["d1_vs_d1"], skip_done=skip_done)
        if limit:
            all_games = all_games[:limit]

        # --- Separate by source and resolve ESPN event IDs ---
        # game_id → espn_event_id
        game_espn_map: dict[int, str] = {}

        espn_direct = [g for g in all_games if has_espn_event_id(g)]
        ncaa_sourced = [g for g in all_games if not has_espn_event_id(g)]

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
        # One client per worker thread, so --sleep spaces that worker's requests (a client per game never waited).
        local = threading.local()
        blanks = {}      # game_id -> blanked box entries (no athlete id, no stats)
        failed = []      # game ids whose summary request failed

        def fetch_one(game_id, espn_game_id):
            if not hasattr(local, "client"):
                local.client = ESPNAPIClient(rate_limit_delay=sleep_secs)
            data = local.client.get_summary(espn_game_id)
            if data is None:
                failed.append(game_id)
                return game_id, []
            blanks[game_id] = sum(ESPNAPIClient.idless_athletes(data).values())
            return game_id, local.client.parse_player_box_score(data)

        fetched = {}  # game_id → rows list
        t_fetch = time.time()

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

        secs = time.time() - t_fetch
        self.stdout.write(f"Fetch phase complete: {total} requests in {secs:.0f}s ({total / secs:.2f} req/s, "
                          f"{secs / total:.2f} s/game); failed {len(failed)}. Writing to database...")

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
        with_blanks = {g: n for g, n in blanks.items() if n}
        self.stdout.write(f"Blanked box entries (not stored): {sum(with_blanks.values())} in {len(with_blanks)} games"
                          + (f"; max {max(with_blanks.values())} in one game" if with_blanks else ""))
        if failed:
            self.stdout.write(self.style.WARNING(f"Failed summary requests (game ids): {sorted(failed)[:50]}"))


def write_player_rows(game_id: int, rows: list, team_by_espn: dict, force: bool = False):
    """Upsert Player and PlayerGameStats rows for one game from ESPNAPIClient.parse_player_box_score rows (two bulk
    upserts), and record the game's periods into a NULL period_count.

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

    # one row per athlete (the last one wins, as with the old row-by-row upsert)
    rows = list({r["espn_athlete_id"]: r for r in rows if r.get("espn_athlete_id")}.values())
    if not rows:
        return new_players, new_stats, period_set
    with transaction.atomic():
        ids = [r["espn_athlete_id"] for r in rows]
        existing = set(Player.objects.filter(espn_athlete_id__in=ids).values_list("espn_athlete_id", flat=True))
        players = Player.objects.bulk_create(
            [Player(espn_athlete_id=r["espn_athlete_id"], **{f: r[f] for f in PLAYER_FIELDS}) for r in rows],
            update_conflicts=True, unique_fields=["espn_athlete_id"], update_fields=list(PLAYER_FIELDS))
        new_players = len(set(ids) - existing)
        pid = {p.espn_athlete_id: p.pk for p in players}
        if any(v is None for v in pid.values()):   # backends that don't return ids on upsert
            pid = dict(Player.objects.filter(espn_athlete_id__in=ids).values_list("espn_athlete_id", "pk"))
        had = set(PlayerGameStats.objects.filter(game_id=game_id).values_list("player_id", flat=True))
        PlayerGameStats.objects.bulk_create(
            [PlayerGameStats(player_id=pid[r["espn_athlete_id"]], game_id=game_id,
                             team_id=team_by_espn.get(r["espn_team_id"]), **{k: r[k] for k in PGS_FIELDS})
             for r in rows],
            update_conflicts=True, unique_fields=["player", "game"], update_fields=["team"] + list(PGS_FIELDS))
        new_stats = len({pid[i] for i in ids} - had)
    return new_players, new_stats, period_set
