"""
sync_ncaa_pbp — fetch ESPN play-by-play for finished NCAA games and reconstruct
per-player lineup stints, stored in PlayerGameStint.

Prerequisites:
  sync_ncaa_player_gamelogs must have already run so that:
    - PlayerGameStats rows exist (provides starter info + DB player IDs)
    - TeamExternalId rows exist (provides ESPN team_id → Team mapping)

Algorithm per game:
  1. Fetch plays from ESPN summary endpoint (type 584 = sub, 412 = end period,
     402 = end game, others carry homeScore/awayScore for score tracking).
  2. Seed each team's on-court set from boxscore starters
     (PlayerGameStats.starter=True).
  3. Process plays in sequenceNumber order:
     - Substitution "subbing out": close that player's active stint.
     - Substitution "subbing in":  open a new stint for that player.
     - End Period (412):  close all active stints; re-open same players
       for the next period.
     - End Game (402):   close all remaining stints.
  4. For every completed stint, upsert a PlayerGameStint row.

Stint scoring:
  homeScore / awayScore on every ESPN play reflects the cumulative score at
  that moment.  pts_scored = team_score_at_end - team_score_at_start; similarly
  for pts_allowed.  Because substitutions are dead-ball events the score does
  not change on the sub event itself.

Stint timing:
  clock.displayValue = "MM:SS" remaining in the period.
  secs_on = clock_start_secs - clock_end_secs.
  Stints are reset at every period boundary (half or OT) so no stint ever spans
  a period break.  Period-start clock: 1200 s for halves, 300 s for OT.

Usage:
    python manage.py sync_ncaa_pbp --season 2026
    python manage.py sync_ncaa_pbp --season 2026 --workers 4
    python manage.py sync_ncaa_pbp --season 2026 --limit 50 --dry-run
    python manage.py sync_ncaa_pbp --season 2026 --force
"""

import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import transaction

from ncaa.models import (
    Game,
    Player,
    PlayerGameStats,
    PlayerGameStint,
    Team,
    TeamExternalId,
)
from ncaa.utils.ncaa_api import ESPNAPIClient

logger = logging.getLogger(__name__)

# ESPN play type IDs
TYPE_SUBSTITUTION = "584"
TYPE_END_PERIOD   = "412"
TYPE_END_GAME     = "402"

# Period durations in seconds
HALF_SECS = 1200   # 20-minute halves
OT_SECS   = 300    # 5-minute OT periods

# Box event keys tracked per team per stint
_BOX_KEYS = ("fgm", "fga", "fg3m", "fta", "tov", "oreb", "dreb")

# ESPN type IDs for field goal attempts (all shot types)
_FGA_TYPE_IDS = {"558", "572", "574", "545", "549", "547", "546"}
# ESPN type ID for free throw attempts (type.text = "MadeFreeThrow" covers both made and missed)
_FTA_TYPE_ID = "540"


def _empty_box() -> dict:
    return {k: 0 for k in _BOX_KEYS}


def _classify_play(play: dict) -> tuple[str, str] | None:
    """
    Classify a single play event for box-score accumulation.
    Returns (event_key, espn_team_id) or None if not a box event.

    event_key is one of: fgm2 | fgm3 | fga_miss | ftm | fta_miss | tov | oreb | dreb

    ESPN uses numeric type.id for shot types (e.g. 558=JumpShot, 572=LayUpShot,
    574=DunkShot, 540=MadeFreeThrow) and scoringPlay=True/False for made/missed.
    Turnovers and rebounds are matched via type.text substring.
    """
    team_id = str((play.get("team") or {}).get("id", ""))
    if not team_id:
        return None

    type_id   = str((play.get("type") or {}).get("id", ""))
    type_text = (play.get("type") or {}).get("text", "").lower()
    text      = play.get("text", "").lower()
    is_made   = bool(play.get("scoringPlay", False))

    # ── Field goal attempts ───────────────────────────────────────────────────
    if type_id in _FGA_TYPE_IDS:
        if is_made:
            is_three = "three point" in text or "three pointer" in text
            return ("fgm3" if is_three else "fgm2", team_id)
        return ("fga_miss", team_id)

    # ── Free throw attempts ───────────────────────────────────────────────────
    # type 540 is labelled "MadeFreeThrow" but covers both made and missed
    if type_id == _FTA_TYPE_ID:
        return ("ftm" if is_made else "fta_miss", team_id)

    # ── Turnovers ─────────────────────────────────────────────────────────────
    if "turnover" in type_text:
        return ("tov", team_id)

    # ── Rebounds ──────────────────────────────────────────────────────────────
    if "rebound" in type_text:
        if "offensive" in type_text or "offensive rebound" in text:
            return ("oreb", team_id)
        if "defensive" in type_text or "defensive rebound" in text:
            return ("dreb", team_id)

    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clock_to_secs(clock_str: str) -> int:
    """'16:43' → 1003 (seconds remaining in period)."""
    try:
        parts = clock_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return 0


