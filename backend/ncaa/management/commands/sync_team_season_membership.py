"""
Make sure a season has TeamSeasonMembership rows (season-level D1 membership).

  python manage.py sync_team_season_membership                 # the season in play
  python manage.py sync_team_season_membership --season 2027
  python manage.py sync_team_season_membership --season 2027 --dry-run

Only creates missing rows; never changes an existing one (past seasons were set from reviewed sources,
data_fixes/2026-11-12_task6f1_membership.py).

1. D1 rows: if the season has no espn_group50 rows yet, fetch ESPN's D1 list for it
   (core API seasons/{y}/types/2/groups/50/teams, one request) and add a row for each listed team,
   mapped by ESPN id (TeamExternalId, then the ESPN-id overrides in mappings/team_alias_overrides.yml).
   Unmapped ESPN ids are reported, not guessed by name.
   is_reclassifying: True when the team's first D1 season in this table is within the last 3 seasons
   (a 4-season window; note 'assumed'), else False.
2. Non-D1 rows (no network): every team with a game this season and no row gets is_d1=False
   (source derived_games), so the table always covers the season's opponents.
"""

import json
import re
import urllib.request
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Min

from ncaa.models import Game, Season, Team, TeamExternalId, TeamSeasonMembership
from ncaa.seasons import resolve_season_year

GROUP50_URL = ("https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball/"
               "seasons/{year}/types/2/groups/50/teams?limit=500")
RECLASS_WINDOW = 4


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
        existing = set(TeamSeasonMembership.objects.filter(season=season).values_list("team_id", flat=True))
        new_rows = []

        if not TeamSeasonMembership.objects.filter(season=season, source=TeamSeasonMembership.SOURCE_ESPN_GROUP50).exists():
            ids = fetch_group50_ids(year)
            emap = espn_team_map()
            unmapped = [i for i in ids if i not in emap]
            if unmapped:
                self.stdout.write(self.style.WARNING(f"ESPN group 50 {year}: {len(unmapped)} ids with no team: {', '.join(unmapped)}"))
            first_d1 = dict(TeamSeasonMembership.objects.filter(is_d1=True).values("team_id")
                            .annotate(first=Min("season__year")).values_list("team_id", "first"))
            for tid in sorted({emap[i] for i in ids if i in emap} - existing):
                first = min(first_d1.get(tid, year), year)
                reclass = year - first < RECLASS_WINDOW
                new_rows.append(TeamSeasonMembership(
                    season=season, team_id=tid, is_d1=True, is_reclassifying=reclass,
                    source=TeamSeasonMembership.SOURCE_ESPN_GROUP50,
                    note=f"reclassifying: assumed (first D1 season {first})" if reclass else ""))
            self.stdout.write(f"ESPN group 50 {year}: {len(ids)} teams, {len(new_rows)} D1 rows to add")
        else:
            self.stdout.write(f"{year}: ESPN group 50 rows already present; no fetch")

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
        if dry or not new_rows:
            return
        with transaction.atomic():
            TeamSeasonMembership.objects.bulk_create(new_rows)
        self.stdout.write(self.style.SUCCESS(f"{year}: created {len(new_rows)} membership rows"))
