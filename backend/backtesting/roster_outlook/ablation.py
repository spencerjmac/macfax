"""
ablation.py — Ablation model variants for roster-outlook backtesting.

Six models on an additive ladder from simplest to most complete:

  A — Prior-year adj_em (team's own previous-season performance)
  B — Equal-minutes talent average (no minutes weighting, no engine adjustments)
  C — Minutes-weighted talent (actual mpg weights, no continuity/fit)
  D — Minutes-weighted talent + continuity (engine continuity adjustment)
  E — Minutes-weighted talent + continuity + fit  (fit=0 if unavailable historically)
  F — Direct-returner-bump counterfactual (returner BPR × BUMP_FACTOR; no continuity formula)

Leakage safety:
  All models receive only source-year data (PlayerSeasonStats + TeamSeasonRatings for Y).
  Target-year data never enters any prediction path.

Two-pass D1 centering:
  For Models B-F, a first pass computes each team's base_off / base_def aggregates.
  The mean across D1 teams (league_mean_base_off/def) is then used as the centering
  anchor for each team's final projected ratings — exactly mirroring service.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .data_loader import (
    ActualOutcome,
    BacktestPair,
    PlayerRow,
    DEFAULT_PLAYER_UNCERTAINTY,
)

logger = logging.getLogger(__name__)

# ── Configurable constants ────────────────────────────────────────────────────

# Returner BPR multiplier for Model F (direct-bump counterfactual)
RETURNER_BUMP_FACTOR: float = 1.05   # returners get +5% projected BPR bonus

# Number of engine inputs to pass when team has too few players
MIN_PLAYERS_FOR_ENGINE: int = 3


# ── Output containers ─────────────────────────────────────────────────────────

@dataclass
class TeamPrediction:
    """Single model's prediction for one team."""
    team_slug: str
    model_name: str
    pred_adj_o: float
    pred_adj_d: float
    pred_adj_em: float
    # Diagnostic fields (optional; not all models compute these)
    pred_adj_em_low: Optional[float] = None
    pred_adj_em_high: Optional[float] = None
    uncertainty: Optional[float] = None
    base_team_offense: Optional[float] = None
    base_team_defense: Optional[float] = None
    n_players: int = 0
    returner_fraction: Optional[float] = None
    continuity_score: Optional[float] = None
    # True when a TeamRosterFit row was found and applied (Model E only).
    # False for all other models and for E when historical fit is unavailable.
    fit_used: bool = False


@dataclass
class AblationResult:
    """
    All model predictions for a single backtest pair.

    predictions[team_slug][model_name] = TeamPrediction
    models: ordered list of model names actually computed
    """
    source_year: int
    target_year: int
    predictions: dict[str, dict[str, TeamPrediction]] = field(default_factory=dict)
    models: list[str] = field(default_factory=list)

    def get(self, team_slug: str, model_name: str) -> Optional[TeamPrediction]:
        return self.predictions.get(team_slug, {}).get(model_name)

    def teams(self) -> list[str]:
        return list(self.predictions.keys())


# ── Public entry point ────────────────────────────────────────────────────────

ALL_MODELS: list[str] = ["A", "B", "C", "D", "E", "F"]


