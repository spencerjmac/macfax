"""
Task 6d step 4: tournament seeds for team-seasons that got rating rows only in this recompute.
Boston College 2005, 2006, 2007, 2009 (its games were under Boston University until 6c) and Hartford 2021 (no
Team row until 6f.1). backfill_tournament re-read for those seasons (Wikipedia, one page per season, >= 1 s
apart; resolves teams by that season's D1 membership since Task 6d). sync_tournament_seeds does not exist;
backfill_tournament writes the pre and post rating rows together.

  python data_fixes/2026-11-13_task6d_seed_backfill.py [--apply]     (from backend/; default: rehearsal)
"""
import io, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.core.management import call_command  # noqa: E402
from django.db import connection, transaction  # noqa: E402

SEASONS = [2005, 2006, 2007, 2009, 2021]


class Rollback(Exception):
    pass


def q(sql, p=None):
    with connection.cursor() as c:
        c.execute(sql, p or []); return c.fetchall()


def expect(label, got, want):
    print(f"  {label}: {got}" + ("" if got == want else f"  (EXPECTED {want})"))
    if got != want:
        raise SystemExit(f"assertion failed: {label}")


def seeded():
    return {(y, pre): n for y, pre, n in q("""select s.year, r.is_pre_tournament, count(*) from core_teamseasonratings r
        join core_season s on s.id = r.season_id where r.tournament_seed is not null group by 1, 2""")}


def run():
    before = seeded()
    for y in SEASONS:
        out = io.StringIO()
        call_command("backfill_tournament", season=y, stdout=out, stderr=out)
        unmatched = [ln for ln in out.getvalue().splitlines() if "UNMATCHED" in ln]
        print(f"  {y}: {before.get((y, False))} -> {seeded().get((y, False))} seeded (post); unmatched: {unmatched}")
    after = seeded()
    want = {y: (65 if y <= 2010 else 68) for y in range(2005, 2027) if y != 2020}
    expect("seeded teams per season (post, pre)", {y: (after.get((y, False)), after.get((y, True))) for y in want},
           {y: (n, n) for y, n in want.items()})
    expect("Boston College seeds 2005/2006/2007/2009", [r[0] for r in q("""select r.tournament_seed is not null from core_teamseasonratings r
        join core_season s on s.id = r.season_id where r.team_id = 27 and s.year in (2005, 2006, 2007, 2009) and not r.is_pre_tournament
        order by s.year""")], [True] * 4)
    expect("Hartford 2021 seed (pre, post)", q("""select r.is_pre_tournament, r.tournament_seed from core_teamseasonratings r
        join core_season s on s.id = r.season_id where r.team_id = 824 and s.year = 2021 order by 1"""), [(False, 16), (True, 16)])
    expect("Boston University 2011 seed (pre, post)", q("""select r.is_pre_tournament, r.tournament_seed from core_teamseasonratings r
        join core_season s on s.id = r.season_id where r.team_id = 28 and s.year = 2011 order by 1"""), [(False, 16), (True, 16)])
    print("  Boston College seeds:", q("""select s.year, r.tournament_seed from core_teamseasonratings r join core_season s on s.id = r.season_id
        where r.team_id = 27 and not r.is_pre_tournament and r.tournament_seed is not null order by 1"""))


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
