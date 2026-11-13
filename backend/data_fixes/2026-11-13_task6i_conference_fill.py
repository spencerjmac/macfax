"""
Task 6i: conference_id on every D1 TeamSeasonMetrics row, 2005-2026 (pre and post).

Before this fix only the 365 post-tournament 2026 rows had a conference; every other row (15,029) was NULL.

Labels (2026-11-13_task6i_conference_labels.csv, one row per D1 team-season by TeamSeasonMembership):
  * 2026: the existing post-tournament labels (unchanged here; the pre rows copy them).
  * 2025 back to 2005: chained backward one season at a time. label(Y-1) = label(Y), except schools listed in
    Wikipedia's "{Y-1}-{YY} NCAA Division I men's basketball season" "Conference membership changes" table,
    which take the former conference (2026-11-13_task6i_wiki_membership_changes.csv, 282 rows, every season
    page 2005-06 .. 2025-26). Bethune-Cookman and Maryland Eastern Shore sat out 2020-21 (not D1 in 2021), so
    their 2020 labels carry back across the gap (B-CU: MEAC, from its 2021-22 MEAC -> SWAC move).
  * Renamed leagues keep one row: Mid-Continent -> Summit League (2005-2007), Pac-10 -> Pac-12 (2005-2011),
    original Big East -> Big East (2005-2013).
  * New Conference rows: GWC Great West Conference (2010-2013) and IND Independent.
  * Checked against ESPN's per-game conferenceCompetition flag: every labelled team-season 2005-2025 has >= 4
    conference-flagged D1 games and >= 60% of them against its own label, and no Independent has >= 4 (Ivy
    games are never flagged; Winston-Salem St. 2008-2009 has none as a transitioning MEAC member).

  python data_fixes/2026-11-13_task6i_conference_fill.py [--apply]     (from backend/; default: rehearsal)
"""
import csv, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.db import connection, transaction  # noqa: E402

HERE = Path(__file__).resolve().parent
LABELS = HERE / "2026-11-13_task6i_conference_labels.csv"
NEW_CONFERENCES = [("GWC", "Great West Conference"), ("IND", "Independent")]


class Rollback(Exception):
    pass


def q(sql, p=None):
    with connection.cursor() as c:
        c.execute(sql, p or []); return c.fetchall()


def expect(label, got, want):
    print(f"  {label}: {got}" + ("" if got == want else f"  (EXPECTED {want})"))
    if got != want:
        raise SystemExit(f"assertion failed: {label}")


def label_of(team_id, year, pre=False):
    r = q("""select c.code from core_teamseasonmetrics m join core_season s on s.id = m.season_id
             left join core_conference c on c.id = m.conference_id
             where m.team_id = %s and s.year = %s and m.is_pre_tournament = %s""", [team_id, year, pre])
    return r[0][0] if r else "no row"


