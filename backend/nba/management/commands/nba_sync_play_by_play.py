"""
Management command: nba_sync_play_by_play

Fetches NBA play-by-play data from PlayByPlayV3, parses lineup events into
contiguous player stints, validates lineup integrity, and writes NBAPlayerGameStint
rows. Also marks NBAGame.pbp_synced=True on success.

Usage:
  python manage.py nba_sync_play_by_play --season 2026
  python manage.py nba_sync_play_by_play --season 2026 --game-id 0022500001
  python manage.py nba_sync_play_by_play --season 2026 --workers 3 --sleep 0.8
  python manage.py nba_sync_play_by_play --season 2026 --force   # reprocess all games

Design:
  Checkpoint/resume: skips games where pbp_synced=True (cleared by --force).
  10-player validation: stints failing 5v5 check are dropped; games with > 5%
    failure rate get pbp_quality_flag=True and are excluded from RAPM training.
  Simultaneous sub batching: subs within 1 second at same clock value are
    treated as a single lineup change before closing the previous stint.

Period clock constants (NBA regulation):
  Quarters 1-4: 12 min = 720 seconds each
  Overtime periods: 5 min = 300 seconds each
"""

from __future__ import annotations

import logging
import re
import sys
import unicodedata
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from nba.models import NBAGame, NBAPlayer, NBAPlayerGameStint, NBAPlayerGameStats, NBATeam
from nba.providers.nba_api_provider import NBAApiProvider
from nba.providers.base import RawPlayEvent

logger = logging.getLogger(__name__)

# ── Period constants ──────────────────────────────────────────────────────────

QUARTER_SECS = 720   # 12 min quarters
OT_SECS      = 300   # 5 min OT periods

# Minimum possession count to include a stint row in RAPM training (not enforced here —
# the RAPM solver filters; we write all stints regardless).

# Regulation game duration tolerance for duration check (soft warning only)
REGULATION_SECS = 2880  # 4 × 720
DURATION_TOLERANCE = 90  # ±90 seconds


def _period_start_secs(period: int) -> int:
    return QUARTER_SECS if period <= 4 else OT_SECS


# ── PlayByPlayV3 action type constants ────────────────────────────────────────
# PlayByPlayV3 uses these action_type strings (NOT "2pt"/"3pt"/"freethrow").
_FGA_TYPES = {"made shot", "missed shot", "heave"}

# ── Name-based player lookup helpers ─────────────────────────────────────────

def _normalize_name(name: str) -> str:
    """Lowercase + strip accents. 'Porziņģis' → 'porzingis'."""
    nfkd = unicodedata.normalize("NFKD", name)
    return nfkd.encode("ascii", "ignore").decode("ascii").lower().strip()


def _build_name_lookup(player_pk_map: dict[int, int]) -> dict[str, int]:
    """
    Build normalized name → NBAPlayer.pk lookup for PlayByPlayV3 description parsing.
    Entries: full name lower, last-name(s) lower, base last name (no Jr./II/III/IV).
    Later entries win on key collision (arbitrary but consistent).
    """
    from nba.models import NBAPlayer
    name_to_pk: dict[str, int] = {}
    for player in NBAPlayer.objects.filter(
        player_id__in=player_pk_map.keys()
    ).only("pk", "player_id", "name"):
        pk = player_pk_map[player.player_id]
        norm = _normalize_name(player.name)
        name_to_pk[norm] = pk

        parts = norm.split()
        if len(parts) > 1:
            last = " ".join(parts[1:])          # "smith jr.", "van vleet"
            base = re.sub(r"\b(jr\.?|sr\.?|ii|iii|iv)\b", "", last).strip()
            for key in (last, base, parts[-1]):
                if key and key not in name_to_pk:
                    name_to_pk[key] = pk
    return name_to_pk


