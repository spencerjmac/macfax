"""
Task 8c.2: Houston Christian (team 115) was not D1 in 2007-08.

Wikipedia's 2008-09 season page lists Houston Baptist moving from "NAIA independent" to "NCAA Division I
Independent" for 2008-09, so its D1 transition began in 2008-09. Its 2008 membership row said D1 (and
reclassifying). This fix:
  1. sets the 2008 membership row to not D1 (is_reclassifying NULL, source manual),
  2. deletes its 2008 TeamSeasonRatings and TeamSeasonMetrics rows (pre and post; no other table holds a
     team 115 / 2008 row),
  3. reruns Task 6d's chain for 2008 only: the post-tournament commands, then the pre-tournament ones
     (POST / PRE imported from 2026-11-13_task6d_recompute_all.py).
Everything runs in one transaction; the default rehearsal rolls it all back.

  python data_fixes/2026-11-13_task8c2_hcu_2008.py [--apply]     (from backend/)
"""
import importlib.util, io, os, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.core.management import call_command  # noqa: E402
from django.db import connection, transaction  # noqa: E402

_spec = importlib.util.spec_from_file_location("task6d", Path(__file__).resolve().parent / "2026-11-13_task6d_recompute_all.py")
_task6d = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_task6d)
POST, PRE = _task6d.POST, _task6d.PRE

HCU, YEAR = 115, 2008
NOTE = ("8c.2: not D1 in 2007-08 (NAIA independent; Wikipedia 2008-09 season page: NAIA independent -> "
        "NCAA Division I Independent in 2008-09)")


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


def snapshot():
    return {(t, pre): (em, wab) for t, pre, em, wab in q("""select r.team_id, r.is_pre_tournament, r.adj_em, r.wab
        from core_teamseasonratings r join core_season s on s.id = r.season_id where s.year = %s""", [YEAR])}


def counts():
    return q("""select (select count(*) from core_teamseasonmembership m join core_season s on s.id = m.season_id
                        where s.year = %(y)s and m.is_d1),
                       (select count(*) from core_teamseasonratings r join core_season s on s.id = r.season_id
                        where s.year = %(y)s and not r.is_pre_tournament),
                       (select count(*) from core_teamseasonratings r join core_season s on s.id = r.season_id
                        where s.year = %(y)s and r.is_pre_tournament),
                       (select count(*) from core_teamseasonmetrics m join core_season s on s.id = m.season_id
                        where s.year = %(y)s and not m.is_pre_tournament),
                       (select count(*) from core_teamseasonmetrics m join core_season s on s.id = m.season_id
                        where s.year = %(y)s and m.is_pre_tournament)""", {"y": YEAR})[0]


