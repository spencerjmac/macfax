"""
Task 6f.1: season-level D1 membership (TeamSeasonMembership), 2005-2027. Local macfax DB.
Requires migration core 0071 (python manage.py migrate core 0071).

  python data_fixes/2026-11-12_task6f1_membership.py            # rehearsal: all steps, rolled back
  python data_fixes/2026-11-12_task6f1_membership.py --apply

Rows: data_fixes/2026-11-12_task6f1_team_season_membership.csv (10,484 rows; team_id, or espn_new for a
team created here). Built from:
- 2014-2027: ESPN core API seasons/{y}/types/2/groups/50/teams (fetched 2026-11-12), with Task 6e's hand
  fixes (Hartford 2024-27 and St. Francis Brooklyn 2024 listed after leaving D1; UC San Diego and
  Bellarmine listed in 2020, a year before joining).
- 2005-2013: Task 6e's derived set = ESPN's partial list + teams with >= 10 played games + manual rows.
  Rulings: North Dakota St. 2005 and New Orleans 2012 are D1 (members; schedule size doesn't decide).
  Programs with no stored games: Hartford and St. Francis Brooklyn 2005-23, Savannah St. 2005-19,
  Winston-Salem St. 2007-10, Southern Indiana 2023-25, and Birmingham-Southern 2005-06 (Wikipedia: last
  D1 season 2006; not in 6e's set).
- Wikipedia ("List of NCAA Division I institutions", "List of schools reclassifying their athletic
  programs to NCAA Division I"): Saint Francis (PA) not D1 in 2027 (last D1 season 2025-26; ESPN agrees);
  transition years for Mercyhurst and West Georgia (2025-27), New Haven (2026-28), West Florida (2027-29).
  Other programs: is_reclassifying = first 4 D1 seasons, noted 'assumed'.
  ESPN's 2009 list includes Morris Brown (ESPN 2417), which Wikipedia says left D1 after 2003: no row.
- Every other team with a game that season: is_d1 = False.
New teams (no games yet, Task 6f.3): Hartford (ESPN 42), St. Francis Brooklyn (2597), Savannah St. (2542),
Winston-Salem St. (2736), Birmingham-Southern (ESPN id unknown). Southern Indiana's ESPN 88 exists (6g).
ESPN 2697 -> West Florida (799): game 123565 (2026-11-02, West Florida home vs Southeastern Baptist) is
ESPN event 401922247 (2697 home vs 111951 Southeastern Baptist, same date).
"""

import csv
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from django.db import connection, transaction  # noqa: E402

APPLY = "--apply" in sys.argv
CSV = HERE / "2026-11-12_task6f1_team_season_membership.csv"
NEW_TEAMS = [  # (name, slug, ESPN id or None)
    ("Hartford", "hartford", "42"), ("St. Francis Brooklyn", "st-francis-brooklyn", "2597"),
    ("Savannah St.", "savannah-st", "2542"), ("Winston-Salem St.", "winston-salem-st", "2736"),
    ("Birmingham-Southern", "birmingham-southern", None),
]
D1_PER_SEASON = {2005: 332, 2006: 334, 2007: 336, 2008: 342, 2009: 347, 2010: 347, 2011: 346, 2012: 346, 2013: 347,
                 2014: 351, 2015: 351, 2016: 351, 2017: 351, 2018: 351, 2019: 353, 2020: 353, 2021: 355, 2022: 358,
                 2023: 363, 2024: 362, 2025: 364, 2026: 365, 2027: 365}
PRE_D1_58 = {  # Task 6e list (a): treated as D1 by Team.is_d1 but not D1 that season
    2005: ["Cal Baptist", "Grand Canyon", "Houston Christian", "Nebraska Omaha", "North Florida", "SIU Edwardsville",
           "Seattle", "UC San Diego", "USC Upstate"],   # North Dakota St. 2005 ruled D1
    2006: ["Houston Christian", "Northern Kentucky", "Seattle", "Tarleton St.", "UC San Diego"],
    2007: ["Abilene Christian", "Bellarmine", "Cal St. Bakersfield", "Florida Gulf Coast", "Incarnate Word", "Nebraska Omaha",
           "North Carolina Central", "Presbyterian", "SIU Edwardsville", "Stonehill", "UC San Diego"],
    2008: ["Le Moyne", "North Alabama", "Queens", "UC San Diego", "Utah Tech"],
    2009: ["Cal Baptist", "Le Moyne", "North Alabama", "UC San Diego", "West Georgia"],
    2010: ["Cal Baptist", "Le Moyne", "UC San Diego", "West Georgia"],
    2011: ["Cal Baptist", "Grand Canyon", "North Alabama", "Queens"],
    2012: ["Grand Canyon"],   # New Orleans 2012 ruled D1
    2013: ["North Alabama"],
    2015: ["North Alabama", "UC San Diego"], 2016: ["UC San Diego"],
    2019: ["East Texas A&M", "Le Moyne", "Lindenwood", "Utah Tech"], 2020: ["Lindenwood"],
    2021: ["Mercyhurst", "Queens"], 2022: ["East Texas A&M"],
}


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


