"""
2026-27: New Orleans missing from the NCAA rankings (364 teams, 2027.csv has 365). Run from backend/:
  python data_fixes/2026-11-17_lsu_new_orleans_merge.py            # rehearsal (rolled back)
  python data_fixes/2026-11-17_lsu_new_orleans_merge.py --apply

The NCAA scoreboard renamed New Orleans to "LSU New Orleans " (trailing space). ingest_gamelogs maps NCAA
games by name; the name was not in mappings/ncaa_team_name_mappings.yml, so TeamMapper.map_and_save created
a non-D1 team "LSU New Orleans " (slug lsu-new-orleans) and stored New Orleans's games against it
(prod: 6652856 @ LSU, 6652878 Southern-N.O., 6653462 Loyola (LA)). New Orleans (D1, slug new-orleans) kept
no 2026-27 games, so the rankings (games_played > 0) dropped it; the dup is non-D1, so it is not listed either.

Fix in code (deploy first, or the next ingest makes the team again): find_team trims names and the mapping
"LSU New Orleans" -> "New Orleans". This script moves every row that points at the dup to New Orleans and
deletes the dup:
  - games, team/player box rows, stints, scoring events, game logs, predictions: re-pointed (a unique-key
    clash aborts the run);
  - team-season rows of the dup (ratings, metrics, stats, membership, roster fit, projection) and its
    TeamExternalId rows: deleted, all derived or per-game NCAA ids; the recompute rebuilds New Orleans's;
  - PlayerSeasonStats of the dup that clash with a New Orleans row for the same player and season: deleted
    (compute_ncaa_player_season_stats rebuilds them from the box rows); the rest re-pointed.
Then recompute: update_ncaa_teams --season 2027 --skip-ingest, update_ncaa_players --season 2027.
"""

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from django.db import connection, transaction  # noqa: E402

DUP_SLUG = "lsu-new-orleans"
CANON_SLUG = "new-orleans"
ALIAS = "LSU New Orleans"

# (table, column): rows re-pointed from the dup to the canonical team.
REPOINT = [
    ("core_game", "home_team_id"),
    ("core_game", "away_team_id"),
    ("core_teamgamestats", "team_id"),
    ("core_teamgamestats", "opponent_id"),
    ("core_gamelog", "team_id"),
    ("core_gamelog", "opponent_id"),
    ("core_missingplayergamestats", "team_id"),
    ("core_playeravailability", "team_id"),
    ("core_playergamestats", "team_id"),
    ("core_playergamestint", "team_id"),
    ("core_playerseasonstats", "team_id"),
    ("core_playerseasonprojection", "team_id"),
    ("core_playerrecruitingprofile", "committed_team_id"),
    ("core_scenariosnapshot", "team_id"),
    ("core_scoringevent", "scoring_team_id"),
    ("validation_predictionsnapshot", "home_team_id"),
    ("validation_predictionsnapshot", "away_team_id"),
    ("validation_predictionsnapshot", "predicted_winner_id"),
]
# Rows of the dup deleted outright (derived per team-season, or per-game NCAA ids).
DELETE = [
    "core_teamseasonratings",
    "core_teamseasonmetrics",
    "core_teamseasonstats",
    "core_teamseasonmembership",
    "core_teamrosterfit",
    "core_teamseasonprojection",
    "core_teamexternalid",
]
# Unique keys that include the team column: a dup row whose key, with the canonical team, already exists.
CLASH = {
    ("core_teamgamestats", "team_id"): ["game_id"],
    ("core_gamelog", "team_id"): ["date", "opponent_name"],
    ("core_missingplayergamestats", "team_id"): ["game_id", "source", "external_id"],
}


class Rollback(Exception):
    pass


def q(sql, params=None):
    with connection.cursor() as c:
        c.execute(sql, params or [])
        return c.fetchall() if c.description else c.rowcount


def one(sql, params=None):
    return q(sql, params)[0][0]


def all_fk_columns():
    """Every (table, column) with a foreign key to core_team, from the catalog."""
    return set(q("""
        select kcu.table_name, kcu.column_name
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu on kcu.constraint_name = tc.constraint_name
        join information_schema.constraint_column_usage ccu on ccu.constraint_name = tc.constraint_name
        where tc.constraint_type = 'FOREIGN KEY' and ccu.table_name = 'core_team'"""))