def run_all_models(
    pair: BacktestPair,
    models: Optional[list[str]] = None,
) -> AblationResult:
    """
    Run all requested ablation models for the given backtest pair.

    Args:
        pair:   Loaded BacktestPair from data_loader.load_backtest_pair().
        models: Subset of ALL_MODELS to compute (default: all six).

    Returns:
        AblationResult with predictions for every evaluable team × model combo.
    """
    if models is None:
        models = ALL_MODELS

    result = AblationResult(
        source_year=pair.source_year,
        target_year=pair.target_year,
        models=models,
    )

    evaluable = pair.evaluable_teams()
    if not evaluable:
        logger.warning(
            "[Ablation %d→%d] No evaluable teams (pools + actuals both required).",
            pair.source_year, pair.target_year,
        )
        return result

    # Two-pass centering: first compute all base aggregates, then project
    # (required for models B/C/D/E/F that use the centering formula)
    league_means = _compute_league_means(pair, evaluable)

    for team_slug in evaluable:
        pool = pair.team_pools[team_slug]
        source_outcome = pair.source_outcomes.get(team_slug)
        preds: dict[str, TeamPrediction] = {}

        if "A" in models:
            preds["A"] = _model_a(team_slug, source_outcome, pair)

        if any(m in models for m in ("B", "C", "D", "E", "F")):
            players = pool.players
            if len(players) < MIN_PLAYERS_FOR_ENGINE:
                logger.debug(
                    "[Ablation %d→%d] %s: only %d qualifying players — skipping B-F.",
                    pair.source_year, pair.target_year, team_slug, len(players),
                )
            else:
                if "B" in models:
                    preds["B"] = _model_b(team_slug, players, pair, league_means)
                if "C" in models:
                    preds["C"] = _model_c(team_slug, players, pair, league_means)
                if "D" in models:
                    preds["D"] = _model_d(team_slug, players, pair, league_means)
                if "E" in models:
                    preds["E"] = _model_e(team_slug, players, pair, league_means)
                if "F" in models:
                    preds["F"] = _model_f(team_slug, players, pair, league_means)

        result.predictions[team_slug] = preds

    logger.info(
        "[Ablation %d→%d] %d teams × %s models computed.",
        pair.source_year, pair.target_year, len(evaluable), models,
    )
    return result


# ── League centering helpers ──────────────────────────────────────────────────

@dataclass
class _LeagueMeans:
    """League-mean base aggregates used for centering (Model B uses equal-weight variant)."""
    # Minutes-weighted base aggregates (used by models C, D, E, F)
    base_off_minutes: float     # mean Σ(share_mpg × obpr) across D1 teams
    base_def_minutes: float     # mean Σ(share_mpg × dbpr) across D1 teams
    # Equal-weight base aggregates (used by Model B)
    base_off_equal: float       # mean avg(obpr) across D1 teams
    base_def_equal: float       # mean avg(dbpr) across D1 teams
    n_teams: int


def _compute_league_means(pair: BacktestPair, evaluable: list[str]) -> _LeagueMeans:
    """First-pass: compute D1 league-mean base aggregates for all evaluable teams."""
    off_minutes_vals: list[float] = []
    def_minutes_vals: list[float] = []
    off_equal_vals: list[float] = []
    def_equal_vals: list[float] = []

    for slug in evaluable:
        players = pair.team_pools[slug].players
        if len(players) < MIN_PLAYERS_FOR_ENGINE:
            continue

        # Minutes-weighted (Model C/D/E/F)
        base_off_m = sum(p.minutes_share_p2 * p.obpr for p in players)
        base_def_m = sum(p.minutes_share_p2 * p.dbpr for p in players)
        off_minutes_vals.append(base_off_m)
        def_minutes_vals.append(base_def_m)

        # Equal-weight (Model B)
        avg_obpr = sum(p.obpr for p in players) / len(players)
        avg_dbpr = sum(p.dbpr for p in players) / len(players)
        off_equal_vals.append(avg_obpr)
        def_equal_vals.append(avg_dbpr)

    def _mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    return _LeagueMeans(
        base_off_minutes=_mean(off_minutes_vals),
        base_def_minutes=_mean(def_minutes_vals),
        base_off_equal=_mean(off_equal_vals),
        base_def_equal=_mean(def_equal_vals),
        n_teams=len(off_minutes_vals),
    )


# ── Model A: Prior-year adj_em ────────────────────────────────────────────────

def _model_a(
    team_slug: str,
    source_outcome: Optional[ActualOutcome],
    pair: BacktestPair,
) -> TeamPrediction:
    """
    Predict next season's adj_em using this season's actual adj_em.
    Simplest possible baseline — 'last year is next year'.
    """
    if source_outcome is not None:
        adj_o = source_outcome.adj_o
        adj_d = source_outcome.adj_d
        adj_em = source_outcome.adj_em
    else:
        # Fall back to D1 average if no prior TSR row found
        adj_o = pair.d1_avg_o
        adj_d = pair.d1_avg_d
        adj_em = 0.0

    return TeamPrediction(
        team_slug=team_slug,
        model_name="A",
        pred_adj_o=adj_o,
        pred_adj_d=adj_d,
        pred_adj_em=adj_em,
    )


# ── Model B: Equal-minutes talent average ─────────────────────────────────────

