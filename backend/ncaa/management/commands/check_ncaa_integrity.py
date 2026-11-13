"""
Read-only integrity checks for NCAA games, box rows and player rows (team identity).

Scans from Tasks 6b and 7d, so team-identity breaks are caught before they reach ratings:
  box_pair_mismatch     a team box row whose team/opponent pair is not its Game's home/away pair
                        (7d: Georgia 2005-08 opponents' rows pointed at Georgia College)
  self_opponent         a Game with home == away, or a box row whose team is its own opponent
  over_40_games         a team with more than 40 D1-vs-D1 games on or before Selection Sunday (0-0
                        excluded); 6b: only the BC/BU merge (54-66 a season) ever exceeded it
  same_team_same_date   a team in two final games on one US-Eastern date that start < 12 h apart
                        (or lack a start time); 0-0 excluded
  duplicate_games       two games with the same teams on one Eastern date and different ESPN ids
  multi_espn_ids        one of our teams fed by several ESPN team ids (raw competitors)
  null_team_player_rows player-game rows with no team

Start time: Game.raw_json "date" (ISO UTC, ESPN-sourced games) or _raw.startTimeEpoch (NCAA-sourced);
Eastern date from that, else the MM/DD/YYYY raw date, else Game.game_date. (Game.start_time_utc is
empty in every season.)

FAIL on anything touching D1 data; WARN where only non-D1 teams are involved (a non-D1 team fed
by several ESPN ids; null-team player rows in a game with a non-D1 side, which are that side's
players). Exit status 1 if any check FAILs.

Usage:
  python manage.py check_ncaa_integrity               # every season
  python manage.py check_ncaa_integrity --season 2008
  python manage.py check_ncaa_integrity --from 2005 --to 2027 --examples 20
"""

import sys

from django.core.management.base import BaseCommand
from django.db import connection, transaction

START_TS = """
    case when g.raw_json->>'date' ~ '^\\d{4}-\\d{2}-\\d{2}T' then (g.raw_json->>'date')::timestamptz
         when g.raw_json->'_raw'->>'startTimeEpoch' ~ '^\\d+$'
              then to_timestamp((g.raw_json->'_raw'->>'startTimeEpoch')::bigint) end
"""
EASTERN_DATE = f"""
    coalesce(({START_TS} at time zone 'America/New_York')::date,
             case when g.raw_json->>'date' ~ '^\\d{{2}}/\\d{{2}}/\\d{{4}}$'
                  then to_date(g.raw_json->>'date', 'MM/DD/YYYY') end,
             g.game_date)
"""
PLAYED = "g.status = 'final' and not (g.home_score = 0 and g.away_score = 0)"
# A team's two games on one Eastern date count only if they start less than this many hours apart
# (or either has no start time). A late West Coast / Hawaii tip lands after midnight Eastern, on the
# same Eastern date as the next evening's game ~20 h later; those are real back-to-back days.
SAME_DATE_MAX_HOURS = 12
# Verified real same-day doubles (game id pairs), not reported:
#   2008 SEC tournament, Atlanta: the tornado moved Georgia-Kentucky (QF) to Saturday noon; Georgia then
#   played Mississippi St. (SF) that night (28115, 28124).
ALLOWED_SAME_DATE_PAIRS = [(28115, 28124)]

