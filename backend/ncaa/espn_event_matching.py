"""
Match NCAA-sourced games (stored without an ESPN event id) to ESPN scoreboard events.

Used by sync_ncaa_player_gamelogs and sync_ncaa_pbp. The rules are pure: the caller passes a
`day_entries(date)` callable (scoreboard_day_entries builds the real one, fetching each date once), so
they can be tested without the network. resolve_games and report_unresolved are the shared driver.

Rules, in order, for the game's date and then the day before (late tips: Game.game_date can be the
UTC date, a day after the date ESPN lists the game under):
  1. Both teams have an ESPN id: the event with both teams (the original rule). On the game's own
     date no score check is applied, as before.
  2. One team has an ESPN id (usually a non-D1 opponent without one): the event with that team. A
     team plays at most once a day, but a postponed or canceled event can share the day, so those
     are dropped; an event against a different team we know (a mapped ESPN id) is a different game.
  Matches by rule 2, and any match on the day before, must also have the game's final score.
Anything else is unresolved, with a reason, so the sync can print it instead of skipping silently.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable, Iterable

# ESPN status names for events that never produced a box score
_DEAD_STATUSES = {"STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED", "STATUS_FORFEIT", "STATUS_SUSPENDED"}


@dataclass(frozen=True)
class EventEntry:
    """One scoreboard event, reduced to what matching needs."""
    event_id: str
    scores: dict  # ESPN team id -> score (int) or None
    status: str = ""

    @property
    def team_ids(self) -> frozenset:
        return frozenset(self.scores)

    @property
    def dead(self) -> bool:
        return self.status in _DEAD_STATUSES


@dataclass(frozen=True)
class Match:
    event_id: str | None
    how: str      # "both teams", "one team", plus ", day before" — or the reason it failed
    ok: bool
    # One-team matches: the event's other team (the side we have no ESPN id for); else ""
    other_espn_id: str = ""


def entries_from_scoreboard(events: Iterable[dict]) -> list[EventEntry]:
    """EventEntry list from an ESPN scoreboard response's `events`."""
    out = []
    for event in events or []:
        comp = (event.get("competitions") or [{}])[0]
        scores = {}
        for c in comp.get("competitors", []):
            tid = str((c.get("team") or {}).get("id", ""))
            if not tid:
                continue
            try:
                scores[tid] = int(c.get("score")) if c.get("score") not in (None, "") else None
            except (TypeError, ValueError):
                scores[tid] = None
        status = ((comp.get("status") or event.get("status") or {}).get("type") or {}).get("name", "")
        if scores and event.get("id"):
            out.append(EventEntry(str(event["id"]), scores, status))
    return out


def _score_matches(entry: EventEntry, home_score, away_score) -> bool:
    got = sorted(s for s in entry.scores.values() if s is not None)
    return len(got) == 2 and got == sorted([home_score, away_score])


def match_espn_event(
    game_date: dt.date,
    home_espn: str,
    away_espn: str,
    home_score: int | None,
    away_score: int | None,
    day_entries: Callable[[dt.date], list[EventEntry] | None],
    known_espn_ids: frozenset | set = frozenset(),
) -> Match:
    """
    ESPN event for one game. `day_entries(date)` returns that date's events, or None when the
    scoreboard could not be fetched. `known_espn_ids` are all mapped ESPN team ids (used to reject a
    one-team match against a different known team).
    """
    if not home_espn and not away_espn:
        return Match(None, "no ESPN id for either team", False)
    both = bool(home_espn and away_espn)
    anchor = home_espn or away_espn
    fetch_failed = []
    known_opponent = None  # an event the one-team rule dropped because its opponent is another mapped team

    for offset in (0, 1):
        day = game_date - dt.timedelta(days=offset)
        entries = day_entries(day)
        if entries is None:
            fetch_failed.append(day)
            continue
        live = [e for e in entries if not e.dead]
        if both:
            cands = [e for e in live if {home_espn, away_espn} <= e.team_ids]
        else:
            # the opponent's ESPN id is unknown to us; an event against another team we know is a different game
            with_anchor = [e for e in live if anchor in e.team_ids]
            cands = [e for e in with_anchor if not (e.team_ids - {anchor}) & set(known_espn_ids)]
            for e in with_anchor:
                if e not in cands and _score_matches(e, home_score, away_score):
                    known_opponent = known_opponent or (e.event_id, sorted(e.team_ids - {anchor})[0])
        if not both or offset:
            cands = [e for e in cands if _score_matches(e, home_score, away_score)]
        if len(cands) == 1:
            how = ("both teams" if both else "one team") + (", day before" if offset else "")
            other = "" if both else sorted(cands[0].team_ids - {anchor})[0]
            return Match(cands[0].event_id, how, True, other)
        if len(cands) > 1:
            return Match(None, f"ambiguous: {len(cands)} ESPN events on {day.isoformat()}", False)

    if fetch_failed and len(fetch_failed) == 2:
        return Match(None, "scoreboard fetch failed", False)
    if known_opponent:
        return Match(None, f"ESPN event {known_opponent[0]} has this score, but its opponent's ESPN id "
                           f"{known_opponent[1]} belongs to another of our teams (duplicate team row?)", False)
    return Match(None, "no ESPN event on the game's date or the day before"
                 + (" (one team without an ESPN id; score must match)" if not both else ""), False)