def _model_b(
    team_slug: str,
    players: list[PlayerRow],
    pair: BacktestPair,
    league_means: _LeagueMeans,
) -> TeamPrediction:
    """
    Minutes-unweighted average BPR → direct engine formula (no continuity/fit).
    Equal contribution from each qualifying player; tests raw talent signal only.
    """
    from core.analytics.player_value.team_projection.constants import SLOPE_OFF, SLOPE_DEF

    n = len(players)
    avg_obpr = sum(p.obpr for p in players) / n
    avg_dbpr = sum(p.dbpr for p in players) / n

    # Center on D1 equal-weight mean
    pred_adj_o = pair.d1_avg_o + SLOPE_OFF * (avg_obpr - league_means.base_off_equal)
    pred_adj_d = pair.d1_avg_d - SLOPE_DEF * (avg_dbpr - league_means.base_def_equal)
    pred_adj_em = pred_adj_o - pred_adj_d

    return TeamPrediction(
        team_slug=team_slug,
        model_name="B",
        pred_adj_o=pred_adj_o,
        pred_adj_d=pred_adj_d,
        pred_adj_em=pred_adj_em,
        base_team_offense=avg_obpr,
        base_team_defense=avg_dbpr,
        n_players=n,
    )


# ── Model C: Minutes-weighted talent (no continuity/fit) ──────────────────────

def _model_c(
    team_slug: str,
    players: list[PlayerRow],
    pair: BacktestPair,
    league_means: _LeagueMeans,
) -> TeamPrediction:
    """
    Minutes-weighted BPR → engine translation formula, NO continuity or fit.
    Tests whether minutes weighting improves over equal weight (Model B).
    """
    from core.analytics.player_value.team_projection.constants import SLOPE_OFF, SLOPE_DEF

    base_off = sum(p.minutes_share_p2 * p.obpr for p in players)
    base_def = sum(p.minutes_share_p2 * p.dbpr for p in players)

    pred_adj_o = pair.d1_avg_o + SLOPE_OFF * (base_off - league_means.base_off_minutes)
    pred_adj_d = pair.d1_avg_d - SLOPE_DEF * (base_def - league_means.base_def_minutes)
    pred_adj_em = pred_adj_o - pred_adj_d

    returner_frac = _compute_returner_frac(players)

    return TeamPrediction(
        team_slug=team_slug,
        model_name="C",
        pred_adj_o=pred_adj_o,
        pred_adj_d=pred_adj_d,
        pred_adj_em=pred_adj_em,
        base_team_offense=base_off,
        base_team_defense=base_def,
        n_players=len(players),
        returner_fraction=returner_frac,
    )


# ── Model D: Minutes-weighted talent + continuity ─────────────────────────────

def _model_d(
    team_slug: str,
    players: list[PlayerRow],
    pair: BacktestPair,
    league_means: _LeagueMeans,
) -> TeamPrediction:
    """
    Full engine with actual recruitment types → includes continuity adjustment.
    Tests whether continuity signal improves over raw minutes-weighted talent (Model C).
    Fit adjustment = 0 (no historical TeamRosterFit for backtest seasons).

    Fallback: when pair.prior_year_has_data is False (prior-year PSS absent from DB),
    every player was classified as 'newcomer' by the data loader, making
    returner_fraction = 0 for all teams — a data-availability artifact, not reality.
    In that case, continuity cannot be computed fairly and this model returns Model C's
    output (no continuity adjustment) rather than applying a spurious maximum penalty.
    """
    if not pair.prior_year_has_data:
        # Can't derive recruitment types; skip continuity to avoid data-artifact bias.
        c = _model_c(team_slug, players, pair, league_means)
        return TeamPrediction(
            team_slug=team_slug,
            model_name="D",
            pred_adj_o=c.pred_adj_o,
            pred_adj_d=c.pred_adj_d,
            pred_adj_em=c.pred_adj_em,
            base_team_offense=c.base_team_offense,
            base_team_defense=c.base_team_defense,
            n_players=len(players),
            returner_fraction=None,   # explicitly None: no valid classification
            continuity_score=None,
        )

    result = _run_engine(players, pair, league_means, roster_fit=None)

    return TeamPrediction(
        team_slug=team_slug,
        model_name="D",
        pred_adj_o=result.projected_adj_o,
        pred_adj_d=result.projected_adj_d,
        pred_adj_em=result.projected_adj_em,
        pred_adj_em_low=result.projected_adj_em_low,
        pred_adj_em_high=result.projected_adj_em_high,
        uncertainty=result.team_projection_uncertainty,
        base_team_offense=result.base_team_offense,
        base_team_defense=result.base_team_defense,
        n_players=len(players),
        returner_fraction=result.returner_minutes_fraction,
        continuity_score=result.continuity_score,
    )


