"""
Roster Fit Service — Phase 3.

Orchestrates DB loading → engine → DB upsert for baseline roster fit scores.

The engine (engine.py) is fully stateless; this service layer adds:
  • Loading PlayerSeasonProjection rows (with Phase 2 minutes outputs)
  • Loading matching PlayerSeasonStats for box-score & four-factor signals
  • Optionally computing season-relative SeasonRefs from actual player data
  • Grouping by team and calling score_roster_fit() per team
  • Upserting TeamRosterFit rows (update_or_create on team + from_season)

For sandbox / hypothetical rosters call the engine directly:
    from ncaa.analytics.player_value.fit.engine import (
        score_roster_fit, RosterFitResult,
    )
    from ncaa.analytics.player_value.fit.archetypes import PlayerFitInput
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from typing import Optional

from ncaa.analytics.player_value.fit.archetypes import PlayerFitInput, SeasonRefs
from ncaa.analytics.player_value.fit.engine import score_roster_fit
from ncaa.analytics.player_value.fit.constants import SEASON_REF_MIN_PLAYERS

logger = logging.getLogger(__name__)

# Fields from PlayerSeasonStats loaded for each player
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


def _build_season_refs(stats_list: list[dict]) -> SeasonRefs:
    """
    Compute SeasonRefs from a list of qualifying player-season stat dicts.

    Qualifying = gp >= 10 and off_poss >= 200.
    Returns DEFAULT_REFS (hard-coded D1 constants) when fewer than
    SEASON_REF_MIN_PLAYERS qualifying rows exist.
    """

    def _ref(vals: list[float]) -> tuple[float, float]:
        """Return (mean, std_dev); defend against empty or zero-var lists."""
        if not vals:
            return (0.0, 1.0)
        m = statistics.mean(vals)
        sd = statistics.pstdev(vals) if len(vals) > 1 else 1.0
        return (m, max(sd, 0.01))

    qual = [
        s for s in stats_list
        if (s.get("gp") or 0) >= 10 and (s.get("off_poss") or 0.0) >= 200
    ]
    if len(qual) < SEASON_REF_MIN_PLAYERS:
        from ncaa.analytics.player_value.fit.archetypes import DEFAULT_REFS
        return DEFAULT_REFS

    def _collect(key: str) -> list[float]:
        return [float(s[key]) for s in qual if s.get(key) is not None]

    return SeasonRefs(
        fg3a_pg=_ref(_collect("fg3a_pg")),
        ast_pg=_ref([float(s["ast"]) for s in qual if s.get("ast") is not None]),
        tov_pg=_ref([float(s["tov"]) for s in qual if s.get("tov") is not None]),
        blk_pg=_ref([float(s["blk"]) for s in qual if s.get("blk") is not None]),
        stl_pg=_ref([float(s["stl"]) for s in qual if s.get("stl") is not None]),
        pf_pg=_ref([float(s["pf"]) for s in qual if s.get("pf") is not None]),
        oreb_pg=_ref(_collect("oreb_pg")),
        dreb_pg=_ref(_collect("dreb_pg")),
        fta_pg=_ref(_collect("fta_pg")),
        efg_pct=_ref(_collect("efg_pct")),
        ts_pct=_ref(_collect("ts_pct")),
        ast_to=_ref(_collect("ast_to")),
        proj_obpr=_ref(_collect("obpr")),
        proj_dbpr=_ref(_collect("dbpr")),
        off_efg_impact=_ref(_collect("off_efg_impact")),
        def_efg_impact=_ref(_collect("def_efg_impact")),
        off_tov_impact=_ref(_collect("off_tov_impact")),
        def_tov_impact=_ref(_collect("def_tov_impact")),
        off_orb_impact=_ref(_collect("off_orb_impact")),
        def_reb_impact=_ref(_collect("def_reb_impact")),
        off_ftr_impact=_ref(_collect("off_ftr_impact")),
        def_ftr_impact=_ref(_collect("def_ftr_impact")),
        on_court_adj_o=_ref(_collect("on_court_adj_o")),
        on_court_adj_d=_ref(_collect("on_court_adj_d")),
    )


def _build_player_fit_input(
    proj: dict,
    stats: Optional[dict],
) -> PlayerFitInput:
    """
    Build one PlayerFitInput from a PlayerSeasonProjection + optional stats dict.

    When stats is None (e.g. true freshman with no from_season data) all
    box-score and impact fields default to None; the engine falls back to D1
    reference means (z-score of 0) for each missing value.
    """
    s = stats or {}
    player_id = proj["player_id"]

    return PlayerFitInput(
        player_id=player_id,
        player_name=proj.get("player_name", ""),

        # Phase 2
        minutes_share_p2=proj.get("minutes_share_p2") or 0.0,
        rotation_rank=proj.get("rotation_rank") or 99,
        role_bucket=proj.get("role_bucket") or "Wing",

        # Phase 1 projections (prefer projection fields; fall back to from-season actuals)
        projected_obpr=proj.get("projected_obpr"),
        projected_dbpr=proj.get("projected_dbpr"),

        # Box-score rates from from_season stats
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

        # Four-factor impact
        off_efg_impact=s.get("off_efg_impact"),
        def_efg_impact=s.get("def_efg_impact"),
        off_tov_impact=s.get("off_tov_impact"),
        def_tov_impact=s.get("def_tov_impact"),
        off_orb_impact=s.get("off_orb_impact"),
        def_reb_impact=s.get("def_reb_impact"),
        off_ftr_impact=s.get("off_ftr_impact"),
        def_ftr_impact=s.get("def_ftr_impact"),

        # On-court adjusted metrics
        on_court_adj_o=s.get("on_court_adj_o"),
        on_court_adj_d=s.get("on_court_adj_d"),
        on_court_off_poss=s.get("on_court_off_poss"),
        on_court_def_poss=s.get("on_court_def_poss"),
    )


def run_fit_pipeline(
    season_year: int,
    verbose: bool = True,
) -> dict:
    """
    Compute and persist roster fit scores for all teams in a given season.

    This is the baseline pipeline that runs against real Phase 2 projections.

    For every team that has PlayerSeasonProjection rows from season_year,
    this function:
      1. Loads all Phase 2 projection data (minutes, role_bucket, etc.).
      2. Loads matching PlayerSeasonStats for box-score & four-factor signals.
      3. Optionally derives season-aware SeasonRefs.
      4. Calls score_roster_fit() per team.
      5. Upserts one TeamRosterFit row per team.

    Args:
        season_year:  The from_season year (e.g. 2026).
        verbose:      Whether to emit INFO-level log messages.

    Returns:
        Summary dict: {season_year, n_teams, n_players, n_written, n_errors}.
    """
    from django.db import transaction
    from ncaa.models import (
        PlayerSeasonProjection,
        PlayerSeasonStats,
        Season,
        TeamRosterFit,
    )

    # ── Load the from_season object ───────────────────────────────────────
    try:
        from_season = Season.objects.get(year=season_year)
    except Season.DoesNotExist:
        logger.error("[FitPipeline] Season %d not found in DB.", season_year)
        return {"season_year": season_year, "n_teams": 0, "n_players": 0,
                "n_written": 0, "n_errors": 0}

    # ── Load all projections that carry Phase 2 minutes output ────────────
    projections = list(
        PlayerSeasonProjection.objects
        .filter(from_season__year=season_year)
        .values(
            "id",
            "player_id",
            "player__display_name",
            "team_id",
            "projected_obpr",
            "projected_dbpr",
            "minutes_share_p2",
            "mpg_p2",
            "rotation_rank",
            "role_bucket",
            "recruitment_type",
        )
    )

    if not projections:
        logger.warning(
            "[FitPipeline] No projections found for season %d.", season_year,
        )
        return {"season_year": season_year, "n_teams": 0, "n_players": 0,
                "n_written": 0, "n_errors": 0}

    # Attach a readable name for diagnostics
    for p in projections:
        p["player_name"] = p.get("player__display_name") or ""

    player_ids = [p["player_id"] for p in projections]

    # ── Load from_season stats (best row per player by possession count) ──
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

    # ── Compute season-relative reference values ─────────────────────────
    refs = _build_season_refs(list(stats_by_player.values()))
    if verbose:
        n_qual = sum(
            1 for s in stats_by_player.values()
            if (s.get("gp") or 0) >= 10 and (s.get("off_poss") or 0.0) >= 200
        )
        logger.info(
            "[FitPipeline] Season %d refs: %d qualifying player-seasons (need %d).",
            season_year, n_qual, SEASON_REF_MIN_PLAYERS,
        )

    # ── Group projections by team ─────────────────────────────────────────
    by_team: dict[Optional[int], list[dict]] = defaultdict(list)
    for proj in projections:
        by_team[proj["team_id"]].append(proj)

    if verbose:
        logger.info(
            "[FitPipeline] Season %d: %d projections across %d teams.",
            season_year, len(projections), len(by_team),
        )

    # ── Score per team and collect DB objects ─────────────────────────────
    n_errors = 0
    roster_fit_rows: list[dict] = []          # keyed by team_id

    for team_id, team_projs in by_team.items():
        if team_id is None:
            continue

        players = [
            _build_player_fit_input(proj, stats_by_player.get(proj["player_id"]))
            for proj in team_projs
        ]

        try:
            result = score_roster_fit(
                players,
                refs=refs,
                team_id=team_id,
                season_year=season_year + 1,  # projecting NEXT season
            )
        except Exception as exc:   # noqa: BLE001
            logger.warning(
                "[FitPipeline] Team %s fit failed: %s", team_id, exc, exc_info=True,
            )
            n_errors += 1
            continue

        roster_fit_rows.append({
            "team_id":             team_id,
            "from_season_id":      from_season.id,
            "projected_season_year": season_year + 1,
            "n_players":           len(players),
            # overall
            "overall_fit_score":   result.overall_fit_score,
            "offensive_fit_score": result.offensive_fit_score,
            "defensive_fit_score": result.defensive_fit_score,
            # offensive subs
            "creation_fit":         result.creation_fit,
            "shooting_fit":         result.shooting_fit,
            "ball_security_fit":    result.ball_security_fit,
            "finishing_fit":        result.finishing_fit,
            "pressure_fit":         result.pressure_fit,
            "off_rebounding_fit":   result.off_rebounding_fit,
            "role_balance_off_fit": result.role_balance_off_fit,
            "off_total_penalty":    result.off_total_penalty,
            # defensive subs
            "rim_protection_fit":    result.rim_protection_fit,
            "def_rebounding_fit":    result.def_rebounding_fit,
            "disruption_fit":        result.disruption_fit,
            "foul_discipline_fit":   result.foul_discipline_fit,
            "perimeter_defense_fit": result.perimeter_defense_fit,
            "size_coverage_fit":     result.size_coverage_fit,
            "mobility_fit":          result.mobility_fit,
            "role_balance_def_fit":  result.role_balance_def_fit,
            "def_total_penalty":     result.def_total_penalty,
            # diagnostics
            "off_penalties":        [[l, p] for l, p in result.off_penalties],
            "def_penalties":        [[l, p] for l, p in result.def_penalties],
            "offensive_strengths":  result.offensive_strengths,
            "offensive_weaknesses": result.offensive_weaknesses,
            "defensive_strengths":  result.defensive_strengths,
            "defensive_weaknesses": result.defensive_weaknesses,
            "fit_summary":          result.fit_summary,
        })

    # ── Bulk upsert ───────────────────────────────────────────────────────
    n_written = 0
    if roster_fit_rows:
        update_fields = [
            "projected_season_year", "n_players",
            "overall_fit_score", "offensive_fit_score", "defensive_fit_score",
            "creation_fit", "shooting_fit", "ball_security_fit", "finishing_fit",
            "pressure_fit", "off_rebounding_fit", "role_balance_off_fit", "off_total_penalty",
            "rim_protection_fit", "def_rebounding_fit", "disruption_fit",
            "foul_discipline_fit", "perimeter_defense_fit", "size_coverage_fit",
            "mobility_fit", "role_balance_def_fit", "def_total_penalty",
            "off_penalties", "def_penalties",
            "offensive_strengths", "offensive_weaknesses",
            "defensive_strengths", "defensive_weaknesses",
            "fit_summary",
        ]

        with transaction.atomic():
            for row in roster_fit_rows:
                obj, _ = TeamRosterFit.objects.update_or_create(
                    team_id=row["team_id"],
                    from_season_id=row["from_season_id"],
                    defaults={k: row[k] for k in row
                               if k not in ("team_id", "from_season_id")},
                )
                n_written += 1

    if verbose:
        logger.info(
            "[FitPipeline] Done: %d teams scored, %d rows written, %d errors.",
            len(roster_fit_rows), n_written, n_errors,
        )

    return {
        "season_year": season_year,
        "projected_season_year": season_year + 1,
        "n_teams":   len(roster_fit_rows),
        "n_players": len(projections),
        "n_written": n_written,
        "n_errors":  n_errors,
    }
