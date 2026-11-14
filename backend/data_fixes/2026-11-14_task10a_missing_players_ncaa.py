"""
Task 10A: players ESPN's box scores leave out, 2023 and 2024, from ncaa.com box scores (MissingPlayerGameStats).

Short team-games: a D1 team (TeamSeasonMembership) in a final, non-0-0 game with a known period count whose
PlayerGameStats minutes are more than 5 below 200 + 25 per OT (Task 9: 894 in 2023, 370 in 2024).

  python data_fixes/2026-11-14_task10a_missing_players_ncaa.py --fetch DIR     network only, no DB writes
  python data_fixes/2026-11-14_task10a_missing_players_ncaa.py DIR [--apply]   default: rehearsal (rolled back)

--fetch (NCAA API client = henrygd proxy, >= 1 s apart, resumable): for each short game, the scoreboard of its
US-Eastern date (then the day before/after if nothing matches); a contest matches when its final score pair equals
ours and it is the only one that does. Then that contest's box score. Raw responses are gzipped in DIR/raw/; DIR/
manifest.json records game -> contest (or why not).
Apply: for each short team-game with a box, the side is bound by points (and FGA when both have it), never by
name. ncaa.com players with minutes or points that our ESPN rows lack (no row, or a row with neither) become
MissingPlayerGameStats rows (source 'ncaa'), unless adding them would put the team over the expected minutes by
more than 3 (a name-variant double count; reported as 'over', nothing added). Link to core_player only by exact
display name for a player with a PlayerGameStats row on that team that season, and only when that is unique.
PlayerGameStats is never changed (checked by count + checksum).
"""
import argparse, collections, gzip, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from datetime import timedelta  # noqa: E402
from django.db import connection, transaction  # noqa: E402

from ncaa.models import MissingPlayerGameStats  # noqa: E402
from ncaa.utils.missing_players import (bind_side, eastern_date, expected_minutes, match_contests,  # noqa: E402
                                        missing_lines, scoreboard_contests)

SEASONS = (2023, 2024)
TOL_SHORT, TOL_FIX = 5, 3
EXPECTED_SHORT = {2023: 894, 2024: 370}


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


def short_team_games():
    """[(game_id, season, team_id, periods, our_minutes, team_score, team_fga, utc, home_score, away_score)]"""
    return q("""
        with side as (
          select g.id, g.season_year y, g.period_count pc, t.team_id, t.score, g.home_score, g.away_score,
                 g.raw_json::jsonb -> '_raw' ->> 'date' utc
          from core_game g join core_season s on s.year = g.season_year
          cross join lateral (values (g.home_team_id, g.home_score), (g.away_team_id, g.away_score)) t(team_id, score)
          join core_teamseasonmembership m on m.team_id = t.team_id and m.season_id = s.id and m.is_d1
          where g.season_year = any(%s) and g.status = 'final' and not (g.home_score = 0 and g.away_score = 0)
            and g.period_count >= 2),
        mins as (select game_id, team_id, sum(minutes) mn from core_playergamestats group by 1, 2)
        select side.id, side.y, side.team_id, side.pc, coalesce(mins.mn, 0), side.score, tgs.fga, side.utc,
               side.home_score, side.away_score
        from side left join mins on mins.game_id = side.id and mins.team_id = side.team_id
        left join core_teamgamestats tgs on tgs.game_id = side.id and tgs.team_id = side.team_id
        where coalesce(mins.mn, 0) < 200 + 25 * (side.pc - 2) - %s
        order by side.y, side.id, side.team_id""", [list(SEASONS), TOL_SHORT])


def game_sides():
    """game_id -> [(team_id, points, fga)] for both teams (Game score, our team box FGA)."""
    out = collections.defaultdict(list)
    for gid, tid, pts, fga in q("""select g.id, t.team_id, t.score, tgs.fga from core_game g
            cross join lateral (values (g.home_team_id, g.home_score), (g.away_team_id, g.away_score)) t(team_id, score)
            left join core_teamgamestats tgs on tgs.game_id = g.id and tgs.team_id = t.team_id
            where g.season_year = any(%s)""", [list(SEASONS)]):
        out[gid].append((tid, pts, fga))
    return out


def box_matches(box, sides) -> bool:
    """Both of our teams bind to distinct ncaa.com sides by points and FGA."""
    bound = [bind_side(box or {}, pts, fga) for _, pts, fga in sides]
    return all(b is not None for b in bound) and len({id(b) for b in bound}) == len(bound)


