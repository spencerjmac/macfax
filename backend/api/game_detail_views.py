"""
NCAA game detail endpoint.

GET /api/games/<int:game_id>/detail/
Returns a unified game detail payload for the frontend GameDetailPage component.
"""
from __future__ import annotations

import json
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from ncaa.models import (
    Game,
    TeamGameStats,
    PlayerGameStats,
    NationalAverages,
    PipelineConfig,
    PlayerGameStint,
)

from .wp_reconstruction import build_wp_curve, FALLBACK_SIGMA
from .game_insights import generate_game_insights

_log = logging.getLogger(__name__)


def _get_sigma(season_year: int) -> float:
    """Return prediction sigma for the season, falling back to PipelineConfig or hardcoded."""
    try:
        na = NationalAverages.objects.select_related("season").get(season__year=season_year)
        if na.prediction_sigma:
            return float(na.prediction_sigma)
    except NationalAverages.DoesNotExist:
        pass
    try:
        cfg = PipelineConfig.objects.first()
        if cfg and cfg.fallback_sigma:
            return float(cfg.fallback_sigma)
    except Exception:  # noqa: BLE001
        pass
    return FALLBACK_SIGMA


def _team_abbr(team) -> str:
    """NCAA Team has no abbreviation field — derive from slug."""
    slug = getattr(team, "slug", None) or ""
    if slug:
        return slug.upper()[:3]
    return (team.name[:3]).upper()


def _build_four_factors(tgs: TeamGameStats | None) -> dict:
    if tgs is None:
        return {"efg_pct": None, "tov_pct": None, "orb_pct": None, "ftr": None}
    return {
        "efg_pct": tgs.efg_pct,
        "tov_pct": tgs.tov_pct,
        "orb_pct": tgs.orb_pct,
        "ftr": tgs.ftr,
    }


def _build_player_rows(player_stats_qs, team) -> list[dict]:
    rows = []
    for ps in player_stats_qs.filter(team=team).order_by("-points"):
        rows.append(
            {
                "name": ps.player.display_name
                if hasattr(ps.player, "display_name")
                else ps.player.name,
                "min": str(getattr(ps, "minutes", "") or ""),
                "pts": ps.points,
                "reb": ps.rebounds,
                "ast": ps.assists,
                "stl": getattr(ps, "steals", None),
                "blk": getattr(ps, "blocks", None),
                "tov": ps.turnovers,
                "fg": f"{ps.fg_made}-{ps.fg_attempted}",
                "fg3": f"{ps.fg3_made}-{ps.fg3_attempted}",
                "ft": f"{ps.ft_made}-{ps.ft_attempted}",
                "plus_minus": None,  # NCAA player game stats don't track +/-
            }
        )
    return rows


@require_GET
def ncaa_game_detail(request, game_id: int):
    game = get_object_or_404(Game, pk=game_id)

    # ── Team-level box scores ─────────────────────────────────────────────────
    team_stats = list(
        TeamGameStats.objects.filter(game=game).select_related("team", "opponent")
    )
    home_tgs = next((t for t in team_stats if t.team_id == game.home_team_id), None)
    away_tgs = next((t for t in team_stats if t.team_id == game.away_team_id), None)

    # ── Player box scores ─────────────────────────────────────────────────────
    player_stats = PlayerGameStats.objects.filter(game=game).select_related("player", "team")
    home_box = _build_player_rows(player_stats, game.home_team)
    away_box = _build_player_rows(player_stats, game.away_team)

    # ── Win probability curve ─────────────────────────────────────────────────
    stints = PlayerGameStint.objects.filter(game=game)
    sigma = _get_sigma(game.season_year)
    wp_curve = build_wp_curve(stints, game.home_team_id, sigma, "ncaa")

    # ── Four factors ──────────────────────────────────────────────────────────
    four_factors = {
        "home": _build_four_factors(home_tgs),
        "away": _build_four_factors(away_tgs),
    }

    # ── Game meta ─────────────────────────────────────────────────────────────
    venue = None
    if game.venue_name:
        parts = [game.venue_name]
        if game.venue_city:
            parts.append(game.venue_city)
        if game.venue_state:
            parts.append(game.venue_state)
        venue = ", ".join(parts)

    game_meta = {
        "id": game.pk,
        "league": "ncaa",
        "date": game.game_date.isoformat(),
        "home_team": {
            "name": game.home_team.name,
            "abbr": _team_abbr(game.home_team),
            "slug": game.home_team.slug,
        },
        "away_team": {
            "name": game.away_team.name,
            "abbr": _team_abbr(game.away_team),
            "slug": game.away_team.slug,
        },
        "home_score": game.home_score,
        "away_score": game.away_score,
        "venue": venue,
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
