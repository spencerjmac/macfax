"""
Task 6f.3b (local macfax DB). Run from backend/:
  python data_fixes/2026-11-13_task6f3b_liu_firstfour_nond1.py --sched-dir DIR            # rehearsal (rolled back)
  python data_fixes/2026-11-13_task6f3b_liu_firstfour_nond1.py --sched-dir DIR --apply

1. LIU Brooklyn under ESPN 6446 -> LIU (team 138), as an ESPN-id override (mappings/team_alias_overrides.yml;
   TeamExternalId holds 112358). ESPN's 6446 schedules 2012-2019 hold 39 events: LIU's early-season tournament
   (MTE) games, NEC-tournament games and the 2018 First Four. 8 (2012-13) are the same games as stored LIU games
   (same opponent, tip and score) and 1 (2017-12-05 Stony Brook) is already stored: ingest skips them. No 6446
   game falls within 12 h of a different stored LIU game. 313240261 is left out (see EXCLUDE). 29 games added.
2. NCAA First Four games outcome.py patches by hand: 2017 New Orleans-Mount St. Mary's (ESPN 400946453),
   Wake Forest-Kansas St. (400946444); 2018 Radford-LIU (401025856, a 6446 event).
3. The 33 non-D1 opponents left unresolved in Task 6f.3 (63 games): a non-D1 Team per ESPN id named with ESPN's
   school name (location; displayName kept as alias), a TeamExternalId row, a not-D1 membership row per season
   played. Never merged: names that equal an existing team's are listed for review
   (data_fixes/2026-11-13_task6f3b_nond1_opponents.json holds ESPN's records and the 63 events).
"""

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import connection, transaction  # noqa: E402
from django.utils.text import slugify  # noqa: E402

NOND1 = HERE / "2026-11-13_task6f3b_nond1_opponents.json"
FIRST_FOUR = {2017: ["400946453", "400946444"], 2018: ["401025856"]}
# ESPN 6446 events left out: ESPN's record of 313240261 (Vermont-LIU, 2011-11-20, Hall of Fame Tip-Off) holds one
# period scored 33-39, i.e. the first half only; storing it would store a wrong final score.
EXCLUDE = {"313240261"}
PROGRAMS = [(824, "42", range(2005, 2024)), (825, "2597", range(2005, 2024)), (826, "2542", range(2005, 2020)),
            (827, "2736", range(2007, 2011)), (281, "88", range(2023, 2026)), (828, "3", range(2005, 2007))]
SCHED_6F3 = Path("/home/spencer/Workspace/cb_scratch/6f3/sched")   # Task 6f.3's cached ESPN schedules


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


def liu_counts(sched_dir):
    out = {}
    for y in range(2005, 2020):
        a = json.loads((sched_dir / f"sched_112358_{y}.json").read_text())
        b = json.loads((sched_dir / f"sched_6446_{y}.json").read_text())
        out[y] = (len(a), len(b), one("select count(*) from core_game where season_year=%s and 138 in (home_team_id, away_team_id)", [y]))
    return out


def create_nond1(teams):
    print("3a. non-D1 opponents: teams, ESPN rows, membership")
    ids = list(teams)
    expect("ESPN ids unmapped", one("select count(*) from core_teamexternalid where source='espn' and external_id = any(%s)", [ids]), 0)
    seasons = dict(q("select year, id from core_season"))
    clashes, created = [], {}
    for eid, t in sorted(teams.items(), key=lambda kv: int(kv[0])):
        name = t["location"]
        same = q("select id from core_team where name=%s", [name])
        if same:
            clashes.append((eid, name, [r[0] for r in same]))
        slug = slugify(name)
        if one("select count(*) from core_team where slug=%s", [slug]):
            slug = f"{slug}-espn-{eid}"
        tid = one("""insert into core_team (slug, name, aliases, is_d1, created_at) values (%s, %s, %s::jsonb, false, now()) returning id""",
                  [slug, name, json.dumps([t["displayName"]])])
        q("""insert into core_teamexternalid (source, external_id, external_name, confidence, is_manual_override, created_at, updated_at, team_id)
             values ('espn', %s, %s, 1.0, true, now(), now(), %s)""", [eid, t["displayName"], tid])
        for y in sorted({g[0] for g in t["games"]}):
            q("""insert into core_teamseasonmembership (season_id, team_id, is_d1, is_reclassifying, source, note, created_at, updated_at)
                 values (%s, %s, false, null, 'manual', 'non-D1 opponent (Task 6f.3b); ESPN id ' || %s, now(), now())""", [seasons[y], tid, eid])
        created[eid] = tid
    expect("teams created", len(created), 33)
    print("  new teams whose name equals an existing team's (review later):", clashes)
    return created, clashes


def ingest(season_events, sched_dir, tag):
    reports = {}
    for y, evs in sorted(season_events.items()):
        f = sched_dir / f"ids_{tag}_{y}.txt"; f.write_text("\n".join(sorted(set(evs))))
        rep = sched_dir / f"report_{tag}_{y}.json"
        call_command("ingest_gamelogs", season=y, source="espn", espn_event_file=str(f), report=str(rep), stdout=open(os.devnull, "w"))
        reports[y] = json.loads(rep.read_text())
        r = reports[y]
        print(f"  {tag} {y}: {len(set(evs))} events -> created {len(r['created'])}, existing {len(r['skipped_existing'])}, "
              f"same pair {len(r['skipped_same_pair'])}, unresolved {len(r['unresolved'])}, no summary {len(r['no_summary'])}", flush=True)
        call_command("sync_team_season_membership", season=y, stdout=open(os.devnull, "w"))
    return reports


