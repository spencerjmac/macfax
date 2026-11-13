"""
Task 6f.3 follow-up: 19 events the first run skipped as "same pair within a day" but which are different
games (2021 two-game series on consecutive days, LIU-St. Francis Brooklyn 2010, Hartford-Stony Brook 2022;
two are the second game of a postponed or canceled series). The duplicate check now needs the same pair
tipping < 12 h apart (ingest_gamelogs._ingest_espn_events).

  python data_fixes/2026-11-13_task6f3_b_series_games.py            # rehearsal (rolled back)
  python data_fixes/2026-11-13_task6f3_b_series_games.py --apply
"""

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import connection, transaction  # noqa: E402

APPLY = "--apply" in sys.argv
EVENTS = {  # season -> ESPN event ids (each paired by the first run with a different game of the same teams)
    2010: ["300382341"],
    2021: ["401256947", "401256956", "401256965", "401256974", "401256984", "401262131", "401262181", "401262190",
           "401262199", "401262227", "401262235", "401262243", "401262250", "401279838", "401281397", "401281405",
           "401283717"],
    2022: ["401402152"],
}


class Rollback(Exception):
    pass


def one(sql, params=None):
    with connection.cursor() as c:
        c.execute(sql, params or [])
        return c.fetchone()[0]


def expect(label, got, want):
    print(f"  {label}: {got}" + ("" if got == want else f"  (EXPECTED {want})"), flush=True)
    if got != want:
        raise SystemExit(f"assertion failed: {label}")


def run():
    ids = [i for v in EVENTS.values() for i in v]
    expect("events", len(ids), 19)
    expect("already stored", one("select count(*) from core_game where source_game_id = any(%s)", [ids]), 0)
    for y, evs in EVENTS.items():
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "ids.txt"; f.write_text("\n".join(evs)); rep = Path(d) / "r.json"
            call_command("ingest_gamelogs", season=y, source="espn", espn_event_file=str(f), report=str(rep),
                         stdout=open(os.devnull, "w"))
            r = json.loads(rep.read_text())
        expect(f"{y}: created", (len(r["created"]), r["skipped_same_pair"], r["unresolved"], r["no_summary"]), (len(evs), [], [], []))
        call_command("sync_team_season_membership", season=y, stdout=open(os.devnull, "w"))
    expect("stored", one("select count(*) from core_game where source_game_id = any(%s)", [ids]), 19)
    expect("played games without two box rows", one("""select count(*) from core_game g where g.source_game_id = any(%s)
        and g.status='final' and not (g.home_score=0 and g.away_score=0)
        and (select count(*) from core_teamgamestats t where t.game_id=g.id) <> 2""", [ids]), 0)
    expect("played games with NULL period_count", one("""select count(*) from core_game g where g.source_game_id = any(%s)
        and g.status='final' and not (g.home_score=0 and g.away_score=0) and g.period_count is null""", [ids]), 0)


if __name__ == "__main__":
    if not APPLY:
        try:
            with transaction.atomic():
                run()
                raise Rollback()
        except Rollback:
            print("REHEARSAL OK (rolled back)")
        sys.exit(0)
    with transaction.atomic():
        run()
    print("DONE")
