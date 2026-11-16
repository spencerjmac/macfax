"""
Task 11: trial run of the 2005-2014 player backfill. sync_ncaa_player_gamelogs on the first 100 D1-vs-D1 games of
2014 (by date), one ESPN request per second:

  sync_ncaa_player_gamelogs --season 2014 --d1-vs-d1 --limit 100 --workers 1 --sleep 1.0

Asserts: the 100 games are D1 vs D1, not 0-0, and had no player rows; only those games gain PlayerGameStats rows;
nothing else in PlayerGameStats changes. Reports request rate, seconds per game, failures, blanked entries, minutes
closure (|team minutes - (200 + 25 per OT)| <= 5) and player points vs the team score.

  python data_fixes/2026-11-16_task11_player_backfill_2014_sample.py [--apply]   (from backend/; default: rehearsal)
"""
import io, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.core.management import call_command  # noqa: E402
from django.db import connection, transaction  # noqa: E402

from ncaa.management.commands.sync_ncaa_player_gamelogs import select_games  # noqa: E402

SEASON, LIMIT = 2014, 100


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


def run():
    games = [g.id for g in select_games(SEASON, d1_vs_d1=True)[:LIMIT]]
    expect("games selected", len(games), LIMIT)
    expect("selected games D1 vs D1, not 0-0, final", q("""select count(*) from core_game g join core_season s on s.year = g.season_year
        join core_teamseasonmembership mh on mh.team_id = g.home_team_id and mh.season_id = s.id and mh.is_d1
        join core_teamseasonmembership ma on ma.team_id = g.away_team_id and ma.season_id = s.id and ma.is_d1
        where g.id = any(%s) and g.status = 'final' and not (g.home_score = 0 and g.away_score = 0)""", [games])[0][0], LIMIT)
    expect("player rows in those games before", q("select count(*) from core_playergamestats where game_id = any(%s)", [games])[0][0], 0)
    other = lambda: q("""select count(*), md5(string_agg(id || ':' || coalesce(minutes, -1) || ':' || points || ':' ||
        coalesce(team_id, 0), ',' order by id)) from core_playergamestats where not (game_id = any(%s))""", [games])[0]
    other_before = other()
    players_before = q("select count(*) from core_player")[0][0]

    out = io.StringIO(); t0 = time.time()
    call_command("sync_ncaa_player_gamelogs", season=SEASON, d1_vs_d1=True, limit=LIMIT, workers=1, sleep=1.0,
                 stdout=out, stderr=out)
    secs = time.time() - t0
    print("  command output:\n    " + "\n    ".join(ln for ln in out.getvalue().splitlines() if ln.strip()))
    expect("other PlayerGameStats unchanged", other(), other_before)
    rows, new_players = q("select count(*) from core_playergamestats where game_id = any(%s)", [games])[0][0], \
        q("select count(*) from core_player")[0][0] - players_before
    print(f"  rows added {rows}, new players {new_players}, wall {secs:.0f}s ({secs / LIMIT:.2f} s/game)")
    sides = q("""
        select g.id, t.team_id, t.score, g.period_count, coalesce(sum(p.minutes), 0), coalesce(sum(p.points), 0), count(p.id)
        from core_game g cross join lateral (values (g.home_team_id, g.home_score), (g.away_team_id, g.away_score)) t(team_id, score)
        left join core_playergamestats p on p.game_id = g.id and p.team_id = t.team_id
        where g.id = any(%s) group by 1, 2, 3, 4""", [games])
    with_rows = [s for s in sides if s[6] > 0]
    closed = [s for s in with_rows if s[3] and abs(s[4] - (200 + 25 * (s[3] - 2))) <= 5]
    pts_ok = [s for s in with_rows if s[5] == s[2]]
    print(f"  team-games {len(sides)}, with player rows {len(with_rows)}, minutes closure {len(closed)}, "
          f"points = score {len(pts_ok)}, period_count NULL {sum(1 for s in sides if not s[3])}")
    short = sorted((s for s in with_rows if s not in closed), key=lambda s: s[4])[:5]
    print(f"  worst minutes: {[(s[0], s[1], s[4], s[3]) for s in short]}")
    bytes_per = q("""select (pg_total_relation_size('core_playergamestats')::float / greatest(count(*), 1)) from core_playergamestats""")[0][0]
    print(f"  PlayerGameStats bytes/row (table + indexes, whole table): {bytes_per:.0f}; this run ~{rows * bytes_per / 1e6:.1f} MB")
    return rows


if __name__ == "__main__":
    if "--apply" not in sys.argv:
        try:
            with transaction.atomic():
                run(); raise Rollback()
        except Rollback:
            print("REHEARSAL OK (rolled back)")
        sys.exit(0)
    size0 = q("select pg_total_relation_size('core_playergamestats') + pg_total_relation_size('core_player'), pg_database_size(current_database())")[0]
    with transaction.atomic():
        run()
    size1 = q("select pg_total_relation_size('core_playergamestats') + pg_total_relation_size('core_player'), pg_database_size(current_database())")[0]
    print(f"  measured growth: player tables {(size1[0] - size0[0]) / 1e6:.2f} MB, database {(size1[1] - size0[1]) / 1e6:.2f} MB")
    print("DONE")
