"""
Task 6f.3: add the games of the six D1 programs missing from the Game table (local macfax DB).

  python data_fixes/2026-11-13_task6f3_missing_programs.py --sched-dir DIR            # rehearsal: subset, rolled back
  python data_fixes/2026-11-13_task6f3_missing_programs.py --sched-dir DIR --apply    # everything

Programs (Team rows from Task 6f.1, D1 seasons from TeamSeasonMembership):
  Hartford 824 (ESPN 42) 2005-2023, St. Francis Brooklyn 825 (2597) 2005-2023, Savannah St. 826 (2542) 2005-2019,
  Winston-Salem St. 827 (2736) 2007-2010, Southern Indiana 281 (88) 2023-2025, Birmingham-Southern 828 2005-2006.
Birmingham-Southern = ESPN 3: competitor "Birmingham Southern Panthers" (id 3) in ESPN events 260590003
(Charleston Southern at Birmingham-Southern, 2006-03-01) and 253512113 (Birmingham-Southern at Centenary, 2005-12-17).

1. ESPN team schedule per program-season, regular season and postseason (seasontype 2 and 3); cached as JSON in
   --sched-dir so the rehearsal and the apply run make the same calls once.
2. ingest_gamelogs --source espn --espn-event-file per season: one summary per event; teams by ESPN id only;
   existing ids and same-pair games on the same date skipped; Game + both box rows; period_count from status.period
   (the summary's linescores, else the schedule's status.period); player rows for 2015+; blanked ESPN players
   counted (reports in --sched-dir). Opponents with no ESPN-id mapping are reported, never created.
3. sync_team_season_membership per season: membership rows for any new opponent (no fetch; D1 rows exist).
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import connection, transaction  # noqa: E402

PROGRAMS = [  # team pk, ESPN id, name, seasons
    (824, "42", "Hartford", range(2005, 2024)),
    (825, "2597", "St. Francis Brooklyn", range(2005, 2024)),
    (826, "2542", "Savannah St.", range(2005, 2020)),
    (827, "2736", "Winston-Salem St.", range(2007, 2011)),
    (281, "88", "Southern Indiana", range(2023, 2026)),
    (828, "3", "Birmingham-Southern", range(2005, 2007)),
]
REHEARSAL = {828: [2005, 2006], 827: [2007], 281: [2023]}
SCHED = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{espn}/schedule?season={y}&seasontype={t}"


class Rollback(Exception):
    pass


def q(sql, params=None):
    with connection.cursor() as c:
        c.execute(sql, params or [])
        return c.fetchall() if c.description else c.rowcount


def one(sql, params=None):
    return q(sql, params)[0][0]


def expect(label, got, want):
    print(f"  {label}: {got}" + ("" if got == want else f"  (EXPECTED {want})"), flush=True)
    if got != want:
        raise SystemExit(f"assertion failed: {label}")


_last = [0.0]


def get(url):
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (macfax data audit)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3)
    raise err


def schedule(espn, y, sched_dir: Path):
    """[{id, date, status, period, home, away, home_score, away_score, notes}] for both season types."""
    f = sched_dir / f"sched_{espn}_{y}.json"
    if f.exists():
        return json.loads(f.read_text())
    out = []
    for t in (2, 3):
        d = get(SCHED.format(espn=espn, y=y, t=t))
        for e in d.get("events", []):
            c = e["competitions"][0]
            comp = {x["homeAway"]: x for x in c["competitors"]}
            sc = lambda x: (x.get("score") or {}).get("displayValue") if isinstance(x.get("score"), dict) else x.get("score")
            st = c.get("status") or {}
            out.append(dict(id=e["id"], date=e["date"], seasontype=t, status=(st.get("type") or {}).get("name"),
                            period=st.get("period"), home=comp["home"]["team"]["id"], away=comp["away"]["team"]["id"],
                            home_name=comp["home"]["team"].get("displayName"), away_name=comp["away"]["team"].get("displayName"),
                            home_score=sc(comp["home"]), away_score=sc(comp["away"]),
                            notes=[n.get("headline") for n in c.get("notes", [])][:1]))
    f.write_text(json.dumps(out))
    return out


def map_bsc():
    print("Birmingham-Southern ESPN id")
    expect("team 828", q("select name, is_d1 from core_team where id=828"), [("Birmingham-Southern", False)])
    expect("ESPN 3 unmapped, 828 has no ESPN row", one("""select count(*) from core_teamexternalid where source='espn'
        and (external_id='3' or team_id=828)"""), 0)
    q("""insert into core_teamexternalid (source, external_id, external_name, confidence, is_manual_override, created_at, updated_at, team_id)
         values ('espn', '3', 'Birmingham Southern Panthers', 1.0, true, now(), now(), 828)""")


def run(subset, sched_dir: Path):
    map_bsc()
    seasons = {}
    for tid, espn, name, ys in PROGRAMS:
        for y in ys:
            if subset and y not in subset.get(tid, []):
                continue
            expect(f"{name} {y}: D1 membership", q("""select m.is_d1 from core_teamseasonmembership m join core_season s on s.id=m.season_id
                where s.year=%s and m.team_id=%s""", [y, tid]), [(True,)])
            expect(f"{name} {y}: games before", one("select count(*) from core_game where season_year=%s and %s in (home_team_id, away_team_id)", [y, tid]), 0)
            for ev in schedule(espn, y, sched_dir):
                seasons.setdefault(y, {})[ev["id"]] = ev
    print(f"schedules: {sum(len(v) for v in seasons.values())} distinct events over {len(seasons)} seasons", flush=True)
    reports = {}
    for y, evs in sorted(seasons.items()):
        ids_file = sched_dir / f"ids_{y}.txt"
        ids_file.write_text("\n".join(sorted(evs)))
        rep_file = sched_dir / f"report_{y}{'_rehearsal' if subset else ''}.json"
        call_command("ingest_gamelogs", season=y, source="espn", espn_event_file=str(ids_file), report=str(rep_file),
                     stdout=open(os.devnull, "w"))
        reports[y] = json.loads(rep_file.read_text())
        r = reports[y]
        print(f"  {y}: {len(evs)} events -> created {len(r['created'])}, skipped existing {len(r['skipped_existing'])}, "
              f"same pair/day {len(r['skipped_same_pair'])}, unresolved {len(r['unresolved'])}, no summary {len(r['no_summary'])}, "
              f"player rows {r['player_rows']}, games with blanked players {len(r['blanked_players'])}", flush=True)
        # Summaries without linescores leave period_count NULL: take ESPN's status.period from the schedule
        # (also written into the raw JSON, where 2005-2025 consumers read it).
        filled = 0
        for eid, ev in evs.items():
            if ev["status"] == "STATUS_FINAL" and isinstance(ev["period"], int) and ev["period"] >= 2:
                filled += q("""update core_game set period_count=%s, went_to_ot=%s, updated_at=now(),
                                  raw_json=jsonb_set(raw_json, '{_raw,competitions,0,status,period}', to_jsonb(%s::int))
                               where source_game_id=%s and status='final' and period_count is null""",
                            [ev["period"], ev["period"] > 2, ev["period"], eid])
        print(f"    period_count from schedule status.period: {filled}", flush=True)
        call_command("sync_team_season_membership", season=y, stdout=open(os.devnull, "w"))
    validate(subset, seasons, reports)


def validate(subset, seasons, reports):
    print("validation")
    for tid, espn, name, ys in PROGRAMS:
        for y in ys:
            if subset and y not in subset.get(tid, []):
                continue
            sched = [e for e in seasons[y].values() if espn in (e["home"], e["away"])]
            r = reports[y]
            unresolved = {u["event"] for u in r["unresolved"]} | set(r["no_summary"])
            skipped = {s["event"] for s in r["skipped_same_pair"]}
            want = len([e for e in sched if e["id"] not in unresolved and e["id"] not in skipped])
            got = one("select count(*) from core_game where season_year=%s and %s in (home_team_id, away_team_id)", [y, tid])
            expect(f"{name} {y}: games stored = schedule ({len(sched)}) - unresolved/skipped", got, want)
    ids = [i for y in seasons for i in seasons[y]]
    expect("new final games without two box rows", one("""select count(*) from core_game g where g.source_game_id = any(%s)
        and g.status='final' and not (g.home_score=0 and g.away_score=0)
        and (select count(*) from core_teamgamestats t where t.game_id=g.id) <> 2""", [ids]), 0)
    expect("new final games with NULL period_count", one("""select count(*) from core_game g where g.source_game_id = any(%s)
        and g.status='final' and not (g.home_score=0 and g.away_score=0) and g.period_count is null""", [ids]), 0)
    expect("new games: a team with no membership row that season", one("""select count(*) from core_game g
        cross join lateral (values (g.home_team_id), (g.away_team_id)) x(tid) join core_season s on s.year=g.season_year
        where g.source_game_id = any(%s) and not exists (select 1 from core_teamseasonmembership m where m.season_id=s.id and m.team_id=x.tid)""",
        [ids]), 0)
    # period_count vs the schedule's status.period
    sp = {e["id"]: e["period"] for y in seasons for e in seasons[y].values()}
    rows = q("select source_game_id, period_count from core_game where source_game_id = any(%s) and period_count is not null", [ids])
    bad = [(i, p, sp.get(i)) for i, p in rows if sp.get(i) is not None and sp.get(i) >= 2 and sp.get(i) != p]
    expect("period_count = schedule status.period", bad, [])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sched-dir", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    sd = Path(a.sched_dir); sd.mkdir(parents=True, exist_ok=True)
    if not a.apply:
        try:
            with transaction.atomic():
                run(REHEARSAL, sd)
                raise Rollback()
        except Rollback:
            print("REHEARSAL OK (rolled back)")
        sys.exit(0)
    with transaction.atomic():
        run(None, sd)
    print("DONE")
