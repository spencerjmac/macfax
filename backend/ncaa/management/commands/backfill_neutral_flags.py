"""
Management command: backfill_neutral_flags

Backfills Game.neutral_site from ESPN scoreboard data (audit bug 1.5:
2026 ingestion lost the flag — 0 neutral games stored vs ~700/season in
2021-2025).

Fetches the ESPN scoreboard once per distinct game date in the season
(~140 requests) and matches rows by source_game_id. Only flips False→True
(the stored default is False); pass --allow-clear to also clear stale True
flags when ESPN says the game was not neutral.

Usage:
  python manage.py backfill_neutral_flags --season 2026 --dry-run
  python manage.py backfill_neutral_flags --season 2026
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Backfill Game.neutral_site from ESPN scoreboards (audit bug 1.5)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true", default=False)
        parser.add_argument("--allow-clear", action="store_true", default=False,
                            help="Also set neutral_site False where ESPN disagrees "
                                 "with a stored True")

    def handle(self, *args, **opts):
        from ncaa.models import Game, TeamExternalId

        from ncaa.utils.ncaa_api import ESPNAPIClient

        season = opts["season"]
        dry = opts["dry_run"]

        # ESPN team id → our team pk (Game.source_game_id is NOT an ESPN
        # event id for ncaa-sourced rows, so match on date + team pair).
        espn_to_pk = {
            ext.external_id: ext.team_id
            for ext in TeamExternalId.objects.filter(source="espn")
        }

        games_by_key: dict[tuple, Game] = {}
        for g in Game.objects.filter(season_year=season):
            games_by_key[(g.game_date, g.home_team_id, g.away_team_id)] = g

        dates = sorted(
            Game.objects.filter(season_year=season)
            .values_list("game_date", flat=True).distinct()
        )
        self.stdout.write(
            f"Season {season}: {len(games_by_key)} games across {len(dates)} dates")

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
                g = games_by_key.get((d, home_pk, away_pk))
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
