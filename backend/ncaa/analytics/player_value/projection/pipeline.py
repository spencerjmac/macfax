"""
pipeline.py — Data loading and write-back for player projections.

Orchestrates:
  1. Load current-season PlayerSeasonStats
  2. Canonicalize to ONE row per player (most possessions; see _pick_canonical_row)
  3. Load prior-season PlayerSeasonStats with same canonical selection
  4. Load TeamSeasonRatings adj_em (for arrival-context competition adjustment)
  5. Count distinct prior seasons per player (for development adjustment)
  6. Call project_player() from engine.py for each canonical player row
  7. Bulk-upsert PlayerSeasonProjection records (one per player per from_season)
  8. Return a summary dict

Split-season handling rule (Phase 1):
  When a player has multiple PlayerSeasonStats rows in the same season
  (split-season, e.g. mid-year transfer), we select the CANONICAL row:
    1. Most total possessions (off_poss + def_poss)  — primary key
    2. Most games played (gp)                         — first tie-break
    3. Most minutes per game (mpg)                    — second tie-break
  This gives the row from the team where the player had the largest
  on-court sample, which is the most stable signal for projection.
  The canonical team is stored on the PlayerSeasonProjection row.

Known Phase 1 limitations:
  - n_prior_seasons counts distinct season-years, not distinct teams, so a
    split-season year counts as one prior season (correct behavior).
  - For the prior season, the canonical row determines the team used for
    recruitment-type classification (returner/transfer) and the prior-team
    adj_em used for competition adjustment.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from ncaa.analytics.player_value.projection.constants import PROJECTION_VERSION
from ncaa.analytics.player_value.projection.engine import project_player
from ncaa.analytics.player_value.minutes.role_buckets import classify_role_bucket

logger = logging.getLogger(__name__)


def classify_recruitment_type(
    player_id: int,
    current_team_id: Optional[int],
    prior_canonical_row: Optional[dict],
    player_team_history: dict,
) -> tuple[str, str]:
    """
    Classify how a player arrived at their current team.

    Extends the basic two-season lookup in engine.py with a third rule that
    detects grad-transfers who are returning to a school they attended before
    their most recent prior season.

    Rules in priority order:
      1. No prior canonical row          → ('newcomer', 'no_prior_season')
      2. prior_team == current_team      → ('returner', 'same_team_prior')
      3. prior_team != current_team AND current_team_id in player's full
         team history (earlier seasons)  → ('returner', 'grad_transfer_return')
      4. prior_team != current_team      → ('transfer', 'different_team_prior')

    Args:
        player_id:           Player's DB primary key.
        current_team_id:     team_id for the canonical row in from_season.
        prior_canonical_row: Canonical PSS dict for prior season, or None.
        player_team_history: {player_id: set[team_id]} built from ALL prior
                             seasons before from_season (not just the last one).

    Returns:
        (recruitment_type, classification_reason) tuple.
    """
    if prior_canonical_row is None:
        return "newcomer", "no_prior_season"

    prior_team_id = prior_canonical_row.get("team_id")
    if prior_team_id is None or current_team_id is None:
        return "returner", "same_team_prior"  # conservative default

    if prior_team_id == current_team_id:
        return "returner", "same_team_prior"

    # Rule 3: current school appears in player's broader team history
    history: set = player_team_history.get(player_id, set())
    if current_team_id in history:
        return "returner", "grad_transfer_return"

    return "transfer", "different_team_prior"


def _pick_canonical_row(rows: list[dict]) -> dict:
    """
    From a list of PlayerSeasonStats value-dicts for the same player
    (typically one row, but two for split-season / mid-year transfers),
    return the single most representative row.

    Selection rule (deterministic):
      1. Highest total possessions (off_poss + def_poss)
      2. Tie-break: most games played (gp)
      3. Tie-break: highest minutes per game (mpg)

    Rationale: the row with the most on-court sample is the most stable
    signal source for projection.  For a single-team player this just
    returns that player's only row with no overhead.
    """
    if len(rows) == 1:
        return rows[0]

    def _sort_key(r: dict) -> tuple:
        poss = (r.get("off_poss") or 0.0) + (r.get("def_poss") or 0.0)
        gp   = r.get("gp")  or 0
        mpg  = r.get("mpg") or 0.0
        return (poss, gp, mpg)

    return max(rows, key=_sort_key)


def run_projection_pipeline(
    season_year: int,
    verbose: bool = True,
) -> dict:
    """
    Run the full player projection pipeline for a given from_season.

    Generates next-season projections for all players with a
    PlayerSeasonStats row in season_year.

    Args:
        season_year: The season to project FROM (e.g. 2026 → projects to 2027).
        verbose:     Whether to emit INFO-level log messages.

    Returns:
        Summary dict with keys: season_year, projected_season_year,
        n_players, n_split_season, n_projected, n_created, n_updated,
        recruitment_type_breakdown, n_with_prior_rapm, projection_version.
    """
    # Django models imported inside function to allow pure-Python unit testing
    # of engine.py without requiring a Django setup.
    from ncaa.models import (
        Season,
        PlayerSeasonStats,
        TeamSeasonRatings,
        PlayerSeasonProjection,
    )

    projected_season_year = season_year + 1

    # ── Load current season ───────────────────────────────────────────────────
    try:
        season = Season.objects.get(year=season_year)
    except Season.DoesNotExist:
        raise ValueError(f"Season {season_year} not found in the database.")

    current_rows = list(
        PlayerSeasonStats.objects
        .filter(season=season)
        .values(
            "id",
            "player_id",
            "team_id",
            "season_id",
            "obpr",
            "dbpr",
            "bpr",
            "box_obpr",
            "box_dbpr",
            "baseline_obpr",
            "baseline_dbpr",
            "off_poss",
            "def_poss",
            "mpg",
            "gp",
            # Box stats for role_bucket classification (Phase 1.2 BT-3)
            "blk",
            "reb",
            "ast",
            "fg3a_pg",
            "player__position",
        )
    )

    if verbose:
        logger.info(
            "[Projection] Season %d: loaded %d PlayerSeasonStats rows.",
            season_year,
            len(current_rows),
        )

    if not current_rows:
        logger.warning("[Projection] No PlayerSeasonStats rows found for season %d.", season_year)
        return {
            "season_year": season_year,
            "projected_season_year": projected_season_year,
            "n_players": 0,
            "n_split_season": 0,
            "n_projected": 0,
            "n_created": 0,
            "n_updated": 0,
            "recruitment_type_breakdown": {},
            "n_with_prior_rapm": 0,
            "projection_version": PROJECTION_VERSION,
        }

    # ── Canonicalize current season: one row per player ─────────────────────
    rows_by_player: dict[int, list[dict]] = defaultdict(list)
    for row in current_rows:
        rows_by_player[row["player_id"]].append(row)

    n_split_season = sum(1 for rows in rows_by_player.values() if len(rows) > 1)
    canonical_current: list[dict] = [
        _pick_canonical_row(rows) for rows in rows_by_player.values()
    ]

    if verbose:
        logger.info(
            "[Projection] Season %d: %d distinct players (%d split-season players canonicalized).",
            season_year,
            len(canonical_current),
            n_split_season,
        )

    # ── Load prior season ─────────────────────────────────────────────────────
    prior_season_year = season_year - 1
    prior_rows_qs = PlayerSeasonStats.objects.filter(
        season__year=prior_season_year
    ).values(
        "player_id",
        "team_id",
        "obpr",
        "dbpr",
        "box_obpr",
        "box_dbpr",
        "off_poss",
        "def_poss",
    )

    # Canonicalize prior season: one row per player (most possessions).
    # This determines:
    #   - Which team is used for recruitment-type classification
    #     (returner if team matches current canonical team; transfer if not)
    #   - Which prior adj_em is used for the arrival-context competition
    #     adjustment for transfers
    prior_rows_by_player: dict[int, list[dict]] = defaultdict(list)
    for row in prior_rows_qs:
        prior_rows_by_player[row["player_id"]].append(row)

    canonical_prior: dict[int, dict] = {
        pid: _pick_canonical_row(rows)
        for pid, rows in prior_rows_by_player.items()
    }

    if verbose:
        logger.info(
            "[Projection] Prior season %d: %d canonical players found.",
            prior_season_year,
            len(canonical_prior),
        )

    # ── Load team strength (adj_em) for competition translation ───────────────
    current_team_em: dict[int, float] = dict(
        TeamSeasonRatings.objects
        .filter(season__year=season_year)
        .values_list("team_id", "adj_em")
    )
    prior_team_em: dict[int, float] = dict(
        TeamSeasonRatings.objects
        .filter(season__year=prior_season_year)
        .values_list("team_id", "adj_em")
    )

    # ── Count distinct prior seasons per player ──────────────────────────────
    # We count distinct season-years (not distinct rows) so that a split-season
    # player who has two rows in the same season year is counted once, not twice.
    from django.db.models import Count

    prior_season_count: dict[int, int] = dict(
        PlayerSeasonStats.objects
        .filter(season__year__lt=season_year)
        .values("player_id")
        .annotate(n=Count("season__year", distinct=True))
        .values_list("player_id", "n")
    )

    # ── Load full team history for grad-transfer detection (Phase 1.2) ──────────
    # Single .distinct() query — NOT an N+1 loop.
    # Builds {player_id: {team_id, ...}} across ALL seasons before season_year.
    _prior_history_rows = PlayerSeasonStats.objects.filter(
        player_id__in={r["player_id"] for r in canonical_current},
        season__year__lt=season_year,
    ).values("player_id", "team_id").distinct()

    player_team_history: dict[int, set] = defaultdict(set)
    for _hr in _prior_history_rows:
        if _hr["team_id"]:
            player_team_history[_hr["player_id"]].add(_hr["team_id"])

    # ── Load recruiting profiles for newcomer BPR priors (Phase 1.1) ─────────
    from ncaa.models import PlayerRecruitingProfile

    # Only players with no prior-season data will be classified as newcomers.
    newcomer_pids = {
        row["player_id"]
        for row in canonical_current
        if row["player_id"] not in canonical_prior
    }
    recruiting_by_player: dict[int, dict] = {}
    if newcomer_pids:
        for profile in PlayerRecruitingProfile.objects.filter(
            player_id__in=newcomer_pids,
            class_year=season_year,
        ).values("player_id", "national_rank", "stars", "composite_score"):
            recruiting_by_player[profile["player_id"]] = {
                "national_rank":   profile["national_rank"],
                "stars":           profile["stars"],
                "composite_score": profile["composite_score"],
            }

    if verbose:
        logger.info(
            "[Projection] Season %d: %d newcomer candidates, %d have recruiting profiles.",
            season_year,
            len(newcomer_pids),
            len(recruiting_by_player),
        )

    # ── Run projections ────────────────────────────────────────────────────
    projections: list[dict] = []
    for row in canonical_current:
        pid     = row["player_id"]
        team_id = row["team_id"]
        prior   = canonical_prior.get(pid)
        n_prior = prior_season_count.get(pid, 0)

        current_em = current_team_em.get(team_id) if team_id else None
        prior_em   = (
            prior_team_em.get(prior["team_id"])
            if prior and prior.get("team_id")
            else None
        )

        rtype, reason = classify_recruitment_type(
            player_id=pid,
            current_team_id=team_id,
            prior_canonical_row=prior,
            player_team_history=player_team_history,
        )
        logger.debug("[Projection] player_id=%d → %s (%s)", pid, rtype, reason)

        role_bucket = classify_role_bucket(
            position=row.get("player__position") or "",
            blk_pg=float(row.get("blk") or 0.0),
            reb_pg=float(row.get("reb") or 0.0),
            ast_pg=float(row.get("ast") or 0.0),
            fg3a_pg=float(row.get("fg3a_pg") or 0.0),
        )

        result = project_player(
            current=row,
            prior=prior,
            current_team_adj_em=current_em,
            prior_team_adj_em=prior_em,
            n_prior_seasons=n_prior,
            recruiting_profile=recruiting_by_player.get(pid),
            role_bucket=role_bucket,
            recruitment_type_override=rtype,
            classification_reason=reason,
        )

        projections.append(
            {
                "player_id":             pid,
                "team_id":               team_id,
                "from_season_id":        row["season_id"],
                "projected_season_year": projected_season_year,
                **result,
            }
        )

    if verbose:
        logger.info("[Projection] Generated %d projection records (one per player).", len(projections))

    # ── Bulk upsert ──────────────────────────────────────────────────────
    # Key is now (player_id, from_season_id) — unique per player per season
    # (unique constraint on model changed from (player, from_season, team)
    # to (player, from_season) in migration 0040).
    existing: dict[tuple, PlayerSeasonProjection] = {
        (r.player_id, r.from_season_id): r
        for r in PlayerSeasonProjection.objects.filter(from_season__year=season_year)
    }

    to_create: list[PlayerSeasonProjection] = []
    to_update: list[PlayerSeasonProjection] = []

    update_fields = [
        "team_id",          # canonical team can shift after data refreshes
        "recruitment_type",
        "projected_obpr",
        "projected_dbpr",
        "projected_bpr",
        "projected_minutes_share",
        "projection_uncertainty",
        "n_prior_seasons",
        "prior_rapm_used",
        "recruiting_prior_used",
        "classification_reason",
        "projected_season_year",
        "projection_version",
        # computed_at is auto_now, handled by Django on save
    ]

    for p in projections:
        key = (p["player_id"], p["from_season_id"])
        obj = existing.get(key)
        if obj is None:
            to_create.append(
                PlayerSeasonProjection(
                    player_id=p["player_id"],
                    team_id=p["team_id"],
                    from_season_id=p["from_season_id"],
                    projected_season_year=p["projected_season_year"],
                    recruitment_type=p["recruitment_type"],
                    projected_obpr=p["projected_obpr"],
                    projected_dbpr=p["projected_dbpr"],
                    projected_bpr=p["projected_bpr"],
                    projected_minutes_share=p["projected_minutes_share"],
                    projection_uncertainty=p["projection_uncertainty"],
                    n_prior_seasons=p["n_prior_seasons"],
                    prior_rapm_used=p["prior_rapm_used"],
                    recruiting_prior_used=p["recruiting_prior_used"],
                    classification_reason=p.get("classification_reason", ""),
                    projection_version=p["projection_version"],
                )
            )
        else:
            for field in update_fields:
                if field in p:
                    setattr(obj, field, p[field])
            to_update.append(obj)

    from django.db import transaction

    with transaction.atomic():
        if to_create:
            PlayerSeasonProjection.objects.bulk_create(to_create, batch_size=500)
        if to_update:
            PlayerSeasonProjection.objects.bulk_update(
                to_update, update_fields, batch_size=500
            )

    n_created = len(to_create)
    n_updated = len(to_update)

    # ── Summary ───────────────────────────────────────────────────────────────
    type_counts: dict[str, int] = defaultdict(int)
    n_with_prior_rapm = 0
    n_with_recruiting_prior = 0
    n_grad_transfer_return = 0
    for p in projections:
        type_counts[p["recruitment_type"]] += 1
        if p.get("prior_rapm_used"):
            n_with_prior_rapm += 1
        if p.get("recruiting_prior_used"):
            n_with_recruiting_prior += 1
        if p.get("classification_reason") == "grad_transfer_return":
            n_grad_transfer_return += 1

    if verbose and n_grad_transfer_return > 0:
        logger.info(
            "[Projection] Grad-transfer returns detected: %d players reclassified transfer → returner.",
            n_grad_transfer_return,
        )

    summary = {
        "season_year":                season_year,
        "projected_season_year":      projected_season_year,
        "n_players":                  len(canonical_current),
        "n_split_season":             n_split_season,
        "n_projected":                len(projections),
        "n_created":                  n_created,
        "n_updated":                  n_updated,
        "recruitment_type_breakdown": dict(type_counts),
        "n_with_prior_rapm":          n_with_prior_rapm,
        "n_with_recruiting_prior":    n_with_recruiting_prior,
        "n_grad_transfer_return":     n_grad_transfer_return,
        "projection_version":         PROJECTION_VERSION,
    }

    if verbose:
        logger.info(
            "[Projection] Done: %d created, %d updated. Split-season: %d. Types: %s. Recruiting priors: %d.",
            n_created,
            n_updated,
            n_split_season,
            dict(type_counts),
            n_with_recruiting_prior,
        )

    return summary
