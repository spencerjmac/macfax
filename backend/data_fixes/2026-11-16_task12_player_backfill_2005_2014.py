"""
Task 12: player box scores for 2005-2014 from ESPN summaries (the Task 11 command's selection and parsing),
D1-vs-D1 games only, one request per second, newest season first.

  python data_fixes/2026-11-16_task12_player_backfill_2005_2014.py --trial 2005 --limit 100   rehearsal (rolled back)
  nohup python data_fixes/2026-11-16_task12_player_backfill_2005_2014.py --run --log LOG --state STATE.jsonl &

Per season (2014 -> 2005): every D1-vs-D1, non-0-0 final game without player rows (resumable: a rerun skips games
already done), fetched once; failures are retried up to 3 more passes. Each game is written in its own
transaction: new Player rows only (an existing player's name, jersey, position and headshot are left as they are,
so older seasons don't overwrite newer data) and PlayerGameStats upserted for that game; a NULL period_count is
filled from the summary. Blanked box entries (no athlete id, no stats) are counted, not stored.
Each team box is judged by what it has: minutes within 5 of 200 + 25 per OT where the box has minutes, player
points = team score where it has stat lines without minutes; games whose boxes are names only (no stat lines) are
skipped and counted. Every processed game is appended to the --state JSONL (resume skips names-only games and
season closure covers all runs). Logged per season: games fetched / failed / names-only, player rows, blanked
entries, closure by rule, free disk. Stops after a season whose closure is under 95%, or as soon as free disk is
under 10 GB. Nothing is recomputed (no BPR, season stats or ratings).
"""
import argparse, json, os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.db import connection, transaction  # noqa: E402

from ncaa.management.commands.sync_ncaa_player_gamelogs import (PGS_FIELDS, PLAYER_FIELDS, has_espn_event_id,  # noqa: E402
                                                                select_games)
from ncaa.models import Game, Player, PlayerGameStats, TeamExternalId  # noqa: E402
from ncaa.utils.ncaa_api import ESPNAPIClient  # noqa: E402

SEASONS = list(range(2014, 2004, -1))
MIN_CLOSURE, MIN_FREE_GB, RETRY_PASSES, SLEEP = 0.95, 10.0, 3, 1.0
DISK_PATH = "/"


class Rollback(Exception):
    pass


class Stop(Exception):
    pass


def q(sql, p=None):
    with connection.cursor() as c:
        c.execute(sql, p or [])
        return c.fetchall() if c.description else c.rowcount


def free_gb():
    return shutil.disk_usage(DISK_PATH).free / 1e9


def write_game(game_id, rows, team_by_espn):
    """New players only; this game's PlayerGameStats upserted; NULL period_count filled. Returns rows written."""
    period = rows[0].get("game_period") if rows else None
    rows = list({r["espn_athlete_id"]: r for r in rows if r.get("espn_athlete_id")}.values())
    with transaction.atomic():
        if isinstance(period, int) and period >= 2:
            Game.objects.filter(pk=game_id, period_count__isnull=True).update(period_count=period, went_to_ot=period > 2)
        if not rows:
            return 0
        Player.objects.bulk_create([Player(espn_athlete_id=r["espn_athlete_id"], **{f: r[f] for f in PLAYER_FIELDS})
                                    for r in rows], ignore_conflicts=True)
        pid = dict(Player.objects.filter(espn_athlete_id__in=[r["espn_athlete_id"] for r in rows])
                   .values_list("espn_athlete_id", "pk"))
        PlayerGameStats.objects.bulk_create(
            [PlayerGameStats(player_id=pid[r["espn_athlete_id"]], game_id=game_id,
                             team_id=team_by_espn.get(r["espn_team_id"]), **{k: r[k] for k in PGS_FIELDS}) for r in rows],
            update_conflicts=True, unique_fields=["player", "game"], update_fields=["team"] + list(PGS_FIELDS))
    return len(rows)


def box_kind(team_entry):
    """'minutes', 'points_only' (stat lines without minutes) or 'names_only' (no stat lines) for one team's box."""
    grp = (team_entry.get("statistics") or [{}])[0]
    keys = grp.get("keys") or []
    lines = [a.get("stats") or [] for a in grp.get("athletes") or []]
    lines = [ln for ln in lines if keys and len(ln) == len(keys)]
    if not lines:
        return "names_only"
    if "minutes" in keys:
        i = keys.index("minutes")
        if any((ln[i] or "").strip() not in ("", "0", "--") for ln in lines):
            return "minutes"
    return "points_only"


