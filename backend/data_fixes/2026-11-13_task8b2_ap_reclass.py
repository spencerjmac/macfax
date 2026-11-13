"""
Task 8b.2: AP week-6 ranks that the poll backfill missed, and one wrong reclassifying flag.

1. AP week 6 (TeamSeasonRatings.ap_poll_week6, pre and post rows). backfill_ap_polls reads sports-reference's
   /cbb/seasons/men/{Y}-polls.html "Week Poll 6" column and name-matches schools; 11 names failed (Pitt, NC State,
   UMass, Florida Atlantic; logged in ap_polls_output.txt) and Boston College 2006 had no rating row at the time.
   2026-11-13_task8b2_ap_week6.csv is the full source poll for 2005-2026 except 2020 (528 rows: 516 already stored,
   12 added here, status added_8b2). Ties are kept as the source has them (2011 #22, 2012 #25, 2019 #25, 2021 #21).
2. Reclassifying: every flagged team-season 2006-2027 was checked against the conference standings on Wikipedia's
   "{Y-1}-{YY} NCAA Division I men's basketball season" page (marks such as "ineligible for the NCAA tournament due
   to transition"). Le Moyne 2027 (its 4th D1 season) is unmarked in a table that marks the transitioning teams, so
   its flag is wrong. No other flag is contradicted; seasons before about 2010 carry no transition marks.

  python data_fixes/2026-11-13_task8b2_ap_reclass.py [--apply]     (from backend/; default: rehearsal)
"""
import collections, csv, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.db import connection, transaction  # noqa: E402

POLL = Path(__file__).resolve().parent / "2026-11-13_task8b2_ap_week6.csv"
LE_MOYNE = 143
NOTE = ("8b.2: eligible in 2026-27 (no transition mark in Wikipedia's 2026-27 season standings; "
        "the 2023 arrivals were eligible in their 4th season too)")


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


def stored_poll():
    return {(y, t, pre): rk for y, t, pre, rk in q("""select s.year, r.team_id, r.is_pre_tournament, r.ap_poll_week6
        from core_teamseasonratings r join core_season s on s.id = r.season_id
        where r.ap_poll_week6 is not null and s.year between 2005 and 2026 and s.year <> 2020""")}


def run():
    poll = list(csv.DictReader(open(POLL)))
    expect("poll rows (existing, added_8b2)", (sum(r["status"] == "existing" for r in poll), sum(r["status"] == "added_8b2" for r in poll)), (516, 12))
    names = dict(q("select id, name from core_team"))
    expect("CSV team names that differ from core_team", [r for r in poll if names.get(int(r["team_id"])) != r["team_name"]], [])

    # 1. AP week 6
    before = stored_poll()
    expect("existing rows already stored (pre and post)", all(before.get((int(r["season"]), int(r["team_id"]), pre)) == int(r["rank"])
           for r in poll if r["status"] == "existing" for pre in (True, False)), True)
    added = [r for r in poll if r["status"] == "added_8b2"]
    expect("added rows NULL before (pre and post)", [r for r in added for pre in (True, False)
           if (int(r["season"]), int(r["team_id"]), pre) in before], [])
    n = 0
    for r in added:
        n += q("""update core_teamseasonratings set ap_poll_week6 = %s
                  where team_id = %s and season_id = (select id from core_season where year = %s) and ap_poll_week6 is null""",
               [int(r["rank"]), int(r["team_id"]), int(r["season"])])
    expect("rating rows updated (12 team-seasons x pre/post)", n, 24)
    after = stored_poll()
    want = collections.Counter((int(r["season"]), int(r["rank"])) for r in poll)
    for pre in (True, False):
        got = collections.Counter((y, rk) for (y, t, p), rk in after.items() if p == pre)
        expect(f"stored ranks equal the source poll ({'pre' if pre else 'post'})", got == want, True)
    per = collections.Counter(y for (y, t, p) in after if not p)
    expect("seasons whose ranks don't cover 1-25 (ties skip the next rank)", [y for y in sorted(per)
           if sorted({rk for (yy, t, p), rk in after.items() if yy == y and not p}) and
           (per[y] < 25 or max(rk for (yy, t, p), rk in after.items() if yy == y and not p) != 25)], [])
    expect("ranked teams per season", dict(sorted(per.items())),
           {y: (26 if y == 2012 else 27 if y == 2019 else 25) for y in range(2005, 2027) if y != 2020})

    # 2. Reclassifying
    expect("Le Moyne 2027 before", q("""select is_d1, is_reclassifying from core_teamseasonmembership m join core_season s
        on s.id = m.season_id where s.year = 2027 and m.team_id = %s""", [LE_MOYNE]), [(True, True)])
    expect("rows updated", q("""update core_teamseasonmembership m set is_reclassifying = false, note = %s, updated_at = now()
        from core_season s where s.id = m.season_id and s.year = 2027 and m.team_id = %s and m.is_reclassifying""",
        [NOTE, LE_MOYNE]), 1)
    expect("2027 reclassifying", [r[0] for r in q("""select t.name from core_teamseasonmembership m join core_team t on t.id = m.team_id
        join core_season s on s.id = m.season_id where s.year = 2027 and m.is_reclassifying order by 1""")],
           ["Mercyhurst", "New Haven", "West Florida", "West Georgia"])
    expect("seeded (NCAA) teams that are reclassifying, any season", q("""select count(*) from core_teamseasonratings r
        join core_teamseasonmembership m on m.team_id = r.team_id and m.season_id = r.season_id
        where r.tournament_seed is not null and m.is_reclassifying""")[0][0], 0)


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