def report(dup, canon, label):
    print(f"{label}:")
    for tid, slug in ((dup, DUP_SLUG), (canon, CANON_SLUG)):
        if tid is None:
            print(f"  {slug}: gone")
            continue
        games = q("""select season_year, count(*), count(*) filter (where status = 'final')
                     from core_game where %s in (home_team_id, away_team_id) and season_year >= 2026
                     group by 1 order by 1""", [tid])
        print(f"  {slug} (id {tid}): games (season, all, final) {games}")


def merge(dup, canon):
    fks = all_fk_columns()
    known = set(REPOINT) | {(t, "team_id") for t in DELETE}
    missing = fks - known
    if missing:
        raise SystemExit(f"FK columns to core_team not handled by this script: {sorted(missing)}")

    seasons = q("select distinct season_year from core_game where %s in (home_team_id, away_team_id)", [dup])
    if [s for (s,) in seasons if s != 2027]:
        raise SystemExit(f"dup team has games outside 2027: {seasons}; stop and look")

    for (table, col), keys in CLASH.items():
        cond = " and ".join(f"c.{k} is not distinct from d.{k}" for k in keys)
        n = one(f"select count(*) from {table} d join {table} c on {cond} and c.{col} = %s where d.{col} = %s",
                [canon, dup])
        if n:
            raise SystemExit(f"{table}: {n} dup rows clash with {CANON_SLUG} rows on {keys}; stop and look")

    n = q("""delete from core_playerseasonstats d using core_playerseasonstats c
             where d.team_id = %s and c.team_id = %s and c.player_id = d.player_id and c.season_id = d.season_id""",
          [dup, canon])
    print(f"  core_playerseasonstats: deleted {n} dup rows that clash with {CANON_SLUG} rows")

    for table in DELETE:
        n = q(f"delete from {table} where team_id = %s", [dup])
        print(f"  {table}: deleted {n}")
    for table, col in REPOINT:
        n = q(f"update {table} set {col} = %s where {col} = %s", [canon, dup])
        print(f"  {table}.{col}: re-pointed {n}")

    left = [(t, c, one(f"select count(*) from {t} where {c} = %s", [dup])) for t, c in sorted(fks)]
    left = [x for x in left if x[2]]
    if left:
        raise SystemExit(f"rows still point at the dup: {left}")

    q("""update core_team set aliases = aliases || to_jsonb(%s::text)
         where id = %s and not aliases ? %s""", [ALIAS, canon, ALIAS])
    q("delete from core_team where id = %s", [dup])
    print(f"  core_team: deleted {DUP_SLUG} (id {dup}); alias {ALIAS!r} on {CANON_SLUG}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit (default: rehearsal, rolled back)")
    args = ap.parse_args()

    rows = q("select id, slug, name, is_d1 from core_team where slug in (%s, %s)", [DUP_SLUG, CANON_SLUG])
    by_slug = {r[1]: r for r in rows}
    for r in rows:
        print(f"team {r[0]} {r[1]!r} name={r[2]!r} is_d1={r[3]}")
    if CANON_SLUG not in by_slug or not by_slug[CANON_SLUG][3]:
        raise SystemExit(f"{CANON_SLUG} missing or not D1")
    if DUP_SLUG not in by_slug:
        print(f"{DUP_SLUG} not found: nothing to merge")
        return
    if by_slug[DUP_SLUG][3]:
        raise SystemExit(f"{DUP_SLUG} is D1; expected the non-D1 team ingest created")
    dup, canon = by_slug[DUP_SLUG][0], by_slug[CANON_SLUG][0]

    report(dup, canon, "before")
    try:
        with transaction.atomic():
            merge(dup, canon)
            report(None, canon, "after")
            if not args.apply:
                raise Rollback
    except Rollback:
        print("REHEARSAL: rolled back. Re-run with --apply to commit.")
        return
    print("APPLIED. Now: python manage.py update_ncaa_teams --season 2027 --skip-ingest && "
          "python manage.py update_ncaa_players --season 2027")


if __name__ == "__main__":
    main()
