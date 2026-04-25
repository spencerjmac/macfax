"""
Phase 4: Contextual Fit Service.

Orchestrates DB loading → engine → DB upsert for pace & scheme compatibility.

This service runs AFTER Phase 3 (run_fit_pipeline) because it reads from
TeamRosterFit to get existing Phase 3 scores, then updates those same rows
with the Phase 4 contextual fields.

For stateless / hypothetical use, call the engine directly:
    from ncaa.analytics.player_value.fit.context.engine import (
        score_contextual_fit, ContextualFitResult,
    )
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from ncaa.analytics.player_value.fit.archetypes import PlayerFitInput, tag_archetypes
from ncaa.analytics.player_value.fit.context.engine import score_contextual_fit

logger = logging.getLogger(__name__)

# TeamSeasonRatings fields needed for contextual fit
_RATINGS_FIELDS = [
    "team_id",
    "adj_tempo",
    "adj_tov_pct",
    "adj_orb_pct",
    "adj_ftr",
    "adj_efg_pct",
    "adj_opp_tov_pct",
    "adj_opp_orb_pct",
    "adj_drb_pct",
]

# Phase 3 service stats fields already cover player signals we need —
# we re-use the same player data loading pattern and re-build PlayerFitInput.
_STATS_VALUES = [
    "player_id",
    "gp",
    "mpg",
    "off_poss",
    "def_poss",
    "ast",
    "stl",
    "blk",
    "tov",
    "pf",
    "fg3a_pg",
    "fta_pg",
    "oreb_pg",
    "dreb_pg",
    "fg_pct",
    "efg_pct",
    "ts_pct",
    "ast_to",
    "off_efg_impact",
    "def_efg_impact",
    "off_tov_impact",
    "def_tov_impact",
    "off_orb_impact",
    "def_reb_impact",
    "off_ftr_impact",
    "def_ftr_impact",
    "on_court_adj_o",
    "on_court_adj_d",
    "on_court_off_poss",
    "on_court_def_poss",
    "obpr",
    "dbpr",
]


def _build_player_fit_input(proj: dict, stats: Optional[dict]) -> PlayerFitInput:
    """Build PlayerFitInput from a projection row + optional stats dict."""
    s = stats or {}
    p = PlayerFitInput(
        player_id=proj["player_id"],
        player_name=proj.get("player_name", ""),
        minutes_share_p2=proj.get("minutes_share_p2") or 0.0,
        rotation_rank=proj.get("rotation_rank") or 99,
        role_bucket=proj.get("role_bucket") or "Wing",
        projected_obpr=proj.get("projected_obpr"),
        projected_dbpr=proj.get("projected_dbpr"),
        gp=int(s.get("gp") or 0),
        fg3a_pg=float(s.get("fg3a_pg") or 0.0),
        ast_pg=float(s.get("ast") or 0.0),
        tov_pg=float(s.get("tov") or 0.0),
        blk_pg=float(s.get("blk") or 0.0),
        stl_pg=float(s.get("stl") or 0.0),
        pf_pg=float(s.get("pf") or 0.0),
        oreb_pg=float(s.get("oreb_pg") or 0.0),
        dreb_pg=float(s.get("dreb_pg") or 0.0),
        fta_pg=float(s.get("fta_pg") or 0.0),
        fg_pct=s.get("fg_pct"),
        efg_pct=s.get("efg_pct"),
        ts_pct=s.get("ts_pct"),
        ast_to=s.get("ast_to"),
        off_efg_impact=s.get("off_efg_impact"),
        def_efg_impact=s.get("def_efg_impact"),
        off_tov_impact=s.get("off_tov_impact"),
        def_tov_impact=s.get("def_tov_impact"),
        off_orb_impact=s.get("off_orb_impact"),
        def_reb_impact=s.get("def_reb_impact"),
        off_ftr_impact=s.get("off_ftr_impact"),
        def_ftr_impact=s.get("def_ftr_impact"),
        on_court_adj_o=s.get("on_court_adj_o"),
        on_court_adj_d=s.get("on_court_adj_d"),
        on_court_off_poss=s.get("on_court_off_poss"),
        on_court_def_poss=s.get("on_court_def_poss"),
    )
    # Populate archetypes (idempotent, same as Phase 3 engine)
    p.archetypes = tag_archetypes(p)
    return p


def run_contextual_fit_pipeline(
    season_year: int,
    verbose: bool = True,
) -> dict:
    """
    Compute and persist Phase 4 contextual fit scores for all teams in a season.

    Requires Phase 3 to have already run (reads TeamRosterFit for Phase 3 scores,
    updates those same rows with Phase 4 fields).

    Args:
        season_year: The from_season year (e.g. 2026).
        verbose:     Whether to emit INFO-level log messages.

    Returns:
        Summary dict: {season_year, n_teams, n_with_style, n_written, n_errors}.
    """
    from django.db import transaction
    from ncaa.models import (
        PlayerSeasonProjection,
        PlayerSeasonStats,
        TeamRosterFit,
        Season,
    )

    try:
        from ncaa.models import TeamSeasonRatings
    except ImportError:
        logger.warning(
            "[ContextFit] TeamSeasonRatings model not found; all teams will get "
            "neutral modifiers.",
        )
        TeamSeasonRatings = None  # type: ignore[assignment]

    # ── Load the from_season ──────────────────────────────────────────────
    try:
        from_season = Season.objects.get(year=season_year)
    except Season.DoesNotExist:
        logger.error("[ContextFit] Season %d not found in DB.", season_year)
        return {"season_year": season_year, "n_teams": 0, "n_with_style": 0,
                "n_written": 0, "n_errors": 0}

    # ── Load Phase 3 TeamRosterFit rows ───────────────────────────────────
    fit_rows = list(
        TeamRosterFit.objects.filter(from_season__year=season_year)
        .values("id", "team_id", "offensive_fit_score", "defensive_fit_score",
                "overall_fit_score")
    )
    if not fit_rows:
        logger.warning(
            "[ContextFit] No TeamRosterFit rows for season %d. "
            "Run compute_roster_fit first.",
            season_year,
        )
        return {"season_year": season_year, "n_teams": 0, "n_with_style": 0,
                "n_written": 0, "n_errors": 0}

    team_to_fit = {row["team_id"]: row for row in fit_rows}

    # ── Load TeamSeasonRatings style data ─────────────────────────────────
    style_by_team: dict[int, dict] = {}
    if TeamSeasonRatings is not None:
        ratings_qs = TeamSeasonRatings.objects.filter(
            season__year=season_year
        ).values(*_RATINGS_FIELDS)
        for row in ratings_qs:
            style_by_team[row["team_id"]] = row

    if verbose:
        logger.info(
            "[ContextFit] Season %d: %d teams with Phase 3 fit, %d with style data.",
            season_year, len(team_to_fit), len(style_by_team),
        )

    # ── Load projections ──────────────────────────────────────────────────
    projections = list(
        PlayerSeasonProjection.objects
        .filter(from_season__year=season_year, team_id__in=list(team_to_fit.keys()))
        .values(
            "id", "player_id", "player__display_name", "team_id",
            "projected_obpr", "projected_dbpr",
            "minutes_share_p2", "mpg_p2", "rotation_rank", "role_bucket",
        )
    )
    for p in projections:
        p["player_name"] = p.get("player__display_name") or ""

    player_ids = [p["player_id"] for p in projections]

    # ── Load player stats ─────────────────────────────────────────────────
    stats_raw = list(
        PlayerSeasonStats.objects
        .filter(season__year=season_year, player_id__in=player_ids)
        .values(*_STATS_VALUES)
    )
    stats_by_player: dict[int, dict] = {}
    for row in stats_raw:
        pid = row["player_id"]
        if pid not in stats_by_player:
            stats_by_player[pid] = row
        else:
            existing_poss = (
                (stats_by_player[pid].get("off_poss") or 0.0)
                + (stats_by_player[pid].get("def_poss") or 0.0)
            )
            new_poss = (row.get("off_poss") or 0.0) + (row.get("def_poss") or 0.0)
            if new_poss > existing_poss:
                stats_by_player[pid] = row

    # ── Group projections by team ─────────────────────────────────────────
    by_team: dict[int, list[dict]] = defaultdict(list)
    for proj in projections:
        if proj["team_id"] is not None:
            by_team[proj["team_id"]].append(proj)

    # ── Score per team ────────────────────────────────────────────────────
    n_errors = 0
    n_with_style = 0
    updates: list[dict] = []

    for team_id, fit_row in team_to_fit.items():
        team_projs = by_team.get(team_id, [])
        if not team_projs:
            continue

        players = [
            _build_player_fit_input(proj, stats_by_player.get(proj["player_id"]))
            for proj in team_projs
        ]

        team_style = style_by_team.get(team_id)
        if team_style:
            n_with_style += 1

        try:
            ctx = score_contextual_fit(
                players=players,
                phase3_off=float(fit_row["offensive_fit_score"] or 50.0),
                phase3_def=float(fit_row["defensive_fit_score"] or 50.0),
                phase3_overall=float(fit_row["overall_fit_score"] or 50.0),
                team_style=team_style,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[ContextFit] Team %s contextual fit failed: %s",
                team_id, exc, exc_info=True,
            )
            n_errors += 1
            continue

        updates.append({
            "fit_id":                     fit_row["id"],
            "pace_alignment_score":        ctx.pace_alignment_score,
            "pace_modifier":               ctx.pace_modifier,
            "off_scheme_alignment_score":  ctx.off_scheme_alignment_score,
            "off_scheme_modifier":         ctx.off_scheme_modifier,
            "def_scheme_alignment_score":  ctx.def_scheme_alignment_score,
            "def_scheme_modifier":         ctx.def_scheme_modifier,
            "off_contextual_modifier":     ctx.off_contextual_modifier,
            "def_contextual_modifier":     ctx.def_contextual_modifier,
            "adjusted_off_fit":            ctx.adjusted_off_fit,
            "adjusted_def_fit":            ctx.adjusted_def_fit,
            "adjusted_overall_fit":        ctx.adjusted_overall_fit,
            "has_team_style_data":         ctx.has_team_style_data,
        })

    # ── Persist updates to existing TeamRosterFit rows ────────────────────
    n_written = 0
    if updates:
        update_fields = [
            "pace_alignment_score", "pace_modifier",
            "off_scheme_alignment_score", "off_scheme_modifier",
            "def_scheme_alignment_score", "def_scheme_modifier",
            "off_contextual_modifier", "def_contextual_modifier",
            "adjusted_off_fit", "adjusted_def_fit", "adjusted_overall_fit",
            "has_team_style_data",
        ]
        with transaction.atomic():
            for upd in updates:
                TeamRosterFit.objects.filter(pk=upd["fit_id"]).update(
                    **{k: upd[k] for k in update_fields}
                )
                n_written += 1

    if verbose:
        logger.info(
            "[ContextFit] Done: %d teams scored, %d with style data, "
            "%d rows updated, %d errors.",
            len(updates), n_with_style, n_written, n_errors,
        )

    return {
        "season_year":   season_year,
        "n_teams":       len(updates),
        "n_with_style":  n_with_style,
        "n_written":     n_written,
        "n_errors":      n_errors,
    }
