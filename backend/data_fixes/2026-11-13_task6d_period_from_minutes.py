"""
Task 6d step 1: three games whose ESPN status.period disagrees with both teams' player minutes (left in 6h.2):
  79100 (2018) raw 2 periods, both teams 225 min -> 3 periods (1 OT)
  93516 (2020) raw 4 periods, both teams 300 min -> 6 periods (4 OT)
  96839 (2021) raw 2 periods, both teams 225 min -> 3 periods (1 OT)
Same rule 6h.2 applied to 31 2018 games: when both teams' minutes agree and close on 200 + 25 per OT, they win.

  python data_fixes/2026-11-13_task6d_period_from_minutes.py [--apply]     (from backend/; default: rehearsal)
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.db import connection, transaction  # noqa: E402

FIX = {79100: (2, 3), 93516: (4, 6), 96839: (2, 3)}   # game id -> (stored period_count, from minutes)


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
    for gid, (old, new) in FIX.items():
        mins = [round(m) for (m,) in q("select sum(minutes) from core_playergamestats where game_id=%s group by team_id order by team_id", [gid])]
        expect(f"game {gid}: both teams' minutes", mins, [200 + 25 * (new - 2)] * 2)
        expect(f"game {gid}: stored period_count", q("select period_count from core_game where id=%s", [gid]), [(old,)])
        expect(f"game {gid}: updated", q("update core_game set period_count=%s, went_to_ot=true, updated_at=now() where id=%s and period_count=%s",
                                         [new, gid, old]), 1)


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