def _build_roster_name_lookup(player_pks: set[int]) -> dict[str, int]:
    """
    Build name → pk for a specific game roster (~13 players per team).
    Unlike the global lookup, this OVERWRITES on collision — at team scope
    there are no cross-era collisions, so last-writer wins is fine.
    Unicode-normalized so accented names match ASCII PBP descriptions.
    """
    from nba.models import NBAPlayer
    name_map: dict[str, int] = {}
    for player in NBAPlayer.objects.filter(pk__in=player_pks).only("pk", "name"):
        norm = _normalize_name(player.name)
        name_map[norm] = player.pk
        parts = norm.split()
        if len(parts) > 1:
            last = " ".join(parts[1:])
            base = re.sub(r"\b(jr\.?|sr\.?|ii|iii|iv)\b", "", last).strip()
            for key in (last, base, parts[-1]):
                if key:
                    name_map[key] = player.pk  # override OK: team scope, no cross-era collisions
    return name_map


def _parse_sub_incoming(description: str) -> str:
    """
    Extract the incoming player name from 'SUB: Eason FOR Smith Jr.' → 'eason'.
    Returns lowercase stripped name, or '' on parse failure.
    """
    desc = description.strip()
    upper = desc.upper()
    if not upper.startswith("SUB:"):
        return ""
    rest = desc[4:].strip()
    idx = rest.upper().find(" FOR ")
    if idx < 0:
        return ""
    return _normalize_name(rest[:idx].strip())


def _lookup_name(name: str, name_to_pk: dict[str, int]) -> "int | None":
    """Try full name, then each suffix-trimmed form."""
    if not name:
        return None
    pk = name_to_pk.get(name)
    if pk is not None:
        return pk
    # Try last word only
    parts = name.split()
    if len(parts) > 1:
        pk = name_to_pk.get(" ".join(parts[1:]))
        if pk is not None:
            return pk
        pk = name_to_pk.get(parts[-1])
    return pk


def _is_offensive_rebound(description: str) -> bool:
    """
    PlayByPlayV3 rebound subType is always 'unknown'.
    Detect offensive rebound from description pattern '(Off:N Def:M)' where N > 0.
    """
    m = re.search(r'\(Off:(\d+)', description)
    return bool(m and int(m.group(1)) > 0)


def _ot_periods_for_secs(total_secs: int) -> int:
    """Infer number of OT periods from total game seconds."""
    extra = max(0, total_secs - REGULATION_SECS)
    return (extra + OT_SECS - 1) // OT_SECS


# ── Stint state ───────────────────────────────────────────────────────────────

BOX_KEYS = ("fgm", "fga", "fg3m", "fta", "tov", "oreb", "dreb")


@dataclass
class StintState:
    player_pk: int
    team_pk:   int        # NBATeam pk
    is_home:   bool       # True if this player's team is home
    period:    int
    clock_start: int      # seconds remaining in period at open
    score_home_start: int
    score_away_start: int
    # Running box snapshot at stint open (keyed "home_fgm", "away_tov", etc.)
    box_start: dict = field(default_factory=dict)


# ── Game parser ───────────────────────────────────────────────────────────────

