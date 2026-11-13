"""
Task 6g follow-up: the 2026 player sync resolved 123 of 125 BC/BU/New Haven/Southern Indiana games.
The other two are against non-D1 Vermont State campuses with no ESPN mapping, so the sync's
scoreboard lookup (both teams by ESPN id) could not pair them:
  game 1096 (NCAA 6501837) New Haven 122 - VTSU Lyndon 51    = ESPN 401828682, away team id 551 "Vermont State Lyndon Hornets"
  game 1647 (NCAA 6501379) Boston University 104 - VTSU-Johnson 57 = ESPN 401824360, away team id 126751 "Vermont State Johnson Badgers"
Ids taken from those ESPN events by the D1 side's id (2441, 104) and matching scores, not by name.

  python data_fixes/2026-11-12_task6g_b_vtsu_campuses.py --apply   (from backend/; without --apply: asserts, rolled back)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import connection, transaction  # noqa: E402

APPLY = "--apply" in sys.argv


def q(sql, params=None):
    with connection.cursor() as c:
        c.execute(sql, params or [])
        return c.fetchall() if c.description else c.rowcount


def expect(label, got, want):
    print(f"  {label}: {got}" + ("" if got == want else f"  (EXPECTED {want})"))
    if got != want:
        raise SystemExit(f"assertion failed: {label}")


class Rollback(Exception):
    pass


def mappings():
    expect("games as stored", q("""select id, source_game_id, home_team_id, away_team_id, home_score, away_score from core_game
        where id in (1096, 1647) order by id"""), [(1096, "6501837", 197, 573, 122, 51), (1647, "6501379", 28, 378, 104, 57)])
    expect("teams 573/378", q("select id, name, is_d1 from core_team where id in (378, 573) order by id"),
           [(378, "VTSU-Johnson", False), (573, "VTSU Lyndon", False)])
    expect("existing ESPN rows for 551/126751 or teams 378/573", q("""select count(*) from core_teamexternalid where source='espn'
        and (external_id in ('551', '126751') or team_id in (378, 573))""")[0][0], 0)
    n = q("""insert into core_teamexternalid (source, external_id, external_name, confidence, is_manual_override, created_at, updated_at, team_id)
             values ('espn', '551', 'Vermont State Lyndon', 1.0, true, now(), now(), 573),
                    ('espn', '126751', 'Vermont State Johnson', 1.0, true, now(), now(), 378)""")
    expect("ESPN mappings inserted", n, 2)


if __name__ == "__main__":
    if not APPLY:
        try:
            with transaction.atomic():
                mappings()
                raise Rollback()
        except Rollback:
            print("REHEARSAL OK (rolled back)")
        sys.exit(0)
    with transaction.atomic():
        mappings()
    call_command("sync_ncaa_player_gamelogs", season=2026, teams="28,197", skip_done=True, sleep=1.1, workers=1)
    expect("player rows now in games 1096/1647 (by team)",
           q("""select game_id, team_id, count(*) from core_playergamestats where game_id in (1096, 1647)
                group by 1, 2 order by 1, 2""") != [], True)
    for gid, tid in ((1096, 197), (1647, 28)):
        expect(f"game {gid}: rows for team {tid} > 0",
               q("select count(*) from core_playergamestats where game_id=%s and team_id=%s", [gid, tid])[0][0] > 0, True)
    print("DONE")
