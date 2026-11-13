"""
Task 6d step 3: delete rating rows (pre and post) and team-metrics rows for team-seasons that are not D1 that
season (TeamSeasonMembership) or have no played game that season (final, not 0-0). Run after the recompute
(data_fixes/2026-11-13_task6d_recompute_all.py), which writes rows only for D1 members with games; what remains
are stale rows the recompute does not touch (e.g. pre-D1 programs rated before 6f.2, the all-zero 2019/2025
post rows).

  python data_fixes/2026-11-13_task6d_delete_non_d1_rows.py [--apply]     (from backend/; default: rehearsal)
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.db import connection, transaction  # noqa: E402

KEEP = """
  with played as (select distinct g.season_year yr, x.tid from core_game g
                  cross join lateral (values (g.home_team_id), (g.away_team_id)) x(tid)
                  where g.status = 'final' and not (g.home_score = 0 and g.away_score = 0))
  select s.id season_id, m.team_id from core_teamseasonmembership m join core_season s on s.id = m.season_id
  join played p on p.yr = s.year and p.tid = m.team_id where m.is_d1
"""


class Rollback(Exception):
    pass


def q(sql, p=None):
    with connection.cursor() as c:
        c.execute(sql, p or []); return c.fetchall() if c.description else c.rowcount


def expect(label, got, want):
    print(f"  {label}: {got}" + ("" if got == want else f"  (EXPECTED {want})"))
    if got != want:
        raise SystemExit(f"assertion failed: {label}")


def run():
    q(f"create temp table keep_ts on commit drop as {KEEP}")
    for table in ("core_teamseasonratings", "core_teamseasonmetrics"):
        rows = q(f"""select s.year, t.is_pre_tournament, count(*) from {table} t join core_season s on s.id = t.season_id
                     where not exists (select 1 from keep_ts k where k.season_id = t.season_id and k.team_id = t.team_id)
                     group by 1, 2 order by 1, 2""")
        print(f"{table}: rows to delete per season (pre / post)")
        by = {}
        for y, pre, n in rows:
            by.setdefault(y, [0, 0])[0 if pre else 1] = n
        for y in sorted(by):
            print(f"  {y}: {by[y][0]} / {by[y][1]}")
        total = sum(n for *_, n in rows)
        detail = q(f"""select s.year, tm.name, t.team_id, t.is_pre_tournament,
                        coalesce((select m.is_d1::text from core_teamseasonmembership m where m.season_id = t.season_id and m.team_id = t.team_id), 'no row'),
                        (select count(*) from core_game g where g.season_year = s.year and t.team_id in (g.home_team_id, g.away_team_id)
                           and g.status = 'final' and not (g.home_score = 0 and g.away_score = 0))
                     from {table} t join core_season s on s.id = t.season_id join core_team tm on tm.id = t.team_id
                     where s.year in (2019, 2025)
                       and not exists (select 1 from keep_ts k where k.season_id = t.season_id and k.team_id = t.team_id)
                     order by 1, 2, 4""")
        print(f"  {table} 2019 and 2025 rows (season, team, id, pre, D1 that season, played games):")
        for r in detail:
            print("   ", r)
        n = q(f"""delete from {table} t where not exists (select 1 from keep_ts k where k.season_id = t.season_id
                  and k.team_id = t.team_id)""")
        expect(f"{table}: deleted", n, total)
    # every kept team-season has both rating rows; ratings rows per season = D1 members with games
    expect("rating rows per season and phase = D1 members with games", q("""
        select s.year, r.is_pre_tournament, count(*), (select count(*) from keep_ts k where k.season_id = s.id)
        from core_teamseasonratings r join core_season s on s.id = r.season_id group by s.year, s.id, r.is_pre_tournament
        having count(*) <> (select count(*) from keep_ts k where k.season_id = s.id)"""), [])


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