# Each check: (name, description, SQL). The SQL selects one row per problem with columns season, detail, severity ('FAIL' or 'WARN').
CHECKS = [
    ("box_pair_mismatch", "box row team/opponent not the Game's home/away pair", f"""
        select g.season_year season, 'FAIL' severity,
               'game ' || g.id || ' (' || g.source_game_id || ') home ' || g.home_team_id || ' away ' || g.away_team_id
               || ': box row ' || t.id || ' team ' || t.team_id || ' (' || tt.name || ') opp ' || t.opponent_id
               || ' (' || ot.name || ')' detail
        from core_teamgamestats t join core_game g on g.id = t.game_id
        join core_team tt on tt.id = t.team_id join core_team ot on ot.id = t.opponent_id
        where g.season_year between %(lo)s and %(hi)s and g.home_team_id <> g.away_team_id
          and not ((t.team_id = g.home_team_id and t.opponent_id = g.away_team_id)
                or (t.team_id = g.away_team_id and t.opponent_id = g.home_team_id))
    """),
    ("self_opponent", "team is its own opponent (Game or box row)", f"""
        select g.season_year season, 'FAIL' severity,
               'game ' || g.id || ' (' || g.source_game_id || ') ' || g.game_date || ' ' || h.name || ' vs itself, '
               || g.home_score || '-' || g.away_score detail
        from core_game g join core_team h on h.id = g.home_team_id
        where g.season_year between %(lo)s and %(hi)s and g.home_team_id = g.away_team_id
        union all
        select g.season_year, 'FAIL', 'box row ' || t.id || ' in game ' || g.id || ': team ' || t.team_id || ' = opponent'
        from core_teamgamestats t join core_game g on g.id = t.game_id
        where g.season_year between %(lo)s and %(hi)s and t.team_id = t.opponent_id
          and g.home_team_id <> g.away_team_id
    """),
    ("over_40_games", "more than 40 D1-vs-D1 games on or before Selection Sunday (0-0 excluded)", f"""
        select season, 'FAIL' severity, name || ' (' || team_id || '): ' || n || ' games' detail from (
          select g.season_year season, s.team_id, tm.name, count(*) n
          from core_game g
          join core_team h on h.id = g.home_team_id join core_team a on a.id = g.away_team_id
          left join core_season se on se.year = g.season_year
          cross join lateral (values (g.home_team_id), (g.away_team_id)) s(team_id)
          join core_team tm on tm.id = s.team_id
          where g.season_year between %(lo)s and %(hi)s and {PLAYED} and h.is_d1 and a.is_d1
            and (se.selection_sunday_date is null or g.game_date <= se.selection_sunday_date)
          group by 1, 2, 3 having count(*) > 40) x
    """),
    ("same_team_same_date",
     f"a team in two final games on one Eastern date, < {SAME_DATE_MAX_HOURS} h apart (0-0 excluded)", f"""
        with tg as (
          select g.id, g.season_year, g.source_game_id sid, s.team_id, {EASTERN_DATE} ed, {START_TS} ts
          from core_game g cross join lateral (values (g.home_team_id), (g.away_team_id)) s(team_id)
          where g.season_year between %(lo)s and %(hi)s and {PLAYED})
        select a.season_year season, 'FAIL' severity,
               tm.name || ' (' || a.team_id || ') on ' || a.ed || ': games ' || a.id || '/' || a.sid || ' and '
               || b.id || '/' || b.sid || coalesce(' (' || round(abs(extract(epoch from b.ts - a.ts)) / 3600.0, 1) || ' h apart)', '') detail
        from tg a join tg b on a.team_id = b.team_id and a.ed = b.ed and a.id < b.id
        join core_team tm on tm.id = a.team_id
        where (a.ts is null or b.ts is null or abs(extract(epoch from b.ts - a.ts)) < {SAME_DATE_MAX_HOURS} * 3600)
          and (a.id, b.id) not in ({", ".join(f"({x}, {y})" for x, y in ALLOWED_SAME_DATE_PAIRS)})
    """),
    ("duplicate_games", "same teams, same Eastern date, different ESPN ids", f"""
        with gg as (
          select g.id, g.season_year, g.source_game_id sid, g.home_team_id, g.away_team_id, g.home_score, g.away_score,
                 least(g.home_team_id, g.away_team_id) t1, greatest(g.home_team_id, g.away_team_id) t2, {EASTERN_DATE} ed
          from core_game g where g.season_year between %(lo)s and %(hi)s)
        select a.season_year season, 'FAIL' severity,
               a.ed || ' ' || h.name || ' vs ' || w.name || ': game ' || a.id || ' (' || a.sid || ', '
               || a.home_score || '-' || a.away_score || ') and game ' || b.id || ' (' || b.sid || ', '
               || b.home_score || '-' || b.away_score || ')' detail
        from gg a join gg b on a.t1 = b.t1 and a.t2 = b.t2 and a.ed = b.ed and a.id < b.id and a.sid <> b.sid
        join core_team h on h.id = a.home_team_id join core_team w on w.id = a.away_team_id
    """),
    ("multi_espn_ids", "one team fed by several ESPN team ids", f"""
        select season, case when is_d1 then 'FAIL' else 'WARN' end severity,
               name || ' (' || team_id || ', ' || case when is_d1 then 'D1' else 'non-D1' end || '): ESPN ids ' || ids detail
        from (
          select g.season_year season, x.team_id, tm.name, tm.is_d1,
                 string_agg(distinct x.espn || ' ' || x.espn_name, '; ') ids
          from core_game g
          cross join lateral (
            select c->'team'->>'id' espn, c->'team'->>'displayName' espn_name,
                   case when c->>'homeAway' = 'home' then g.home_team_id else g.away_team_id end team_id
            from jsonb_array_elements(g.raw_json->'_raw'->'competitions'->0->'competitors') c) x
          join core_team tm on tm.id = x.team_id
          where g.season_year between %(lo)s and %(hi)s and x.espn is not null
          group by 1, 2, 3, 4 having count(distinct x.espn) > 1) y
    """),
    ("null_team_player_rows", "player-game rows with no team", f"""
        select g.season_year season,
               case when h.is_d1 and a.is_d1 then 'FAIL' else 'WARN' end severity,
               'game ' || g.id || ' (' || g.source_game_id || ') ' || h.name || ' vs ' || a.name || ': '
               || count(*) || ' rows' detail
        from core_playergamestats p join core_game g on g.id = p.game_id
        join core_team h on h.id = g.home_team_id join core_team a on a.id = g.away_team_id
        where g.season_year between %(lo)s and %(hi)s and p.team_id is null
        group by g.season_year, g.id, g.source_game_id, h.name, a.name, h.is_d1, a.is_d1
    """),
]


