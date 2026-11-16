"""
Task 10B (trimmed): ESPN athlete ids for Task 10A's ncaa.com rows (MissingPlayerGameStats.espn_athlete_id, migration
core 0073).

Each 10A ncaa row without an ESPN id was looked up by exact display name on its team-season's ESPN core-API roster
(sports.core.api.espn.com .../seasons/{Y}/teams/{espn team id}/athletes, fetched 2026-11-14). Only Shaqir O'Neal
(Texas Southern 2024) matched, in his 2 rows; he is ESPN athlete 4684156 = core_player 2755, which 10A had already
linked by exact name + team + season. The other 532 rows (21 players) are not on ESPN's rosters at all, the same
players ESPN's box scores leave out, so they keep a blank ESPN id.

The identity-only 'espn_roster' candidates planned for 10B are not added: none of ~9,700 blanked ESPN box entries
matched a roster player (ESPN's rosters omit them too), and the roster fallback produced stale names.

  python data_fixes/2026-11-16_task10b_link_10a_espn_ids.py [--apply]     (from backend/; default: rehearsal)
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.db import transaction  # noqa: E402
from django.db.models import F  # noqa: E402

from ncaa.models import MissingPlayerGameStats, Player  # noqa: E402

# (season, team id, name) -> (ESPN athlete id, core_player id)
LINKS = {(2024, 303, "Shaqir O'Neal"): ("4684156", 2755)}


class Rollback(Exception):
    pass


def expect(label, got, want):
    print(f"  {label}: {got}" + ("" if got == want else f"  (EXPECTED {want})"))
    if got != want:
        raise SystemExit(f"assertion failed: {label}")


def run():
    rows = MissingPlayerGameStats.objects
    expect("rows before (total, ncaa, espn_roster, with ESPN id)",
           (rows.count(), rows.filter(source="ncaa").count(), rows.filter(source="espn_roster").count(),
            rows.exclude(espn_athlete_id="").count()), (534, 534, 0, 0))
    for (season, team, name), (espn_id, pid) in LINKS.items():
        expect(f"core_player {pid}", list(Player.objects.filter(id=pid).values_list("espn_athlete_id", "display_name")),
               [(espn_id, name)])
        target = rows.filter(source="ncaa", game__season_year=season, team_id=team, name=name, espn_athlete_id="")
        expect(f"{name} {season} rows to link (player already {pid})", list(target.values_list("player_id", flat=True)),
               [pid, pid])
        expect("rows updated", target.update(espn_athlete_id=espn_id), 2)
    expect("rows with an ESPN id after", rows.exclude(espn_athlete_id="").count(), 2)
    expect("ESPN id agrees with the linked core_player", rows.exclude(espn_athlete_id="").exclude(
        player__espn_athlete_id__isnull=False, espn_athlete_id=F("player__espn_athlete_id")).count(), 0)
    expect("rows after (total, espn_roster)", (rows.count(), rows.filter(source="espn_roster").count()), (534, 0))


if __name__ == "__main__":
    if "--apply" not in sys.argv:
        try:
            with transaction.atomic():
                run(); raise Rollback()
        except Rollback:
            print("REHEARSAL OK (rolled back)")
        sys.exit(0)
    with transaction.atomic():
        run()
    print("DONE")
