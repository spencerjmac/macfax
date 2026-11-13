"""
Task 8a.2: 2026 is_reclassifying for the 2023 Division II arrivals.

TeamSeasonMembership flagged every team in its first 4 D1 seasons as reclassifying ("assumed"). For 2025-26 that
is wrong for the five schools that started D1 play in 2022-23: Wikipedia's "2025-26 NCAA Division I men's
basketball season" standings mark transition-ineligible teams with "*" ("ineligible for the 2026 NCAA tournament
due to transition from Division II"), and none of the five carries it. Queens won the ASUN tournament and played
in the 2026 NCAA tournament (a team in the field can't be reclassifying).
  set False: Queens 243, East Texas A&M 78, Lindenwood 146, Southern Indiana 281, Stonehill 290
  unchanged (marked "*"): Le Moyne 143 (first D1 season 2024)
Only 2026 rows change; sync_team_season_membership never updates existing rows.

  python data_fixes/2026-11-13_task8a2_reclassifying_2026.py [--apply]     (from backend/; default: rehearsal)
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.db import connection, transaction  # noqa: E402

FIX = {243: "Queens", 78: "East Texas A&M", 146: "Lindenwood", 281: "Southern Indiana", 290: "Stonehill"}
KEEP = {143: "Le Moyne"}
NOTE = ("8a.2: not reclassifying in 2025-26; eligible for the 2026 NCAA tournament (no transition mark in "
        "Wikipedia's 2025-26 season standings)")


class Rollback(Exception):
    pass


def q(sql, p=None):
    with connection.cursor() as c:
        c.execute(sql, p or [])
        return c.fetchall() if c.description else c.rowcount


def expect(label, got, want):
    print(f"  {label}: {got}" + ("" if got == want else f"  (EXPECTED {want})"))
    if got != want:
        raise SystemExit(f"assertion failed: {label}")


def rows(ids):
    return q("""select t.id, t.name, m.is_d1, m.is_reclassifying from core_teamseasonmembership m join core_team t on t.id = m.team_id
                join core_season s on s.id = m.season_id where s.year = 2026 and t.id = any(%s) order by t.id""", [list(ids)])


def reclass_2026():
    return [r[0] for r in q("""select t.name from core_teamseasonmembership m join core_team t on t.id = m.team_id
        join core_season s on s.id = m.season_id where s.year = 2026 and m.is_reclassifying order by t.name""")]


def run():
    expect("names by id", {r[0]: r[1] for r in rows(FIX | KEEP)}, FIX | KEEP)
    expect("before: fix rows (is_d1, is_reclassifying)", {r[0]: (r[2], r[3]) for r in rows(FIX)}, {t: (True, True) for t in FIX})
    before = reclass_2026()
    expect("before: 2026 reclassifying count", len(before), 9)
    n = q("""update core_teamseasonmembership m set is_reclassifying = false, note = %s, updated_at = now()
             from core_season s where s.id = m.season_id and s.year = 2026 and m.team_id = any(%s) and m.is_reclassifying""",
          [NOTE, list(FIX)])
    expect("rows updated", n, 5)
    expect("after: fix rows", {r[0]: (r[2], r[3]) for r in rows(FIX)}, {t: (True, False) for t in FIX})
    expect("after: Le Moyne unchanged", {r[0]: (r[2], r[3]) for r in rows(KEEP)}, {143: (True, True)})
    expect("after: 2026 reclassifying", reclass_2026(), ["Le Moyne", "Mercyhurst", "New Haven", "West Georgia"])
    expect("other seasons' reclassifying rows unchanged", q("""select count(*) from core_teamseasonmembership m join core_season s
        on s.id = m.season_id where s.year <> 2026 and m.is_reclassifying""")[0][0], REST)
    expect("2026 NCAA tournament teams still reclassifying", q("""select count(*) from core_game g
        join core_season s on s.year = g.season_year
        join core_teamseasonmembership m on m.season_id = s.id and m.team_id in (g.home_team_id, g.away_team_id)
        where g.season_year = 2026 and g.raw_json::jsonb -> '_raw' ->> 'championshipId' = '6393' and m.is_reclassifying""")[0][0], 0)


REST = None

if __name__ == "__main__":
    REST = q("""select count(*) from core_teamseasonmembership m join core_season s on s.id = m.season_id
                where s.year <> 2026 and m.is_reclassifying""")[0][0]
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