class Runner:
    def __init__(self, log, state):
        self.client = ESPNAPIClient(rate_limit_delay=SLEEP)
        self.team_by_espn = {e.external_id: e.team_id for e in TeamExternalId.objects.filter(source="espn")}
        self.log, self.state = log, state
        self.requests = 0

    def say(self, msg):
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        print(line, flush=True)
        if self.log:
            with open(self.log, "a") as f:
                f.write(line + "\n")

    def record(self, rec):
        if self.state:
            with open(self.state, "a") as f:
                f.write(json.dumps(rec) + "\n")

    def recorded(self):
        out = {}
        if self.state and os.path.exists(self.state):
            for ln in open(self.state):
                r = json.loads(ln); out[r["game"]] = r
        return out

    def process(self, g, data):
        """Write one game (unless every box is names-only) and judge each team box by what it has."""
        rows = self.client.parse_player_box_score(data)
        n_blank = sum(ESPNAPIClient.idless_athletes(data).values())
        sides = []
        for te in (data.get("boxscore") or {}).get("players") or []:
            e = str((te.get("team") or {}).get("id", ""))
            kind, tid = box_kind(te), self.team_by_espn.get(e)
            mine = [r for r in rows if r["espn_team_id"] == e]
            ok = None
            if kind == "minutes":
                period = (rows[0].get("game_period") if rows else None) or g.period_count
                ok = bool(period) and abs(sum(r["minutes"] or 0 for r in mine) - (200 + 25 * (period - 2))) <= 5
            elif kind == "points_only":
                score = g.home_score if tid == g.home_team_id else g.away_score if tid == g.away_team_id else None
                ok = score is not None and sum(r["points"] or 0 for r in mine) == score
            sides.append({"espn_team": e, "team": tid, "kind": kind, "ok": ok})
        names_only = bool(sides) and all(sd["kind"] == "names_only" for sd in sides)
        written = 0 if names_only or not sides else write_game(g.id, rows, self.team_by_espn)
        rec = {"game": g.id, "season": g.season_year, "names_only": names_only or not sides, "rows": written,
               "blanked": n_blank, "sides": sides}
        self.record(rec)
        return rec

    def season(self, season, limit=0):
        done = self.recorded()
        games = [g for g in select_games(season, d1_vs_d1=True, skip_done=True)
                 if has_espn_event_id(g) and not (g.id in done and done[g.id]["names_only"])]
        if limit:
            games = games[:limit]
        st = {"todo": len(games), "fetched": 0, "failed": 0, "names_only": 0, "rows": 0, "blanked": 0}
        recs = []
        t0 = time.time()
        pending, failed = games, []
        for attempt in range(1 + RETRY_PASSES):
            failed = []
            for i, g in enumerate(pending):
                if i % 100 == 0 and free_gb() < MIN_FREE_GB:
                    raise Stop(f"free disk {free_gb():.2f} GB < {MIN_FREE_GB} GB")
                data = self.client.get_summary(g.source_game_id)
                self.requests += 1
                if data is None:
                    failed.append(g); continue
                rec = self.process(g, data); recs.append(rec)
                st["fetched"] += 1; st["names_only"] += rec["names_only"]
                st["rows"] += rec["rows"]; st["blanked"] += rec["blanked"]
                if st["fetched"] % 500 == 0:
                    self.say(f"  {season}: {st['fetched']}/{st['todo']} fetched, "
                             f"{(time.time() - t0) / st['fetched']:.2f} s/game, free disk {free_gb():.2f} GB")
            if not failed:
                break
            self.say(f"  {season}: pass {attempt + 1}: {len(failed)} failed" + (", retrying" if attempt < RETRY_PASSES else ""))
            pending = failed
            if attempt < RETRY_PASSES:
                time.sleep(30)
        st["failed"] = len(failed)
        st["secs"] = round(time.time() - t0)
        return st, recs


def judge(recs):
    """Closure over team boxes: minutes boxes within 5 of the expected minutes, points-only boxes points = score."""
    c = {"minutes": [0, 0], "points_only": [0, 0], "names_only_sides": 0}
    for r in recs:
        for sd in r["sides"]:
            if sd["kind"] == "names_only":
                c["names_only_sides"] += 1
            else:
                c[sd["kind"]][0] += 1; c[sd["kind"]][1] += bool(sd["ok"])
    checked = c["minutes"][0] + c["points_only"][0]
    ok = c["minutes"][1] + c["points_only"][1]
    return c, checked, ok


def run(log, state):
    r = Runner(log, state)
    r.say(f"START backfill {SEASONS[0]}->{SEASONS[-1]}, D1 vs D1, {SLEEP}s between requests; state {state}; "
          f"free disk {free_gb():.2f} GB")
    try:
        for season in SEASONS:
            st, _ = r.season(season)
            recs = [x for x in r.recorded().values() if x["season"] == season]   # this and earlier runs
            c, checked, ok = judge(recs)
            pct = ok / checked if checked else None
            pr = q("select count(*) from core_playergamestats p join core_game g on g.id = p.game_id where g.season_year = %s",
                   [season])[0][0]
            r.say(f"SEASON {season}: to fetch {st['todo']}, fetched {st['fetched']}, failed {st['failed']}, names-only games "
                  f"skipped {st['names_only']}, player rows written {st['rows']} (season total {pr}), blanked entries "
                  f"{st['blanked']}; closure (all runs) minutes {c['minutes'][1]}/{c['minutes'][0]}, points-only "
                  f"{c['points_only'][1]}/{c['points_only'][0]}, overall "
                  + (f"{pct:.1%}" if pct is not None else "n/a")
                  + f", names-only boxes {c['names_only_sides']}; {st['secs']}s; free disk {free_gb():.2f} GB")
            if pct is not None and pct < MIN_CLOSURE:
                raise Stop(f"{season} closure {pct:.1%} < {MIN_CLOSURE:.0%}")
            if free_gb() < MIN_FREE_GB:
                raise Stop(f"free disk {free_gb():.2f} GB < {MIN_FREE_GB} GB")
    except Stop as e:
        r.say(f"STOPPED: {e}")
        return
    r.say(f"DONE all seasons; {r.requests} requests this run")


def trial(season, limit):
    r = Runner(None, None)
    rows_before = q("select count(*) from core_playergamestats")[0][0]
    try:
        with transaction.atomic():
            st, recs = r.season(season, limit=limit)
            c, checked, ok = judge(recs)
            print(f"TRIAL {season}: {st}; closure {c}, overall {ok}/{checked}; requests {r.requests}")
            raise Rollback()
    except Rollback:
        pass
    assert q("select count(*) from core_playergamestats")[0][0] == rows_before
    print("TRIAL rolled back")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trial", type=int)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--log")
    ap.add_argument("--state", help="JSONL of processed games (resume: names-only games are not refetched)")
    a = ap.parse_args()
    if a.trial:
        trial(a.trial, a.limit)
    elif a.run:
        run(a.log, a.state)