def _parse_game(
    game: NBAGame,
    events: list[RawPlayEvent],
    player_pk_map: dict[int, int],        # NBA.com player_id → NBAPlayer.pk
    team_pk_map: dict[int, int],          # NBA.com team_id → NBATeam.pk
    name_to_pk: dict[str, int],           # normalized name → NBAPlayer.pk (global)
    game_roster: "dict[int, set[int]]",   # team.pk → set of NBAPlayer.pk for THIS game
) -> tuple[list[dict], bool, str, list[str]]:
    """
    Parse a game's PBP events into stint records.

    Returns:
        (stints_list, quality_flag, message)
        quality_flag = True if > 5% of stints fail 10-player check.
    """
    if not events:
        return [], False, "no events", []

    failed_lookups: list[str] = []  # names that could not be resolved

    home_team_id = game.home_team.nba_team_id
    away_team_id = game.away_team.nba_team_id
    home_team_pk = team_pk_map.get(home_team_id)
    away_team_pk = team_pk_map.get(away_team_id)

    # ── Team-constrained name lookup (eliminates cross-era "Williams" ambiguity) ─
    # Build fresh from each team's actual game roster (~13 players) so common
    # last names (James, Smith, Thompson) map to the correct current-game player,
    # not a historical namesake from a different era in the global lookup.
    home_pks = game_roster.get(home_team_pk, set())
    away_pks = game_roster.get(away_team_pk, set())
    home_name_to_pk = _build_roster_name_lookup(home_pks)
    away_name_to_pk = _build_roster_name_lookup(away_pks)

    def _lookup_for_team(name: str, is_home: bool) -> "int | None":
        # Primary: team-constrained (correct player for this game's roster)
        pk = _lookup_name(name, home_name_to_pk if is_home else away_name_to_pk)
        if pk is not None:
            return pk
        # Fallback: global lookup for players missing from game_roster (brief DNP
        # appearances with no box score row). Cross-era collision risk is low for
        # fringe players; prefer this over None which guarantees lineup failure.
        return _lookup_name(name, name_to_pk)

    # ── Pass 1: reconstruct starting lineup from period 1 events ─────────────

    home_starters: set[int] = set()   # NBAPlayer.pk
    away_starters: set[int] = set()
    home_subbed_in: set[int] = set()
    away_subbed_in: set[int] = set()

    for ev in events:
        if ev.period != 1:
            break
        tid = ev.team_id
        if tid is None:
            continue
        is_home = (tid == home_team_id)
        subbed_in = home_subbed_in if is_home else away_subbed_in
        starters  = home_starters  if is_home else away_starters

        if ev.action_type == "substitution":
            # personId = OUTGOING player; parse incoming from description
            outgoing_pk = player_pk_map.get(ev.person_id) if ev.person_id else None
            incoming_name = _parse_sub_incoming(ev.description)
            incoming_pk = _lookup_for_team(incoming_name, is_home)

            if outgoing_pk and outgoing_pk not in subbed_in:
                starters.add(outgoing_pk)
            if incoming_pk:
                subbed_in.add(incoming_pk)
            elif incoming_name:
                failed_lookups.append(f"P1:{incoming_name}")
        elif ev.person_id is not None:
            pk = player_pk_map.get(ev.person_id)
            if pk is not None and pk not in subbed_in:
                starters.add(pk)

    if len(home_starters) < 5 or len(away_starters) < 5:
        return [], False, (
            f"could not reconstruct starting lineup "
            f"(home={len(home_starters)}, away={len(away_starters)})"
        ), []

    # ── Pass 2: process all events ────────────────────────────────────────────

    on_court_home: set[int] = set(list(home_starters)[:5])
    on_court_away: set[int] = set(list(away_starters)[:5])

    active_stints: dict[int, StintState] = {}   # player_pk → StintState
    completed_stints: list[dict] = []
    stint_counter: dict[int, int] = defaultdict(int)  # player_pk → next stint_index

    # Running box totals (per team, absolute cumulative for the game)
    home_box: dict[str, int] = {k: 0 for k in BOX_KEYS}
    away_box: dict[str, int] = {k: 0 for k in BOX_KEYS}

    current_score_home = 0
    current_score_away = 0
    current_period = 1

    def _box_snapshot() -> dict:
        snap = {}
        for k in BOX_KEYS:
            snap[f"home_{k}"] = home_box[k]
            snap[f"away_{k}"] = away_box[k]
        return snap

    def _open_stint(pk: int, is_home: bool, period: int, clock: int) -> None:
        team_pk = home_team_pk if is_home else away_team_pk
        active_stints[pk] = StintState(
            player_pk=pk,
            team_pk=team_pk,
            is_home=is_home,
            period=period,
            clock_start=clock,
            score_home_start=current_score_home,
            score_away_start=current_score_away,
            box_start=_box_snapshot(),
        )

    def _close_stint(pk: int, clock_end: int) -> dict | None:
        st = active_stints.pop(pk, None)
        if st is None:
            return None
        secs_on = max(0, st.clock_start - clock_end)
        snap_now = _box_snapshot()

        if st.is_home:
            pts_scored  = current_score_home - st.score_home_start
            pts_allowed = current_score_away - st.score_away_start
            team_box = {k: max(0, home_box[k] - st.box_start[f"home_{k}"]) for k in BOX_KEYS}
            opp_box  = {k: max(0, away_box[k] - st.box_start[f"away_{k}"]) for k in BOX_KEYS}
        else:
            pts_scored  = current_score_away - st.score_away_start
            pts_allowed = current_score_home - st.score_home_start
            team_box = {k: max(0, away_box[k] - st.box_start[f"away_{k}"]) for k in BOX_KEYS}
            opp_box  = {k: max(0, home_box[k] - st.box_start[f"home_{k}"]) for k in BOX_KEYS}

        idx = stint_counter[pk]
        stint_counter[pk] += 1

        return {
            "player_pk":       pk,
            "team_pk":         st.team_pk,
            "stint_index":     idx,
            "period":          st.period,
            "clock_start_secs": st.clock_start,
            "clock_end_secs":  clock_end,
            "secs_on":         secs_on,
            "pts_scored":      max(0, pts_scored),
            "pts_allowed":     max(0, pts_allowed),
            "plus_minus":      pts_scored - pts_allowed,
            "team_fgm":  team_box["fgm"],
            "team_fga":  team_box["fga"],
            "team_fg3m": team_box["fg3m"],
            "team_fta":  team_box["fta"],
            "team_tov":  team_box["tov"],
            "team_oreb": team_box["oreb"],
            "team_dreb": team_box["dreb"],
            "opp_fgm":   opp_box["fgm"],
            "opp_fga":   opp_box["fga"],
            "opp_fg3m":  opp_box["fg3m"],
            "opp_fta":   opp_box["fta"],
            "opp_tov":   opp_box["tov"],
            "opp_oreb":  opp_box["oreb"],
            "opp_dreb":  opp_box["dreb"],
        }

    def _flush_period_end(period: int) -> None:
        for pk in list(active_stints.keys()):
            st = _close_stint(pk, 0)
            if st:
                completed_stints.append(st)

    def _reopen_for_next_period(period: int) -> None:
        clock_start = _period_start_secs(period)
        for pk in on_court_home:
            _open_stint(pk, True, period, clock_start)
        for pk in on_court_away:
            _open_stint(pk, False, period, clock_start)

    # Open initial stints at Q1 start
    for pk in on_court_home:
        _open_stint(pk, True, 1, QUARTER_SECS)
    for pk in on_court_away:
        _open_stint(pk, False, 1, QUARTER_SECS)

    # ── Event processing ──────────────────────────────────────────────────────

    i = 0
    while i < len(events):
        ev = events[i]

        # Update running score from events that have score data
        if ev.score_home is not None:
            current_score_home = ev.score_home
        if ev.score_away is not None:
            current_score_away = ev.score_away

        # ── Period transition ─────────────────────────────────────────────────
        if ev.action_type == "period":
            if ev.sub_type == "end":
                _flush_period_end(current_period)
            elif ev.sub_type == "start":
                current_period = ev.period
                _reopen_for_next_period(current_period)
            i += 1
            continue

        # ── Box event accumulation ────────────────────────────────────────────
        # PlayByPlayV3 action types: "made shot", "missed shot", "free throw",
        # "rebound" (subType always "unknown"), "turnover"
        tid = ev.team_id
        if tid is not None:
            box   = home_box if tid == home_team_id else away_box
            atype = ev.action_type
            if atype in _FGA_TYPES:
                box["fga"] += 1
                if ev.shot_result == "Made":
                    box["fgm"] += 1
                    desc_up = ev.description.upper()
                    if "3PT" in desc_up or "3-PT" in desc_up:
                        box["fg3m"] += 1
            elif atype == "free throw":
                box["fta"] += 1
            elif atype == "rebound":
                if _is_offensive_rebound(ev.description):
                    box["oreb"] += 1
                else:
                    box["dreb"] += 1
            elif atype == "turnover":
                box["tov"] += 1

        # ── Substitution batch (1-second window) ──────────────────────────────
        # PlayByPlayV3: personId = OUTGOING player; incoming parsed from description.
        if ev.action_type == "substitution":
            batch_clock = ev.clock_secs
            batch_period = ev.period
            outs_home: list[int] = []
            outs_away: list[int] = []
            ins_home:  list[int] = []
            ins_away:  list[int] = []

            # Collect all subs at this clock value (within 1 sec).
            # on_court_home/away are not modified during collection, so checking
            # them here reflects the pre-batch state — used to guard against
            # NBA.com PBP data errors where the incoming player is already on court
            # (e.g. "SUB: Davis FOR Ajinca" when Davis is already playing).
            # Skipping the entire event preserves 5v5 lineup integrity.
            j = i
            while j < len(events) and events[j].action_type == "substitution":
                ev2 = events[j]
                if abs(ev2.clock_secs - batch_clock) > 1 or ev2.period != batch_period:
                    break
                is_home2 = (ev2.team_id == home_team_id)

                outgoing_pk = player_pk_map.get(ev2.person_id) if ev2.person_id else None

                incoming_name = _parse_sub_incoming(ev2.description)
                incoming_pk = _lookup_for_team(incoming_name, is_home2)

                court = on_court_home if is_home2 else on_court_away
                # Only process clean swaps: outgoing IS on court, incoming is NOT.
                # Any deviation corrupts the 5-player invariant — skip the whole event.
                if not (outgoing_pk is not None and outgoing_pk in court
                        and incoming_pk is not None and incoming_pk not in court):
                    logger.debug(
                        "skipping bad sub game=%s P%s@%s: out_pk=%s in_court=%s "
                        "in_pk=%s already_on=%s desc=%r",
                        game.game_id, batch_period, batch_clock,
                        outgoing_pk,
                        outgoing_pk in court if outgoing_pk is not None else "n/a",
                        incoming_pk,
                        incoming_pk in court if incoming_pk is not None else "n/a",
                        ev2.description,
                    )
                    j += 1
                    continue

                if outgoing_pk:
                    (outs_home if is_home2 else outs_away).append(outgoing_pk)
                if incoming_pk:
                    (ins_home if is_home2 else ins_away).append(incoming_pk)
                elif incoming_name:
                    failed_lookups.append(incoming_name)
                    logger.debug(
                        "sub lookup miss game=%s clock=%s name=%r home_keys=%d away_keys=%d",
                        game.game_id, ev2.clock_secs, incoming_name,
                        len(home_name_to_pk), len(away_name_to_pk),
                    )
                else:
                    failed_lookups.append(f"PARSE_FAIL:{ev2.description[:50]!r}")
                    logger.debug(
                        "sub desc parse failed game=%s clock=%s desc=%r",
                        game.game_id, ev2.clock_secs, ev2.description,
                    )

                j += 1

            # Close ALL active stints at this clock (not just the subs).
            # This ensures all 10 players in each lineup share identical
            # clock_start/clock_end, so the RAPM solver can group them by
            # (game_pk, period, clock_start, clock_end) into 5v5 observations.
            for pk in list(active_stints.keys()):
                st = _close_stint(pk, batch_clock)
                if st:
                    completed_stints.append(st)

            for pk in outs_home:
                on_court_home.discard(pk)
            for pk in outs_away:
                on_court_away.discard(pk)
            for pk in ins_home:
                on_court_home.add(pk)
            for pk in ins_away:
                on_court_away.add(pk)

            # Re-open stints for ALL players now on court at the new clock
            for pk in on_court_home:
                _open_stint(pk, True, batch_period, batch_clock)
            for pk in on_court_away:
                _open_stint(pk, False, batch_period, batch_clock)

            i = j
            continue

        i += 1

    # Close any remaining open stints at game end
    for pk in list(active_stints.keys()):
        st = _close_stint(pk, 0)
        if st:
            completed_stints.append(st)

    # ── 10-player validation ──────────────────────────────────────────────────
    # Group by stint_index to check that each lineup has 5+5

    # Build stint_index → {player_pk, team_pk} mapping by finding which players
    # share the same stint overlapping window. Simpler: use game-level stint grouping.
    # We use a proxy: for each point in time, the active lineup should be 5+5.
    # Instead of full validation here (expensive), we check per global stint
    # that home and away each have ≥1 representative with same stint_index.
    # Full 5-player-per-side validation is done via game-level grouping below.

    # Group stints by stint_index per player and build lineup snapshots per event
    # Simplified approach: validate by checking that completed_stints came from
    # periods with full 5+5 lineups. We already seed 5+5 starters — if any
    # substitution added wrong team player, lineups would diverge.
    # Hard validation: for each stint_index, count home vs away players.

    # Build a global stint ID: (player_pk, stint_index per player) → game-level index
    # by matching periods + clock windows. This is complex; instead use the known
    # fact that we open/close stints in batches and stints within same window share
    # a game-level index. We track this via a running global stint index.

    # Practical validation: after all events processed, count that for each stint
    # period+clock_start+clock_end window, we have 5 home and 5 away players.
    # We track this by grouping on (period, clock_start_secs, clock_end_secs) — stints
    # opened simultaneously will share these values (within 1-sec tolerance).

    total_stints_written = 0
    dropped_stints = 0

    # Group by approximate timing window to reconstruct lineup groups
    from collections import defaultdict as _dd
    lineup_groups: dict[tuple, list[dict]] = _dd(list)
    for st in completed_stints:
        # Key: (period, clock_start, clock_end) — all players in same window
        key = (st["period"], st["clock_start_secs"], st["clock_end_secs"])
        lineup_groups[key].append(st)

    valid_stints: list[dict] = []
    for key, group in lineup_groups.items():
        home_count = sum(1 for s in group if s["team_pk"] == home_team_pk)
        away_count = sum(1 for s in group if s["team_pk"] == away_team_pk)
        if home_count == 5 and away_count == 5:
            valid_stints.extend(group)
            total_stints_written += len(group)
        else:
            dropped_stints += len(group)

    total_groups = len(lineup_groups)
    dropped_groups = 0
    bad_group_samples: list[str] = []
    for key, group in lineup_groups.items():
        hc = sum(1 for s in group if s["team_pk"] == home_team_pk)
        ac = sum(1 for s in group if s["team_pk"] == away_team_pk)
        if hc != 5 or ac != 5:
            dropped_groups += 1
            if len(bad_group_samples) < 5:
                bad_group_samples.append(f"P{key[0]}@{key[1]}-{key[2]}:h{hc}a{ac}n{len(group)}")
    quality_flag = (total_groups > 0 and dropped_groups / total_groups > 0.05)

    # Duration check (soft warning)
    total_secs = sum(s["secs_on"] for s in valid_stints) // 10  # divide by 10 players
    ot_periods = _ot_periods_for_secs(total_secs)
    expected_secs = REGULATION_SECS + ot_periods * OT_SECS
    if abs(total_secs - expected_secs) > DURATION_TOLERANCE:
        logger.debug(
            "game %s: duration %ds expected ~%ds (OT=%d) — blowout garbage time likely",
            game.game_id, total_secs, expected_secs, ot_periods,
        )

    msg = (
        f"roster_h={len(home_pks)}/a={len(away_pks)}, "
        f"{len(valid_stints)} stints, {dropped_stints} dropped ({dropped_groups}/{total_groups} groups)"
    )
    if failed_lookups:
        msg += f", {len(failed_lookups)} missed sub lookups"
    if quality_flag:
        msg += f" [QUALITY FLAG] bad:{','.join(bad_group_samples)}"

    return valid_stints, quality_flag, msg, failed_lookups


