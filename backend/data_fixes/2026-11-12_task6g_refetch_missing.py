"""
Task 6g: re-fetch what's missing after the team-identity fix (Task 6c) and settle the games
check_ncaa_integrity still flagged. Local macfax DB only.

  python data_fixes/2026-11-12_task6g_refetch_missing.py            # rehearsal: SQL steps + asserts, rolled back, no network
  python data_fixes/2026-11-12_task6g_refetch_missing.py --apply    # SQL steps, then ESPN re-ingest + 2026 player sync

Run from backend/. Every step asserts its expected counts and stops on a mismatch.

Decisions (evidence in the Task 6g report):
- Indiana St.-USC, Outrigger Rainbow Classic 2004-12-21 HST: ESPN holds two records, 243560282
  (Indiana St. 64-USC 68, game 9694) and 243560030 (USC 81-Indiana St. 78, game 9696). Only 243560282
  reproduces both teams' ESPN 2004-05 season point totals (USC 2159 in 29 games, Indiana St. 1890 in
  31), so 9694 is kept and 9696 is deleted with its box rows. ESPN has no team stats for it; the
  kept box rows carry points only.
- Creighton-Houston 2006-12-22 HST (game 19688, ESPN 263560156) is a real Rainbow Classic game, not
  a duplicate: allowed in check_ncaa_integrity (ESPN's time is a placeholder; no stats to load).
- San Diego St. 2026: game 8340 (NCAA 6593725, Mountain West semifinal vs New Mexico, 64-62) is real
  but dated 2026-03-14 5 PM ET by the NCAA feed; ESPN 401851504 has it Friday 2026-03-13 (tip
  2026-03-14T03:59Z, neutral, Thomas & Mack). Corrected: game_date 2026-03-13, start_time_utc,
  neutral_site. Game 8344 (final vs Utah St., 2026-03-14) is unchanged. Both are before Selection
  Sunday (2026-03-15).
  SUPERSEDED by Task 6h: ESPN's 03:59Z is an 11:59 PM ET placeholder; the play-by-play wallclock tip is
  2026-03-14T04:29Z (12:29 AM EDT Sat), so 8340's Eastern date is 3/14 (data_fixes/2026-11-12_task6h_*).
- ESPN 108822 ("Newbury College Wolves", location "Newbury College") is not Newberry (SC, ESPN 2444):
  no player appears for both, though Newberry has 2017/2020/2021 boxes. New non-D1 team Newbury College;
  its 2 games (61204, 83464) move off Newberry (731).
"""

import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import connection, transaction  # noqa: E402

APPLY = "--apply" in sys.argv
EWU, BC, BU, NEW_HAVEN, SO_INDIANA = 82, 27, 28, 197, 281
ONE_SIDED = {9377: 2005, 45620: 2012, 96969: 2021, 105760: 2023}   # game id -> season


class Rollback(Exception):
    pass


def q(sql, params=None):
    with connection.cursor() as c:
        c.execute(sql, params or [])
        return c.fetchall() if c.description else c.rowcount


def one(sql, params=None):
    return q(sql, params)[0][0]


def expect(label, got, want):
    print(f"  {label}: {got}" + ("" if got == want else f"  (EXPECTED {want})"))
    if got != want:
        raise SystemExit(f"assertion failed: {label}")


def preconditions():
    print("preconditions")
    expect("EWU 2017 games", one("select count(*) from core_game where season_year=2017 and %s in (home_team_id, away_team_id)", [EWU]), 32)
    expect("EWU 2017 box rows (any side)", one("""select count(*) from core_teamgamestats t join core_game g on g.id=t.game_id
        where g.season_year=2017 and %s in (g.home_team_id, g.away_team_id)""", [EWU]), 0)
    for gid in ONE_SIDED:
        expect(f"game {gid} box rows", one("select count(*) from core_teamgamestats where game_id=%s", [gid]), 1)
    expect("2026 player rows for BC/BU/New Haven/Southern Indiana", one("""select count(*) from core_playergamestats p
        join core_game g on g.id=p.game_id where g.season_year=2026 and p.team_id in (%s,%s,%s,%s)""",
        [BC, BU, NEW_HAVEN, SO_INDIANA]), 0)
    expect("null-team player rows", one("select count(*) from core_playergamestats where team_id is null"), 82)


