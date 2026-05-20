"""
Win-probability curve reconstruction from PlayerGameStint aggregates.

Works for both NCAA (PlayerGameStint) and NBA (NBAPlayerGameStint).
Pass the queryset of stints, the game's home_team_id, sigma, and league.

Period geometry
---------------
NCAA: periods 1–2 are 20-minute halves (1200 s each), 3+ are 5-minute OT (300 s).
      Total regulation = 2400 s.
NBA : periods 1–4 are 12-minute quarters (720 s each), 5+ are 5-minute OT (300 s).
      Total regulation = 2880 s.

Stints store *delta* scores (pts_scored/pts_allowed = points scored DURING the
stint), not cumulative. We cumsum across chronologically sorted stint boundaries
to reconstruct the running score.

Returns
-------
List of {"t": float, "wp": float, "home_score": int, "away_score": int}
where t is elapsed fraction of total game time (0.0 = tipoff, 1.0 = final buzzer).
Returns [] when no stint data is available.
"""
from __future__ import annotations

from collections import Counter
from itertools import groupby
from typing import Literal

from scipy.stats import norm

# ── Period geometry constants ──────────────────────────────────────────────────
_NCAA_HALF_SECS = 1200       # 20 min halves
_NCAA_OT_SECS   = 300        # 5 min OT
_NCAA_REG_SECS  = 2400       # 2 halves

_NBA_QUARTER_SECS = 720      # 12 min quarters
_NBA_OT_SECS      = 300      # 5 min OT
_NBA_REG_SECS     = 2880     # 4 quarters

FALLBACK_SIGMA = 11.08       # points; matches PipelineConfig.fallback_sigma


def _period_duration(period: int, league: Literal["ncaa", "nba"]) -> int:
    """Return total seconds in the given period."""
    if league == "ncaa":
        return _NCAA_OT_SECS if period > 2 else _NCAA_HALF_SECS
    else:
        return _NBA_OT_SECS if period > 4 else _NBA_QUARTER_SECS


def _regulation_secs(league: Literal["ncaa", "nba"]) -> int:
    return _NCAA_REG_SECS if league == "ncaa" else _NBA_REG_SECS


def _elapsed_at_stint_end(period: int, clock_end_secs: int, league: Literal["ncaa", "nba"]) -> float:
    """
    Convert (period, clock_end_secs) to absolute elapsed seconds from tipoff.
    clock_end_secs = seconds REMAINING in period at stint end.
    Elapsed = sum of completed prior periods + (this period duration - remaining).
    """
    prior_elapsed = sum(_period_duration(p, league) for p in range(1, period))
    return prior_elapsed + (_period_duration(period, league) - clock_end_secs)


def build_wp_curve(
    stints_qs,
    home_team_id: int,
    sigma: float,
    league: Literal["ncaa", "nba"],
    expected_margin: float = 0.0,
) -> list[dict]:
    """
    Build a step-function win-probability curve from player-game stints.

    Parameters
    ----------
    stints_qs       : QuerySet of PlayerGameStint or NBAPlayerGameStint
    home_team_id    : int — PK of the home team (used to partition stints)
    sigma           : float — pregame prediction sigma in points
    league          : "ncaa" or "nba"
    expected_margin : float — expected pregame point margin (home − away, + = home favored)

    Returns
    -------
    List of dicts: {t, wp, home_score, away_score}
    """
    if sigma <= 0:
        sigma = FALLBACK_SIGMA

    # ── Load and partition stints ─────────────────────────────────────────────
    home_stints: list = []
    away_stints: list = []

    for stint in stints_qs.select_related("player", "team"):
        # NBAPlayerGameStint.team is nullable — guard against None
        if stint.team_id is not None and stint.team_id == home_team_id:
            home_stints.append(stint)
        else:
            away_stints.append(stint)

    if not home_stints and not away_stints:
        return []

    # ── Pick one representative player per team ───────────────────────────────
    # Use the player with the most stints — maximises timeline coverage.
    def _representative(stints_list: list) -> list:
        if not stints_list:
            return []
        counts = Counter(s.player_id for s in stints_list)
        best_pid = counts.most_common(1)[0][0]
        return [s for s in stints_list if s.player_id == best_pid]

    home_rep = sorted(
        _representative(home_stints),
        key=lambda s: (s.period, -s.clock_start_secs),  # chronological
    )
    away_rep = sorted(
        _representative(away_stints),
        key=lambda s: (s.period, -s.clock_start_secs),
    )

    # ── Build timeline events ─────────────────────────────────────────────────
    # Each event: (elapsed_secs, home_delta, away_delta)
    # For home-side stints : pts_scored = home pts,  pts_allowed = away pts
    # For away-side stints : pts_scored = away pts,  pts_allowed = home pts
    events: list[dict] = []

    for s in home_rep:
        t = _elapsed_at_stint_end(s.period, s.clock_end_secs, league)
        events.append({"t": t, "home_delta": s.pts_scored, "away_delta": s.pts_allowed})

    for s in away_rep:
        t = _elapsed_at_stint_end(s.period, s.clock_end_secs, league)
        events.append({"t": t, "home_delta": s.pts_allowed, "away_delta": s.pts_scored})

    if not events:
        return []

    events.sort(key=lambda e: e["t"])

    # Merge duplicate timestamps (home + away may share a boundary) by averaging
    merged: list[dict] = []
    for t_val, group in groupby(events, key=lambda e: e["t"]):
        group_list = list(group)
        avg_home = sum(g["home_delta"] for g in group_list) / len(group_list)
        avg_away = sum(g["away_delta"] for g in group_list) / len(group_list)
        merged.append({"t": t_val, "home_delta": avg_home, "away_delta": avg_away})

    # ── Determine total game seconds (extend for OT) ──────────────────────────
    reg_secs = _regulation_secs(league)
    max_t = max(e["t"] for e in merged)
    total_secs = max(reg_secs, max_t)

    # ── Build curve ───────────────────────────────────────────────────────────
    wp_start = float(norm.cdf(expected_margin / sigma))
    curve: list[dict] = [
        {"t": 0.0, "wp": round(wp_start, 3), "home_score": 0, "away_score": 0}
    ]

    home_score = 0.0
    away_score = 0.0

    for event in merged:
        home_score += event["home_delta"]
        away_score += event["away_delta"]
        elapsed = event["t"]
        remaining = max(total_secs - elapsed, 1.0)  # clamp min 1 s to avoid div/0
        fraction_remaining = remaining / total_secs
        sigma_t = sigma * (fraction_remaining ** 0.5)

        score_diff = home_score - away_score
        if sigma_t > 0:
            wp = float(norm.cdf(score_diff / sigma_t))
        else:
            wp = 1.0 if score_diff > 0 else (0.0 if score_diff < 0 else 0.5)

        t_fraction = elapsed / total_secs
        curve.append(
            {
                "t": round(t_fraction, 4),
                "wp": round(wp, 3),
                "home_score": round(home_score),
                "away_score": round(away_score),
            }
        )

    return curve
