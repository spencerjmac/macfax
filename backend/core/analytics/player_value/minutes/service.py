"""
Minutes allocation service — Phase 2.

Orchestrates DB loading → engine → DB write‑back for the baseline
minutes allocation of a season's projections.

The engine (engine.py) is fully stateless; this service layer adds:
  • Loading PlayerSeasonProjection rows for a given from_season
  • Loading matching PlayerSeasonStats for MPG / box‑score signals
  • Loading Player.position for role‑bucket classification
  • Grouping projections by canonical team
  • Running allocate_roster_minutes() per team
  • Writing role_bucket, minutes_share_p2, mpg_p2, rotation_rank,
    minutes_overridden back to PlayerSeasonProjection

For sandbox / hypothetical rosters call the engine directly:
    from core.analytics.player_value.minutes.engine import (
        PlayerMinutesInput, allocate_roster_minutes
    )
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from core.analytics.player_value.minutes.engine import (
    PlayerMinutesInput,
    allocate_roster_minutes,
)

logger = logging.getLogger(__name__)


def run_minutes_pipeline(
    season_year: int,
    verbose: bool = True,
) -> dict:
    """
    Run Phase 2 minutes allocation for all projections in a from_season.

    For every team that has PlayerSeasonProjection rows from season_year,
    this function groups the projected players into a roster, runs the
    allocator, and writes results back to PlayerSeasonProjection.

    Args:
        season_year: The from_season year whose projections to process.
        verbose:     Whether to emit INFO‑level log messages.

    Returns:
        Summary dict with keys:
          season_year, n_teams, n_players, n_written.
    """
    from django.db import transaction
    from core.models import PlayerSeasonProjection, PlayerSeasonStats, Player

    # ── Load all projections for this season ──────────────────────────────
    projections = list(
        PlayerSeasonProjection.objects
        .filter(from_season__year=season_year)
        .values(
            "id",
            "player_id",
            "team_id",
            "projected_bpr",
            "projection_uncertainty",
            "recruitment_type",
            "n_prior_seasons",
        )
    )

    if not projections:
        logger.warning("[Minutes] No projections found for season %d.", season_year)
        return {"season_year": season_year, "n_teams": 0, "n_players": 0, "n_written": 0}

    player_ids = [p["player_id"] for p in projections]

    # ── Load current‑season stats for MPG / box‑score signals ─────────────
    # Deduplication: take the row with highest total possessions for each
    # player (mirrors Phase 1 canonical‑row selection in pipeline.py).
    stats_raw = list(
        PlayerSeasonStats.objects
        .filter(season__year=season_year, player_id__in=player_ids)
        .values("player_id", "mpg", "gp", "off_poss", "def_poss",
                "ast", "blk", "reb", "fg3a_pg")
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

    # ── Load player positions ──────────────────────────────────────────────
    position_by_player: dict[int, str] = dict(
        Player.objects.filter(id__in=player_ids).values_list("id", "position")
    )

    # ── Group projections by canonical team ───────────────────────────────
    by_team: dict[Optional[int], list[dict]] = defaultdict(list)
    for proj in projections:
        by_team[proj["team_id"]].append(proj)

    if verbose:
        logger.info(
            "[Minutes] Season %d: %d projections across %d teams.",
            season_year,
            len(projections),
            len(by_team),
        )

    # ── Allocate per team ─────────────────────────────────────────────────
    proj_updates: dict[int, dict] = {}
    n_teams_run = 0

    for team_id, team_projs in by_team.items():
        inputs: list[PlayerMinutesInput] = []

        for proj in team_projs:
            pid = proj["player_id"]
            st  = stats_by_player.get(pid, {})
            pos = position_by_player.get(pid, "")
            poss = (st.get("off_poss") or 0.0) + (st.get("def_poss") or 0.0)

            inputs.append(PlayerMinutesInput(
                player_id=pid,
                projected_bpr=proj["projected_bpr"] or 0.0,
                projection_uncertainty=proj["projection_uncertainty"] or 0.5,
                recruitment_type=proj["recruitment_type"] or "newcomer",
                n_prior_seasons=proj["n_prior_seasons"] or 0,
                prior_mpg=st.get("mpg") or 0.0,
                prior_gp=st.get("gp") or 0,
                prior_poss=poss,
                position=pos,
                ast_pg=st.get("ast") or 0.0,
                blk_pg=st.get("blk") or 0.0,
                reb_pg=st.get("reb") or 0.0,
                fg3a_pg=st.get("fg3a_pg") or 0.0,
            ))

        try:
            result = allocate_roster_minutes(inputs)
        except (ValueError, ZeroDivisionError) as exc:
            logger.warning("[Minutes] Team %s allocation failed: %s", team_id, exc)
            continue

        output_by_player = {o.player_id: o for o in result.players}
        for proj in team_projs:
            out = output_by_player.get(proj["player_id"])
            if out:
                proj_updates[proj["id"]] = {
                    "role_bucket":        out.role_bucket,
                    "minutes_share_p2":   out.minutes_share,
                    "mpg_p2":             out.mpg,
                    "rotation_rank":      out.rotation_rank,
                    "minutes_overridden": out.is_overridden,
                }

        n_teams_run += 1

    # ── Bulk write‑back ────────────────────────────────────────────────────
    n_written = 0
    if proj_updates:
        all_objs = list(
            PlayerSeasonProjection.objects.filter(id__in=list(proj_updates.keys()))
        )
        for obj in all_objs:
            upd = proj_updates[obj.pk]
            obj.role_bucket        = upd["role_bucket"]
            obj.minutes_share_p2   = upd["minutes_share_p2"]
            obj.mpg_p2             = upd["mpg_p2"]
            obj.rotation_rank      = upd["rotation_rank"]
            obj.minutes_overridden = upd["minutes_overridden"]

        with transaction.atomic():
            PlayerSeasonProjection.objects.bulk_update(
                all_objs,
                ["role_bucket", "minutes_share_p2", "mpg_p2",
                 "rotation_rank", "minutes_overridden"],
                batch_size=500,
            )
        n_written = len(all_objs)

    if verbose:
        logger.info(
            "[Minutes] Done: %d teams processed, %d projection rows updated.",
            n_teams_run,
            n_written,
        )

    return {
        "season_year": season_year,
        "n_teams":     n_teams_run,
        "n_players":   len(projections),
        "n_written":   n_written,
    }