def _period_start_secs(period: int) -> int:
    """Seconds on clock at the START of a period (before any action)."""
    return HALF_SECS if period <= 2 else OT_SECS


def _fetch_plays(espn_game_id: str, sleep: float) -> list:
    """Fetch plays list for one ESPN game (run in thread pool)."""
    client = ESPNAPIClient(rate_limit_delay=sleep)
    return client.get_plays(espn_game_id)


# ── Core reconstruction ───────────────────────────────────────────────────────

def reconstruct_stints(
    plays: list,
    starters: dict[str, str],  # espn_athlete_id → espn_team_id
    home_espn_team_id: str,
    away_espn_team_id: str,
    player_map: dict[str, Player],        # espn_athlete_id → Player
    team_map: dict[str, Optional[Team]],  # espn_team_id → Team
) -> list[dict]:
    """
    Walk the play sequence and return a list of completed stint dicts:
        player_id, team_id (DB), stint_index, period,
        clock_start_secs, clock_end_secs, secs_on,
        pts_scored, pts_allowed, plus_minus,
        team_fgm, team_fga, team_fg3m, team_fta, team_tov, team_oreb, team_dreb,
        opp_fgm,  opp_fga,  opp_fg3m,  opp_fta,  opp_tov,  opp_oreb,  opp_dreb
    """

    # on_court: espn_team_id → set of espn_athlete_ids currently on court
    on_court: dict[str, set] = {
        home_espn_team_id: set(),
        away_espn_team_id: set(),
    }
    for ath_id, team_id in starters.items():
        on_court.setdefault(team_id, set()).add(ath_id)

    # active_stints[espn_athlete_id] = (stint_index, period, clock_start_secs,
    #                                    home_score_start, away_score_start,
    #                                    espn_team_id,
    #                                    home_box_start, away_box_start)
    active_stints: dict[str, tuple] = {}

    # Running cumulative box event counters per espn_team_id
    box_state: dict[str, dict] = {
        home_espn_team_id: _empty_box(),
        away_espn_team_id: _empty_box(),
    }

    # Per-player stint counter
    player_stint_idx: dict[str, int] = defaultdict(int)

    current_home = 0
    current_away = 0
    current_period = 1

    def _open_stints_for_players(player_ids_by_team, period, clock_start,
                                  home_score, away_score):
        # Snapshot current box state so each stint can diff at close time
        home_snap = dict(box_state[home_espn_team_id])
        away_snap = dict(box_state[away_espn_team_id])
        for team_id, pids in player_ids_by_team.items():
            for pid in pids:
                active_stints[pid] = (
                    player_stint_idx[pid],
                    period,
                    clock_start,
                    home_score,
                    away_score,
                    team_id,
                    home_snap,
                    away_snap,
                )

    def _close_stint(ath_id, clock_end, home_score_end, away_score_end) -> Optional[dict]:
        if ath_id not in active_stints:
            return None
        (idx, period, clock_start, hs_start, as_start, team_id,
         home_box_start, away_box_start) = active_stints.pop(ath_id)

        player = player_map.get(ath_id)
        if player is None:
            return None  # player not in our DB

        team = team_map.get(team_id)
        secs = max(0, clock_start - clock_end)

        if team_id == home_espn_team_id:
            pts_scored  = home_score_end - hs_start
            pts_allowed = away_score_end - as_start
            team_box_start = home_box_start
            opp_box_start  = away_box_start
            team_box_cur   = box_state[home_espn_team_id]
            opp_box_cur    = box_state[away_espn_team_id]
        else:
            pts_scored  = away_score_end - as_start
            pts_allowed = home_score_end - hs_start
            team_box_start = away_box_start
            opp_box_start  = home_box_start
            team_box_cur   = box_state[away_espn_team_id]
            opp_box_cur    = box_state[home_espn_team_id]

        # Guard against negative deltas (data anomaly)
        pts_scored  = max(0, pts_scored)
        pts_allowed = max(0, pts_allowed)

        # Box event deltas for this stint
        team_box = {k: max(0, team_box_cur[k] - team_box_start[k]) for k in _BOX_KEYS}
        opp_box  = {k: max(0, opp_box_cur[k]  - opp_box_start[k])  for k in _BOX_KEYS}

        player_stint_idx[ath_id] += 1

        return {
            "player": player,
            "team": team,
            "stint_index": idx,
            "period": period,
            "clock_start_secs": clock_start,
            "clock_end_secs": clock_end,
            "secs_on": secs,
            "pts_scored":  pts_scored,
            "pts_allowed": pts_allowed,
            "plus_minus":  pts_scored - pts_allowed,
            # Team box events
            "team_fgm":  team_box["fgm"],
            "team_fga":  team_box["fga"],
            "team_fg3m": team_box["fg3m"],
            "team_fta":  team_box["fta"],
            "team_tov":  team_box["tov"],
            "team_oreb": team_box["oreb"],
            "team_dreb": team_box["dreb"],
            # Opp box events
            "opp_fgm":  opp_box["fgm"],
            "opp_fga":  opp_box["fga"],
            "opp_fg3m": opp_box["fg3m"],
            "opp_fta":  opp_box["fta"],
            "opp_tov":  opp_box["tov"],
            "opp_oreb": opp_box["oreb"],
            "opp_dreb": opp_box["dreb"],
        }

    completed: list[dict] = []

    # Open initial stints for starters at game start (period 1, clock 1200, score 0-0)
    _open_stints_for_players(on_court, 1, HALF_SECS, 0, 0)

    def _seq_key(p):
        # sequenceNumber arrives as a string; lexicographic sort misorders
        # plays ("1000" < "999") → clock jumps → overlapping stints (audit
        # bug 1.3). Sort numerically, tolerating non-numeric values.
        raw = p.get("sequenceNumber", "0")
        try:
            return (0, float(raw))
        except (TypeError, ValueError):
            return (1, 0.0)

    # Deferred period reopen: END_PERIOD closes all stints, but the next
    # period's stints must only open if another period actually happens.
    # Reopening unconditionally created a phantom 300s OT block for every
    # player at the end of regulation (audit bug 1.2).
    pending_reopen_period: Optional[int] = None

    for play in sorted(plays, key=_seq_key):
        play_type = play.get("type", {}).get("id", "")
        period = play.get("period", {}).get("number", current_period)
        clock_str = play.get("clock", {}).get("displayValue", "0:00")
        clock_secs = _clock_to_secs(clock_str)

        # Track current score from every play
        hs = play.get("homeScore")
        as_ = play.get("awayScore")
        if hs is not None:
            current_home = int(hs)
        if as_ is not None:
            current_away = int(as_)
        current_period = period

        # Materialize the deferred reopen only when play in a real new period
        # arrives (END_GAME right after END_PERIOD → no reopen, no phantoms).
        if (pending_reopen_period is not None
                and play_type != TYPE_END_GAME
                and period >= pending_reopen_period):
            _open_stints_for_players(
                on_court, period, _period_start_secs(period),
                current_home, current_away,
            )
            pending_reopen_period = None

        # ── Accumulate box events ─────────────────────────────────────────
        box_event = _classify_play(play)
        if box_event is not None:
            evt, evt_team_id = box_event
            if evt_team_id in box_state:
                bs = box_state[evt_team_id]
                if evt == "fgm2":
                    bs["fgm"] += 1
                    bs["fga"] += 1
                elif evt == "fgm3":
                    bs["fgm"] += 1
                    bs["fga"] += 1
                    bs["fg3m"] += 1
                elif evt == "fga_miss":
                    bs["fga"] += 1
                elif evt == "ftm":
                    bs["fta"] += 1
                elif evt == "fta_miss":
                    bs["fta"] += 1
                elif evt == "tov":
                    bs["tov"] += 1
                elif evt == "oreb":
                    bs["oreb"] += 1
                elif evt == "dreb":
                    bs["dreb"] += 1

        if play_type == TYPE_SUBSTITUTION:
            team_id = str(play.get("team", {}).get("id", ""))
            participants = play.get("participants", [])
            if not participants:
                continue
            ath_id = str(participants[0].get("athlete", {}).get("id", ""))
            text = play.get("text", "").lower()

            if "subbing out" in text:
                # Player leaving the court
                stint = _close_stint(ath_id, clock_secs, current_home, current_away)
                if stint:
                    completed.append(stint)
                on_court.get(team_id, set()).discard(ath_id)

            elif "subbing in" in text:
                # Player entering the court. If a stint is somehow still
                # active (missed sub-out event), close it first so stored
                # stints can never overlap for one player.
                if ath_id in active_stints:
                    stint = _close_stint(ath_id, clock_secs,
                                         current_home, current_away)
                    if stint:
                        completed.append(stint)
                on_court.setdefault(team_id, set()).add(ath_id)
                home_snap = dict(box_state[home_espn_team_id])
                away_snap = dict(box_state[away_espn_team_id])
                active_stints[ath_id] = (
                    player_stint_idx[ath_id],
                    period,
                    clock_secs,
                    current_home,
                    current_away,
                    team_id,
                    home_snap,
                    away_snap,
                )

        elif play_type == TYPE_END_PERIOD:
            # Close all active stints at period end (clock=0)
            for ath_id in list(active_stints.keys()):
                stint = _close_stint(ath_id, 0, current_home, current_away)
                if stint:
                    completed.append(stint)

            # Defer the reopen until a play in the next period actually
            # arrives — reopening here fabricated a full OT stint block at
            # the end of regulation for every game (audit bug 1.2).
            pending_reopen_period = period + 1

        elif play_type == TYPE_END_GAME:
            # Close all remaining active stints
            for ath_id in list(active_stints.keys()):
                stint = _close_stint(ath_id, 0, current_home, current_away)
                if stint:
                    completed.append(stint)

    # Safety net: close any stints still open at the very end
    for ath_id in list(active_stints.keys()):
        stint = _close_stint(ath_id, 0, current_home, current_away)
        if stint:
            completed.append(stint)

    return completed


