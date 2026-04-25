"""
data_loader.py — Leakage-safe data loading for roster-outlook backtesting.

For each source season Y, loads:
  - PlayerSeasonStats for Y  (player-level talent proxy inputs)
  - PlayerSeasonStats for Y-1 (for recruitment_type derivation — same logic as pipeline.py)
  - TeamSeasonRatings for Y  (D1 context + "prior-year" outcome for Model A baseline)
  - TeamSeasonRatings for Y+1 (actual outcomes — EVALUATION ONLY, never used as input)
  - TeamRosterFit for Y if it exists (fit adjustment layer; None if unavailable)

Leakage guarantee
  All Y+1 data is returned in a clearly-named `actual_outcomes` structure.
  Callers must apply it ONLY to prediction errors after predictions are finalized.

Recruitment type derivation (mirrors pipeline.py _pick_canonical_row logic):
  For player P on team T in source year Y:
    - P had PSS at team T in Y-1  → "returner"
    - P had PSS at team T' ≠ T in Y-1 → "transfer"
    - P had no PSS in Y-1          → "newcomer"

Minutes normalization:
  minutes_share_p2 = (mpg / team_total_mpg) × 5.0
  → team total ≈ 5.0 (matches Phase 2 convention; see engine.py)

D1 team filter:
  Only teams that appear in TeamSeasonRatings for BOTH source year Y AND target
  year Y+1 are included, ensuring we have ground truth for evaluation.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Minimum qualifying criteria to avoid noise from inactive players
MIN_MPG: float = 5.0
MIN_GP: int = 5

# minutes_share_p2 convention: team sums ≈ 5.0 (see engine.py)
MINUTES_SHARE_SCALE: float = 5.0

# Default per-player uncertainty when we don't run Phase 1-2 (use midpoint)
DEFAULT_PLAYER_UNCERTAINTY: float = 0.35


# ── Data containers ────────────────────────────────────────────────────────────

@dataclass
class PlayerRow:
    """Per-player source-year data used to build engine inputs."""
    player_id: int
    team_slug: str
    obpr: float
    dbpr: float
    bpr: float
    mpg: float
    gp: int
    recruitment_type: str  # 'returner' | 'transfer' | 'newcomer'
    minutes_share_p2: float = 0.0  # filled by _normalize_minutes()


@dataclass
class TeamPlayerPool:
    """One team's qualifying players for source year Y."""
    team_slug: str
    source_year: int
    players: list[PlayerRow]
    n_players: int = 0

    def __post_init__(self):
        self.n_players = len(self.players)


@dataclass
class ActualOutcome:
    """Ground-truth team outcome from TeamSeasonRatings."""
    team_slug: str
    adj_o: float
    adj_d: float
    adj_em: float
    rank_adj_em: Optional[int] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    tournament_seed: Optional[int] = None


@dataclass
class BacktestPair:
    """
    One fully-loaded source→target backtest pair.

    team_pools       — source-year player inputs (what the model gets to see)
    actual_outcomes  — target-year adj_em/o/d  (ground truth; evaluation only)
    source_outcomes  — source-year adj_em/o/d  (Model A prior-year baseline)
    d1_avg_o        — D1 average adj_o in source year (D1 calibration anchor)
    d1_avg_d        — D1 average adj_d in source year
    prior_year_has_data — True when source_year-1 PlayerSeasonStats exist, allowing
                          meaningful recruitment-type classification (returner/transfer/
                          newcomer).  False when prior-year PSS is absent from the DB
                          (e.g. source_year=2023 with no 2022 data); in that case all
                          players fall back to 'newcomer', making returner_fraction=0
                          for every team — a data artifact, not reality.  Ablation
                          Models D/E/F respect this flag and skip continuity when False.
    """
    source_year: int
    target_year: int
    team_pools: dict[str, TeamPlayerPool]       # team_slug → pool
    actual_outcomes: dict[str, ActualOutcome]   # target-year TSR (leakage-safe)
    source_outcomes: dict[str, ActualOutcome]   # source-year TSR
    d1_avg_o: float
    d1_avg_d: float
    n_d1_teams: int = 0
    prior_year_has_data: bool = True  # False → no source_year-1 PSS; continuity unreliable

    # Summary stats (set after construction)
    n_teams_with_pools: int = 0
    n_teams_with_actuals: int = 0

    def __post_init__(self):
        self.n_teams_with_pools = len(self.team_pools)
        self.n_teams_with_actuals = len(self.actual_outcomes)

    def evaluable_teams(self) -> list[str]:
        """Return team slugs that have both a player pool AND an actual outcome."""
        return [
            slug for slug in self.team_pools
            if slug in self.actual_outcomes and len(self.team_pools[slug].players) >= 3
        ]