# ---------------------------------------------------------------- fetch (network, no DB writes)
def fetch(out: Path):
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    from ncaa.utils.ncaa_api import NCAAAPIClient, NCAAAPIError
    raw = out / "raw"; raw.mkdir(parents=True, exist_ok=True)
    client = NCAAAPIClient(rate_limit_delay=1.1)
    retry = Retry(total=2, backoff_factor=5.0, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    client.session.mount("https://", HTTPAdapter(max_retries=retry))
    log = open(out / "requests.log", "a")

    def get(path: Path, endpoint: str):
        if path.exists():
            return json.load(gzip.open(path, "rt"))
        try:
            data = client._make_request(endpoint, cache_key=None)
            status = "ok"
        except NCAAAPIError as e:
            data, status = None, f"error {e}"[:200]
        log.write(f"{time.strftime('%H:%M:%S')}\t{endpoint}\t{status}\n"); log.flush()
        if data is not None:
            json.dump(data, gzip.open(path, "wt"))
        return data

    games = {}
    for gid, y, tid, pc, mn, score, fga, utc, hs, as_ in short_team_games():
        games[gid] = (y, utc, hs, as_)
    sides = game_sides()
    man_path = out / "manifest.json"
    manifest = json.load(open(man_path)) if man_path.exists() else {}
    print(f"{len(games)} short games; {len(manifest)} already in manifest", flush=True)
    for i, (gid, (y, utc, hs, as_)) in enumerate(sorted(games.items())):
        if str(gid) in manifest and manifest[str(gid)].get("status") in ("ok", "no_match", "ambiguous_unresolved", "box_error"):
            continue
        d0 = eastern_date(utc)
        found, tried, sb_failed = [], [], False
        for d in (d0, d0 - timedelta(days=1), d0 + timedelta(days=1)):
            sb = get(raw / f"sb_{d.isoformat()}.json.gz", f"/scoreboard/basketball-men/d1/{d.year}/{d.month:02d}/{d.day:02d}")
            tried.append(d.isoformat())
            sb_failed |= sb is None
            found = match_contests(hs, as_, scoreboard_contests(sb or {}))
            if found:
                break
        rec = {"season": y, "dates": tried}
        if not found and sb_failed:
            rec["status"] = "sb_error"
        elif not found:
            rec["status"] = "no_match"
        elif len(found) > 1:
            # same final score pair twice on the date: fetch each candidate box, keep the one whose two sides
            # match our two teams by points and FGA
            rec["candidates"] = [c["contest_id"] for c in found]
            ok = [c for c in found if box_matches(get(raw / f"box_{c['contest_id']}.json.gz", f"/game/{c['contest_id']}/boxscore"),
                                                  sides[gid])]
            if len(ok) == 1:
                rec.update(status="ok", contest_id=ok[0]["contest_id"], seo=[ok[0]["home_seo"], ok[0]["away_seo"]],
                           resolved_by="box points+fga")
            else:
                rec["status"] = "ambiguous_unresolved"
        else:
            cid = found[0]["contest_id"]; rec["contest_id"] = cid
            rec["seo"] = [found[0]["home_seo"], found[0]["away_seo"]]
            box = get(raw / f"box_{cid}.json.gz", f"/game/{cid}/boxscore")
            rec["status"] = "ok" if box and box.get("teamBoxscore") else "box_error"
        manifest[str(gid)] = rec
        if i % 25 == 0:
            json.dump(manifest, open(man_path, "w"))
            print(f"  {i + 1}/{len(games)} {collections.Counter(r['status'] for r in manifest.values())}", flush=True)
    json.dump(manifest, open(man_path, "w"))
    print("FETCH DONE", collections.Counter(r["status"] for r in manifest.values()), flush=True)


# ---------------------------------------------------------------- apply
def pgs_checksum():
    return q("""select count(*), md5(string_agg(id::text || ':' || coalesce(minutes, -1)::text || ':' || points::text, ','
                order by id)) from core_playergamestats""")[0]


def run(out: Path):
    raw = out / "raw"
    manifest = json.load(open(out / "manifest.json"))
    tgs = short_team_games()
    expect("short team-games by season", dict(collections.Counter(r[1] for r in tgs)), EXPECTED_SHORT)
    expect("side table empty before", MissingPlayerGameStats.objects.count(), 0)
    pgs_before = pgs_checksum()

    sides = game_sides()
    ours = collections.defaultdict(list)
    for gid, tid, name, mn, pts in q("""select p.game_id, p.team_id, pl.display_name, p.minutes, p.points
            from core_playergamestats p join core_player pl on pl.id = p.player_id join core_game g on g.id = p.game_id
            where g.season_year = any(%s)""", [list(SEASONS)]):
        ours[(gid, tid)].append((name, mn, pts))
    roster = collections.defaultdict(set)   # (season, team, display_name) -> player ids
    for y, tid, name, pid in q("""select distinct g.season_year, p.team_id, pl.display_name, pl.id from core_playergamestats p
            join core_player pl on pl.id = p.player_id join core_game g on g.id = p.game_id
            where g.season_year = any(%s)""", [list(SEASONS)]):
        roster[(y, tid, name)].add(pid)

    stats = collections.defaultdict(collections.Counter)
    new_rows, unlinked = [], []
    for gid, y, tid, pc, mn, score, fga, utc, hs, as_ in tgs:
        st = stats[y]; st["short"] += 1
        rec = manifest.get(str(gid), {"status": "not_fetched"})
        if rec["status"] != "ok":
            st[f"unmatched_{rec['status']}"] += 1; st["still_short"] += 1; continue
        box = json.load(gzip.open(raw / f"box_{rec['contest_id']}.json.gz", "rt"))
        side = bind_side(box, score, fga) if box_matches(box, sides[gid]) else None
        if side is None:
            st["unmatched_side"] += 1; st["still_short"] += 1; continue
        if not side.get("playerStats"):
            st["ncaa_no_players"] += 1; st["still_short"] += 1; continue
        lines = missing_lines(side["playerStats"], ours[(gid, tid)])
        want = expected_minutes(pc)
        total = mn + sum(l["minutes"] or 0 for l in lines)
        if total > want + TOL_FIX:
            st["over"] += 1; st["still_short"] += 1; continue
        if not lines:
            st["ncaa_none_missing"] += 1; st["still_short"] += 1; continue
        st["fixed" if total >= want - TOL_FIX else "still_short"] += 1
        st["players_added"] += len(lines)
        for l in lines:
            ids = roster.get((y, tid, l["name"]), set())
            pid = next(iter(ids)) if len(ids) == 1 else None
            if pid is None:
                st["unlinked"] += 1
                unlinked.append((y, gid, tid, l["name"], l["minutes"], l["points"], "ambiguous" if ids else "no exact name"))
            note = "; ".join(x for x in (l.pop("note"), "linked by exact name + team + season" if pid else "") if x)
            new_rows.append(MissingPlayerGameStats(game_id=gid, team_id=tid, player_id=pid, source="ncaa",
                                                   external_game_id=rec["contest_id"], note=note, **l))
    MissingPlayerGameStats.objects.bulk_create(new_rows)
    expect("rows inserted", MissingPlayerGameStats.objects.count(), len(new_rows))
    expect("PlayerGameStats unchanged (count, checksum)", pgs_checksum(), pgs_before)
    expect("every added row has minutes or points", MissingPlayerGameStats.objects.filter(minutes__isnull=True,
           points__isnull=True).count(), 0)
    # After: re-measure with the side table added
    fixed_db = q("""
        with s as (select %s::int tol)
        select g.season_year, count(*) filter (where abs(coalesce(p.mn, 0) + coalesce(x.mn, 0) - (200 + 25 * (g.period_count - 2))) <= 3)
        from core_game g join (select game_id, team_id from core_missingplayergamestats group by 1, 2) k on k.game_id = g.id
        left join (select game_id, team_id, sum(minutes) mn from core_playergamestats group by 1, 2) p
          on p.game_id = g.id and p.team_id = k.team_id
        left join (select game_id, team_id, sum(minutes) mn from core_missingplayergamestats group by 1, 2) x
          on x.game_id = g.id and x.team_id = k.team_id
        group by 1 order by 1""", [TOL_FIX])
    expect("fixed team-games re-measured in SQL", dict(fixed_db), {y: stats[y]["fixed"] for y in SEASONS if stats[y]["fixed"]})
    for y in SEASONS:
        print(f"  {y}: {dict(stats[y])}")
    with open(out / "unlinked.tsv", "w") as f:
        f.write("season\tgame_id\tteam_id\tname\tminutes\tpoints\treason\n")
        for r in unlinked:
            f.write("\t".join(map(str, r)) + "\n")
    print(f"  unlinked players listed in {out / 'unlinked.tsv'} ({len(unlinked)})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    out = Path(a.dir).expanduser()
    if a.fetch:
        fetch(out); sys.exit(0)
    if not a.apply:
        try:
            with transaction.atomic():
                run(out); raise Rollback()
        except Rollback:
            print("REHEARSAL OK (rolled back)")
        sys.exit(0)
    with transaction.atomic():
        run(out)
    print("DONE")
