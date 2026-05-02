"""
ncaa/analytics/staleness.py — Pipeline phase staleness detection.

Pure business logic — no Django imports, no DB access.
All timestamps are passed in by callers so this module is fully testable
without a database.

Usage:
    from ncaa.analytics.staleness import check_staleness, check_team_staleness_bulk
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class StalenessWarning:
    """
    A staleness warning for a single team and season.

    severity: "warning" | "error"
      "warning" — data is stale but still usable with caution
      "error"   — data is so stale it should not be displayed to users

    upstream_phase: the phase that was re-run
    downstream_phase: the phase whose data is now stale
    upstream_computed_at: when the upstream phase last ran
    downstream_computed_at: when the downstream phase last ran
    delta_seconds: how many seconds stale (downstream older than upstream by this much)
    message: human-readable description for API response / admin UI
    """
    team_id: int
    season_year: int
    severity: str
    upstream_phase: str
    downstream_phase: str
    upstream_computed_at: datetime
    downstream_computed_at: datetime
    delta_seconds: float
    message: str


def _ensure_aware(dt: datetime) -> datetime:
    """Return a timezone-aware datetime, assuming UTC if naive."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _stale_seconds(upstream: datetime, downstream: datetime) -> float:
    """Return how many seconds downstream lags behind upstream (positive = stale)."""
    u = _ensure_aware(upstream)
    d = _ensure_aware(downstream)
    return (u - d).total_seconds()


def _make_warning(
    team_id: int,
    season_year: int,
    upstream_phase: str,
    downstream_phase: str,
    upstream_computed_at: datetime,
    downstream_computed_at: datetime,
    delta_seconds: float,
) -> StalenessWarning:
    hours = delta_seconds / 3600
    severity = "error" if delta_seconds >= 86400 else "warning"
    hours_str = f"{hours:.1f}h" if hours >= 1 else f"{delta_seconds / 60:.0f}m"
    message = (
        f"{downstream_phase} data is {hours_str} stale relative to {upstream_phase}. "
        f"{upstream_phase} last ran at {upstream_computed_at.strftime('%Y-%m-%d %H:%M UTC')}, "
        f"{downstream_phase} last ran at {downstream_computed_at.strftime('%Y-%m-%d %H:%M UTC')}."
    )
    return StalenessWarning(
        team_id=team_id,
        season_year=season_year,
        severity=severity,
        upstream_phase=upstream_phase,
        downstream_phase=downstream_phase,
        upstream_computed_at=upstream_computed_at,
        downstream_computed_at=downstream_computed_at,
        delta_seconds=delta_seconds,
        message=message,
    )


def check_staleness(
    season_year: int,
    team_id: int,
    psp_computed_at: Optional[datetime],      # PlayerSeasonProjection (Phase 1) latest
    trf_computed_at: Optional[datetime],      # TeamRosterFit (Phase 3) latest
    tsp_computed_at: Optional[datetime],      # TeamSeasonProjection (Phase 5) latest
    warn_threshold_seconds: float = 300.0,    # 5 minutes — grace period for pipeline runs
) -> list[StalenessWarning]:
    """
    Check for staleness between pipeline phases for a single team/season.

    Rules:
      Phase 3 stale if trf_computed_at < psp_computed_at - threshold
        (roster fit was computed before the latest player projections)
      Phase 5 stale if tsp_computed_at < psp_computed_at - threshold
        (team projection was computed before the latest player projections)
      Phase 5 stale if tsp_computed_at < trf_computed_at - threshold
        (team projection was computed before the latest roster fit)

    Severity:
      If stale by > 24 hours: severity = "error"
      If stale by > warn_threshold_seconds: severity = "warning"

    Returns an empty list when all phases are current.
    None timestamps are treated as "not yet computed" and do not trigger warnings.
    """
    warnings: list[StalenessWarning] = []

    # Phase 1 → Phase 3
    if psp_computed_at is not None and trf_computed_at is not None:
        delta = _stale_seconds(psp_computed_at, trf_computed_at)
        if delta > warn_threshold_seconds:
            warnings.append(_make_warning(
                team_id, season_year,
                "Phase 1", "Phase 3",
                psp_computed_at, trf_computed_at, delta,
            ))

    # Phase 1 → Phase 5
    if psp_computed_at is not None and tsp_computed_at is not None:
        delta = _stale_seconds(psp_computed_at, tsp_computed_at)
        if delta > warn_threshold_seconds:
            warnings.append(_make_warning(
                team_id, season_year,
                "Phase 1", "Phase 5",
                psp_computed_at, tsp_computed_at, delta,
            ))

    # Phase 3 → Phase 5
    if trf_computed_at is not None and tsp_computed_at is not None:
        delta = _stale_seconds(trf_computed_at, tsp_computed_at)
        if delta > warn_threshold_seconds:
            warnings.append(_make_warning(
                team_id, season_year,
                "Phase 3", "Phase 5",
                trf_computed_at, tsp_computed_at, delta,
            ))

    return warnings


def check_team_staleness_bulk(
    season_year: int,
    teams_data: list[dict],
) -> dict[int, list[StalenessWarning]]:
    """
    Run check_staleness() for multiple teams at once.

    teams_data: list of dicts with keys:
      team_id, psp_computed_at, trf_computed_at, tsp_computed_at

    Returns: {team_id: [StalenessWarning, ...]}
    Only includes teams with at least one warning.
    """
    result: dict[int, list[StalenessWarning]] = {}
    for row in teams_data:
        tid = row["team_id"]
        warnings = check_staleness(
            season_year=season_year,
            team_id=tid,
            psp_computed_at=row.get("psp_computed_at"),
            trf_computed_at=row.get("trf_computed_at"),
            tsp_computed_at=row.get("tsp_computed_at"),
        )
        if warnings:
            result[tid] = warnings
    return result