# ── Public API ────────────────────────────────────────────────────────────────

def load_backtest_pair(
    source_year: int,
    min_mpg: float = MIN_MPG,
    min_gp: int = MIN_GP,
) -> BacktestPair:
    """
    Load all data for source_year → source_year+1 backtest pair.

    Args:
        source_year: Season whose PlayerSeasonStats are used as model inputs.
                     (e.g. 2023 → predicts 2024 outcomes)
        min_mpg:     Minimum minutes/game to include a player (noise filter).
        min_gp:      Minimum games played to include a player (noise filter).

    Returns:
        BacktestPair ready for ablation.run_all_models().
    """
    # Django models imported here to allow DB-free unit testing of helpers
    from ncaa.models import PlayerSeasonStats, TeamSeasonRatings, TeamRosterFit

    target_year = source_year + 1

    # ── Load D1 teams present in BOTH source and target TSR ────────────────
    source_tsr_slugs = set(
        TeamSeasonRatings.objects
        .filter(season__year=source_year, team__slug__isnull=False)
        .values_list("team__slug", flat=True)
    )
    target_tsr_map: dict[str, ActualOutcome] = {}
    for row in TeamSeasonRatings.objects.filter(
        season__year=target_year, team__slug__isnull=False
    ).values(
        "team__slug", "adj_o", "adj_d", "adj_em",
        "rank_adj_em", "wins", "losses", "tournament_seed",
    ):
        slug = row["team__slug"]
        target_tsr_map[slug] = ActualOutcome(
            team_slug=slug,
            adj_o=float(row["adj_o"] or 0.0),
            adj_d=float(row["adj_d"] or 0.0),
            adj_em=float(row["adj_em"] or 0.0),
            rank_adj_em=row["rank_adj_em"],
            wins=row["wins"],
            losses=row["losses"],
            tournament_seed=row["tournament_seed"],
        )

    # D1 is intersection: teams with both source AND target TSR
    d1_slugs = source_tsr_slugs & set(target_tsr_map.keys())

    # ── Load source-year TSR outcomes (for Model A prior-year baseline) ─────
    source_outcomes: dict[str, ActualOutcome] = {}
    for row in TeamSeasonRatings.objects.filter(
        season__year=source_year, team__slug__in=d1_slugs
    ).values(
        "team__slug", "adj_o", "adj_d", "adj_em",
        "rank_adj_em", "wins", "losses", "tournament_seed",
    ):
        slug = row["team__slug"]
        source_outcomes[slug] = ActualOutcome(
            team_slug=slug,
            adj_o=float(row["adj_o"] or 0.0),
            adj_d=float(row["adj_d"] or 0.0),
            adj_em=float(row["adj_em"] or 0.0),
            rank_adj_em=row["rank_adj_em"],
            wins=row["wins"],
            losses=row["losses"],
            tournament_seed=row["tournament_seed"],
        )

    # D1 context: avg adj_o/d from source-year TSR
    from django.db.models import Avg
    agg = TeamSeasonRatings.objects.filter(season__year=source_year).aggregate(
        avg_o=Avg("adj_o"), avg_d=Avg("adj_d")
    )
    from ncaa.analytics.player_value.team_projection.constants import (
        FALLBACK_D1_ADJ_O, FALLBACK_D1_ADJ_D,
    )
    d1_avg_o = float(agg["avg_o"] or FALLBACK_D1_ADJ_O)
    d1_avg_d = float(agg["avg_d"] or FALLBACK_D1_ADJ_D)

    # ── Load source-year PlayerSeasonStats (grouped by team) ───────────────
    source_rows = list(
        PlayerSeasonStats.objects
        .filter(
            season__year=source_year,
            team__slug__in=d1_slugs,
            mpg__gte=min_mpg,
            gp__gte=min_gp,
        )
        .values(
            "player_id", "team__slug",
            "obpr", "dbpr", "bpr",
            "mpg", "gp",
        )
    )

    # ── Load prior-year (Y-1) PSS for recruitment_type derivation ──────────
    prior_rows = list(
        PlayerSeasonStats.objects
        .filter(season__year=source_year - 1)
        .values("player_id", "team__slug")
    )
    # Detect whether prior-year PSS data is available at all.
    # If not, every player will fall back to 'newcomer', making returner_fraction=0
    # for every team — a data-availability artifact, not real roster turnover.
    prior_year_has_data: bool = bool(prior_rows)

    # Map player_id → prior team slug (canonical: highest mpg prior row)
    prior_team_by_player: dict[int, str] = {}
    for pr in prior_rows:
        pid = pr["player_id"]
        slug = pr["team__slug"] or ""
        if pid not in prior_team_by_player:
            prior_team_by_player[pid] = slug

    # ── Group players by team, derive recruitment type, normalize minutes ──
    by_team: dict[str, list[dict]] = defaultdict(list)
    for row in source_rows:
        slug = row["team__slug"]
        if slug:
            by_team[slug].append(row)

    team_pools: dict[str, TeamPlayerPool] = {}
    for team_slug, rows in by_team.items():
        players = _build_player_rows(rows, team_slug, prior_team_by_player)
        if players:
            team_pools[team_slug] = TeamPlayerPool(
                team_slug=team_slug,
                source_year=source_year,
                players=players,
            )

    logger.info(
        "[Backtest %d→%d] %d D1 teams, %d with player pools, %d with actuals",
        source_year, target_year,
        len(d1_slugs), len(team_pools), len(target_tsr_map),
    )

    return BacktestPair(
        source_year=source_year,
        target_year=target_year,
        team_pools=team_pools,
        actual_outcomes=target_tsr_map,
        source_outcomes=source_outcomes,
        d1_avg_o=d1_avg_o,
        d1_avg_d=d1_avg_d,
        n_d1_teams=len(d1_slugs),
        prior_year_has_data=prior_year_has_data,
    )