# ── Model E: Minutes-weighted talent + continuity + fit ───────────────────────

def _model_e(
    team_slug: str,
    players: list[PlayerRow],
    pair: BacktestPair,
    league_means: _LeagueMeans,
) -> TeamPrediction:
    """
    Engine with continuity + fit adjustment (if TeamRosterFit is available for source year).
    For historical backtest seasons (2023-2025), TeamRosterFit typically does not exist,
    so fit_adj=0 and Model E ≡ Model D.  Differentiated when running on 2026 data.

    Fallback: same as Model D — when pair.prior_year_has_data is False, returns Model C
    output to avoid spurious continuity penalty from missing prior-year classification.
    """
    if not pair.prior_year_has_data:
        c = _model_c(team_slug, players, pair, league_means)
        return TeamPrediction(
            team_slug=team_slug,
            model_name="E",
            pred_adj_o=c.pred_adj_o,
            pred_adj_d=c.pred_adj_d,
            pred_adj_em=c.pred_adj_em,
            base_team_offense=c.base_team_offense,
            base_team_defense=c.base_team_defense,
            n_players=len(players),
            returner_fraction=None,
            continuity_score=None,
        )

    roster_fit = _load_roster_fit(team_slug=players[0].team_slug, source_year=pair.source_year)
    result = _run_engine(players, pair, league_means, roster_fit=roster_fit)

    return TeamPrediction(
        team_slug=team_slug,
        model_name="E",
        pred_adj_o=result.projected_adj_o,
        pred_adj_d=result.projected_adj_d,
        pred_adj_em=result.projected_adj_em,
        pred_adj_em_low=result.projected_adj_em_low,
        pred_adj_em_high=result.projected_adj_em_high,
        uncertainty=result.team_projection_uncertainty,
        base_team_offense=result.base_team_offense,
        base_team_defense=result.base_team_defense,
        n_players=len(players),
        returner_fraction=result.returner_minutes_fraction,
        continuity_score=result.continuity_score,
        fit_used=roster_fit is not None,
    )


# ── Model F: Direct-returner-bump counterfactual ─────────────────────────────

def _model_f(
    team_slug: str,
    players: list[PlayerRow],
    pair: BacktestPair,
    league_means: _LeagueMeans,
) -> TeamPrediction:
    """
    Counterfactual: instead of using the engine's continuity formula (which uses
    returner_fraction to adjust ratings), simply multiply returner players' BPR
    by RETURNER_BUMP_FACTOR (+5%) and use Model C's direct translation.

    This tests whether a naive 'returning players are 5% better' heuristic
    outperforms the engineered continuity adjustment (Model D).

    Fallback: when pair.prior_year_has_data is False, recruitment types are invalid
    (all players 'newcomer'), so there are no returners to bump.  Returns Model C
    output to avoid a meaningless result where the bump applies to nobody.
    """
    if not pair.prior_year_has_data:
        c = _model_c(team_slug, players, pair, league_means)
        return TeamPrediction(
            team_slug=team_slug,
            model_name="F",
            pred_adj_o=c.pred_adj_o,
            pred_adj_d=c.pred_adj_d,
            pred_adj_em=c.pred_adj_em,
            base_team_offense=c.base_team_offense,
            base_team_defense=c.base_team_defense,
            n_players=len(players),
            returner_fraction=None,
        )

    from core.analytics.player_value.team_projection.constants import SLOPE_OFF, SLOPE_DEF

    bumped: list[PlayerRow] = []
    for p in players:
        if p.recruitment_type == "returner":
            # Apply flat BPR bump to returners
            new_obpr = p.obpr * RETURNER_BUMP_FACTOR
            new_dbpr = p.dbpr * RETURNER_BUMP_FACTOR
            new_bpr = new_obpr + new_dbpr
            bumped.append(PlayerRow(
                player_id=p.player_id,
                team_slug=p.team_slug,
                obpr=new_obpr,
                dbpr=new_dbpr,
                bpr=new_bpr,
                mpg=p.mpg,
                gp=p.gp,
                recruitment_type=p.recruitment_type,
                minutes_share_p2=p.minutes_share_p2,
            ))
        else:
            bumped.append(p)

    base_off = sum(p.minutes_share_p2 * p.obpr for p in bumped)
    base_def = sum(p.minutes_share_p2 * p.dbpr for p in bumped)

    pred_adj_o = pair.d1_avg_o + SLOPE_OFF * (base_off - league_means.base_off_minutes)
    pred_adj_d = pair.d1_avg_d - SLOPE_DEF * (base_def - league_means.base_def_minutes)
    pred_adj_em = pred_adj_o - pred_adj_d

    returner_frac = _compute_returner_frac(players)

    return TeamPrediction(
        team_slug=team_slug,
        model_name="F",
        pred_adj_o=pred_adj_o,
        pred_adj_d=pred_adj_d,
        pred_adj_em=pred_adj_em,
        base_team_offense=base_off,
        base_team_defense=base_def,
        n_players=len(players),
        returner_fraction=returner_frac,
    )