def run(sched_dir):
    before = liu_counts(sched_dir)
    print("1. LIU (138) via ESPN 6446 override")
    from ncaa.management.commands.sync_team_season_membership import espn_team_map
    expect("override 6446 -> LIU", espn_team_map().get("6446"), 138)
    liu_events = {y: [e["id"] for e in json.loads((sched_dir / f"sched_6446_{y}.json").read_text()) if e["id"] not in EXCLUDE]
                  for y in range(2012, 2020)}
    r1 = ingest(liu_events, sched_dir, "liu")
    n1 = sum(len(r["created"]) for r in r1.values())
    expect("LIU games created", n1, 29)
    expect("LIU unresolved / no summary", sum(len(r["unresolved"]) + len(r["no_summary"]) for r in r1.values()), 0)
    expect("LIU skipped as the same game (8 in 2012-13) / already stored (1)",
           (sum(len(r["skipped_same_pair"]) for r in r1.values()), sum(len(r["skipped_existing"]) for r in r1.values())), (8, 1))
    after = liu_counts(sched_dir)
    print("  LIU per season (112358 schedule, 6446 schedule, stored before -> after):")
    for y in range(2005, 2020):
        print(f"    {y}: {before[y][0]}, {before[y][1]}, {before[y][2]} -> {after[y][2]}")

    print("2. First Four")
    r2 = ingest({2017: FIRST_FOUR[2017]}, sched_dir, "firstfour")
    expect("2017 First Four created", len(r2[2017]["created"]), 2)
    ff = [i for v in FIRST_FOUR.values() for i in v]
    expect("First Four games present, two box rows each", q("""select g.source_game_id, (select count(*) from core_teamgamestats t where t.game_id=g.id)
        from core_game g where g.source_game_id = any(%s) order by 1""", [ff]), [(i, 2) for i in sorted(ff)])

    teams = json.loads(NOND1.read_text())
    create_nond1(teams)
    print("3b. the 63 games")
    ev3 = {}
    for t in teams.values():
        for y, eid in t["games"]:
            ev3.setdefault(y, []).append(eid)
    expect("events", sum(len(v) for v in ev3.values()), 63)
    r3 = ingest(ev3, sched_dir, "nond1")
    expect("non-D1 games created", sum(len(r["created"]) for r in r3.values()), 63)

    # Summaries without linescores leave period_count NULL: take ESPN's status.period from the cached schedules
    # (6446's here, Task 6f.3's for the non-D1 games), also written into the raw JSON (as in 6f.3).
    sp = {}
    for f in list(sched_dir.glob("sched_*.json")) + list(SCHED_6F3.glob("sched_*.json")):
        for e in json.loads(f.read_text()):
            if e["status"] == "STATUS_FINAL" and isinstance(e["period"], int) and e["period"] >= 2:
                sp[e["id"]] = e["period"]
    filled = 0
    for (sid,) in q("""select source_game_id from core_game where source_game_id = any(%s) and status='final'
                       and period_count is null""", [[e for r in (r1, r2, r3) for y in r for e in r[y]["created"]]]):
        if sid in sp:
            filled += q("""update core_game set period_count=%s, went_to_ot=%s, updated_at=now(),
                              raw_json=jsonb_set(raw_json, '{_raw,competitions,0,status,period}', to_jsonb(%s::int))
                           where source_game_id=%s""", [sp[sid], sp[sid] > 2, sp[sid], sid])
    print(f"  period_count from schedule status.period: {filled}")

    print("validation")
    for tid, espn, ys in PROGRAMS:
        for y in ys:
            sched = json.loads((SCHED_6F3 / f"sched_{espn}_{y}.json").read_text())
            got = one("select count(*) from core_game where season_year=%s and %s in (home_team_id, away_team_id)", [y, tid])
            expect(f"team {tid} {y}: stored = ESPN schedule", got, len(sched))
    new = [e for r in (r1, r2, r3) for y in r for e in r[y]["created"]]
    expect("new played games without two box rows", one("""select count(*) from core_game g where g.source_game_id = any(%s)
        and g.status='final' and not (g.home_score=0 and g.away_score=0)
        and (select count(*) from core_teamgamestats t where t.game_id=g.id) <> 2""", [new]), 0)
    expect("new played games with NULL period_count", q("""select g.source_game_id, g.season_year, g.home_score, g.away_score,
        g.raw_json->'_raw'->'competitions'->0->'status' from core_game g where g.source_game_id = any(%s)
        and g.status='final' and not (g.home_score=0 and g.away_score=0) and g.period_count is null""", [new]), [])
    expect("teams in new games without a membership row", one("""select count(*) from core_game g
        cross join lateral (values (g.home_team_id), (g.away_team_id)) x(tid) join core_season s on s.year=g.season_year
        where g.source_game_id = any(%s) and not exists (select 1 from core_teamseasonmembership m where m.season_id=s.id and m.team_id=x.tid)""",
        [new]), 0)
    print(f"  games added: LIU {n1}, First Four 2017 {len(r2[2017]['created'])} (2018 via LIU), non-D1 opponents {sum(len(r['created']) for r in r3.values())}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--sched-dir", required=True); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(); sd = Path(a.sched_dir)
    if not a.apply:
        try:
            with transaction.atomic():
                run(sd)
                raise Rollback()
        except Rollback:
            print("REHEARSAL OK (rolled back)")
        sys.exit(0)
    with transaction.atomic():
        run(sd)
    print("DONE")