def available_source_years() -> list[int]:
    """
    Return source years where backtesting is possible — i.e., there exist
    PlayerSeasonStats for year Y and TeamSeasonRatings for both Y and Y+1.
    """
    from ncaa.models import PlayerSeasonStats, TeamSeasonRatings
    from django.db.models import Count

    pss_years = set(
        PlayerSeasonStats.objects.values_list("season__year", flat=True).distinct()
    )
    tsr_years = set(
        TeamSeasonRatings.objects.values_list("season__year", flat=True).distinct()
    )
    return sorted(
        yr for yr in pss_years
        if yr in tsr_years and (yr + 1) in tsr_years
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_player_rows(
    rows: list[dict],
    team_slug: str,
    prior_team_by_player: dict[int, str],
) -> list[PlayerRow]:
    """
    Convert raw PSS dicts to PlayerRow objects with recruitment_type and
    normalized minutes_share_p2.

    Filters out rows with null BPR fields (only box stats, no RAPM) by
    using 0.0 for both obpr and dbpr in that case, since we're using
    actual realized stats as a proxy.
    """
    if not rows:
        return []

    total_mpg = sum(float(r["mpg"] or 0.0) for r in rows)
    if total_mpg <= 0:
        return []

    players = []
    for row in rows:
        pid = row["player_id"]
        mpg = float(row["mpg"] or 0.0)
        obpr = float(row["obpr"] or 0.0)
        dbpr = float(row["dbpr"] or 0.0)
        bpr = float(row["bpr"] or (obpr + dbpr))

        recruitment_type = _derive_recruitment_type(pid, team_slug, prior_team_by_player)
        minutes_share_p2 = (mpg / total_mpg) * MINUTES_SHARE_SCALE

        players.append(PlayerRow(
            player_id=pid,
            team_slug=team_slug,
            obpr=obpr,
            dbpr=dbpr,
            bpr=bpr,
            mpg=mpg,
            gp=int(row["gp"] or 0),
            recruitment_type=recruitment_type,
            minutes_share_p2=minutes_share_p2,
        ))

    return players


def _derive_recruitment_type(
    player_id: int,
    current_team_slug: str,
    prior_team_by_player: dict[int, str],
) -> str:
    """
    Classify how a player arrived at their source-year team vs the prior year.

    Returns 'returner', 'transfer', or 'newcomer' — same semantics as
    pipeline.py / engine.py classify_recruitment_type().

    Note: players whose prior-year team had no slug (non-D1 schools) are
    treated as newcomers, not transfers — consistent with pipeline.py behavior
    and matching how the engine treats first-time D1 players.
    """
    prior_slug = prior_team_by_player.get(player_id)
    if not prior_slug:
        # None → no prior season; "" → prior was non-D1 school (no slug).
        # Both cases: treat as newcomer — the player is new to D1 context.
        return "newcomer"
    if prior_slug == current_team_slug:
        return "returner"
    return "transfer"