def run():
    expect("membership before (is_d1, is_reclassifying)", q("""select m.is_d1, m.is_reclassifying from core_teamseasonmembership m
        join core_season s on s.id = m.season_id where s.year = %s and m.team_id = %s""", [YEAR, HCU]), [(True, True)])
    expect("counts before (D1, TSR post, TSR pre, TSM post, TSM pre)", counts(), (342, 342, 342, 342, 342))
    # conferences survive the recompute (compute_team_metrics keeps stored values); record them
    conf_before = q("""select md5(string_agg(m.team_id || ':' || m.is_pre_tournament || ':' || m.conference_id, ','
        order by m.team_id, m.is_pre_tournament)) from core_teamseasonmetrics m join core_season s on s.id = m.season_id
        where s.year = %s and m.team_id <> %s""", [YEAR, HCU])[0][0]
    seeds_before = q("""select r.team_id, r.is_pre_tournament, r.tournament_seed, r.tournament_finish, r.ap_poll_week6
        from core_teamseasonratings r join core_season s on s.id = r.season_id
        where s.year = %s and (r.tournament_seed is not null or r.ap_poll_week6 is not null) order by 1, 2""", [YEAR])
    before = snapshot()

    expect("membership rows updated", q("""update core_teamseasonmembership m set is_d1 = false, is_reclassifying = null,
        source = 'manual', note = %s, updated_at = now() from core_season s
        where s.id = m.season_id and s.year = %s and m.team_id = %s""", [NOTE, YEAR, HCU]), 1)
    expect("rating rows deleted", q("""delete from core_teamseasonratings r using core_season s
        where s.id = r.season_id and s.year = %s and r.team_id = %s""", [YEAR, HCU]), 2)
    expect("metrics rows deleted", q("""delete from core_teamseasonmetrics m using core_season s
        where s.id = m.season_id and s.year = %s and m.team_id = %s""", [YEAR, HCU]), 2)

    for phase, cmds in (("post", POST), ("pre", PRE)):
        for cmd in cmds:
            kw = {"season": YEAR, **({"pre_tournament": True} if phase == "pre" else {})}
            call_command(cmd, stdout=io.StringIO(), stderr=io.StringIO(), **kw)
            print(f"    ran {phase} {cmd}")

    expect("counts after (D1, TSR post, TSR pre, TSM post, TSM pre)", counts(), (341, 341, 341, 341, 341))
    expect("Houston Christian 2008 rating/metrics rows", q("""select (select count(*) from core_teamseasonratings r join core_season s
        on s.id = r.season_id where s.year = %(y)s and r.team_id = %(t)s) + (select count(*) from core_teamseasonmetrics m
        join core_season s on s.id = m.season_id where s.year = %(y)s and m.team_id = %(t)s)""", {"y": YEAR, "t": HCU})[0][0], 0)
    expect("rated teams that aren't D1 in 2008 / D1 teams without a rating", q("""select
        (select count(*) from core_teamseasonratings r join core_season s on s.id = r.season_id where s.year = %(y)s
           and not exists (select 1 from core_teamseasonmembership m where m.team_id = r.team_id and m.season_id = r.season_id and m.is_d1)),
        (select count(*) from core_teamseasonmembership m join core_season s on s.id = m.season_id where s.year = %(y)s and m.is_d1
           and not exists (select 1 from core_teamseasonratings r where r.team_id = m.team_id and r.season_id = m.season_id
                           and r.is_pre_tournament))""", {"y": YEAR})[0], (0, 0))
    expect("conferences unchanged", q("""select md5(string_agg(m.team_id || ':' || m.is_pre_tournament || ':' || m.conference_id, ','
        order by m.team_id, m.is_pre_tournament)) from core_teamseasonmetrics m join core_season s on s.id = m.season_id
        where s.year = %s""", [YEAR])[0][0], conf_before)
    expect(f"seeds, finishes and AP ranks unchanged ({len(seeds_before)} rating rows)", q("""select r.team_id, r.is_pre_tournament,
        r.tournament_seed, r.tournament_finish, r.ap_poll_week6 from core_teamseasonratings r join core_season s on s.id = r.season_id
        where s.year = %s and (r.tournament_seed is not null or r.ap_poll_week6 is not null) order by 1, 2""", [YEAR]) == seeds_before, True)

    after = snapshot()
    names = dict(q("select id, name from core_team"))
    for pre in (False, True):
        keys = [k for k in after if k[1] == pre]
        for i, label in ((0, "AdjEM"), (1, "WAB")):
            d = {k[0]: after[k][i] - before[k][i] for k in keys if after[k][i] is not None and before[k][i] is not None}
            top = sorted(d.items(), key=lambda kv: -abs(kv[1]))[:3]
            print(f"  2008 {'pre ' if pre else 'post'} {label} change, other teams (n={len(d)}): max |d| {max(abs(v) for v in d.values()):.3f}, "
                  f"mean |d| {statistics.mean(abs(v) for v in d.values()):.3f}, mean d {statistics.mean(d.values()):+.3f}; "
                  f"top {[(names[t], round(v, 3)) for t, v in top]}")


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