def run():
    print("teams and ESPN mappings")
    expect("membership table empty", one("select count(*) from core_teamseasonmembership"), 0)
    for name, slug, eid in NEW_TEAMS:
        expect(f"{name} absent", one("select count(*) from core_team where name=%s or slug=%s", [name, slug]), 0)
        if eid:
            expect(f"ESPN {eid} unmapped", one("select count(*) from core_teamexternalid where source='espn' and external_id=%s", [eid]), 0)
    new_ids = {}
    for name, slug, eid in NEW_TEAMS:
        new_ids[name] = one("insert into core_team (slug, name, aliases, is_d1, created_at) values (%s, %s, '[]'::jsonb, false, now()) returning id",
                            [slug, name])
        if eid:
            q("""insert into core_teamexternalid (source, external_id, external_name, confidence, is_manual_override, created_at, updated_at, team_id)
                 values ('espn', %s, %s, 1.0, true, now(), now(), %s)""", [eid, name, new_ids[name]])
    print("  created:", new_ids)
    expect("ESPN 88 -> Southern Indiana (281)", q("select team_id from core_teamexternalid where source='espn' and external_id='88'"), [(281,)])
    expect("West Florida (799) has no ESPN row; 2697 unmapped", one("""select count(*) from core_teamexternalid where source='espn'
        and (team_id=799 or external_id='2697')"""), 0)
    q("""insert into core_teamexternalid (source, external_id, external_name, confidence, is_manual_override, created_at, updated_at, team_id)
         values ('espn', '2697', 'West Florida', 1.0, true, now(), now(), 799)""")

    print("membership rows")
    by_espn = {eid: new_ids[name] for name, _, eid in NEW_TEAMS if eid}
    by_espn["bsc"] = new_ids["Birmingham-Southern"]
    seasons = dict(q("select year, id from core_season"))
    rows = list(csv.DictReader(open(CSV)))
    expect("CSV rows", len(rows), 10484)
    vals = []
    for r in rows:
        tid = int(r["team_id"]) if r["team_id"] else by_espn[r["espn_new"]]
        rc = None if r["is_reclassifying"] == "" else r["is_reclassifying"] == "True"
        vals.append((seasons[int(r["season"])], tid, r["is_d1"] == "True", rc, r["source"], r["note"]))
    with connection.cursor() as c:
        c.executemany("""insert into core_teamseasonmembership (season_id, team_id, is_d1, is_reclassifying, source, note, created_at, updated_at)
                         values (%s, %s, %s, %s, %s, %s, now(), now())""", vals)
    expect("rows inserted", one("select count(*) from core_teamseasonmembership"), 10484)

    print("validation")
    d1 = dict(q("""select s.year, count(*) from core_teamseasonmembership m join core_season s on s.id=m.season_id
                   where m.is_d1 group by 1"""))
    expect("D1 per season", d1, D1_PER_SEASON)
    expect("one row per (season, team)", one("""select count(*) from (select season_id, team_id from core_teamseasonmembership
        group by 1, 2 having count(*) > 1) x"""), 0)
    pre = [(y, n) for y, names in PRE_D1_58.items() for n in names]
    expect("6e pre-D1 list size", len(pre), 58 - 2)   # 58 minus the two ruled D1
    bad = [(y, n) for y, n in pre if q("""select m.is_d1 from core_teamseasonmembership m join core_season s on s.id=m.season_id
        join core_team t on t.id=m.team_id where s.year=%s and t.name=%s""", [y, n]) != [(False,)]]
    expect("6e pre-D1 team-seasons with is_d1=false (row present)", bad, [])
    expect("rulings: North Dakota St. 2005, New Orleans 2012 D1", q("""select s.year, t.name, m.is_d1 from core_teamseasonmembership m
        join core_season s on s.id=m.season_id join core_team t on t.id=m.team_id
        where (s.year, t.name) in ((2005, 'North Dakota St.'), (2012, 'New Orleans')) order by 1"""),
           [(2005, "North Dakota St.", True), (2012, "New Orleans", True)])
    expect("Centenary (LA) 2005-2011 D1", q("""select count(*) filter (where m.is_d1), count(*) from core_teamseasonmembership m
        join core_season s on s.id=m.season_id join core_team t on t.id=m.team_id where t.name='Centenary (LA)' and s.year between 2005 and 2011"""),
           [(7, 7)])
    expect("2027 rows (D1, total)", q("""select count(*) filter (where m.is_d1), count(*) from core_teamseasonmembership m
        join core_season s on s.id=m.season_id where s.year=2027"""), [(365, one("""select count(*) from core_teamseasonmembership m
        join core_season s on s.id=m.season_id where s.year=2027"""))])
    expect("every team with a game has a row", one("""select count(*) from (select distinct g.season_year, x.tid from core_game g
        cross join lateral (values (g.home_team_id), (g.away_team_id)) x(tid) where g.season_year between 2005 and 2027) gt
        join core_season s on s.year = gt.season_year
        where not exists (select 1 from core_teamseasonmembership m where m.season_id = s.id and m.team_id = gt.tid)"""), 0)
    expect("is_reclassifying NULL exactly when not D1", one("""select count(*) from core_teamseasonmembership
        where (is_d1 and is_reclassifying is null) or (not is_d1 and is_reclassifying is not null)"""), 0)


if __name__ == "__main__":
    if not APPLY:
        try:
            with transaction.atomic():
                run()
                raise Rollback()
        except Rollback:
            print("REHEARSAL OK (rolled back)")
        sys.exit(0)
    with transaction.atomic():
        run()
    print("DONE")
