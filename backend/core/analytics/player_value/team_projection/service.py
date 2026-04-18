"""
Phase 5: Team Projection Service — DB I/O pipeline.

Two-pass architecture:
  PASS 1 — Load all PlayerSeasonProjection for the season, grouped by team.
            Compute base_off + base_def per team.
            Average (centering) → league_mean_base_off / league_mean_base_def.
            Load D1 context (NationalAverages + TeamSeasonRatings mean).

  PASS 2 — Run engine.project_team() per team.
            Collect all projected_adj_em / adj_o / adj_d values.
            Assign ranks from sorted distribution.
            Write / update TeamSeasonProjection rows.

Entry points:
    run_team_projection_pipeline(season_year) → list[TeamSeasonProjection]
    get_projection_distribution_stats(season_year) → dict
"""

from __future__ import annotations

import logging
from collections import defaultdict

from django.db import transaction

from core.models import (
    NationalAverages,
    PlayerSeasonProjection,
    Season,
    TeamRosterFit,
    TeamSeasonProjection,
    TeamSeasonRatings,
)

from .constants import FALLBACK_D1_ADJ_O, FALLBACK_D1_ADJ_D
from .engine import (
    D1Context,
    PlayerProjectionInput,
    RosterFitInput,
    TeamProjectionResult,
    compute_team_base_aggregates,
    project_team,
)

log = logging.getLogger(__name__)


# ── Main pipeline ─────────────────────────────────────────────────────────────