class Command(BaseCommand):
    help = "Read-only NCAA team-identity integrity checks; exits 1 if any check fails."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, help="Season year (e.g. 2008). Default: every season.")
        parser.add_argument("--from", dest="season_from", type=int, help="First season (inclusive).")
        parser.add_argument("--to", dest="season_to", type=int, help="Last season (inclusive).")
        parser.add_argument("--examples", type=int, default=10, help="Examples printed per check (default 10).")

    def handle(self, *args, **opts):
        if opts["season"]:
            lo = hi = opts["season"]
        else:
            lo = opts["season_from"] or 0
            hi = opts["season_to"] or 9999
        n_ex = opts["examples"]
        failed = []
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                scope = f"season {lo}" if lo == hi else f"seasons {lo if lo else 'first'}-{hi if hi < 9999 else 'last'}"
                self.stdout.write(f"NCAA integrity checks, {scope}")
                for name, desc, sql in CHECKS:
                    cur.execute(f"select season, severity, detail from ({sql}) q order by severity, season, detail",
                                {"lo": lo, "hi": hi})
                    rows = cur.fetchall()
                    n_fail = sum(1 for r in rows if r[1] == "FAIL")
                    n_warn = len(rows) - n_fail
                    status = "FAIL" if n_fail else ("WARN" if n_warn else "ok")
                    by_season = {}
                    for season, sev, _ in rows:
                        by_season.setdefault(season, [0, 0])[0 if sev == "FAIL" else 1] += 1
                    seasons = ", ".join(f"{s}: {f}" + (f"+{w}w" if w else "") for s, (f, w) in sorted(by_season.items()))
                    self.stdout.write(f"\n[{status}] {name}: {n_fail} fail, {n_warn} warn  ({desc})")
                    if seasons:
                        self.stdout.write(f"  by season: {seasons}")
                    for season, sev, detail in rows[:n_ex]:
                        self.stdout.write(f"  {sev} {season}  {detail}")
                    if len(rows) > n_ex:
                        self.stdout.write(f"  ... {len(rows) - n_ex} more")
                    if n_fail:
                        failed.append(name)
        if failed:
            self.stdout.write(self.style.ERROR(f"\nFAILED: {', '.join(failed)}"))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("\nAll checks passed (warnings, if any, listed above)."))