def run():
    rows = list(csv.DictReader(open(LABELS)))
    expect("label rows", len(rows), 7705)

    # 1. Conference rows for leagues the table lacks.
    for code, name in NEW_CONFERENCES:
        expect(f"{code} exists before", q("select count(*) from core_conference where code = %s", [code])[0][0], 0)
        q("insert into core_conference (code, name) values (%s, %s) returning id", [code, name])
    conf = dict(q("select code, id from core_conference"))
    expect("conference codes in CSV all exist", sorted({r["conference_code"] for r in rows} - conf.keys()), [])

    # 2. CSV agrees with the DB: names by team id, one row per D1 membership.
    names = dict(q("select id, name from core_team"))
    expect("CSV team names that differ from core_team", [r for r in rows if names.get(int(r["team_id"])) != r["team_name"]], [])
    d1 = {(y, t) for y, t in q("""select s.year, m.team_id from core_teamseasonmembership m join core_season s on s.id = m.season_id
                                   where m.is_d1 and s.year between 2005 and 2026""")}
    keys = {(int(r["season"]), int(r["team_id"])) for r in rows}
    expect("CSV keys unique", len(keys), len(rows))
    expect("CSV team-seasons vs D1 membership (missing, extra)", (len(d1 - keys), len(keys - d1)), (0, 0))

    # 3. 2026 post labels already stored must equal the CSV (the chain starts there).
    stored26 = {t: c for t, c in q("""select m.team_id, c.code from core_teamseasonmetrics m join core_season s on s.id = m.season_id
        join core_conference c on c.id = m.conference_id where s.year = 2026 and not m.is_pre_tournament""")}
    csv26 = {int(r["team_id"]): r["conference_code"] for r in rows if r["season"] == "2026"}
    expect("2026 post labels differing from CSV", sum(stored26.get(t) != c for t, c in csv26.items()), 0)

    before = q("""select count(*), count(m.conference_id) from core_teamseasonmetrics m join core_season s on s.id = m.season_id
                  where s.year between 2005 and 2026""")[0]
    expect("metrics rows 2005-2026 (total, with conference) before", before, (15394, 365))

    # 4. Fill every NULL row from the CSV.
    with connection.cursor() as c:
        c.execute("create temp table t6i_labels (year int, team_id bigint, conference_id bigint) on commit drop")
        c.executemany("insert into t6i_labels values (%s, %s, %s)",
                      [(int(r["season"]), int(r["team_id"]), conf[r["conference_code"]]) for r in rows])
        c.execute("""update core_teamseasonmetrics m set conference_id = l.conference_id
                     from core_season s, t6i_labels l
                     where s.id = m.season_id and l.year = s.year and l.team_id = m.team_id and m.conference_id is null""")
        updated = c.rowcount
    expect("rows updated", updated, 15394 - 365)

    # 5. Checks.
    expect("metrics rows 2005-2026 without conference", q("""select count(*) from core_teamseasonmetrics m
        join core_season s on s.id = m.season_id where s.year between 2005 and 2026 and m.conference_id is null""")[0][0], 0)
    expect("metrics rows on a non-D1 team-season", q("""select count(*) from core_teamseasonmetrics m join core_season s on s.id = m.season_id
        where s.year between 2005 and 2026 and not exists (select 1 from core_teamseasonmembership x
        where x.team_id = m.team_id and x.season_id = m.season_id and x.is_d1)""")[0][0], 0)
    expect("pre/post rows with different conferences", q("""select count(*) from core_teamseasonmetrics a
        join core_teamseasonmetrics b on b.team_id = a.team_id and b.season_id = a.season_id
        where a.is_pre_tournament and not b.is_pre_tournament and a.conference_id is distinct from b.conference_id""")[0][0], 0)
    expect("rows whose conference differs from the CSV", q("""select count(*) from core_teamseasonmetrics m join core_season s on s.id = m.season_id
        join t6i_labels l on l.year = s.year and l.team_id = m.team_id where m.conference_id <> l.conference_id""")[0][0], 0)
    per = dict(((y, c), n) for y, c, n in q("""select s.year, c.code, count(*) from core_teamseasonmetrics m join core_season s on s.id = m.season_id
        join core_conference c on c.id = m.conference_id where not m.is_pre_tournament group by 1, 2"""))
    expect("Great West members 2010-2013", [per.get((y, "GWC"), 0) for y in range(2010, 2014)], [7, 7, 6, 5])
    expect("Pac-12 members 2024, 2025", [per.get((2024, "P12"), 0), per.get((2025, "P12"), 0)], [12, 0])
    expect("Big East 2005, 2006, 2013, 2014", [per.get((y, "BE")) for y in (2005, 2006, 2013, 2014)], [12, 16, 15, 10])
    expect("American 2014", per.get((2014, "Amer")), 10)
    expect("Independents 2005-2026", {y: per.get((y, "IND"), 0) for y in range(2005, 2027) if per.get((y, "IND"))},
           {2005: 10, 2006: 10, 2007: 11, 2008: 10, 2009: 14, 2010: 7, 2011: 7, 2012: 5, 2013: 2, 2014: 1, 2015: 1, 2023: 2, 2024: 1})
    spot = [  # (team id, season, code)
        (27, 2005, "BE"), (27, 2006, "ACC"), (27, 2025, "ACC"),                    # Boston College
        (824, 2005, "AE"), (824, 2022, "AE"), (824, 2023, "IND"),                  # Hartford
        (825, 2005, "NEC"), (825, 2023, "NEC"),                                    # St. Francis Brooklyn
        (826, 2005, "IND"), (826, 2011, "IND"), (826, 2012, "MEAC"), (826, 2019, "MEAC"),  # Savannah St.
        (827, 2007, "IND"), (827, 2008, "MEAC"), (827, 2009, "MEAC"), (827, 2010, "IND"),  # Winston-Salem St.
        (828, 2005, "BSth"), (828, 2006, "BSth"),                                  # Birmingham-Southern
        (719, 2005, "Sum"), (719, 2011, "Sum"),                                    # Centenary (LA)
        (281, 2023, "OVC"), (281, 2025, "OVC"),                                    # Southern Indiana
        (82, 2017, "BSky"),                                                        # Eastern Washington
        (24, 2020, "MEAC"), (24, 2022, "SWAC"),                                    # Bethune-Cookman (sat out 2021)
    ]
    expect("spot checks (pre, post) not as expected",
           [(t, y, c, label_of(t, y, True), label_of(t, y)) for t, y, c in spot if (label_of(t, y, True), label_of(t, y)) != (c, c)], [])


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