def run_team_projection_pipeline(
    season_year: int,
    *,
    dry_run: bool = False,
) -> list[TeamSeasonProjection]:
    """
    Run the full Phase 5 pipeline for `season_year`.

    Returns the list of TeamSeasonProjection instances written (or computed if
    dry_run=True).

    Args:
        season_year: Year of the *source* season whose Phase 1-4 outputs to use.
                     The projected season will be season_year + 1.
        dry_run:     If True, compute projections but do not write to DB.
    """
    log.info("Phase 5: starting team projection pipeline for season %s", season_year)

    # ── Load source season ────────────────────────────────────────────────────
    try:
        season = Season.objects.get(year=season_year)
    except Season.DoesNotExist:
        raise ValueError(f"Season {season_year} not found in DB")

    projected_year = season_year + 1

    # ── PASS 1: load all player projections, group by team ──────────────────
    all_player_rows = list(
        PlayerSeasonProjection.objects.filter(from_season=season)
        .select_related("team")
        .values(
            "team_id",
            "player_id",
            "projected_obpr",
            "projected_dbpr",
            "projected_bpr",
            "minutes_share_p2",
            "recruitment_type",
            "projection_uncertainty",
        )
    )

    if not all_player_rows:
        log.warning("No PlayerSeasonProjection rows found for season %s", season_year)
        return []

    # Group by team
    players_by_team: dict[int, list[PlayerProjectionInput]] = defaultdict(list)
    for row in all_player_rows:
        if row["minutes_share_p2"] is None or row["projected_bpr"] is None:
            continue
        players_by_team[row["team_id"]].append(
            PlayerProjectionInput(
                player_id=row["player_id"],
                projected_obpr=row["projected_obpr"] or 0.0,
                projected_dbpr=row["projected_dbpr"] or 0.0,
                projected_bpr=row["projected_bpr"] or 0.0,
                minutes_share_p2=row["minutes_share_p2"],
                recruitment_type=row["recruitment_type"] or "newcomer",
                projection_uncertainty=row["projection_uncertainty"] or 0.5,
            )
        )

    log.info("Loaded %d teams with player projections", len(players_by_team))

    # ── Compute base aggregates for every team (needed for centering) ─────────
    base_off_by_team: dict[int, float] = {}
    base_def_by_team: dict[int, float] = {}
    for team_id, players in players_by_team.items():
        b_off, b_def = compute_team_base_aggregates(players)
        base_off_by_team[team_id] = b_off
        base_def_by_team[team_id] = b_def

    league_mean_base_off = sum(base_off_by_team.values()) / len(base_off_by_team)
    league_mean_base_def = sum(base_def_by_team.values()) / len(base_def_by_team)

    log.debug(
        "League centering: mean_base_off=%.3f  mean_base_def=%.3f",
        league_mean_base_off, league_mean_base_def,
    )

    # ── Load D1 context ───────────────────────────────────────────────────────
    avg_adj_o, avg_adj_d = _get_d1_averages(season)

    d1_context = D1Context(
        avg_adj_o=avg_adj_o,
        avg_adj_d=avg_adj_d,
        league_mean_base_off=league_mean_base_off,
        league_mean_base_def=league_mean_base_def,
        n_projected_teams=len(players_by_team),
    )

    # ── Load roster-fit scores (Phase 3+4) ────────────────────────────────────
    fit_by_team: dict[int, RosterFitInput] = {}
    for fit in TeamRosterFit.objects.filter(from_season=season).select_related("team"):
        fit_by_team[fit.team_id] = RosterFitInput(
            offensive_fit_score=fit.offensive_fit_score or 50.0,
            defensive_fit_score=fit.defensive_fit_score or 50.0,
            adjusted_off_fit=fit.adjusted_off_fit if fit.adjusted_off_fit is not None else 50.0,
            adjusted_def_fit=fit.adjusted_def_fit if fit.adjusted_def_fit is not None else 50.0,
            has_team_style_data=fit.has_team_style_data,
        )

    log.info("Loaded %d TeamRosterFit records", len(fit_by_team))

    # ── PASS 2: project each team ─────────────────────────────────────────────
    team_results: list[tuple[int, TeamProjectionResult]] = []

    for team_id, players in players_by_team.items():
        roster_fit = fit_by_team.get(team_id)  # None if no fit computed yet
        result = project_team(players, roster_fit, d1_context)
        team_results.append((team_id, result))

    log.info("Engine ran for %d teams", len(team_results))

    # ── Assign ranks from the full distribution ───────────────────────────────
    _assign_ranks(team_results)

    # ── Rebuild summaries now that ranks are assigned ─────────────────────────
    for _, result in team_results:
        from .engine import _build_summary  # noqa: PLC0415 (local import OK)
        result.projection_summary = _build_summary(result)

    # ── Write to DB ───────────────────────────────────────────────────────────
    if dry_run:
        unsaved = [
            TeamSeasonProjection(
                team_id=team_id,
                from_season=season,
                **_build_projection_fields(projected_year, result),
            )
            for team_id, result in team_results
        ]
        log.info("dry_run=True — %d projections computed, no DB writes", len(unsaved))
        return unsaved

    written: list[TeamSeasonProjection] = []
    with transaction.atomic():
        for team_id, result in team_results:
            obj = _upsert_projection(team_id, season, projected_year, result)
            written.append(obj)

    log.info("Wrote %d TeamSeasonProjection rows for season %s", len(written), season_year)
    return written


# ── Rank assignment ───────────────────────────────────────────────────────────


