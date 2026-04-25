"""
ablation.py — Ablation model variants for roster-outlook backtesting.

Eight models on an additive ladder from simplest to most complete:

  A — Prior-year adj_em (team's own previous-season performance)
  B — Equal-minutes talent average (no minutes weighting, no engine adjustments)
  C — Minutes-weighted talent (actual mpg weights, no continuity/fit)
  D — Minutes-weighted talent + continuity  ← OFFICIAL PRODUCTION BASELINE (Phase 9e)
  E — Minutes-weighted talent + continuity + fit  (ablation only — fit zeroed in production)
  F — Direct-returner-bump counterfactual (returner BPR × BUMP_FACTOR; no continuity formula)
  G — Convex blend of Model D + prior-year TSR (ablation only; w calibrated per sweep)
  H — Split-weight blend of Model D + prior-year TSR (ablation only; independent off/def weights)

Official production baseline: Model D.
  Phase 9e calibration sweep (April 2026, N=1081, source years 2023-2025) found the
  fit layer (E vs D) carries no detectable predictive signal under any tested
  configuration.  FIT_TO_RATING_OFF/DEF are set to 0.0 in constants.py so the
  production engine computes D-equivalent mean projections.  Model E is retained
  in the ablation ladder as a research variant and future re-evaluation vehicle.

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

# ── Phase 9d: prior-year blend weights ───────────────────────────────────────
# Model G blends Model D's roster projection with the prior-year actual adj_em.
# Model H applies independent blend weights to adj_o and adj_d separately.
# Set via calibration sweep (see sweep_blend_weights); update after each sweep run.
#
# Leakage safety: the prior-year signal is source_outcomes[slug].adj_{o,d,em}
# which comes from source-year TeamSeasonRatings — never from the target year.

PRIOR_BLEND_WEIGHT_G: float = 0.90          # calibrated (Phase 9d sweep): RMSE min at w=0.90
PRIOR_BLEND_WEIGHT_H_OFF: float = 0.90      # adj_o weight for Model H (Phase 9d calibrated)
PRIOR_BLEND_WEIGHT_H_DEF: float = 0.90      # adj_d weight for Model H (Phase 9d calibrated)

# Candidate weights evaluated by sweep_blend_weights()
BLEND_WEIGHT_CANDIDATES: list[float] = [
    0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
    0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95,
]


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
    # Phase 9d: blend fields (Models G/H only; None for all other models)
    blend_weight: Optional[float] = None       # prior-year blend weight applied
    prior_year_adj_em: Optional[float] = None  # prior-year adj_em used in blend


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

ALL_MODELS: list[str] = ["A", "B", "C", "D", "E", "F", "G", "H"]


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

        if any(m in models for m in ("B", "C", "D", "E", "F", "G", "H")):
            players = pool.players
            if len(players) < MIN_PLAYERS_FOR_ENGINE:
                logger.debug(
                    "[Ablation %d→%d] %s: only %d qualifying players — skipping B-H.",
                    pair.source_year, pair.target_year, team_slug, len(players),
                )
            else:
                if "B" in models:
                    preds["B"] = _model_b(team_slug, players, pair, league_means)
                if "C" in models:
                    preds["C"] = _model_c(team_slug, players, pair, league_means)

                # D must be computed before G/H (it is their anchor).
                # Compute D even when not explicitly requested if G or H is needed.
                d_needed = any(m in models for m in ("D", "G", "H"))
                d_pred: Optional[TeamPrediction] = None
                if d_needed:
                    d_pred = _model_d(team_slug, players, pair, league_means)
                    if "D" in models:
                        preds["D"] = d_pred

                if "E" in models:
                    preds["E"] = _model_e(team_slug, players, pair, league_means)
                if "F" in models:
                    preds["F"] = _model_f(team_slug, players, pair, league_means)

                # G and H blend Model D with the prior-year source-year TSR.
                if "G" in models and d_pred is not None:
                    preds["G"] = _model_g(team_slug, source_outcome, d_pred)
                if "H" in models and d_pred is not None:
                    preds["H"] = _model_h(team_slug, source_outcome, d_pred)

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
    from ncaa.analytics.player_value.team_projection.constants import SLOPE_OFF, SLOPE_DEF

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
    from ncaa.analytics.player_value.team_projection.constants import SLOPE_OFF, SLOPE_DEF

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

    from ncaa.analytics.player_value.team_projection.constants import SLOPE_OFF, SLOPE_DEF

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
    from ncaa.analytics.player_value.team_projection.engine import (
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
        from ncaa.models import TeamRosterFit
        from ncaa.analytics.player_value.team_projection.engine import RosterFitInput
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


# ── Model G: prior-year adj_em blend (anchored on D) ─────────────────────────

def _model_g(
    team_slug: str,
    source_outcome: Optional[ActualOutcome],
    d_prediction: TeamPrediction,
    blend_weight: float = PRIOR_BLEND_WEIGHT_G,
) -> TeamPrediction:
    """
    Model G: convex blend of Model D's roster projection and the prior-year actual
    team strength from source-year TeamSeasonRatings.

    Leakage safety: prior-year signal = source_outcomes[slug].adj_{o,d,em}, which
    is the source-year TSR (Y) — never the target year (Y+1).

    Formula (applied to adj_o and adj_d independently; adj_em = adj_o - adj_d):
        pred_adj_o  = (1 - w) × D.pred_adj_o  + w × prior.adj_o
        pred_adj_d  = (1 - w) × D.pred_adj_d  + w × prior.adj_d
        pred_adj_em = pred_adj_o - pred_adj_d

    Fallback: when source_outcome is None (no source-year TSR for this team) or
    blend_weight == 0, returns Model D exactly.
    """
    if source_outcome is None or blend_weight == 0.0:
        return TeamPrediction(
            team_slug=team_slug,
            model_name="G",
            pred_adj_o=d_prediction.pred_adj_o,
            pred_adj_d=d_prediction.pred_adj_d,
            pred_adj_em=d_prediction.pred_adj_em,
            base_team_offense=d_prediction.base_team_offense,
            base_team_defense=d_prediction.base_team_defense,
            n_players=d_prediction.n_players,
            returner_fraction=d_prediction.returner_fraction,
            continuity_score=d_prediction.continuity_score,
            blend_weight=blend_weight,
            prior_year_adj_em=source_outcome.adj_em if source_outcome else None,
        )

    w = blend_weight
    pred_adj_o = (1 - w) * d_prediction.pred_adj_o + w * source_outcome.adj_o
    pred_adj_d = (1 - w) * d_prediction.pred_adj_d + w * source_outcome.adj_d
    pred_adj_em = pred_adj_o - pred_adj_d

    return TeamPrediction(
        team_slug=team_slug,
        model_name="G",
        pred_adj_o=pred_adj_o,
        pred_adj_d=pred_adj_d,
        pred_adj_em=pred_adj_em,
        base_team_offense=d_prediction.base_team_offense,
        base_team_defense=d_prediction.base_team_defense,
        n_players=d_prediction.n_players,
        returner_fraction=d_prediction.returner_fraction,
        continuity_score=d_prediction.continuity_score,
        blend_weight=blend_weight,
        prior_year_adj_em=source_outcome.adj_em,
    )


# ── Model H: split adj_o / adj_d blend (anchored on D) ───────────────────────

def _model_h(
    team_slug: str,
    source_outcome: Optional[ActualOutcome],
    d_prediction: TeamPrediction,
    blend_weight_off: float = PRIOR_BLEND_WEIGHT_H_OFF,
    blend_weight_def: float = PRIOR_BLEND_WEIGHT_H_DEF,
) -> TeamPrediction:
    """
    Model H: split-weight blend of Model D's roster projection and prior-year team
    strength, applying potentially independent weights to adj_o and adj_d.

    When blend_weight_off == blend_weight_def == PRIOR_BLEND_WEIGHT_G, H and G
    produce identical outputs (useful as a sanity check during calibration).
    The split is meaningful when offensive and defensive stability differ.

    Formula:
        pred_adj_o  = (1 - w_off) × D.pred_adj_o + w_off × prior.adj_o
        pred_adj_d  = (1 - w_def) × D.pred_adj_d + w_def × prior.adj_d
        pred_adj_em = pred_adj_o - pred_adj_d    [identity always satisfied]

    Fallback: when source_outcome is None or both weights == 0, returns D exactly.
    blend_weight stored as blend_weight_off (primary; noted in docstring).
    """
    if source_outcome is None or (blend_weight_off == 0.0 and blend_weight_def == 0.0):
        return TeamPrediction(
            team_slug=team_slug,
            model_name="H",
            pred_adj_o=d_prediction.pred_adj_o,
            pred_adj_d=d_prediction.pred_adj_d,
            pred_adj_em=d_prediction.pred_adj_em,
            base_team_offense=d_prediction.base_team_offense,
            base_team_defense=d_prediction.base_team_defense,
            n_players=d_prediction.n_players,
            returner_fraction=d_prediction.returner_fraction,
            continuity_score=d_prediction.continuity_score,
            blend_weight=blend_weight_off,
            prior_year_adj_em=source_outcome.adj_em if source_outcome else None,
        )

    pred_adj_o = (1 - blend_weight_off) * d_prediction.pred_adj_o + blend_weight_off * source_outcome.adj_o
    pred_adj_d = (1 - blend_weight_def) * d_prediction.pred_adj_d + blend_weight_def * source_outcome.adj_d
    pred_adj_em = pred_adj_o - pred_adj_d

    return TeamPrediction(
        team_slug=team_slug,
        model_name="H",
        pred_adj_o=pred_adj_o,
        pred_adj_d=pred_adj_d,
        pred_adj_em=pred_adj_em,
        base_team_offense=d_prediction.base_team_offense,
        base_team_defense=d_prediction.base_team_defense,
        n_players=d_prediction.n_players,
        returner_fraction=d_prediction.returner_fraction,
        continuity_score=d_prediction.continuity_score,
        blend_weight=blend_weight_off,  # store off weight; def weight accessible via PRIOR_BLEND_WEIGHT_H_DEF
        prior_year_adj_em=source_outcome.adj_em,
    )


# ── Blend weight sweep ────────────────────────────────────────────────────────

def sweep_blend_weights(
    all_pairs: list,   # list of (AblationResult, BacktestPair)
    weights: Optional[list[float]] = None,
    anchor_model: str = "D",
) -> list[dict]:
    """
    Sweep candidate prior-year blend weights for Model G using already-computed
    anchor predictions — no engine re-runs required.

    For each candidate weight w, applies:
        blended_adj_em = (1-w) * anchor_adj_em + w * prior_adj_em
    and computes RMSE, MAE, bias, R², and Spearman ρ.

    Args:
        all_pairs:     List of (AblationResult, BacktestPair) from run_all_models.
        weights:       Candidate weights to test (default: BLEND_WEIGHT_CANDIDATES).
        anchor_model:  The roster-only model to blend with prior year (default: "D").

    Returns:
        List of dicts [{weight, n, rmse, mae, bias, r_squared, spearman_rho}, ...],
        sorted by weight ascending.

    Leakage safety: prior-year signal comes from pair.source_outcomes — source-year
    TSR only. No target-year data is accessed during the sweep.
    """
    import math

    try:
        from scipy.stats import spearmanr
    except ImportError:
        spearmanr = None

    if weights is None:
        weights = BLEND_WEIGHT_CANDIDATES

    # Collect (anchor_adj_em, prior_adj_em, actual_adj_em) triples
    rows: list[tuple[float, float, float]] = []
    for ablation_result, pair in all_pairs:
        src_outcomes = pair.source_outcomes
        act_outcomes = pair.actual_outcomes
        for team_slug, preds_by_model in ablation_result.predictions.items():
            anchor_pred = preds_by_model.get(anchor_model)
            if anchor_pred is None:
                continue
            src = src_outcomes.get(team_slug)
            if src is None:
                continue
            act = act_outcomes.get(team_slug)
            if act is None:
                continue
            rows.append((anchor_pred.pred_adj_em, src.adj_em, act.adj_em))

    if not rows:
        return []

    results: list[dict] = []
    for w in weights:
        errors = []
        abs_errors = []
        preds_list = []
        actuals_list = []
        for anchor_em, prior_em, actual_em in rows:
            blended = (1.0 - w) * anchor_em + w * prior_em
            err = blended - actual_em
            errors.append(err)
            abs_errors.append(abs(err))
            preds_list.append(blended)
            actuals_list.append(actual_em)

        n = len(errors)
        bias = sum(errors) / n
        mae = sum(abs_errors) / n
        rmse = math.sqrt(sum(e ** 2 for e in errors) / n)

        # R²
        mean_actual = sum(actuals_list) / n
        ss_res = sum((p - a) ** 2 for p, a in zip(preds_list, actuals_list))
        ss_tot = sum((a - mean_actual) ** 2 for a in actuals_list)
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

        # Spearman ρ
        if spearmanr is not None and n >= 4:
            rho, _ = spearmanr(preds_list, actuals_list)
        else:
            rho = float("nan")

        results.append({
            "weight": w,
            "n": n,
            "rmse": round(rmse, 4),
            "mae": round(mae, 4),
            "bias": round(bias, 4),
            "r_squared": round(r_squared, 4),
            "spearman_rho": round(rho, 4) if not math.isnan(rho) else None,
        })

    return results


# ── Utilities ─────────────────────────────────────────────────────────────────

def _compute_returner_frac(players: list[PlayerRow]) -> float:
    """Fraction of minutes contributed by returning players."""
    total_share = sum(p.minutes_share_p2 for p in players)
    returner_share = sum(p.minutes_share_p2 for p in players if p.recruitment_type == "returner")
    return returner_share / total_share if total_share > 0 else 0.0
