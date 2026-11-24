"""
Make sure a season has TeamSeasonMembership rows (season-level D1 membership).

  python manage.py sync_team_season_membership                 # the season in play
  python manage.py sync_team_season_membership --season 2027
  python manage.py sync_team_season_membership --season 2027 --dry-run

Creates missing rows, and upgrades a team's derived_games row to D1 once ESPN lists it. Reviewed rows
(manual and other sources; past seasons, data_fixes/2026-11-12_task6f1_membership.py) are never changed.

1. D1 rows: fetches ESPN's D1 list for the season (core API seasons/{y}/types/2/groups/50/teams,
   one request), mapped by ESPN id (TeamExternalId, then the ESPN-id overrides in
   mappings/team_alias_overrides.yml). Each listed team without a row gets a D1 row; a listed team whose
   row is a derived_games is_d1=False row is upgraded to D1 (it was written before the team could be
   mapped, or before ESPN listed it).
   An unmapped listed id stops the run before anything is written: it is a D1 team we cannot identify,
   and step 2 would otherwise mark it non-D1. Ids are never guessed by name; add the ESPN id
   (TeamExternalId or the overrides file). LISTED_NOT_D1 holds ids ESPN still lists after a program
   left D1.
   is_reclassifying: True when the team's first D1 season in this table is within the last 3 seasons
   (a 4-season window; note 'assumed'), else False.
   Fetched when the season has no espn_group50 rows yet, and on every run for the season in play
   (the nightly pipeline). A past season that has rows makes no request. If the in-play fetch fails
   once rows exist, the run warns and goes on to step 2 (derived rows are upgraded on a later run).
2. Non-D1 rows (no network): every team with a game this season and no row gets is_d1=False
   (source derived_games), so the table always covers the season's opponents.
"""

import json
import re
from datetime import date
import urllib.request
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Min
from django.utils import timezone

from ncaa.models import Game, Season, Team, TeamExternalId, TeamSeasonMembership
from ncaa.seasons import resolve_season_year

GROUP50_URL = ("https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball/"
               "seasons/{year}/types/2/groups/50/teams?limit=500")
RECLASS_WINDOW = 4
# ESPN ids that group 50 still lists after the program left D1: id -> first season not D1
LISTED_NOT_D1 = {
    "42": 2024,     # Hartford: Division III from 2023-24
    "2597": 2024,   # St. Francis Brooklyn: athletics ended after 2022-23
}


def espn_team_map() -> dict:
    """ESPN team id -> Team pk, from TeamExternalId plus ESPN-id overrides (exact canonical names)."""
    out = {e.external_id: e.team_id for e in TeamExternalId.objects.filter(source="espn")}
    path = Path(settings.BASE_DIR) / "mappings" / "team_alias_overrides.yml"
    if path.exists():
        overrides = (yaml.safe_load(open(path)) or {}).get("espn", {})
        by_name = dict(Team.objects.values_list("name", "id"))
        for key, name in overrides.items():
            if re.fullmatch(r"\d+", str(key)) and name in by_name:
                out.setdefault(str(key), by_name[name])
    return out


