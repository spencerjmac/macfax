"""
Management command: backfill_neutral_flags

Sets Game.neutral_site from ESPN scoreboard data. The NCAA scoreboard (the source of 2026+ games) has no
neutral-site field, so NCAA-sourced games are stored non-neutral (audit bug 1.5: 0 neutral games in 2026 vs
~700/season in 2021-2025). Runs daily as a step of update_ncaa_teams over the ingest window; run it by hand
for a whole season.

Fetches the ESPN scoreboard once per distinct game date (in --start/--end when given) and matches games by
date and team pair, either order: Game.source_game_id is not an ESPN event id for NCAA-sourced games, and on
neutral sites NCAA and ESPN can list different home teams. Only flips False->True (the stored default is
False); pass --allow-clear to also clear stale True flags when ESPN says the game was not neutral.

Usage:
  python manage.py backfill_neutral_flags --season 2026 --dry-run
  python manage.py backfill_neutral_flags --season 2026
  python manage.py backfill_neutral_flags --season 2027 --start 2026-11-14 --end 2026-11-19
"""

from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise CommandError(f"Bad date {value!r} (want YYYY-MM-DD)") from e


class Command(BaseCommand):
    help = "Set Game.neutral_site from ESPN scoreboards (NCAA-sourced games have no neutral flag)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--start", type=str, help="First game date (YYYY-MM-DD). Default: season start")
        parser.add_argument("--end", type=str, help="Last game date (YYYY-MM-DD). Default: season end")
        parser.add_argument("--dry-run", action="store_true", default=False)
        parser.add_argument("--allow-clear", action="store_true", default=False,
                            help="Also set neutral_site False where ESPN disagrees "
                                 "with a stored True")

    def handle(self, *args, **opts):
        from ncaa.models import Game, TeamExternalId

        from ncaa.utils.ncaa_api import ESPNAPIClient

        season = opts["season"]
        dry = opts["dry_run"]
        start, end = _date(opts.get("start")), _date(opts.get("end"))

        # ESPN team id → our team pk (Game.source_game_id is NOT an ESPN
        # event id for ncaa-sourced rows, so match on date + team pair).
        espn_to_pk = {
            ext.external_id: ext.team_id
            for ext in TeamExternalId.objects.filter(source="espn")
        }

        games = Game.objects.filter(season_year=season)
        if start:
            games = games.filter(game_date__gte=start)
        if end:
            games = games.filter(game_date__lte=end)

        # Unordered pair: on a neutral site NCAA's home team can be ESPN's away team.
        games_by_key: dict[tuple, Game] = {}
        for g in games:
            games_by_key[(g.game_date, frozenset((g.home_team_id, g.away_team_id)))] = g

        dates = sorted({d for d, _ in games_by_key})
        window = f" ({start or 'start'} to {end or 'end'})" if start or end else ""
        self.stdout.write(
            f"Season {season}{window}: {len(games_by_key)} games across {len(dates)} dates")

        client = ESPNAPIClient()
        to_set, to_clear = [], []
        n_matched = 0
        n_fetched = 0
        for d in dates:
            for ev in client.get_scoreboard(d):
                home_pk = espn_to_pk.get(str((ev.get("home") or {}).get("id")))
                away_pk = espn_to_pk.get(str((ev.get("away") or {}).get("id")))
                if not home_pk or not away_pk:
                    continue
                g = games_by_key.get((d, frozenset((home_pk, away_pk))))
                if g is None:
                    continue
                n_matched += 1
                neutral = bool(ev.get("neutral_site", False))
                if neutral and not g.neutral_site:
                    g.neutral_site = True
                    to_set.append(g)
                elif not neutral and g.neutral_site and opts["allow_clear"]:
                    g.neutral_site = False
                    to_clear.append(g)
            n_fetched += 1
            if n_fetched % 25 == 0:
                self.stdout.write(
                    f"  ...{n_fetched}/{len(dates)} dates | matched {n_matched} "
                    f"| neutral so far {len(to_set)}")

        self.stdout.write(
            f"ESPN matched: {n_matched}/{len(games_by_key)} | "
            f"set True: {len(to_set)} | clear: {len(to_clear)}")
        if dry:
            self.stdout.write("[dry-run] no writes")
            return
        with transaction.atomic():
            Game.objects.bulk_update(to_set + to_clear, ["neutral_site"],
                                     batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f"Updated {len(to_set) + len(to_clear)} games."))