# ── Management command ────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Ingest NBA play-by-play data into NBAPlayerGameStint rows"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--game-id", type=str, help="Process a single game only")
        parser.add_argument("--workers", type=int, default=1, help="Parallel fetch threads (max 3 recommended)")
        parser.add_argument("--sleep", type=float, default=0.8, help="Seconds between API calls")
        parser.add_argument("--force", action="store_true", help="Reprocess games already marked pbp_synced")
        parser.add_argument("--dry-run", action="store_true", help="Parse but do not write to database")
        parser.add_argument("--limit", type=int, help="Process at most N games (for testing)")

    def handle(self, *args, **options):
        season_year = options["season"]
        game_id_filter = options.get("game_id")
        workers = min(max(1, options["workers"]), 5)
        sleep = max(0.3, options["sleep"])
        force = options["force"]
        dry_run = options["dry_run"]
        limit = options.get("limit")

        self.stdout.write(f"\n[PBP SYNC] Season {season_year}")
        if dry_run:
            self.stdout.write("[DRY RUN] No writes")

        provider = NBAApiProvider(sleep_seconds=sleep, max_retries=3, timeout=60)

        # ── Build player and team lookup maps ─────────────────────────────────
        player_pk_map: dict[int, int] = {
            p.player_id: p.pk
            for p in NBAPlayer.objects.only("pk", "player_id")
        }
        team_pk_map: dict[int, int] = {
            t.nba_team_id: t.pk
            for t in NBATeam.objects.only("pk", "nba_team_id")
        }
        name_to_pk = _build_name_lookup(player_pk_map)
        self.stdout.write(f"  {len(player_pk_map)} players, {len(team_pk_map)} teams, {len(name_to_pk)} name keys")

        # ── Select games to process ───────────────────────────────────────────
        qs = NBAGame.objects.filter(
            season__year=season_year,
            status="Final",
            counts_toward_regular_season=True,
        ).select_related("home_team", "away_team", "season").order_by("date")

        if game_id_filter:
            qs = qs.filter(game_id=game_id_filter)
        elif not force:
            qs = qs.exclude(pbp_synced=True)

        if force and not game_id_filter:
            self.stdout.write("[FORCE] Clearing pbp_synced on all season games...")
            NBAGame.objects.filter(season__year=season_year).update(
                pbp_synced=False, pbp_synced_at=None, pbp_quality_flag=False
            )
            qs = qs.filter(season__year=season_year, status="Final", counts_toward_regular_season=True)

        pending = list(qs)
        if limit:
            pending = pending[:limit]

        total = len(pending)
        self.stdout.write(f"  {total} games to process")

        # Pre-fetch per-game rosters from existing box scores for team-constrained
        # name resolution inside _parse_game (eliminates same-name ambiguity).
        _roster_rows = NBAPlayerGameStats.objects.filter(
            game__game_id__in=[g.game_id for g in pending]
        ).values("game__game_id", "team_id", "player_id")
        game_id_to_roster: dict[str, dict[int, set[int]]] = {}
        for _row in _roster_rows:
            _gid = _row["game__game_id"]
            game_id_to_roster.setdefault(_gid, {}).setdefault(_row["team_id"], set()).add(_row["player_id"])

        if total == 0:
            self.stdout.write("Nothing to do.")
            return

        # ── Process games: fetch → parse → write per batch ───────────────────
        # Sequential by default (workers=1). With workers > 1, fetch a batch
        # of N games in parallel, then write all before the next batch.
        # This ensures pbp_synced=True is set after every game, so Ctrl+C
        # loses at most `workers` games of fetch work, not the entire season.
        if workers > 1:
            self.stdout.write(
                f"  workers={workers}: fetching in batches of {workers}, writing after each batch."
            )
        else:
            self.stdout.write("  Sequential mode (fetch → parse → write per game).")

        processed = 0
        skipped = 0
        quality_flagged = 0
        total_stints_written = 0

        def _fetch_one(game: NBAGame) -> tuple[str, list[RawPlayEvent]]:
            try:
                events = provider.get_play_by_play(game.game_id)
                return game.game_id, events
            except Exception as exc:
                logger.warning("PBP fetch failed for %s: %s", game.game_id, exc)
                return game.game_id, []

        # Process in batches of `workers` size
        batch_size = workers
        for batch_start in range(0, total, batch_size):
            batch = pending[batch_start: batch_start + batch_size]

            # Fetch batch (parallel if workers > 1, sequential if workers == 1)
            if workers == 1:
                batch_data = [_fetch_one(batch[0])]
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(_fetch_one, g): g for g in batch}
                    batch_data = [future.result() for future in as_completed(futures)]

            game_map_batch = {g.game_id: g for g in batch}

            for game_id_str, events in batch_data:
                game = game_map_batch.get(game_id_str)
                if game is None:
                    continue

                done = processed + skipped + 1
                stints, quality_flag, msg, failed_names = _parse_game(game, events, player_pk_map, team_pk_map, name_to_pk, game_id_to_roster.get(game_id_str, {}))

                if not stints:
                    self.stdout.write(f"  [{done}/{total}] [SKIP] {game_id_str}: {msg}")
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(f"  [{done}/{total}] [DRY]  {game_id_str}: {msg}")
                    processed += 1
                    total_stints_written += len(stints)
                    continue

                # ── Write stints + mark game synced ───────────────────────────
                player_fk_cache: dict[int, NBAPlayer] = {}
                team_fk_cache: dict[int, NBATeam] = {}
                stint_objs = []

                for s in stints:
                    pk = s["player_pk"]
                    if pk not in player_fk_cache:
                        try:
                            player_fk_cache[pk] = NBAPlayer.objects.get(pk=pk)
                        except NBAPlayer.DoesNotExist:
                            continue
                    tpk = s["team_pk"]
                    if tpk and tpk not in team_fk_cache:
                        try:
                            team_fk_cache[tpk] = NBATeam.objects.get(pk=tpk)
                        except NBATeam.DoesNotExist:
                            pass

                    stint_objs.append(NBAPlayerGameStint(
                        player=player_fk_cache[pk],
                        game=game,
                        team=team_fk_cache.get(tpk),
                        stint_index=s["stint_index"],
                        period=s["period"],
                        clock_start_secs=s["clock_start_secs"],
                        clock_end_secs=s["clock_end_secs"],
                        secs_on=s["secs_on"],
                        pts_scored=s["pts_scored"],
                        pts_allowed=s["pts_allowed"],
                        plus_minus=s["plus_minus"],
                        team_fgm=s["team_fgm"], team_fga=s["team_fga"],
                        team_fg3m=s["team_fg3m"], team_fta=s["team_fta"],
                        team_tov=s["team_tov"], team_oreb=s["team_oreb"],
                        team_dreb=s["team_dreb"],
                        opp_fgm=s["opp_fgm"], opp_fga=s["opp_fga"],
                        opp_fg3m=s["opp_fg3m"], opp_fta=s["opp_fta"],
                        opp_tov=s["opp_tov"], opp_oreb=s["opp_oreb"],
                        opp_dreb=s["opp_dreb"],
                    ))

                with transaction.atomic():
                    NBAPlayerGameStint.objects.bulk_create(
                        stint_objs,
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
                    NBAGame.objects.filter(pk=game.pk).update(
                        pbp_synced=True,
                        pbp_synced_at=timezone.now(),
                        pbp_quality_flag=quality_flag,
                    )

                processed += 1
                total_stints_written += len(stints)
                if quality_flag:
                    quality_flagged += 1
                    self.stdout.write(self.style.WARNING(f"  [{done}/{total}] [QFLAG] {game_id_str}: {msg}"))
                    if failed_names:
                        sample = ", ".join(repr(n) for n in failed_names[:8])
                        self.stdout.write(self.style.WARNING(f"            missed names: {sample}"))
                elif done % 25 == 0 or done == total:
                    self.stdout.write(f"  [{done}/{total}] {game_id_str}: {msg}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n[OK] {processed}/{total} games processed, "
                f"{skipped} skipped, {quality_flagged} quality-flagged, "
                f"{total_stints_written} stints written"
            )
        )
