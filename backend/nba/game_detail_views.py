"""
NBA game detail endpoint.

GET /api/nba/games/<int:game_id>/detail/
Returns a unified game detail payload matching the NCAA contract.
"""
from __future__ import annotations

import json
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from .models import (
    NBAGame,
    NBATeamGameStats,
    NBAPlayerGameStats,
    NBAPlayerGameStint,
    NBAModelCalibration,
)
from api.wp_reconstruction import build_wp_curve, FALLBACK_SIGMA
from api.game_insights import generate_game_insights

_log = logging.getLogger(__name__)


def _get_sigma(game: NBAGame) -> float:
    """Return prediction sigma for the game's season."""
    try:
        calib = NBAModelCalibration.objects.get(season=game.season)
        if calib.prediction_sigma:
            return float(calib.prediction_sigma)
    except NBAModelCalibration.DoesNotExist:
        pass
    return FALLBACK_SIGMA


def _safe_div(num, denom, scale=1.0) -> float | None:
    if num is None or denom is None or denom == 0:
        return None
    return round(num / denom * scale, 1)


def _compute_four_factors(tgs: NBATeamGameStats, opp_tgs: NBATeamGameStats | None) -> dict:
    """Compute four factors on-the-fly from raw box score fields."""
    efg_pct = None
    if tgs.fga and tgs.fgm is not None and tgs.fg3m is not None:
        efg_pct = round((tgs.fgm + 0.5 * tgs.fg3m) / tgs.fga * 100, 1)

    tov_pct = None
    if tgs.tov is not None and tgs.fga is not None and tgs.fta is not None:
        denom = tgs.fga + 0.44 * tgs.fta + tgs.tov
        tov_pct = _safe_div(tgs.tov, denom, scale=100)

    orb_pct = None
    if (
        tgs.oreb is not None
        and opp_tgs is not None
        and opp_tgs.dreb is not None
    ):
        denom = tgs.oreb + opp_tgs.dreb
        orb_pct = _safe_div(tgs.oreb, denom, scale=100)

    ftr = _safe_div(tgs.fta, tgs.fga, scale=100)

    return {"efg_pct": efg_pct, "tov_pct": tov_pct, "orb_pct": orb_pct, "ftr": ftr}


def _fmt_secs(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _build_player_rows(player_stats_qs, team) -> list[dict]:
    rows = []
    for ps in player_stats_qs.filter(team=team).order_by("-pts"):
        rows.append(
            {
                "name": ps.player.name,
                "min": _fmt_secs(ps.seconds_played),
                "pts": ps.pts,
                "reb": ps.reb,
                "ast": ps.ast,
                "stl": ps.stl,
                "blk": ps.blk,
                "tov": ps.tov,
                "fg": f"{ps.fgm}-{ps.fga}" if ps.fgm is not None else "—",
                "fg3": f"{ps.fg3m}-{ps.fg3a}" if ps.fg3m is not None else "—",
                "ft": f"{ps.ftm}-{ps.fta}" if ps.ftm is not None else "—",
                "plus_minus": ps.plus_minus,
            }
        )
    return rows


@require_GET
def nba_game_detail(request, game_id: int):
    game = get_object_or_404(NBAGame, game_id=game_id)

    # ── Team-level box scores ─────────────────────────────────────────────────
    team_stats = list(
        NBATeamGameStats.objects.filter(game=game).select_related("team")
    )
    home_tgs = next((t for t in team_stats if t.is_home), None)
    away_tgs = next((t for t in team_stats if not t.is_home), None)

    # ── Player box scores ─────────────────────────────────────────────────────
    player_stats = NBAPlayerGameStats.objects.filter(game=game).select_related("player", "team")
    home_box = _build_player_rows(player_stats, game.home_team)
    away_box = _build_player_rows(player_stats, game.away_team)

    # ── Win probability curve ─────────────────────────────────────────────────
    wp_curve: list[dict] = []
    if game.pbp_synced and not game.pbp_quality_flag:
        stints = NBAPlayerGameStint.objects.filter(game=game)
        sigma = _get_sigma(game)
        wp_curve = build_wp_curve(stints, game.home_team_id, sigma, "nba")
    else:
        sigma = _get_sigma(game)

    # ── Four factors ──────────────────────────────────────────────────────────
    four_factors = {
        "home": _compute_four_factors(home_tgs, away_tgs) if home_tgs else
                {"efg_pct": None, "tov_pct": None, "orb_pct": None, "ftr": None},
        "away": _compute_four_factors(away_tgs, home_tgs) if away_tgs else
                {"efg_pct": None, "tov_pct": None, "orb_pct": None, "ftr": None},
    }

    # ── Game meta ─────────────────────────────────────────────────────────────
    game_meta = {
        "id": game.pk,
        "league": "nba",
        "date": game.date.isoformat(),
        "home_team": {
            "name": game.home_team.name,
            "abbr": game.home_team.abbreviation,
            "slug": game.home_team.slug,
        },
        "away_team": {
            "name": game.away_team.name,
            "abbr": game.away_team.abbreviation,
            "slug": game.away_team.slug,
        },
        "home_score": game.home_score,
        "away_score": game.away_score,
        "venue": game.arena or None,
        "status": game.status,
    }

    # ── AI insights (generate once, cache forever) ────────────────────────────
    if game.game_insights:
        try:
            insights = json.loads(game.game_insights)
        except json.JSONDecodeError:
            insights = [game.game_insights]
    else:
        insights = generate_game_insights(game_meta, four_factors, wp_curve)
        game.game_insights = json.dumps(insights)
        game.save(update_fields=["game_insights"])

    return JsonResponse(
        {
            "game_meta": game_meta,
            "wp_curve": wp_curve,
            "four_factors": four_factors,
            "box_score": {"home": home_box, "away": away_box},
            "insights": insights,
        }
    )