def _assign_ranks(
    team_results: list[tuple[int, TeamProjectionResult]],
) -> None:
    """
    Assign projected_national_rank / offense_rank / defense_rank and
    national_rank_range_low / high / offense_rank_range_* / defense_rank_range_*
    in-place on each TeamProjectionResult.

    National rank: higher adj_em → better (rank 1 = best).
    Offense rank:  higher adj_o  → better (rank 1 = highest offense).
    Defense rank:  lower  adj_d  → better (rank 1 = stingiest defense).

    Rank ranges are computed from the uncertainty bands:
        rank_range_low  = best possible rank (lowest number, least teams ahead)
        rank_range_high = worst possible rank (highest number, most teams ahead)
    """
    n = len(team_results)
    if n == 0:
        return

    adj_em_vals = [r.projected_adj_em for _, r in team_results]
    adj_o_vals = [r.projected_adj_o for _, r in team_results]
    adj_d_vals = [r.projected_adj_d for _, r in team_results]

    # Sort indices for each metric
    em_order = sorted(range(n), key=lambda i: adj_em_vals[i], reverse=True)
    o_order = sorted(range(n), key=lambda i: adj_o_vals[i], reverse=True)
    d_order = sorted(range(n), key=lambda i: adj_d_vals[i])  # ascending (lower = better)

    em_rank_by_idx = {em_order[i]: i + 1 for i in range(n)}
    o_rank_by_idx = {o_order[i]: i + 1 for i in range(n)}
    d_rank_by_idx = {d_order[i]: i + 1 for i in range(n)}

    for idx, (_, result) in enumerate(team_results):
        result.projected_national_rank = em_rank_by_idx[idx]
        result.projected_offense_rank = o_rank_by_idx[idx]
        result.projected_defense_rank = d_rank_by_idx[idx]

        # EM rank range: count teams that would rank ahead at each uncertainty bound
        em_high = result.projected_adj_em_high   # optimistic EM → fewer teams ahead
        em_low = result.projected_adj_em_low     # pessimistic EM → more teams ahead
        result.national_rank_range_low = sum(1 for v in adj_em_vals if v > em_high) + 1
        result.national_rank_range_high = sum(1 for v in adj_em_vals if v > em_low) + 1

        # Offense rank range (higher adj_o = better)
        o_high = result.projected_adj_o_high
        o_low = result.projected_adj_o_low
        result.offense_rank_range_low = sum(1 for v in adj_o_vals if v > o_high) + 1
        result.offense_rank_range_high = sum(1 for v in adj_o_vals if v > o_low) + 1

        # Defense rank range (lower adj_d = better)
        # adj_d_low is numerically smaller → better defense scenario
        d_low = result.projected_adj_d_low   # best defense scenario
        d_high = result.projected_adj_d_high  # worst defense scenario
        result.defense_rank_range_low = sum(1 for v in adj_d_vals if v < d_low) + 1
        result.defense_rank_range_high = sum(1 for v in adj_d_vals if v < d_high) + 1


# ── DB helpers ───────────────────────────────────────────────────────────────


def _get_d1_averages(season: Season) -> tuple[float, float]:
    """
    Return (avg_adj_o, avg_adj_d) for the season.

    Both are pulled from the TeamSeasonRatings distribution so they share the
    same baseline. This ensures the league-mean projected AdjEM (adj_o − adj_d)
    is ~ 0.0 by construction (KenPom-style ratings are approximately zero-sum).

    Fallback chain for avg_adj_o:
      1. TeamSeasonRatings.adj_o mean  (preferred — same scale as adj_d)
      2. NationalAverages.avg_ortg     (fallback if no TeamSeasonRatings yet)
      3. FALLBACK_D1_ADJ_O hard-coded constant
    """
    from django.db.models import Avg  # noqa: PLC0415

    agg = TeamSeasonRatings.objects.filter(season=season).aggregate(
        mean_o=Avg("adj_o"),
        mean_d=Avg("adj_d"),
    )

    avg_adj_o = FALLBACK_D1_ADJ_O
    avg_adj_d = FALLBACK_D1_ADJ_D

    if agg["mean_o"] is not None:
        avg_adj_o = float(agg["mean_o"])
    else:
        # No TeamSeasonRatings yet — try NationalAverages as a proxy
        try:
            na = NationalAverages.objects.get(season=season)
            if na.avg_ortg:
                avg_adj_o = float(na.avg_ortg)
        except NationalAverages.DoesNotExist:
            log.warning("No adj_o data for season %s; using fallback %.2f", season.year, avg_adj_o)

    if agg["mean_d"] is not None:
        avg_adj_d = float(agg["mean_d"])
    else:
        log.warning("No adj_d data for season %s; using fallback %.2f", season.year, avg_adj_d)

    log.debug("D1 context: avg_adj_o=%.3f  avg_adj_d=%.3f", avg_adj_o, avg_adj_d)
    return avg_adj_o, avg_adj_d