# ── Engine runner ─────────────────────────────────────────────────────────────

def _run_engine(
    players: list[PlayerRow],
    pair: BacktestPair,
    league_means: _LeagueMeans,
    roster_fit=None,
) -> "TeamProjectionResult":
    """
    Run the Phase 5 team projection engine with the given player pool.

    Builds PlayerProjectionInput objects from PlayerRow data, constructs D1Context
    using the pre-computed league means, and calls project_team().

    Args:
        roster_fit: Pre-loaded RosterFitInput (or None).  When None, the engine
                    applies zero fit adjustment.  Callers are responsible for
                    loading this via _load_roster_fit() before calling here so
                    that fit_used can be tracked on the returned TeamPrediction.
    """
    from core.analytics.player_value.team_projection.engine import (
        D1Context,
        PlayerProjectionInput,
        project_team,
    )

    engine_inputs = [
        PlayerProjectionInput(
            player_id=p.player_id,
            projected_obpr=p.obpr,
            projected_dbpr=p.dbpr,
            projected_bpr=p.bpr,
            minutes_share_p2=p.minutes_share_p2,
            recruitment_type=p.recruitment_type,
            projection_uncertainty=DEFAULT_PLAYER_UNCERTAINTY,
        )
        for p in players
    ]

    d1_context = D1Context(
        avg_adj_o=pair.d1_avg_o,
        avg_adj_d=pair.d1_avg_d,
        league_mean_base_off=league_means.base_off_minutes,
        league_mean_base_def=league_means.base_def_minutes,
        n_projected_teams=league_means.n_teams,
    )

    return project_team(engine_inputs, roster_fit, d1_context)


def _load_roster_fit(team_slug: str, source_year: int):
    """Load TeamRosterFit for team+year, or return None if unavailable."""
    try:
        from core.models import TeamRosterFit
        from core.analytics.player_value.team_projection.engine import RosterFitInput
        fit = TeamRosterFit.objects.filter(
            team__slug=team_slug,
            from_season__year=source_year,
        ).first()
        if fit is None:
            return None
        return RosterFitInput(
            offensive_fit_score=float(fit.offensive_fit_score or 50.0),
            defensive_fit_score=float(fit.defensive_fit_score or 50.0),
            adjusted_off_fit=float(fit.adjusted_off_fit or 50.0),
            adjusted_def_fit=float(fit.adjusted_def_fit or 50.0),
            has_team_style_data=bool(fit.has_team_style_data) if hasattr(fit, "has_team_style_data") else True,
        )
    except Exception:
        return None


# ── Utilities ─────────────────────────────────────────────────────────────────

def _compute_returner_frac(players: list[PlayerRow]) -> float:
    """Fraction of minutes contributed by returning players."""
    total_share = sum(p.minutes_share_p2 for p in players)
    returner_share = sum(p.minutes_share_p2 for p in players if p.recruitment_type == "returner")
    return returner_share / total_share if total_share > 0 else 0.0