# ── Command ───────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Reconstruct NCAA player lineup stints from ESPN play-by-play."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True,
            help="Ending season year (e.g., 2026)",
        )
        parser.add_argument(
            "--workers", type=int, default=1,
            help="Parallel fetch workers (default 1; ESPN max ~4)",
        )
        parser.add_argument(
            "--sleep", type=float, default=0.8,
            help="Seconds to sleep between ESPN requests per worker (default 0.8)",
        )
        parser.add_argument(
            "--limit", type=int, default=0,
            help="Cap number of games (for testing; 0 = all)",
        )
        parser.add_argument(
            "--batch-size", type=int, default=100,
            help="Games to fetch+write per batch (default 100; controls memory use)",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Delete existing PlayerGameStint rows for each game before reinserting",
        )
        parser.add_argument(
            "--game-ids", nargs="+", type=int, default=None,
            help="Restrict to these Game primary keys (targeted repair re-sync; "
                 "combine with --force)",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Fetch plays and print stats but do not write to database",
        )

    def handle(self, *args, **options):
        season_year: int = options["season"]
        workers: int     = max(1, options["workers"])
        sleep: float     = options["sleep"]
        limit: int       = options["limit"]
        batch_size: int  = max(10, options["batch_size"])
        force: bool      = options["force"]
        dry_run: bool    = options["dry_run"]

        self.stdout.write(
            f"[sync_ncaa_pbp] season={season_year}  workers={workers}"
            + (" [DRY RUN]" if dry_run else "")
            + (" [FORCE]" if force else "")
        )

        # ── Build lookup maps ─────────────────────────────────────────────────
        espn_team_map: dict[str, Team] = {}
        for ext in TeamExternalId.objects.filter(source="espn").select_related("team"):
            espn_team_map[ext.external_id] = ext.team

        team_pk_to_espn: dict[int, str] = {v.pk: k for k, v in espn_team_map.items()}

        # espn_athlete_id → Player
        player_map: dict[str, Player] = {
            p.espn_athlete_id: p
            for p in Player.objects.all()
        }

        # ── Resolve ESPN event IDs ────────────────────────────────────────────
        games_qs = (
            Game.objects.filter(season_year=season_year, status="final")
            .select_related("home_team", "away_team")
            .order_by("game_date")
        )
        if options.get("game_ids"):
            games_qs = games_qs.filter(pk__in=options["game_ids"])
        all_games = list(games_qs)

        if not force:
            done_game_ids = set(
                PlayerGameStint.objects.filter(
                    game__season_year=season_year
                ).values_list("game_id", flat=True).distinct()
            )
            all_games = [g for g in all_games if g.pk not in done_game_ids]

        if limit:
            all_games = all_games[:limit]

        # Also only process games that have PlayerGameStats (so we have starters)
        has_player_stats = set(
            PlayerGameStats.objects.filter(
                game__season_year=season_year,
                starter=True,
            ).values_list("game_id", flat=True).distinct()
        )
        all_games = [g for g in all_games if g.pk in has_player_stats]

        # Resolve ESPN event IDs (same strategy as sync_ncaa_player_gamelogs)
        game_espn_map: dict[int, str] = {}

        espn_direct = [g for g in all_games if g.source == "espn"]
        ncaa_sourced = [g for g in all_games if g.source != "espn"]

        for g in espn_direct:
            game_espn_map[g.pk] = g.source_game_id

        if ncaa_sourced:
            self.stdout.write(
                f"Resolving ESPN IDs for {len(ncaa_sourced)} NCAA-sourced games..."
            )
            import requests as _requests
            by_date = defaultdict(list)
            for g in ncaa_sourced:
                by_date[g.game_date].append(g)

            client = ESPNAPIClient(rate_limit_delay=sleep)
            resolved = 0
            for game_date, day_games in sorted(by_date.items()):
                date_str = game_date.strftime("%Y%m%d")
                try:
                    client._rate_limit()
                    url = f"{client.BASE_URL}/scoreboard"
                    resp = client.session.get(
                        url,
                        params={"dates": date_str, "groups": "50", "limit": "500"},
                        timeout=client.timeout,
                    )
                    resp.raise_for_status()
                    events = resp.json().get("events", [])
                except Exception as exc:
                    logger.warning("Scoreboard fetch failed %s: %s", game_date, exc)
                    continue

                event_lookup: dict[frozenset, str] = {}
                for event in events:
                    comp = event.get("competitions", [{}])[0]
                    team_ids = frozenset(
                        str(c.get("team", {}).get("id", ""))
                        for c in comp.get("competitors", [])
                    )
                    if team_ids:
                        event_lookup[team_ids] = event["id"]

                for g in day_games:
                    home_espn = team_pk_to_espn.get(g.home_team_id, "")
                    away_espn = team_pk_to_espn.get(g.away_team_id, "")
                    if not home_espn or not away_espn:
                        continue
                    key = frozenset({home_espn, away_espn})
                    if key in event_lookup:
                        game_espn_map[g.pk] = event_lookup[key]
                        resolved += 1

            self.stdout.write(
                f"  Resolved {resolved}/{len(ncaa_sourced)} NCAA→ESPN IDs."
            )

        game_list = [(g, game_espn_map[g.pk]) for g in all_games if g.pk in game_espn_map]
        total = len(game_list)
        self.stdout.write(
            f"Processing {total} games in batches of {batch_size}..."
        )

        if total == 0:
            self.stdout.write("Nothing to do.")
            return

        # ── Build starter map per game ────────────────────────────────────────
        # game_pk → {espn_athlete_id: espn_team_id}
        starter_rows = (
            PlayerGameStats.objects.filter(
                game_id__in=[g.pk for g, _ in game_list],
                starter=True,
            ).select_related("player", "team")
        )
        starters_by_game: dict[int, dict[str, str]] = defaultdict(dict)
        for row in starter_rows:
            ath_id = row.player.espn_athlete_id
            espn_tid = team_pk_to_espn.get(row.team_id, "") if row.team_id else ""
            if ath_id and espn_tid:
                starters_by_game[row.game_id][ath_id] = espn_tid

        stints_created = 0
        games_processed = 0
        games_skipped = 0

        def _fetch(game_pk, espn_id):
            return game_pk, _fetch_plays(espn_id, sleep)

        total_batches = (total + batch_size - 1) // batch_size

        for batch_start in range(0, total, batch_size):
            batch = game_list[batch_start: batch_start + batch_size]
            batch_num = batch_start // batch_size + 1
            self.stdout.write(
                f"  Batch {batch_num}/{total_batches}: "
                f"games {batch_start + 1}–{min(batch_start + batch_size, total)}"
            )

            # ── Fetch plays for this batch in parallel ────────────────────────
            fetched: dict[int, list] = {}
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_fetch, g.pk, eid): g.pk for g, eid in batch
                }
                for fut in as_completed(futures):
                    gid, plays = fut.result()
                    fetched[gid] = plays

            # ── Reconstruct + write stints for this batch ─────────────────────
            for game_obj, _ in batch:
                plays = fetched.get(game_obj.pk, [])
                if not plays:
                    games_skipped += 1
                    continue

                starters = starters_by_game.get(game_obj.pk, {})
                if len(starters) < 5:
                    games_skipped += 1
                    continue

                home_espn = team_pk_to_espn.get(game_obj.home_team_id, "")
                away_espn = team_pk_to_espn.get(game_obj.away_team_id, "")
                if not home_espn or not away_espn:
                    games_skipped += 1
                    continue

                local_team_map: dict[str, Optional[Team]] = {
                    home_espn: espn_team_map.get(home_espn),
                    away_espn: espn_team_map.get(away_espn),
                }

                stints = reconstruct_stints(
                    plays=plays,
                    starters=starters,
                    home_espn_team_id=home_espn,
                    away_espn_team_id=away_espn,
                    player_map=player_map,
                    team_map=local_team_map,
                )

                if not stints:
                    games_skipped += 1
                    continue

                if dry_run:
                    pts_total = sum(
                        s["pts_scored"] + s["pts_allowed"] for s in stints
                    )
                    self.stdout.write(
                        f"  [dry-run] {game_obj.source_game_id}: "
                        f"{len(stints)} stints, pts_events={pts_total}"
                    )
                    stints_created += len(stints)
                    games_processed += 1
                    continue

                with transaction.atomic():
                    if force:
                        PlayerGameStint.objects.filter(game=game_obj).delete()

                    PlayerGameStint.objects.bulk_create(
                        [
                            PlayerGameStint(
                                player=s["player"],
                                game=game_obj,
                                team=s["team"],
                                stint_index=s["stint_index"],
                                period=s["period"],
                                clock_start_secs=s["clock_start_secs"],
                                clock_end_secs=s["clock_end_secs"],
                                secs_on=s["secs_on"],
                                pts_scored=s["pts_scored"],
                                pts_allowed=s["pts_allowed"],
                                plus_minus=s["plus_minus"],
                                # Box events
                                team_fgm=s["team_fgm"],
                                team_fga=s["team_fga"],
                                team_fg3m=s["team_fg3m"],
                                team_fta=s["team_fta"],
                                team_tov=s["team_tov"],
                                team_oreb=s["team_oreb"],
                                team_dreb=s["team_dreb"],
                                opp_fgm=s["opp_fgm"],
                                opp_fga=s["opp_fga"],
                                opp_fg3m=s["opp_fg3m"],
                                opp_fta=s["opp_fta"],
                                opp_tov=s["opp_tov"],
                                opp_oreb=s["opp_oreb"],
                                opp_dreb=s["opp_dreb"],
                            )
                            for s in stints
                        ],
                        update_conflicts=True,
                        unique_fields=["player", "game", "stint_index"],
                        update_fields=[
                            "team", "period", "clock_start_secs", "clock_end_secs",
                            "secs_on", "pts_scored", "pts_allowed", "plus_minus",
                            "team_fgm", "team_fga", "team_fg3m", "team_fta",
                            "team_tov", "team_oreb", "team_dreb",
                            "opp_fgm", "opp_fga", "opp_fg3m", "opp_fta",
                            "opp_tov", "opp_oreb", "opp_dreb",
                        ],
                    )

                stints_created += len(stints)
                games_processed += 1

            # Explicitly free batch memory before next iteration
            del fetched

        self.stdout.write(
            self.style.SUCCESS(
                f"Done.  games_processed={games_processed}  "
                f"games_skipped={games_skipped}  "
                f"stints={'created' if not dry_run else 'would-create'}={stints_created}"
                + (" [DRY RUN]" if dry_run else "")
            )
        )