def _build_projection_fields(projected_year: int, result: TeamProjectionResult) -> dict:
    """Build the field dict shared by _upsert_projection and dry-run object construction."""
    return {
        "projected_season_year": projected_year,
        "base_team_offense": result.base_team_offense,
        "base_team_defense": result.base_team_defense,
        "base_team_roster_strength": result.base_team_roster_strength,
        "returner_minutes_fraction": result.returner_minutes_fraction,
        "continuity_score": result.continuity_score,
        "continuity_adjustment_off": result.continuity_adjustment_off,
        "continuity_adjustment_def": result.continuity_adjustment_def,
        # Phase 6: BPR-weighted stability diagnostics
        "returner_bpr_fraction": result.returner_bpr_fraction,
        "transfer_minutes_fraction": result.transfer_minutes_fraction,
        "transfer_bpr_fraction": result.transfer_bpr_fraction,
        "transfer_dependence_score": result.transfer_dependence_score,
        "continuity_value_score": result.continuity_value_score,
        "transfer_fit_risk_score": result.transfer_fit_risk_score,
        "fit_adjustment_off": result.fit_adjustment_off,
        "fit_adjustment_def": result.fit_adjustment_def,
        "coaching_continuity_adjustment": result.coaching_continuity_adjustment,
        "projected_adj_o": result.projected_adj_o,
        "projected_adj_d": result.projected_adj_d,
        "projected_adj_em": result.projected_adj_em,
        "team_projection_uncertainty": result.team_projection_uncertainty,
        "projected_adj_o_low": result.projected_adj_o_low,
        "projected_adj_o_high": result.projected_adj_o_high,
        "projected_adj_d_low": result.projected_adj_d_low,
        "projected_adj_d_high": result.projected_adj_d_high,
        "projected_adj_em_low": result.projected_adj_em_low,
        "projected_adj_em_high": result.projected_adj_em_high,
        "projected_national_rank": result.projected_national_rank,
        "projected_offense_rank": result.projected_offense_rank,
        "projected_defense_rank": result.projected_defense_rank,
        "national_rank_range_low": result.national_rank_range_low,
        "national_rank_range_high": result.national_rank_range_high,
        "offense_rank_range_low": result.offense_rank_range_low,
        "offense_rank_range_high": result.offense_rank_range_high,
        "defense_rank_range_low": result.defense_rank_range_low,
        "defense_rank_range_high": result.defense_rank_range_high,
        "projection_summary": result.projection_summary,
        "driver_breakdown": result.driver_breakdown,
    }


def _upsert_projection(
    team_id: int,
    season: Season,
    projected_year: int,
    result: TeamProjectionResult,
) -> TeamSeasonProjection:
    """Create or update the TeamSeasonProjection row for the given team."""
    obj, _ = TeamSeasonProjection.objects.update_or_create(
        team_id=team_id,
        from_season=season,
        defaults=_build_projection_fields(projected_year, result),
    )
    return obj


# ── Validation / diagnostics ─────────────────────────────────────────────────


def get_projection_distribution_stats(season_year: int) -> dict:
    """
    Return distribution statistics for TeamSeasonProjection for `season_year`.
    Useful for validating pipeline output against historical norms.
    """
    from django.db.models import Avg, Max, Min, StdDev, Count  # noqa: PLC0415

    qs = TeamSeasonProjection.objects.filter(from_season__year=season_year)
    agg = qs.aggregate(
        n=Count("id"),
        avg_o=Avg("projected_adj_o"),
        std_o=StdDev("projected_adj_o"),
        avg_d=Avg("projected_adj_d"),
        std_d=StdDev("projected_adj_d"),
        avg_em=Avg("projected_adj_em"),
        std_em=StdDev("projected_adj_em"),
        min_em=Min("projected_adj_em"),
        max_em=Max("projected_adj_em"),
        avg_uncertainty=Avg("team_projection_uncertainty"),
    )
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in agg.items()}


def get_top_teams(season_year: int, n: int = 10) -> list[dict]:
    """Return top-N teams by projected_adj_em for quick validation."""
    return list(
        TeamSeasonProjection.objects.filter(from_season__year=season_year)
        .select_related("team")
        .order_by("projected_national_rank")[:n]
        .values(
            "projected_national_rank",
            "team__name",
            "projected_adj_o",
            "projected_adj_d",
            "projected_adj_em",
            "national_rank_range_low",
            "national_rank_range_high",
            "team_projection_uncertainty",
        )
    )