def fetch_group50_ids(year: int) -> list:
    req = urllib.request.Request(GROUP50_URL.format(year=year), headers={"User-Agent": "Mozilla/5.0 (macfax)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    ids = sorted({m for it in data.get("items", []) for m in re.findall(r"/teams/(\d+)", it.get("$ref", ""))})
    if not ids or (data.get("count") and len(ids) != data["count"]):
        raise CommandError(f"ESPN group 50 for {year}: got {len(ids)} ids, count {data.get('count')}")
    return ids


class Command(BaseCommand):
    help = "Create missing TeamSeasonMembership rows for a season (D1 from ESPN group 50; others from games)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, default=None, help="Season year (default: the season in play)")
        parser.add_argument("--dry-run", action="store_true", help="Report only; write nothing")

    def handle(self, *args, **opts):
        year = resolve_season_year(opts["season"])
        dry = opts["dry_run"]
        season = Season.objects.filter(year=year).first()
        if season is None:
            raise CommandError(f"Season {year} not found")
        rows = {m.team_id: m for m in TeamSeasonMembership.objects.filter(season=season)}
        existing = set(rows)
        has_espn_rows = any(m.source == TeamSeasonMembership.SOURCE_ESPN_GROUP50 for m in rows.values())
        new_rows, upgrades = [], []

        # Past seasons with rows came from reviewed sources: no fetch. The season in play re-checks every run.
        ids = None
        if not has_espn_rows:
            ids = fetch_group50_ids(year)
        elif year == resolve_season_year(None):
            try:
                ids = fetch_group50_ids(year)
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f"ESPN group 50 {year}: fetch failed ({e}); D1 rows unchanged this run"))
        else:
            self.stdout.write(f"{year}: ESPN group 50 rows already present (past season); no fetch")

        if ids is not None:
            ids = [i for i in ids if not (i in LISTED_NOT_D1 and year >= LISTED_NOT_D1[i])]
            emap = espn_team_map()
            unmapped = [i for i in ids if i not in emap]
            if unmapped:
                raise CommandError(
                    f"ESPN group 50 {year}: {len(unmapped)} listed D1 teams have no team mapping (ESPN ids "
                    f"{', '.join(unmapped)}). Add the ESPN id (TeamExternalId or mappings/team_alias_overrides.yml), "
                    f"or LISTED_NOT_D1 if the program left D1. Nothing written.")
            first_d1 = dict(TeamSeasonMembership.objects.filter(is_d1=True).values("team_id")
                            .annotate(first=Min("season__year")).values_list("team_id", "first"))

            def reclassifying(tid):
                first = min(first_d1.get(tid, year), year)
                reclass = year - first < RECLASS_WINDOW
                return reclass, (f"reclassifying: assumed (first D1 season {first})" if reclass else "")

            listed = {emap[i] for i in ids}
            for tid in sorted(listed - existing):
                reclass, note = reclassifying(tid)
                new_rows.append(TeamSeasonMembership(
                    season=season, team_id=tid, is_d1=True, is_reclassifying=reclass,
                    source=TeamSeasonMembership.SOURCE_ESPN_GROUP50, note=note))
            for tid in sorted(listed & existing):
                row = rows[tid]
                if row.source == TeamSeasonMembership.SOURCE_DERIVED_GAMES and not row.is_d1:
                    reclass, note = reclassifying(tid)
                    row.is_d1, row.is_reclassifying = True, reclass
                    row.source = TeamSeasonMembership.SOURCE_ESPN_GROUP50
                    row.note = f"upgraded from derived_games: listed in ESPN group 50 on {date.today()}" + (
                        f"; {note}" if note else "")
                    row.updated_at = timezone.now()   # bulk_update skips auto_now
                    upgrades.append(row)
            self.stdout.write(f"ESPN group 50 {year}: {len(ids)} teams, {len(new_rows)} D1 rows to add, "
                              f"{len(upgrades)} derived rows to upgrade")

        d1_new = {r.team_id for r in new_rows}
        played = set()
        for h, a in Game.objects.filter(season_year=year).values_list("home_team_id", "away_team_id"):
            played.update((h, a))
        for tid in sorted(played - existing - d1_new):
            new_rows.append(TeamSeasonMembership(
                season=season, team_id=tid, is_d1=False, is_reclassifying=None,
                source=TeamSeasonMembership.SOURCE_DERIVED_GAMES, note="not in ESPN group 50; has games this season"))
        n_nd1 = len(new_rows) - len(d1_new)
        self.stdout.write(f"{year}: {n_nd1} non-D1 rows to add (teams with games, no row)")
        for row in upgrades:
            self.stdout.write(f"  upgrade to D1: {row.team.name}")
        if dry or not (new_rows or upgrades):
            return
        with transaction.atomic():
            TeamSeasonMembership.objects.bulk_create(new_rows)
            TeamSeasonMembership.objects.bulk_update(
                upgrades, ["is_d1", "is_reclassifying", "source", "note", "updated_at"])
        self.stdout.write(self.style.SUCCESS(
            f"{year}: created {len(new_rows)} membership rows, upgraded {len(upgrades)} to D1"))
