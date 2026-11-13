"""
Task 6f.3b follow-up: LIU 109 - College of New Rochelle 76 (2018-11-07, ESPN 401088457), on LIU's ESPN 112358 2019
schedule but not stored: its opponent (ESPN 111171) had no team until 2026-11-13_task6f3b_liu_firstfour_nond1.py
created it. With it, LIU's stored 2019 games equal ESPN's 112358 + 6446 schedules (32).

  python data_fixes/2026-11-13_task6f3b_b_liu_new_rochelle.py [--apply]     (from backend/; default: rehearsal)
"""
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.core.management import call_command  # noqa: E402
from django.db import connection, transaction  # noqa: E402

EVENT = "401088457"


class Rollback(Exception):
    pass


def one(sql, p=None):
    with connection.cursor() as c:
        c.execute(sql, p or []); return c.fetchone()[0]


def expect(label, got, want):
    print(f"  {label}: {got}" + ("" if got == want else f"  (EXPECTED {want})"))
    if got != want:
        raise SystemExit(f"assertion failed: {label}")


def run():
    expect("LIU 2019 games before", one("select count(*) from core_game where season_year=2019 and 138 in (home_team_id, away_team_id)"), 31)
    expect("event stored", one("select count(*) from core_game where source_game_id=%s", [EVENT]), 0)
    with tempfile.TemporaryDirectory() as d:
        rep = Path(d) / "r.json"
        call_command("ingest_gamelogs", season=2019, source="espn", espn_event_ids=EVENT, report=str(rep), stdout=open(os.devnull, "w"))
        r = json.loads(rep.read_text())
    expect("created", r["created"], [EVENT])
    call_command("sync_team_season_membership", season=2019, stdout=open(os.devnull, "w"))
    expect("LIU 2019 games after", one("select count(*) from core_game where season_year=2019 and 138 in (home_team_id, away_team_id)"), 32)
    expect("box rows", one("select count(*) from core_teamgamestats t join core_game g on g.id=t.game_id where g.source_game_id=%s", [EVENT]), 2)
    expect("period_count", one("select period_count from core_game where source_game_id=%s", [EVENT]), 2)


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