def sql_fixes():
    print("mappings")
    expect("existing ESPN rows for 2441/88/108822/3087/126749 or espn rows of 197/281",
           one("""select count(*) from core_teamexternalid where source='espn' and
               (external_id in ('2441','88','108822','3087','126749') or team_id in (197, 281))"""), 0)
    # One ESPN row per team (unique team+source): 567 and 648 already hold their other ESPN ids, so
    # 126749 and 3087 are mapped by id in mappings/team_alias_overrides.yml instead.
    expect("ESPN rows of 567/648", sorted(q("select team_id, external_id from core_teamexternalid where source='espn' and team_id in (567, 648)")),
           [(567, "3170"), (648, "16231")])
    expect("teams 197/281/567/648 as expected", one("""select count(*) from core_team where (id, name, is_d1) in
        ((197,'New Haven',true),(281,'Southern Indiana',true),(567,'St. Thomas (TX)',false),(648,'Old Westbury',false))"""), 4)
    expect("Newbury College absent", one("select count(*) from core_team where slug='newbury-college' or name='Newbury College'"), 0)
    q("insert into core_team (slug, name, aliases, is_d1, created_at) values ('newbury-college', 'Newbury College', '[]'::jsonb, false, now())")
    newbury = one("select id from core_team where slug='newbury-college'")
    n = q("""insert into core_teamexternalid (source, external_id, external_name, confidence, is_manual_override, created_at, updated_at, team_id)
             select 'espn', x.eid, x.ename, 1.0, true, now(), now(), x.tid from (values
               ('2441', 'New Haven', 197), ('88', 'Southern Indiana', 281),
               ('108822', 'Newbury College', %s)) x(eid, ename, tid)""", [newbury])
    expect("ESPN mappings inserted", n, 3)

    print("Newbury College games off Newberry (731)")
    games = [r[0] for r in q("""select g.id from core_game g, jsonb_array_elements(g.raw_json->'_raw'->'competitions'->0->'competitors') c
        where c->'team'->>'id'='108822' and case when c->>'homeAway'='home' then g.home_team_id else g.away_team_id end = 731 order by 1""")]
    expect("games", games, [61204, 83464])
    expect("box rows naming 731 in them", one("""select count(*) from core_teamgamestats where game_id = any(%s)
        and (team_id=731 or opponent_id=731)""", [games]), 4)
    q("update core_teamgamestats set team_id=%s, updated_at=now() where game_id = any(%s) and team_id=731", [newbury, games])
    q("update core_teamgamestats set opponent_id=%s, updated_at=now() where game_id = any(%s) and opponent_id=731", [newbury, games])
    q("update core_game set home_team_id=%s, updated_at=now() where id = any(%s) and home_team_id=731", [newbury, games])
    q("update core_game set away_team_id=%s, updated_at=now() where id = any(%s) and away_team_id=731", [newbury, games])
    expect("player/stint rows with team 731 in those games", one("""select (select count(*) from core_playergamestats where game_id = any(%s) and team_id=731)
        + (select count(*) from core_playergamestint where game_id = any(%s) and team_id=731)""", [games, games]), 0)

    print("null-team player rows -> the unmapped side's team (by ESPN id)")
    side = """with s as (select g.id game_id, case when c->>'homeAway'='home' then g.home_team_id else g.away_team_id end team_id
                 from core_game g, jsonb_array_elements(g.raw_json->'_raw'->'competitions'->0->'competitors') c
                 where c->'team'->>'id' in ('3087', '108822', '126749'))"""
    expect("games with an unmapped side and null rows", one(side + """select count(distinct s.game_id) from s
        join core_playergamestats p on p.game_id=s.game_id and p.team_id is null"""), 7)
    expect("null rows outside those games", one(side + """select count(*) from core_playergamestats p
        where p.team_id is null and p.game_id not in (select game_id from s)"""), 0)
    n = q(side + """update core_playergamestats p set team_id = s.team_id from s where s.game_id = p.game_id and p.team_id is null""")
    expect("null player rows assigned", n, 82)

    print("Indiana St.-USC 2004-12-21: keep 9694 (ESPN 243560282), delete 9696 (ESPN 243560030)")
    expect("9694 is Indiana St. 64 - USC 68", q("select home_team_id, away_team_id, home_score, away_score, source_game_id from core_game where id=9694"),
           [(125, 327, 64, 68, "243560282")])
    expect("9694 box rows (team:pts)", sorted(q("select team_id, pts from core_teamgamestats where game_id=9694")), [(125, 64), (327, 68)])
    expect("9696 is USC 81 - Indiana St. 78", q("select home_team_id, away_team_id, home_score, away_score, source_game_id from core_game where id=9696"),
           [(327, 125, 81, 78, "243560030")])
    expect("9696 dependents (player, stint, event, validation)", one("""select (select count(*) from core_playergamestats where game_id=9696)
        + (select count(*) from core_playergamestint where game_id=9696) + (select count(*) from core_scoringevent where game_id=9696)
        + (select count(*) from validation_predictionsnapshot where game_id=9696) + (select count(*) from validation_gamevalidationresult where game_id=9696)"""), 0)
    expect("9696 box rows deleted", q("delete from core_teamgamestats where game_id=9696"), 2)
    expect("game 9696 deleted", q("delete from core_game where id=9696"), 1)

    print("San Diego St.-New Mexico, MW semifinal: game 8340 -> 2026-03-13 (ESPN 401851504)")
    expect("8340 as stored", q("""select source_game_id, game_date::text, home_team_id, away_team_id, home_score, away_score, neutral_site, start_time_utc
        from core_game where id=8340"""), [("6593725", "2026-03-14", 264, 198, 64, 62, False, None)])
    q("""update core_game set game_date='2026-03-13', start_time_utc='2026-03-14T03:59:00Z', neutral_site=true, updated_at=now()
         where id=8340""")
    expect("8344 untouched (final vs Utah St., 2026-03-14)", q("select source_game_id, game_date::text, home_score, away_score from core_game where id=8344"),
           [("6593721", "2026-03-14", 73, 62)])