def flag_shared_events(matches: dict[int, Match]) -> dict[int, Match]:
    """
    Two games matched to the same ESPN event means a duplicate game in our data (seen 2026-11:
    the same game stored twice under two NCAA contest ids). Keep the lowest game id, unresolve the rest.
    """
    by_event: dict[str, list[int]] = {}
    for gid, m in matches.items():
        if m.ok:
            by_event.setdefault(m.event_id, []).append(gid)
    out = dict(matches)
    for event_id, gids in by_event.items():
        if len(gids) > 1:
            keep, *rest = sorted(gids)
            for gid in rest:
                out[gid] = Match(None, f"same ESPN event {event_id} as game {keep} (likely a duplicate game)", False)
    return out


def scoreboard_day_entries(client, logger=None) -> Callable[[dt.date], list[EventEntry] | None]:
    """day_entries for match_espn_event: that date's D1 scoreboard via `client` (an ESPNAPIClient),
    fetched once per date; None when the fetch fails."""
    boards: dict = {}

    def day_entries(day: dt.date):
        if day not in boards:
            try:
                client._rate_limit()
                resp = client.session.get(
                    f"{client.BASE_URL}/scoreboard",
                    params={"dates": day.strftime("%Y%m%d"), "groups": "50", "limit": "500"},
                    timeout=client.timeout,
                )
                resp.raise_for_status()
                boards[day] = entries_from_scoreboard(resp.json().get("events", []))
            except Exception as e:  # network, HTTP or JSON: that date is unresolvable this run
                if logger:
                    logger.warning(f"Scoreboard fetch failed for {day}: {e}")
                boards[day] = None
        return boards[day]

    return day_entries


def resolve_games(games, team_pk_to_espn: dict, known_espn_ids, day_entries) -> dict[int, Match]:
    """Match for every game (objects with pk, game_date, home/away_team_id, home/away_score)."""
    matches = {
        g.pk: match_espn_event(
            g.game_date,
            team_pk_to_espn.get(g.home_team_id, ""),
            team_pk_to_espn.get(g.away_team_id, ""),
            g.home_score, g.away_score, day_entries, known_espn_ids,
        )
        for g in games
    }
    return flag_shared_events(matches)


def report_unresolved(write, matches: dict[int, Match], games) -> dict[int, str]:
    """
    Print the resolution summary and every game left without an ESPN event (count, ids, reasons) through
    `write(text, warn: bool)`. Returns {game pk: reason} for the unresolved games.
    """
    by_pk = {g.pk: g for g in games}
    unresolved = {pk: m.how for pk, m in matches.items() if not m.ok}
    how: dict[str, int] = {}
    for m in matches.values():
        if m.ok:
            how[m.how] = how.get(m.how, 0) + 1
    write(f"  Resolved {len(matches) - len(unresolved)}/{len(matches)} NCAA games to ESPN event IDs"
          + (f" ({', '.join(f'{k}: {v}' for k, v in sorted(how.items()))})" if how else "") + ".", False)
    if unresolved:
        write(f"  Unresolved: {len(unresolved)} games — ids {sorted(unresolved)}", True)
        by_reason: dict[str, list] = {}
        for pk, reason in unresolved.items():
            by_reason.setdefault(reason, []).append(pk)
        for reason, pks in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
            write(f"    {len(pks):>4}  {reason}", True)
        for pk in sorted(unresolved):
            g = by_pk[pk]
            write(f"      {pk}  {g.game_date}  {g.home_team.slug} v {g.away_team.slug}: {unresolved[pk]}", False)
    return unresolved

