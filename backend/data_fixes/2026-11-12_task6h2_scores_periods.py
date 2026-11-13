"""
Task 6h.2 (local macfax DB). Run from backend/:
  python data_fixes/2026-11-12_task6h2_scores_periods.py            # rehearsal: every step, rolled back
  python data_fixes/2026-11-12_task6h2_scores_periods.py --apply

1. Wrong 2026 scores (NCAA feed vs ESPN). Corrected only with a second record:
   - 8198 CUSA 1st round, Missouri St. (home in our record) vs FIU: we store Missouri St. 72-75 (loss).
     Second record: Missouri St. played the next CUSA round (quarterfinal vs Liberty, our game 8234 on
     2026-03-11, and ESPN 401851407); FIU played no further game. ESPN 401851405: Missouri St. 75, FIU 72.
     Our two box rows hold exactly ESPN's two stat lines but on the wrong teams (our "Missouri St." row is
     26-55 FG, 3-14 3PT, 17-27 FT, 38 reb = ESPN's FIU line). Fix: scores 75-72, and the two box rows
     swap team/opponent so each team carries its own line and points; our home/away is kept (ESPN marks
     the game neutral, Propst Arena).
   - 5781, 5852, 5858: our stored box shooting (2 FGM + 3PM + FTM) gives the NCAA score, not ESPN's, and
     ncaa.com's own player box was not retrieved, so no second record: unchanged.
2. 2026: 48 stint-derived period_count values set to ESPN's scoreboard status.period (player minutes agree
   with ESPN in all 48): 2026-11-12_task6h2_2026_period_corrections.csv.
3. 2005-2025 period_count / went_to_ot. TeamGameStats.minutes is NULL everywhere, so
   TeamGameStats.game_minutes = 45 if went_to_ot else 40, which compute_national_averages and
   compute_ncaa_player_season_stats read. Set from ESPN raw status.period (NULL when < 2: canceled,
   postponed, forfeit, uncontested, suspended), except 31 2018 games where ESPN's period is 2 too high and
   both teams' player minutes show it (29 regulation games with period 4, one 1-OT game with 5, one 2-OT
   game with 6): 2026-11-12_task6h2_2018_period_exceptions.csv. went_to_ot = period_count > 2.
4. The finished 2027 game with player rows and NULL period_count: filled by the daily player sync, whose
   --skip-done now re-fetches such games (sync_ncaa_player_gamelogs --season 2027 --skip-done).
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
CORR_2026 = HERE / "2026-11-12_task6h2_2026_period_corrections.csv"
EXC_2018 = HERE / "2026-11-12_task6h2_2018_period_exceptions.csv"
RAW_P = "(case when g.raw_json->'_raw'->'competitions'->0->'status'->>'period' ~ '^\\d+$' " \
        "then (g.raw_json->'_raw'->'competitions'->0->'status'->>'period')::int end)"



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


def scores():
    print("1. game 8198 (CUSA 1st round): Missouri St. 75, FIU 72")
    fiu = one("select id from core_team where name='FIU'")
    expect("8198 as stored (home Missouri St. 182, away FIU)",
           q("select home_team_id, away_team_id, home_score, away_score from core_game where id=8198"), [(182, fiu, 72, 75)])
    rows = q("""select id, team_id, opponent_id, home_away, pts, fgm, fga, fg3m, fg3a, ftm, fta, reb
                from core_teamgamestats where game_id=8198 order by id""")
    expect("8198 box rows", rows, [(13851, 182, fiu, "H", 72, 26, 55, 3, 14, 17, 27, 38),
                                   (13854, fiu, 182, "A", 75, 26, 49, 11, 26, 12, 22, 27)])
    expect("next CUSA round: Missouri St. in game 8234 (QF vs Liberty)",
           q("select game_date::text, away_team_id from core_game where id=8234"), [("2026-03-11", 182)])
    expect("FIU games after 2026-03-10", one("""select count(*) from core_game where season_year=2026 and game_date > '2026-03-10'
        and %s in (home_team_id, away_team_id)""", [fiu]), 0)
    q("update core_game set home_score=75, away_score=72, updated_at=now() where id=8198")
    # (game_id, team_id) is unique and not deferrable: park row 13851 on Georgia College (714, not in this
    # game) for the swap; all inside this transaction.
    q("update core_teamgamestats set team_id=714 where id=13851 and game_id=8198")
    q("update core_teamgamestats set team_id=182, opponent_id=%s, home_away='H', updated_at=now() where id=13854", [fiu])
    q("update core_teamgamestats set team_id=%s, opponent_id=182, home_away='A', updated_at=now() where id=13851", [fiu])
    expect("8198 after (team, pts, FG, 3PT, FT)", q("""select team_id, home_away, pts, fgm||'-'||fga, fg3m||'-'||fg3a, ftm||'-'||fta
        from core_teamgamestats where game_id=8198 order by home_away desc"""),
           [(182, "H", 75, "26-49", "11-26", "12-22"), (fiu, "A", 72, "26-55", "3-14", "17-27")])
    expect("player points = score (Missouri St., FIU)", q("""select (select sum(points) from core_playergamestats where game_id=8198 and team_id=182),
        (select sum(points) from core_playergamestats where game_id=8198 and team_id=%s)""", [fiu]), [(75, 72)])


def periods_2026():
    print("2. 2026: 48 stint-derived period_count values -> ESPN")
    rows = list(csv.DictReader(open(CORR_2026)))
    expect("CSV rows", len(rows), 48)
    n = 0
    for r in rows:
        n += q("update core_game set period_count=%s, went_to_ot=%s, updated_at=now() where id=%s and season_year=2026 and period_count=%s",
               [int(r["period_count"]), int(r["period_count"]) > 2, int(r["game_id"]), int(r["old_period_count"])])
    expect("games updated", n, 48)


def periods_2005_2025():
    print("3. 2005-2025: period_count / went_to_ot from ESPN raw status.period (+ 31 2018 exceptions)")
    exc = {int(r["game_id"]): int(r["period_count"]) for r in csv.DictReader(open(EXC_2018))}
    expect("2018 exceptions", (len(exc), sorted(set(exc.values()))), (31, [2, 3, 4]))
    expect("exceptions are 2018 games with raw period = new + 2", one(f"""select count(*) from core_game g
        join unnest(%s::bigint[], %s::int[]) e(id, p) on e.id = g.id where g.season_year=2018 and {RAW_P} = e.p + 2""",
        [list(exc), list(exc.values())]), 31)
    q(f"""create temp table want on commit drop as
          select g.id, g.season_year yr, g.period_count old_pc, g.went_to_ot old_ot,
                 coalesce(e.p, case when {RAW_P} >= 2 then {RAW_P} end) new_pc
          from core_game g left join unnest(%s::bigint[], %s::int[]) e(id, p) on e.id = g.id
          where g.season_year between 2005 and 2025""", [list(exc), list(exc.values())])
    q("alter table want add column new_ot boolean")
    q("update want set new_ot = coalesce(new_pc > 2, false)")
    per = q("""select yr, count(*) filter (where old_pc is distinct from new_pc) pc_changes,
                      count(*) filter (where old_ot is distinct from new_ot) ot_changes,
                      count(*) filter (where old_pc is distinct from new_pc or old_ot is distinct from new_ot) changed,
                      count(*) filter (where new_pc is null) null_after
               from want group by 1 order by 1""")
    print("  season | period_count changes | went_to_ot changes | games changed | NULL after")
    for yr, a, b, c, d in per:
        print(f"  {yr} | {a} | {b} | {c} | {d}")
    n = q("""update core_game g set period_count = w.new_pc, went_to_ot = w.new_ot, updated_at = now() from want w
             where w.id = g.id and (g.period_count is distinct from w.new_pc or g.went_to_ot is distinct from w.new_ot)""")
    expect("games updated", n, sum(r[3] for r in per))
    expect("2005-2025 rows still differing", one("""select count(*) from core_game g join want w on w.id=g.id
        where g.period_count is distinct from w.new_pc or g.went_to_ot is distinct from w.new_ot"""), 0)


def periods_2027():
    print("4. 2027: finished games with NULL period_count")
    expect("before", one("select count(*) from core_game where season_year=2027 and status='final' and period_count is null"), 1)
    call_command("sync_ncaa_player_gamelogs", season=2027, skip_done=True, sleep=1.1, workers=1)
    expect("after", one("select count(*) from core_game where season_year=2027 and status='final' and period_count is null"), 0)


if __name__ == "__main__":
    steps = [scores, periods_2026, periods_2005_2025, periods_2027]
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
