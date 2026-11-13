"""
Task 6h: close three data gaps (local macfax DB).

  python data_fixes/2026-11-12_task6h_data_gaps.py            # rehearsal: every step incl. the ESPN fetch, rolled back
  python data_fixes/2026-11-12_task6h_data_gaps.py --apply

Run from backend/. Each step asserts its expected counts and stops on a mismatch.

1. 2017 Eastern Washington (team 82): its 32 games have box rows (Task 6g) but no player rows ->
   sync_ncaa_player_gamelogs --season 2017 --teams 82 (ESPN summaries, >= 1.1 s apart).
2. 2026 period_count: NULL for 416 finished games. Only fix_ncaa_stint_data ever set it (from stints),
   and these 416 have no stints. Filled from ESPN scoreboard status.period, matched by ESPN team id and
   score, cross-checked against player minutes (200 + 25 per OT) where player rows exist:
   data_fixes/2026-11-12_task6h_period_counts.csv (game_id, espn_event, period_count).
   (The daily player sync now sets period_count for new games; see sync_ncaa_player_gamelogs.)
3. 2026 game dates. Convention: game_date is the Eastern date of the tip (= NCAA startDate; 6295 of
   6296 finished games). Against ESPN, 23 games looked a day late, but ESPN's header time for each is the
   04:59Z / 03:59Z (11:59 PM ET) late-game placeholder; ESPN's play-by-play wallclock puts every one of
   their tips on our date. The one real mismatch is game 8340, which Task 6g moved to 3/13 from that same
   placeholder: reverted to 3/14 with the wallclock tip (data_fixes/2026-11-12_task6h_game_dates.csv).
"""

import csv
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

APPLY = "--apply" in sys.argv
EWU = 82
PERIODS_CSV = HERE / "2026-11-12_task6h_period_counts.csv"
DATES_CSV = HERE / "2026-11-12_task6h_game_dates.csv"


class Rollback(Exception):
    pass


def q(sql, params=None):
    with connection.cursor() as c:
        c.execute(sql, params or [])
        return c.fetchall() if c.description else c.rowcount


def one(sql, params=None):
    return q(sql, params)[0][0]


def expect(label, got, want):
    print(f"  {label}: {got}" + ("" if got == want else f"  (EXPECTED {want})"))
    if got != want:
        raise SystemExit(f"assertion failed: {label}")


def ewu_players():
    print("1. Eastern Washington 2017 players")
    games = "select id from core_game where season_year=2017 and status='final' and %s in (home_team_id, away_team_id)"
    expect("games", one(f"select count(*) from ({games}) g", [EWU]), 32)
    expect("box rows", one(f"select count(*) from core_teamgamestats where game_id in ({games})", [EWU]), 64)
    expect("EWU player rows before", one(f"select count(*) from core_playergamestats where team_id=%s and game_id in ({games})", [EWU, EWU]), 0)
    call_command("sync_ncaa_player_gamelogs", season=2017, teams=str(EWU), sleep=1.1, workers=1)
    expect("games with EWU player rows after",
           one(f"select count(distinct game_id) from core_playergamestats where team_id=%s and game_id in ({games})", [EWU, EWU]), 32)


def period_counts():
    print("2. 2026 period_count from ESPN status.period")
    rows = list(csv.DictReader(open(PERIODS_CSV)))
    expect("CSV rows", len(rows), 416)
    expect("2026 finished games with NULL period_count", one("""select count(*) from core_game
        where season_year=2026 and status='final' and period_count is null"""), 416)
    ids = [int(r["game_id"]) for r in rows]
    expect("CSV games are exactly those", one("""select count(*) from core_game where id = any(%s)
        and season_year=2026 and status='final' and period_count is null""", [ids]), 416)
    n = 0
    for r in rows:
        p = int(r["period_count"])
        assert p >= 2, r
        n += q("update core_game set period_count=%s, went_to_ot=%s, updated_at=now() where id=%s and period_count is null",
               [p, p > 2, int(r["game_id"])])
    expect("games updated", n, 416)
    expect("2026 finished games with NULL period_count after", one("""select count(*) from core_game
        where season_year=2026 and status='final' and period_count is null"""), 0)


def game_dates():
    print("3. 2026 game dates (Eastern date of the tip, from ESPN)")
    rows = list(csv.DictReader(open(DATES_CSV)))
    print(f"  CSV rows: {len(rows)}")
    assert len(rows) <= 25, "more than 25 date corrections: stop (task rule)"
    n = 0
    for r in rows:
        expect(f"game {r['game_id']} stored date", one("select game_date::text from core_game where id=%s", [int(r["game_id"])]), r["old_date"])
        n += q("update core_game set game_date=%s, start_time_utc=coalesce(%s::timestamptz, start_time_utc), updated_at=now() "
               "where id=%s and game_date=%s", [r["new_date"], r.get("new_start_time_utc") or None, int(r["game_id"]), r["old_date"]])
    expect("games re-dated", n, len(rows))


if __name__ == "__main__":
    steps = [ewu_players, period_counts, game_dates]
    if not APPLY:
        try:
            with transaction.atomic():
                for s in steps:
                    s()
                raise Rollback()
        except Rollback:
            print("REHEARSAL OK (rolled back)")
        sys.exit(0)
    with transaction.atomic():
        for s in steps:
            s()
    print("DONE")