def eastern_window(gid):
    raw = one("select raw_json->>'date' from core_game where id=%s", [gid])
    utc = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    et = utc.astimezone(ZoneInfo("America/New_York")).date()
    return min(et, utc.date()), max(et, utc.date())


def refetch():
    print("re-ingest boxes from ESPN (ingest_gamelogs --game-ids)")
    targets = [(gid, yr) for gid, yr in ONE_SIDED.items()]
    targets += [(r[0], 2017) for r in q("""select id from core_game where season_year=2017 and %s in (home_team_id, away_team_id)
                                           order by game_date, id""", [EWU])]
    by_window = {}
    for gid, yr in targets:
        sid = one("select source_game_id from core_game where id=%s", [gid])
        by_window.setdefault((yr,) + eastern_window(gid), []).append(sid)
    for (yr, start, end), sids in sorted(by_window.items()):
        call_command("ingest_gamelogs", season=yr, source="espn", start=str(start), end=str(end), refresh=True,
                     game_ids=",".join(sids), stdout=open(os.environ.get("TASK6G_LOG", os.devnull), "a"))
        print(f"  {yr} {start}..{end}: {', '.join(sids)}")

    print("2026 player sync for BC, BU, New Haven, Southern Indiana")
    call_command("sync_ncaa_player_gamelogs", season=2026, teams=f"{BC},{BU},{NEW_HAVEN},{SO_INDIANA}", sleep=1.1, workers=1)


def postconditions():
    print("postconditions")
    expect("EWU 2017 games", one("select count(*) from core_game where season_year=2017 and %s in (home_team_id, away_team_id)", [EWU]), 32)
    expect("EWU 2017 EWU box rows", one("""select count(*) from core_teamgamestats t join core_game g on g.id=t.game_id
        where g.season_year=2017 and t.team_id=%s""", [EWU]), 32)
    expect("EWU 2017 opponent box rows", one("""select count(*) from core_teamgamestats t join core_game g on g.id=t.game_id
        where g.season_year=2017 and t.opponent_id=%s""", [EWU]), 32)
    for gid in ONE_SIDED:
        expect(f"game {gid} box rows", one("select count(*) from core_teamgamestats where game_id=%s and fga > 0", [gid]), 2)
    expect("null-team player rows", one("select count(*) from core_playergamestats where team_id is null"), 0)
    for tid in (BC, BU, NEW_HAVEN, SO_INDIANA):
        n = one("""select count(*) from core_game g where g.season_year=2026 and g.status='final' and %s in (g.home_team_id, g.away_team_id)
                   and not exists (select 1 from core_playergamestats p where p.game_id=g.id and p.team_id=%s)""", [tid, tid])
        print(f"  team {tid}: 2026 final games without its player rows: {n}")


if __name__ == "__main__":
    preconditions()
    if not APPLY:
        try:
            with transaction.atomic():
                sql_fixes()
                raise Rollback()
        except Rollback:
            print("REHEARSAL OK (rolled back; no network)")
        sys.exit(0)
    with transaction.atomic():
        sql_fixes()
    print("SQL steps committed")
    refetch()
    postconditions()
    print("DONE")
