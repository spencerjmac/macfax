"""
Find players that ESPN's box scores leave out, from ncaa.com box scores (via the NCAA API client).

Pure helpers (no DB, no network) used by data_fixes/2026-11-14_task10a_missing_players_ncaa.py:
  * eastern_date: the US-Eastern calendar date of a UTC tip (ncaa.com scoreboards are by Eastern date).
  * scoreboard_contests / match_contests: games on a scoreboard whose final score pair equals ours.
  * bind_side: the ncaa.com box side for one of our teams, by points (and FGA when both have it), never by name.
  * missing_lines: ncaa.com players with minutes or points whom our ESPN rows for that team-game lack
    (no row, or a row with no minutes and no points).
"""

import re
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def expected_minutes(periods: int) -> int:
    """Team player minutes in a game: 5 players x 40, plus 5 x 5 per overtime."""
    return 200 + 25 * (periods - 2)


def eastern_date(utc_iso: str) -> date:
    dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    return dt.astimezone(EASTERN).date()


def _int(v):
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def name_tokens(name: str) -> list:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`’]", "", s)
    toks = [t for t in re.split(r"[^a-z]+", s) if t]
    return [t for t in toks if t not in SUFFIXES]


def name_key(name: str) -> str:
    return "".join(name_tokens(name))


def scoreboard_contests(scoreboard: dict) -> list:
    """[{contest_id, home_score, away_score, home_seo, away_seo}] for final games on an ncaa.com scoreboard."""
    out = []
    for entry in scoreboard.get("games") or []:
        g = entry.get("game") or {}
        if (g.get("gameState") or "").lower() != "final":
            continue
        url = g.get("url") or ""
        cid = url.rstrip("/").split("/")[-1] if url else str(g.get("gameID") or "")
        out.append({"contest_id": cid,
                    "home_score": _int((g.get("home") or {}).get("score")),
                    "away_score": _int((g.get("away") or {}).get("score")),
                    "home_seo": ((g.get("home") or {}).get("names") or {}).get("seo", ""),
                    "away_seo": ((g.get("away") or {}).get("names") or {}).get("seo", "")})
    return out


def match_contests(home_score: int, away_score: int, contests: list) -> list:
    """Contests whose final score pair equals ours, either orientation (neutral-site home/away can differ)."""
    want = sorted((home_score, away_score))
    return [c for c in contests if sorted((c["home_score"] or -1, c["away_score"] or -1)) == want]


def bind_side(box: dict, points: int, fga=None):
    """The teamBoxscore entry for our team: unique by points; when both sides give FGA, it must agree."""
    sides = [tb for tb in box.get("teamBoxscore") or [] if _int((tb.get("teamStats") or {}).get("points")) == points]
    if len(sides) != 1:
        return None
    tb = sides[0]
    their_fga = _int((tb.get("teamStats") or {}).get("fieldGoalsAttempted"))
    if fga and their_fga and fga != their_fga:
        return None
    return tb


def player_line(p: dict) -> dict:
    """ncaa.com player stats -> MissingPlayerGameStats fields (NULL where the source has nothing)."""
    oreb, reb = _int(p.get("offensiveRebounds")), _int(p.get("totalRebounds"))
    return {
        "external_id": str(p.get("id")),
        "name": f"{(p.get('firstName') or '').strip()} {(p.get('lastName') or '').strip()}".strip(),
        "jersey": str(p.get("number") or "")[:5],
        "position": (p.get("position") or "")[:10],
        "starter": p.get("starter") if isinstance(p.get("starter"), bool) else None,
        "minutes": None if _int(p.get("minutesPlayed")) is None else float(_int(p.get("minutesPlayed"))),
        "points": _int(p.get("points")),
        "fg_made": _int(p.get("fieldGoalsMade")), "fg_attempted": _int(p.get("fieldGoalsAttempted")),
        "fg3_made": _int(p.get("threePointsMade")), "fg3_attempted": _int(p.get("threePointsAttempted")),
        "ft_made": _int(p.get("freeThrowsMade")), "ft_attempted": _int(p.get("freeThrowsAttempted")),
        "rebounds": reb, "offensive_rebounds": oreb,
        "defensive_rebounds": reb - oreb if reb is not None and oreb is not None else None,
        "assists": _int(p.get("assists")), "turnovers": _int(p.get("turnovers")),
        "steals": _int(p.get("steals")), "blocks": _int(p.get("blockedShots")), "fouls": _int(p.get("personalFouls")),
    }


def missing_lines(ncaa_players: list, our_rows: list) -> list:
    """ncaa.com players (minutes > 0 or points > 0) that our rows for the same team-game lack.

    our_rows: [(display_name, minutes, points)]. A player counts as present when a row with minutes or points
    matches by full name, or failing that by last name + first initial when exactly one such row exists. A
    matched row with neither minutes nor points (ESPN blanked the line) does not count as present; the line
    comes back with note 'blanked'. Rows ncaa.com repeats (same row id and name) count once.
    """
    rows = [(name_tokens(n), (m or 0) > 0 or (pt or 0) > 0) for n, m, pt in our_rows]
    out, seen = [], set()
    for p in ncaa_players:
        line = player_line(p)
        key = (line["external_id"], name_key(line["name"]))
        if key in seen:      # ncaa.com sometimes lists the same box row twice
            continue
        seen.add(key)
        if not ((line["minutes"] or 0) > 0 or (line["points"] or 0) > 0):
            continue
        toks = name_tokens(line["name"])
        full = [played for t, played in rows if "".join(t) == "".join(toks)]
        if not full and toks:
            full = [played for t, played in rows
                    if t and t[-1] == toks[-1] and t[0][:1] == toks[0][:1]]
            if len(full) > 1:
                continue  # ambiguous short-name match: treat as present, never guess
        if any(full):
            continue
        line["note"] = "blanked" if full else ""
        out.append(line)
    return out
