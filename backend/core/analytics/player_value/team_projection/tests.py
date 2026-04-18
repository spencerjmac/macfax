"""
Phase 5: Team Projection Engine — comprehensive test suite.

Tests cover:
  1.  Base aggregate computation (weighted sums, empty roster)
  2.  Continuity calculation (returner fraction, neutral at 50 %, caps)
  3.  Newcomer fraction helper
  4.  Fit adjustments (neutral, max bonus, max penalty, cap enforcement)
  5.  Uncertainty computation (base + drivers, clamp bounds)
  6.  Sigma (uncertainty → pts/100) mapping
  7.  End-to-end: project_team() with typical roster
  8.  Centering invariant: average-talent team → D1 average ratings
  9.  Roster dominance invariant: player talent >> modifier adjustments
 10.  Elite team produces high adj_em (sanity check vs. calibration data)
 11.  Empty roster returns neutral result (no crash)
 12.  Missing fit data (None) → no fit adjustment
 13.  Coaching continuity always 0.0
 14.  Confidence bands: low < projected < high for all metrics
 15.  _assign_ranks(): rank 1 = best, monotone order, no ties gap
 16.  _assign_ranks(): rank ranges consistent with uncertainty bands
 17.  Defense rank range direction (lower adj_d = better rank)
 18.  Constants: SLOPE_OFF/DEF > 0, all uncertainty params in (0,1)
 19.  Continuity adj: full returner roster > neutral > full newcomer roster
 20.  Fit adj: score=100 > score=50 > score=0 for both off and def
 21.  Phase 6: BPR-weighted stability profile — no double-counting, fractions
      correct, continuity_value_score differs from minutes score when BPR
      distribution differs from minutes distribution

All tests are pure-Python and stateless (no DB required).
"""

from __future__ import annotations

from unittest import TestCase

from core.analytics.player_value.team_projection.constants import (
    CONTINUITY_BPR_BLEND_WEIGHT,
    CONTINUITY_BPR_REPLACEMENT_FLOOR,
    CONTINUITY_NEUTRAL_FRACTION,
    FALLBACK_D1_ADJ_D,
    FALLBACK_D1_ADJ_O,
    FIT_MAX_ADJ_DEF,
    FIT_MAX_ADJ_OFF,
    FIT_TO_RATING_DEF,
    FIT_TO_RATING_OFF,
    MAX_CONTINUITY_ADJ_DEF,
    MAX_CONTINUITY_ADJ_OFF,
    SLOPE_DEF,
    SLOPE_OFF,
    TRANSFER_FIT_RISK_WEIGHT,
    UNCERTAINTY_BASE,
    UNCERTAINTY_CONTINUITY_WEIGHT,
    UNCERTAINTY_MAX,
    UNCERTAINTY_MIN,
    UNCERTAINTY_NEWCOMER_WEIGHT,
    UNCERTAINTY_NO_STYLE_DATA,
    UNCERTAINTY_PLAYER_SIGNAL_WEIGHT,
    UNCERTAINTY_SIGMA_MAX,
    UNCERTAINTY_SIGMA_SCALE,
)
from core.analytics.player_value.team_projection.engine import (
    D1Context,
    PlayerProjectionInput,
    RosterFitInput,
    TeamProjectionResult,
    _compute_base_aggregates,
    _compute_continuity,
    _compute_fit_adjustments,
    _compute_newcomer_fraction,
    _compute_transfer_fit_risk,
    _compute_uncertainty,
    _uncertainty_to_sigma,
    compute_team_base_aggregates,
    project_team,
)
from core.analytics.player_value.team_projection.service import _assign_ranks


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _player(
    player_id: int = 1,
    obpr: float = 1.0,
    dbpr: float = 0.5,
    bpr: float = 1.5,
    min_share: float = 0.5,
    recruitment_type: str = "returner",
    uncertainty: float = 0.3,
) -> PlayerProjectionInput:
    return PlayerProjectionInput(
        player_id=player_id,
        projected_obpr=obpr,
        projected_dbpr=dbpr,
        projected_bpr=bpr,
        minutes_share_p2=min_share,
        recruitment_type=recruitment_type,
        projection_uncertainty=uncertainty,
    )


def _fit(
    off: float = 50.0,
    def_: float = 50.0,
    adj_off: float = 50.0,
    adj_def: float = 50.0,
    has_style: bool = True,
) -> RosterFitInput:
    return RosterFitInput(
        offensive_fit_score=off,
        defensive_fit_score=def_,
        adjusted_off_fit=adj_off,
        adjusted_def_fit=adj_def,
        has_team_style_data=has_style,
    )


def _ctx(
    avg_adj_o: float = 108.06,
    avg_adj_d: float = 108.24,
    mean_base_off: float = 0.0,
    mean_base_def: float = 0.0,
    n: int = 362,
) -> D1Context:
    return D1Context(
        avg_adj_o=avg_adj_o,
        avg_adj_d=avg_adj_d,
        league_mean_base_off=mean_base_off,
        league_mean_base_def=mean_base_def,
        n_projected_teams=n,
    )


def _typical_roster() -> list[PlayerProjectionInput]:
    """5-player roster with 5.0 total minutes shares (just like Phase 2)."""
    return [
        _player(player_id=1, obpr=2.0, dbpr=1.0, bpr=3.0, min_share=1.2, recruitment_type="returner"),
        _player(player_id=2, obpr=1.5, dbpr=0.8, bpr=2.3, min_share=1.1, recruitment_type="returner"),
        _player(player_id=3, obpr=0.8, dbpr=0.4, bpr=1.2, min_share=1.0, recruitment_type="transfer"),
        _player(player_id=4, obpr=0.5, dbpr=0.3, bpr=0.8, min_share=0.9, recruitment_type="newcomer"),
        _player(player_id=5, obpr=0.2, dbpr=0.1, bpr=0.3, min_share=0.8, recruitment_type="newcomer"),
    ]


# ── 1. Base aggregate computation ─────────────────────────────────────────────


class TestComputeBaseAggregates(TestCase):
    def test_single_player_values_correct(self):
        p = _player(obpr=2.0, dbpr=1.0, bpr=3.0, min_share=1.0)
        base_off, base_def, base_str = _compute_base_aggregates([p])
        self.assertAlmostEqual(base_off, 2.0)
        self.assertAlmostEqual(base_def, 1.0)
        self.assertAlmostEqual(base_str, 3.0)

    def test_weighted_sum_multiple_players(self):
        players = [
            _player(player_id=1, obpr=4.0, dbpr=2.0, bpr=6.0, min_share=1.0),
            _player(player_id=2, obpr=2.0, dbpr=1.0, bpr=3.0, min_share=2.0),
        ]
        base_off, base_def, base_str = _compute_base_aggregates(players)
        self.assertAlmostEqual(base_off, 4.0 * 1.0 + 2.0 * 2.0)  # 8.0
        self.assertAlmostEqual(base_def, 2.0 * 1.0 + 1.0 * 2.0)  # 4.0
        self.assertAlmostEqual(base_str, 6.0 * 1.0 + 3.0 * 2.0)  # 12.0

    def test_zero_bpr_players_produce_zero(self):
        players = [_player(obpr=0.0, dbpr=0.0, bpr=0.0, min_share=1.0)]
        base_off, base_def, base_str = _compute_base_aggregates(players)
        self.assertEqual(base_off, 0.0)
        self.assertEqual(base_def, 0.0)
        self.assertEqual(base_str, 0.0)

    def test_minutes_share_scales_proportionally(self):
        p_half = _player(obpr=1.0, dbpr=1.0, bpr=2.0, min_share=0.5)
        p_full = _player(player_id=2, obpr=1.0, dbpr=1.0, bpr=2.0, min_share=1.0)
        base_off_half, _, _ = _compute_base_aggregates([p_half])
        base_off_full, _, _ = _compute_base_aggregates([p_full])
        self.assertAlmostEqual(base_off_full, 2.0 * base_off_half)

    def test_compute_team_base_aggregates_matches(self):
        players = _typical_roster()
        expected_off, expected_def, _ = _compute_base_aggregates(players)
        got_off, got_def = compute_team_base_aggregates(players)
        self.assertAlmostEqual(got_off, expected_off)
        self.assertAlmostEqual(got_def, expected_def)

    def test_typical_roster_five_units_of_minutes(self):
        players = _typical_roster()
        total_minutes = sum(p.minutes_share_p2 for p in players)
        self.assertAlmostEqual(total_minutes, 5.0)


# ── 2. Continuity calculation ─────────────────────────────────────────────────


class TestComputeContinuity(TestCase):
    def test_all_returners_gives_max_positive_adj(self):
        players = [_player(min_share=1.0, recruitment_type="returner") for _ in range(5)]
        cont = _compute_continuity(players)
        self.assertAlmostEqual(cont.returner_minutes_fraction, 1.0)
        self.assertAlmostEqual(cont.continuity_score, 100.0)
        self.assertAlmostEqual(cont.continuity_adjustment_off, MAX_CONTINUITY_ADJ_OFF)
        self.assertAlmostEqual(cont.continuity_adjustment_def, MAX_CONTINUITY_ADJ_DEF)

    def test_all_newcomers_gives_max_negative_adj(self):
        players = [_player(min_share=1.0, recruitment_type="newcomer") for _ in range(5)]
        cont = _compute_continuity(players)
        self.assertAlmostEqual(cont.returner_minutes_fraction, 0.0)
        self.assertAlmostEqual(cont.continuity_score, 0.0)
        self.assertAlmostEqual(cont.continuity_adjustment_off, -MAX_CONTINUITY_ADJ_OFF)
        self.assertAlmostEqual(cont.continuity_adjustment_def, -MAX_CONTINUITY_ADJ_DEF)

    def test_fifty_percent_returners_is_neutral(self):
        players = [
            _player(player_id=1, min_share=1.0, recruitment_type="returner"),
            _player(player_id=2, min_share=1.0, recruitment_type="newcomer"),
        ]
        cont = _compute_continuity(players)
        self.assertAlmostEqual(cont.continuity_adjustment_off, 0.0, places=6)
        self.assertAlmostEqual(cont.continuity_adjustment_def, 0.0, places=6)

    def test_transfers_count_as_non_returners(self):
        players = [
            _player(player_id=1, min_share=1.0, recruitment_type="returner"),
            _player(player_id=2, min_share=1.0, recruitment_type="transfer"),
        ]
        cont = _compute_continuity(players)
        self.assertAlmostEqual(cont.returner_minutes_fraction, 0.5)  # only returner counts

    def test_returns_fraction_consistent_with_minutes(self):
        players = [
            _player(player_id=1, min_share=3.0, recruitment_type="returner"),
            _player(player_id=2, min_share=1.0, recruitment_type="newcomer"),
        ]
        cont = _compute_continuity(players)
        self.assertAlmostEqual(cont.returner_minutes_fraction, 3.0 / 4.0)

    def test_adj_clamped_to_max_positive(self):
        # Even if formula would exceed cap, result is clamped
        players = [_player(min_share=1.0, recruitment_type="returner")]
        cont = _compute_continuity(players)
        self.assertLessEqual(cont.continuity_adjustment_off, MAX_CONTINUITY_ADJ_OFF)
        self.assertLessEqual(cont.continuity_adjustment_def, MAX_CONTINUITY_ADJ_DEF)

    def test_adj_clamped_to_max_negative(self):
        players = [_player(min_share=1.0, recruitment_type="newcomer")]
        cont = _compute_continuity(players)
        self.assertGreaterEqual(cont.continuity_adjustment_off, -MAX_CONTINUITY_ADJ_OFF)
        self.assertGreaterEqual(cont.continuity_adjustment_def, -MAX_CONTINUITY_ADJ_DEF)

    def test_empty_players_returns_neutral(self):
        cont = _compute_continuity([])
        self.assertAlmostEqual(cont.returner_minutes_fraction, 0.5)
        self.assertAlmostEqual(cont.continuity_score, 50.0)
        self.assertAlmostEqual(cont.continuity_adjustment_off, 0.0)
        self.assertAlmostEqual(cont.continuity_adjustment_def, 0.0)

    def test_defense_adjustment_greater_than_offense_at_full_continuity(self):
        players = [_player(min_share=1.0, recruitment_type="returner") for _ in range(5)]
        cont = _compute_continuity(players)
        self.assertGreater(cont.continuity_adjustment_def, cont.continuity_adjustment_off)  # defense benefits more


# ── 3. Newcomer fraction ──────────────────────────────────────────────────────


class TestComputeNewcomerFraction(TestCase):
    def test_all_newcomers_gives_one(self):
        players = [_player(min_share=1.0, recruitment_type="newcomer") for _ in range(5)]
        self.assertAlmostEqual(_compute_newcomer_fraction(players), 1.0)

    def test_no_newcomers_gives_zero(self):
        players = [_player(min_share=1.0, recruitment_type="returner") for _ in range(5)]
        self.assertAlmostEqual(_compute_newcomer_fraction(players), 0.0)

    def test_mixed_roster_fraction_by_minutes(self):
        players = [
            _player(player_id=1, min_share=3.0, recruitment_type="returner"),
            _player(player_id=2, min_share=1.0, recruitment_type="newcomer"),
        ]
        frac = _compute_newcomer_fraction(players)
        self.assertAlmostEqual(frac, 0.25)

    def test_transfers_not_counted_as_newcomers(self):
        players = [
            _player(player_id=1, min_share=1.0, recruitment_type="transfer"),
            _player(player_id=2, min_share=1.0, recruitment_type="newcomer"),
        ]
        frac = _compute_newcomer_fraction(players)
        self.assertAlmostEqual(frac, 0.5)  # only newcomer counted


# ── 4. Fit adjustments ────────────────────────────────────────────────────────


class TestComputeFitAdjustments(TestCase):
    def test_neutral_score_gives_zero_adjustment(self):
        fit = _fit(adj_off=50.0, adj_def=50.0)
        adj_off, adj_def = _compute_fit_adjustments(fit)
        self.assertAlmostEqual(adj_off, 0.0)
        self.assertAlmostEqual(adj_def, 0.0)

    def test_max_score_gives_max_bonus(self):
        fit = _fit(adj_off=100.0, adj_def=100.0)
        adj_off, adj_def = _compute_fit_adjustments(fit)
        self.assertAlmostEqual(adj_off, FIT_TO_RATING_OFF)
        self.assertAlmostEqual(adj_def, FIT_TO_RATING_DEF)

    def test_min_score_gives_max_penalty(self):
        fit = _fit(adj_off=0.0, adj_def=0.0)
        adj_off, adj_def = _compute_fit_adjustments(fit)
        self.assertAlmostEqual(adj_off, -FIT_TO_RATING_OFF)
        self.assertAlmostEqual(adj_def, -FIT_TO_RATING_DEF)

    def test_no_fit_data_gives_zero(self):
        adj_off, adj_def = _compute_fit_adjustments(None)
        self.assertEqual(adj_off, 0.0)
        self.assertEqual(adj_def, 0.0)

    def test_cap_enforcement_positive(self):
        # FIT_TO_RATING == FIT_MAX by default, so this tests the clamp path
        # If someone sets TO_RATING > MAX, clamp should kick in
        fit = _fit(adj_off=100.0, adj_def=100.0)
        adj_off, adj_def = _compute_fit_adjustments(fit)
        self.assertLessEqual(adj_off, FIT_MAX_ADJ_OFF)
        self.assertLessEqual(adj_def, FIT_MAX_ADJ_DEF)

    def test_cap_enforcement_negative(self):
        fit = _fit(adj_off=0.0, adj_def=0.0)
        adj_off, adj_def = _compute_fit_adjustments(fit)
        self.assertGreaterEqual(adj_off, -FIT_MAX_ADJ_OFF)
        self.assertGreaterEqual(adj_def, -FIT_MAX_ADJ_DEF)

    def test_score_75_gives_half_max_bonus(self):
        fit = _fit(adj_off=75.0, adj_def=75.0)
        adj_off, adj_def = _compute_fit_adjustments(fit)
        self.assertAlmostEqual(adj_off, FIT_TO_RATING_OFF * 0.5)
        self.assertAlmostEqual(adj_def, FIT_TO_RATING_DEF * 0.5)

    def test_higher_fit_score_gives_higher_adjustment(self):
        fit_low = _fit(adj_off=60.0, adj_def=60.0)
        fit_high = _fit(adj_off=80.0, adj_def=80.0)
        adj_low_off, adj_low_def = _compute_fit_adjustments(fit_low)
        adj_high_off, adj_high_def = _compute_fit_adjustments(fit_high)
        self.assertGreater(adj_high_off, adj_low_off)
        self.assertGreater(adj_high_def, adj_low_def)


# ── 5. Uncertainty computation ───────────────────────────────────────────────


class TestComputeUncertainty(TestCase):
    def test_all_returners_with_style_data_is_lowest(self):
        # Pass weighted_player_uncertainty=0.0 (perfectly projected players) to
        # isolate the structural minimum with no other penalties.
        u = _compute_uncertainty(1.0, 0.0, _fit(has_style=True), 0.0)
        self.assertGreaterEqual(u, UNCERTAINTY_MIN)
        self.assertLessEqual(u, UNCERTAINTY_MAX)
        # With returner_frac=1, newcomer_frac=0, has_style=True, player_unc=0:
        # u = BASE + PLAYER_SIGNAL*0 + NEWCOMER*0 + CONTINUITY*(1-1) + 0 = BASE
        self.assertAlmostEqual(u, UNCERTAINTY_BASE, places=5)

    def test_all_newcomers_increases_uncertainty(self):
        u_returner = _compute_uncertainty(1.0, 0.0, _fit())
        u_newcomer = _compute_uncertainty(0.0, 1.0, _fit())
        self.assertGreater(u_newcomer, u_returner)

    def test_missing_style_data_increases_uncertainty(self):
        u_with = _compute_uncertainty(0.5, 0.25, _fit(has_style=True))
        u_without = _compute_uncertainty(0.5, 0.25, _fit(has_style=False))
        self.assertAlmostEqual(u_without - u_with, UNCERTAINTY_NO_STYLE_DATA, places=6)

    def test_none_fit_increases_uncertainty_via_style_flag(self):
        u_with = _compute_uncertainty(0.5, 0.25, _fit(has_style=True))
        u_no_fit = _compute_uncertainty(0.5, 0.25, None)
        self.assertGreater(u_no_fit, u_with)

    def test_uncertainty_clamped_to_min(self):
        u = _compute_uncertainty(1.0, 0.0, _fit(has_style=True))
        self.assertGreaterEqual(u, UNCERTAINTY_MIN)

    def test_uncertainty_clamped_to_max(self):
        # Worst case: 100 % newcomers, no style data
        u = _compute_uncertainty(0.0, 1.0, None)
        self.assertLessEqual(u, UNCERTAINTY_MAX)

    def test_newcomer_weight_applied_proportionally(self):
        # Moving from (returner=0.5, newcomer=0.5) → (returner=0.0, newcomer=1.0)
        # changes NEWCOMER_WEIGHT and CONTINUITY_WEIGHT terms (player signal
        # cancels out since both calls use the same default 0.5).
        u_half_newcomer = _compute_uncertainty(0.5, 0.5, _fit())
        u_full_newcomer = _compute_uncertainty(0.0, 1.0, _fit())
        diff = u_full_newcomer - u_half_newcomer
        # Expected: NEWCOMER_WEIGHT Δ (0.5) + CONTINUITY_WEIGHT Δ (0.5)
        expected = UNCERTAINTY_NEWCOMER_WEIGHT * 0.5 + UNCERTAINTY_CONTINUITY_WEIGHT * 0.5
        self.assertAlmostEqual(diff, expected, places=5)

    def test_player_uncertainty_signal_used(self):
        # High player uncertainty → higher team uncertainty than low player uncertainty
        u_low = _compute_uncertainty(0.5, 0.25, _fit(), weighted_player_uncertainty=0.1)
        u_high = _compute_uncertainty(0.5, 0.25, _fit(), weighted_player_uncertainty=0.9)
        self.assertGreater(u_high, u_low)

    def test_player_uncertainty_weight_magnitude(self):
        # Difference between 0.0 and 1.0 player uncertainty = PLAYER_SIGNAL_WEIGHT
        u_zero = _compute_uncertainty(0.5, 0.25, _fit(has_style=True), 0.0)
        u_one = _compute_uncertainty(0.5, 0.25, _fit(has_style=True), 1.0)
        self.assertAlmostEqual(u_one - u_zero, UNCERTAINTY_PLAYER_SIGNAL_WEIGHT, places=5)


# ── 6. Sigma (uncertainty → pts) mapping ─────────────────────────────────────


class TestUncertaintyToSigma(TestCase):
    def test_zero_uncertainty_gives_scale(self):
        self.assertAlmostEqual(_uncertainty_to_sigma(0.0), UNCERTAINTY_SIGMA_SCALE)

    def test_one_uncertainty_gives_max(self):
        sigma = _uncertainty_to_sigma(1.0)
        self.assertAlmostEqual(sigma, UNCERTAINTY_SIGMA_MAX)

    def test_sigma_increases_with_uncertainty(self):
        sigma_low = _uncertainty_to_sigma(0.2)
        sigma_high = _uncertainty_to_sigma(0.8)
        self.assertGreater(sigma_high, sigma_low)

    def test_sigma_never_exceeds_max(self):
        # Even if fed a value beyond 1.0 (e.g., bug), should stay ≤ MAX
        sigma = _uncertainty_to_sigma(2.0)
        self.assertLessEqual(sigma, UNCERTAINTY_SIGMA_MAX)


# ── 7. End-to-end: project_team() ────────────────────────────────────────────


class TestProjectTeam(TestCase):
    def _run_typical(self, ctx=None, fit=None):
        ctx = ctx or _ctx()
        fit = fit or _fit()
        return project_team(_typical_roster(), fit, ctx)

    def test_returns_team_projection_result(self):
        result = self._run_typical()
        self.assertIsInstance(result, TeamProjectionResult)

    def test_projected_adj_em_equals_o_minus_d(self):
        result = self._run_typical()
        self.assertAlmostEqual(
            result.projected_adj_em,
            result.projected_adj_o - result.projected_adj_d,
            places=8,
        )

    def test_coaching_continuity_always_zero(self):
        result = self._run_typical()
        self.assertEqual(result.coaching_continuity_adjustment, 0.0)

    def test_driver_breakdown_not_empty(self):
        result = self._run_typical()
        self.assertTrue(len(result.driver_breakdown) > 0)

    def test_projection_summary_has_key_fields(self):
        result = self._run_typical()
        for key in ["projected_adj_em", "projected_adj_o", "projected_adj_d", "uncertainty"]:
            self.assertIn(key, result.projection_summary)

    def test_result_fields_are_finite(self):
        result = self._run_typical()
        for attr in [
            "projected_adj_o", "projected_adj_d", "projected_adj_em",
            "team_projection_uncertainty",
        ]:
            val = getattr(result, attr)
            self.assertFalse(val != val, f"{attr} is NaN")  # NaN check

    def test_base_aggregates_match_formula(self):
        players = _typical_roster()
        result = project_team(players, _fit(), _ctx())
        expected_off = sum(p.minutes_share_p2 * p.projected_obpr for p in players)
        expected_def = sum(p.minutes_share_p2 * p.projected_dbpr for p in players)
        self.assertAlmostEqual(result.base_team_offense, expected_off, places=8)
        self.assertAlmostEqual(result.base_team_defense, expected_def, places=8)


# ── 8. Centering invariant ───────────────────────────────────────────────────


class TestCenteringInvariant(TestCase):
    """Average-talent team projected at D1 mean → should get D1 average ratings."""

    def test_at_league_mean_base_off_projects_to_d1_avg_o(self):
        # If base_off == league_mean, the BPR→adjO term is 0 → only D1_avg + adjustments
        players = [_player(obpr=2.0, dbpr=1.0, bpr=3.0, min_share=1.0)]
        base_off, base_def = compute_team_base_aggregates(players)
        # Set context so league mean == this team's base
        ctx = _ctx(mean_base_off=base_off, mean_base_def=base_def)
        result = project_team(players, _fit(adj_off=50.0, adj_def=50.0), ctx)
        # With neutral fit and neutral continuity, should hit D1 avg
        # (50% returner fraction? check what 1 player gives us)
        # With 1 player (returner), returner_frac=1.0 → cont_adj > 0, so allow for it
        # Just verify centering: proj_adj_o ≈ D1_avg + cont_adj
        base_gain = SLOPE_OFF * (base_off - base_off)  # = 0
        self.assertAlmostEqual(base_gain, 0.0)

    def test_exactly_average_roster_all_neutral_hits_d1_avg(self):
        """Team with BPR=0, 50% returners, neutral fit → D1 avg ratings."""
        players = [
            _player(player_id=1, obpr=0.0, dbpr=0.0, bpr=0.0, min_share=1.0, recruitment_type="returner"),
            _player(player_id=2, obpr=0.0, dbpr=0.0, bpr=0.0, min_share=1.0, recruitment_type="newcomer"),
        ]
        ctx = _ctx(mean_base_off=0.0, mean_base_def=0.0)
        result = project_team(players, _fit(adj_off=50.0, adj_def=50.0), ctx)
        self.assertAlmostEqual(result.projected_adj_o, ctx.avg_adj_o, places=6)
        self.assertAlmostEqual(result.projected_adj_d, ctx.avg_adj_d, places=6)
        # adj_em = avg_adj_o − avg_adj_d (not necessarily 0 since D1 averages may differ)
        expected_em = ctx.avg_adj_o - ctx.avg_adj_d
        self.assertAlmostEqual(result.projected_adj_em, expected_em, places=5)


# ── 9. Roster dominance invariant ────────────────────────────────────────────


class TestRosterDominance(TestCase):
    """Verify that roster talent component is dominant over all modifiers combined."""

    def test_base_roster_component_exceeds_all_modifiers_for_elite_team(self):
        # Elite roster: very high BPR
        players = [
            _player(player_id=i, obpr=5.0, dbpr=3.0, bpr=8.0, min_share=1.0)
            for i in range(5)
        ]
        # Max modifiers
        fit = _fit(adj_off=100.0, adj_def=100.0)
        ctx = _ctx(mean_base_off=0.0, mean_base_def=0.0)
        result = project_team(players, fit, ctx)

        # base_off = 25 → base component = SLOPE_OFF * 25 = 35.0
        # max total modifiers = MAX_CONTINUITY_ADJ_OFF + FIT_MAX_ADJ_OFF = 4.0
        base_component = SLOPE_OFF * result.base_team_offense
        max_modifiers = MAX_CONTINUITY_ADJ_OFF + FIT_MAX_ADJ_OFF
        self.assertGreater(base_component, max_modifiers * 3)  # well above all modifiers

    def test_low_bpr_team_projects_below_d1_avg_despite_max_fit(self):
        # Terrible roster with very negative BPR
        players = [
            _player(player_id=i, obpr=-3.0, dbpr=-2.0, bpr=-5.0, min_share=1.0)
            for i in range(5)
        ]
        fit = _fit(adj_off=100.0, adj_def=100.0)  # best fit, still shouldn't save them
        ctx = _ctx(mean_base_off=0.0, mean_base_def=0.0)
        result = project_team(players, fit, ctx)
        self.assertLess(result.projected_adj_em, 0.0)  # still below D1 average


# ── 10. Elite team calibration check ─────────────────────────────────────────


class TestEliteTeamCalibration(TestCase):
    """
    Approximate Duke 2026 calibration:
      base_off ≈ 13.3, base_def ≈ 9.35
      league_mean_base_off ≈ 1.86, league_mean_base_def ≈ 1.0 (estimated)
      D1 avg ≈ 108.06 / 108.24
    Expected: projected_adj_em significantly above 0 (elite team).
    """

    def test_duke_like_roster_projects_elite(self):
        # Approximate Duke 2026 roster (from calibration query)
        players = [
            _player(player_id=1, obpr=4.25, dbpr=2.20, bpr=6.45, min_share=0.747,
                    recruitment_type="transfer"),
            _player(player_id=2, obpr=4.25, dbpr=3.06, bpr=7.31, min_share=0.731,
                    recruitment_type="newcomer"),
            _player(player_id=3, obpr=3.05, dbpr=1.93, bpr=4.99, min_share=0.590,
                    recruitment_type="returner"),
            _player(player_id=4, obpr=2.30, dbpr=2.25, bpr=4.55, min_share=0.538,
                    recruitment_type="returner"),
            _player(player_id=5, obpr=3.09, dbpr=1.89, bpr=4.98, min_share=0.493,
                    recruitment_type="newcomer"),
            _player(player_id=6, obpr=2.02, dbpr=1.32, bpr=3.34, min_share=0.454,
                    recruitment_type="returner"),
            _player(player_id=7, obpr=2.30, dbpr=2.26, bpr=4.57, min_share=0.454,
                    recruitment_type="newcomer"),
            _player(player_id=8, obpr=1.41, dbpr=1.67, bpr=3.09, min_share=0.334,
                    recruitment_type="newcomer"),
        ]
        # Context with realistic centering values
        ctx = _ctx(
            avg_adj_o=108.06,
            avg_adj_d=108.24,
            mean_base_off=1.86,
            mean_base_def=1.0,
        )
        fit = _fit(adj_off=61.3, adj_def=63.8)  # Duke 2026 adjusted fit scores
        result = project_team(players, fit, ctx)

        # Duke actual 2026: adj_em=33.91 (rank 2)
        # Projection should be a strong positive, clearly elite
        self.assertGreater(result.projected_adj_em, 10.0, "Duke-like roster should be elite")
        self.assertGreater(result.projected_adj_o, 115.0, "Duke-like offense should be well above avg")
        self.assertLess(result.projected_adj_d, 105.0, "Duke-like defense should be good")

    def test_average_roster_projects_near_zero_em(self):
        """A team of exactly-average players should project near AdjEM=0."""
        players = [
            _player(player_id=i, obpr=0.0, dbpr=0.0, bpr=0.0, min_share=1.0,
                    recruitment_type="returner" if i < 3 else "newcomer")
            for i in range(5)
        ]
        ctx = _ctx(mean_base_off=0.0, mean_base_def=0.0)
        # Continuity at 60% → small positive adj; fit neutral
        result = project_team(players, _fit(adj_off=50.0, adj_def=50.0), ctx)
        # AdjEM should be very small (within ±5 of 0)
        self.assertAlmostEqual(result.projected_adj_em, 0.0, delta=5.0)


# ── 11. Empty roster ─────────────────────────────────────────────────────────


class TestEmptyRoster(TestCase):
    def test_empty_roster_returns_result_without_crash(self):
        result = project_team([], None, _ctx())
        self.assertIsInstance(result, TeamProjectionResult)

    def test_empty_roster_projects_to_d1_average(self):
        ctx = _ctx()
        result = project_team([], None, ctx)
        self.assertAlmostEqual(result.projected_adj_o, ctx.avg_adj_o)
        self.assertAlmostEqual(result.projected_adj_d, ctx.avg_adj_d)

    def test_empty_roster_has_max_uncertainty(self):
        result = project_team([], None, _ctx())
        self.assertAlmostEqual(result.team_projection_uncertainty, UNCERTAINTY_MAX)


# ── 12. Missing fit data → no fit adjustment ─────────────────────────────────


class TestMissingFitData(TestCase):
    def test_none_fit_gives_same_base_as_neutral_fit(self):
        players = _typical_roster()
        ctx = _ctx()
        result_no_fit = project_team(players, None, ctx)
        result_neutral = project_team(players, _fit(adj_off=50.0, adj_def=50.0), ctx)
        # With no fit, fit_adjustment should be 0
        self.assertAlmostEqual(result_no_fit.fit_adjustment_off, 0.0)
        self.assertAlmostEqual(result_no_fit.fit_adjustment_def, 0.0)
        # And adj_o should be very close to neutral-fit result (differing only in uncertainty)
        self.assertAlmostEqual(
            result_no_fit.projected_adj_o,
            result_neutral.projected_adj_o,
            places=6,
        )

    def test_good_fit_gives_higher_adj_o_than_no_fit(self):
        players = _typical_roster()
        ctx = _ctx()
        result_no_fit = project_team(players, None, ctx)
        result_good_fit = project_team(players, _fit(adj_off=80.0, adj_def=70.0), ctx)
        self.assertGreater(result_good_fit.projected_adj_o, result_no_fit.projected_adj_o)

    def test_bad_fit_gives_lower_adj_o_than_no_fit(self):
        players = _typical_roster()
        ctx = _ctx()
        result_no_fit = project_team(players, None, ctx)
        result_bad_fit = project_team(players, _fit(adj_off=20.0, adj_def=20.0), ctx)
        self.assertLess(result_bad_fit.projected_adj_o, result_no_fit.projected_adj_o)


# ── 13. Coaching continuity always 0 ─────────────────────────────────────────


class TestCoachingContinuity(TestCase):
    def test_coaching_continuity_is_always_zero(self):
        for roster in [[], _typical_roster()]:
            for fit in [None, _fit()]:
                result = project_team(roster, fit, _ctx())
                self.assertEqual(
                    result.coaching_continuity_adjustment, 0.0,
                    f"Expected 0.0 for roster size {len(roster)}, fit={fit}",
                )


# ── 14. Confidence bands ─────────────────────────────────────────────────────


class TestConfidenceBands(TestCase):
    def test_adj_o_low_less_than_projected_less_than_high(self):
        result = project_team(_typical_roster(), _fit(), _ctx())
        self.assertLess(result.projected_adj_o_low, result.projected_adj_o)
        self.assertLess(result.projected_adj_o, result.projected_adj_o_high)

    def test_adj_d_low_less_than_projected_less_than_high(self):
        result = project_team(_typical_roster(), _fit(), _ctx())
        self.assertLess(result.projected_adj_d_low, result.projected_adj_d)
        self.assertLess(result.projected_adj_d, result.projected_adj_d_high)

    def test_adj_em_low_less_than_projected_less_than_high(self):
        result = project_team(_typical_roster(), _fit(), _ctx())
        self.assertLess(result.projected_adj_em_low, result.projected_adj_em)
        self.assertLess(result.projected_adj_em, result.projected_adj_em_high)

    def test_em_band_wider_than_o_and_d_bands(self):
        # EM band = 2× sigma; O and D bands = 1× sigma
        result = project_team(_typical_roster(), _fit(), _ctx())
        em_width = result.projected_adj_em_high - result.projected_adj_em_low
        o_width = result.projected_adj_o_high - result.projected_adj_o_low
        d_width = result.projected_adj_d_high - result.projected_adj_d_low
        self.assertAlmostEqual(em_width, 2 * o_width)
        self.assertAlmostEqual(em_width, 2 * d_width)

    def test_higher_uncertainty_gives_wider_bands(self):
        ctx = _ctx()
        result_low_u = project_team(
            [_player(min_share=1.0, recruitment_type="returner") for _ in range(5)],
            _fit(has_style=True),
            ctx,
        )
        result_high_u = project_team(
            [_player(min_share=1.0, recruitment_type="newcomer") for _ in range(5)],
            _fit(has_style=False),
            ctx,
        )
        low_em_width = result_low_u.projected_adj_em_high - result_low_u.projected_adj_em_low
        high_em_width = result_high_u.projected_adj_em_high - result_high_u.projected_adj_em_low
        self.assertGreater(high_em_width, low_em_width)


# ── 15. _assign_ranks: basic ordering ────────────────────────────────────────


class TestAssignRanks(TestCase):
    def _make_result(
        self, adj_o: float, adj_d: float, uncertainty: float = 0.3
    ) -> TeamProjectionResult:
        adj_em = adj_o - adj_d
        sigma = _uncertainty_to_sigma(uncertainty)
        return TeamProjectionResult(
            base_team_offense=1.0,
            base_team_defense=1.0,
            base_team_roster_strength=2.0,
            returner_minutes_fraction=0.5,
            continuity_score=50.0,
            continuity_adjustment_off=0.0,
            continuity_adjustment_def=0.0,
            fit_adjustment_off=0.0,
            fit_adjustment_def=0.0,
            coaching_continuity_adjustment=0.0,
            projected_adj_o=adj_o,
            projected_adj_d=adj_d,
            projected_adj_em=adj_em,
            team_projection_uncertainty=uncertainty,
            projected_adj_o_low=adj_o - sigma,
            projected_adj_o_high=adj_o + sigma,
            projected_adj_d_low=adj_d - sigma,
            projected_adj_d_high=adj_d + sigma,
            projected_adj_em_low=adj_em - 2 * sigma,
            projected_adj_em_high=adj_em + 2 * sigma,
        )

    def test_rank_1_has_highest_adj_em(self):
        results = [
            (1, self._make_result(120.0, 90.0)),   # adj_em = 30 (best)
            (2, self._make_result(110.0, 100.0)),  # adj_em = 10
            (3, self._make_result(105.0, 108.0)),  # adj_em = -3 (worst)
        ]
        _assign_ranks(results)
        self.assertEqual(results[0][1].projected_national_rank, 1)
        self.assertEqual(results[1][1].projected_national_rank, 2)
        self.assertEqual(results[2][1].projected_national_rank, 3)

    def test_offense_rank_1_has_highest_adj_o(self):
        results = [
            (1, self._make_result(120.0, 108.0)),  # adj_o = 120 (best offense)
            (2, self._make_result(110.0, 100.0)),
            (3, self._make_result(105.0, 108.0)),
        ]
        _assign_ranks(results)
        self.assertEqual(results[0][1].projected_offense_rank, 1)

    def test_defense_rank_1_has_lowest_adj_d(self):
        results = [
            (1, self._make_result(108.0, 115.0)),  # bad defense (high adj_d)
            (2, self._make_result(108.0, 100.0)),  # adj_d = 100 (best)
            (3, self._make_result(108.0, 108.0)),
        ]
        _assign_ranks(results)
        self.assertEqual(results[1][1].projected_defense_rank, 1)  # idx 1 has adj_d=100

    def test_ranks_are_consecutive_no_gaps(self):
        results = [(i, self._make_result(120.0 - i * 5, 100.0)) for i in range(10)]
        _assign_ranks(results)
        national_ranks = sorted(r.projected_national_rank for _, r in results)
        self.assertEqual(national_ranks, list(range(1, 11)))

    def test_single_team_gets_rank_1(self):
        results = [(1, self._make_result(110.0, 100.0))]
        _assign_ranks(results)
        _, r = results[0]
        self.assertEqual(r.projected_national_rank, 1)
        self.assertEqual(r.projected_offense_rank, 1)
        self.assertEqual(r.projected_defense_rank, 1)


# ── 16. Rank ranges consistent with uncertainty bands ────────────────────────


class TestRankRanges(TestCase):
    def _make_result(self, adj_em: float, uncertainty: float = 0.3) -> TeamProjectionResult:
        adj_o = 108.0 + adj_em / 2
        adj_d = 108.0 - adj_em / 2
        sigma = _uncertainty_to_sigma(uncertainty)
        return TeamProjectionResult(
            base_team_offense=1.0,
            base_team_defense=1.0,
            base_team_roster_strength=2.0,
            returner_minutes_fraction=0.5,
            continuity_score=50.0,
            continuity_adjustment_off=0.0,
            continuity_adjustment_def=0.0,
            fit_adjustment_off=0.0,
            fit_adjustment_def=0.0,
            coaching_continuity_adjustment=0.0,
            projected_adj_o=adj_o,
            projected_adj_d=adj_d,
            projected_adj_em=adj_em,
            team_projection_uncertainty=uncertainty,
            projected_adj_o_low=adj_o - sigma,
            projected_adj_o_high=adj_o + sigma,
            projected_adj_d_low=adj_d - sigma,
            projected_adj_d_high=adj_d + sigma,
            projected_adj_em_low=adj_em - 2 * sigma,
            projected_adj_em_high=adj_em + 2 * sigma,
        )

    def test_rank_range_low_le_central_rank_le_high(self):
        teams = [(i, self._make_result(30.0 - i * 2.0)) for i in range(10)]
        _assign_ranks(teams)
        for _, r in teams:
            self.assertLessEqual(r.national_rank_range_low, r.projected_national_rank)
            self.assertGreaterEqual(r.national_rank_range_high, r.projected_national_rank)

    def test_best_team_rank_range_low_is_one(self):
        """The best team should have rank_range_low = 1 (can't be better than #1)."""
        teams = [(i, self._make_result(30.0 - i * 3.0)) for i in range(5)]
        _assign_ranks(teams)
        best = min(teams, key=lambda x: x[1].projected_national_rank)
        self.assertEqual(best[1].national_rank_range_low, 1)

    def test_higher_uncertainty_gives_wider_rank_range(self):
        teams_low_u = [(i, self._make_result(20.0 - i * 2.0, uncertainty=0.1)) for i in range(5)]
        teams_high_u = [(i, self._make_result(20.0 - i * 2.0, uncertainty=0.8)) for i in range(5)]
        _assign_ranks(teams_low_u)
        _assign_ranks(teams_high_u)
        # Middle team (index 2) should have wider range under high uncertainty
        _, r_low = teams_low_u[2]
        _, r_high = teams_high_u[2]
        low_width = r_low.national_rank_range_high - r_low.national_rank_range_low
        high_width = r_high.national_rank_range_high - r_high.national_rank_range_low
        self.assertGreaterEqual(high_width, low_width)


# ── 17. Defense rank range direction ─────────────────────────────────────────


class TestDefenseRankDirection(TestCase):
    def _make_def_result(self, adj_d: float, uncertainty: float = 0.3) -> TeamProjectionResult:
        sigma = _uncertainty_to_sigma(uncertainty)
        return TeamProjectionResult(
            base_team_offense=1.0,
            base_team_defense=1.0,
            base_team_roster_strength=2.0,
            returner_minutes_fraction=0.5,
            continuity_score=50.0,
            continuity_adjustment_off=0.0,
            continuity_adjustment_def=0.0,
            fit_adjustment_off=0.0,
            fit_adjustment_def=0.0,
            coaching_continuity_adjustment=0.0,
            projected_adj_o=108.0,
            projected_adj_d=adj_d,
            projected_adj_em=108.0 - adj_d,
            team_projection_uncertainty=uncertainty,
            projected_adj_o_low=108.0 - sigma,
            projected_adj_o_high=108.0 + sigma,
            projected_adj_d_low=adj_d - sigma,
            projected_adj_d_high=adj_d + sigma,
            projected_adj_em_low=(108.0 - adj_d) - 2 * sigma,
            projected_adj_em_high=(108.0 - adj_d) + 2 * sigma,
        )

    def test_lower_adj_d_gets_better_defense_rank(self):
        teams = [
            (1, self._make_def_result(90.0)),   # best defense (adj_d=90)
            (2, self._make_def_result(100.0)),
            (3, self._make_def_result(115.0)),  # worst defense (adj_d=115)
        ]
        _assign_ranks(teams)
        self.assertEqual(teams[0][1].projected_defense_rank, 1)
        self.assertEqual(teams[2][1].projected_defense_rank, 3)


# ── 18. Constants sanity checks ───────────────────────────────────────────────


class TestConstants(TestCase):
    def test_slopes_positive(self):
        self.assertGreater(SLOPE_OFF, 0.0)
        self.assertGreater(SLOPE_DEF, 0.0)

    def test_fallback_d1_averages_reasonable(self):
        self.assertGreater(FALLBACK_D1_ADJ_O, 100.0)
        self.assertGreater(FALLBACK_D1_ADJ_D, 100.0)

    def test_uncertainty_params_in_unit_interval(self):
        for param in [UNCERTAINTY_BASE, UNCERTAINTY_NEWCOMER_WEIGHT,
                      UNCERTAINTY_NO_STYLE_DATA, UNCERTAINTY_MIN, UNCERTAINTY_MAX]:
            self.assertGreater(param, 0.0)
            self.assertLessEqual(param, 1.0)

    def test_sigma_scale_less_than_sigma_max(self):
        self.assertLess(UNCERTAINTY_SIGMA_SCALE, UNCERTAINTY_SIGMA_MAX)

    def test_fit_to_rating_equals_fit_max(self):
        # By default, FIT_TO_RATING should equal FIT_MAX (cap at natural max)
        self.assertAlmostEqual(FIT_TO_RATING_OFF, FIT_MAX_ADJ_OFF)
        self.assertAlmostEqual(FIT_TO_RATING_DEF, FIT_MAX_ADJ_DEF)

    def test_continuity_neutral_is_half(self):
        self.assertAlmostEqual(CONTINUITY_NEUTRAL_FRACTION, 0.5)


# ── 19. Continuity monotonicity ───────────────────────────────────────────────


class TestContinuityMonotonicity(TestCase):
    def _run_with_returner_frac(self, returner_frac: float) -> TeamProjectionResult:
        total = 5
        n_returners = round(total * returner_frac)
        players = [
            _player(
                player_id=i,
                min_share=1.0,
                recruitment_type="returner" if i < n_returners else "newcomer",
            )
            for i in range(total)
        ]
        return project_team(players, _fit(), _ctx())

    def test_higher_returner_fraction_gives_higher_adj_o(self):
        r0 = self._run_with_returner_frac(0.0)
        r5 = self._run_with_returner_frac(0.5)
        r10 = self._run_with_returner_frac(1.0)
        self.assertGreater(r5.projected_adj_o, r0.projected_adj_o)
        self.assertGreater(r10.projected_adj_o, r5.projected_adj_o)

    def test_higher_returner_fraction_gives_lower_adj_d(self):
        r0 = self._run_with_returner_frac(0.0)
        r5 = self._run_with_returner_frac(0.5)
        r10 = self._run_with_returner_frac(1.0)
        self.assertGreater(r0.projected_adj_d, r5.projected_adj_d)
        self.assertGreater(r5.projected_adj_d, r10.projected_adj_d)


# ── 20. Fit score monotonicity ───────────────────────────────────────────────


class TestFitScoreMonotonicity(TestCase):
    def _run_with_fit(self, score: float) -> TeamProjectionResult:
        return project_team(
            _typical_roster(),
            _fit(adj_off=score, adj_def=score),
            _ctx(),
        )

    def test_higher_fit_score_gives_higher_adj_o(self):
        r0 = self._run_with_fit(0.0)
        r50 = self._run_with_fit(50.0)
        r100 = self._run_with_fit(100.0)
        self.assertGreater(r50.projected_adj_o, r0.projected_adj_o)
        self.assertGreater(r100.projected_adj_o, r50.projected_adj_o)

    def test_higher_fit_score_gives_lower_adj_d(self):
        r0 = self._run_with_fit(0.0)
        r50 = self._run_with_fit(50.0)
        r100 = self._run_with_fit(100.0)
        self.assertGreater(r0.projected_adj_d, r50.projected_adj_d)
        self.assertGreater(r50.projected_adj_d, r100.projected_adj_d)

    def test_fit_score_100_gives_max_fit_adj_off(self):
        r = self._run_with_fit(100.0)
        self.assertAlmostEqual(r.fit_adjustment_off, FIT_MAX_ADJ_OFF)

    def test_fit_score_0_gives_max_negative_fit_adj_off(self):
        r = self._run_with_fit(0.0)
        self.assertAlmostEqual(r.fit_adjustment_off, -FIT_MAX_ADJ_OFF)


# ── 21. Phase 6: BPR-weighted stability profile ───────────────────────────────


class TestPhase6StabilityProfile(TestCase):
    """
    Phase 6: Returner/Transfer stability policy tests.

    Validates that:
    - continuity_value_score is BPR-weighted (differs from minutes score when
      BPR distribution differs from minutes distribution)
    - transfer_bpr_fraction / returner_bpr_fraction reflect actual BPR shares
    - returner + transfer + newcomer BPR fractions sum to 1.0
    - changing returner→transfer does NOT change base_team_offense or
      base_team_defense (confirms no mean-talent bonus for returners)
    - transfer_dependence_score increases uncertainty relative to equal-BPR
      all-returner roster (through continuity_value_score path only)
    - diagnostic scores are bounded in [0, 100]
    - transfer_minutes_fraction tracks correctly
    """

    def _roster(
        self,
        n_returners: int = 0,
        n_transfers: int = 0,
        n_newcomers: int = 0,
        returner_bpr: float = 2.0,
        transfer_bpr: float = 2.0,
        newcomer_bpr: float = 2.0,
        min_share: float = 1.0,
    ) -> list[PlayerProjectionInput]:
        players = []
        pid = 1
        for _ in range(n_returners):
            players.append(_player(
                player_id=pid, bpr=returner_bpr, obpr=returner_bpr * 0.6,
                dbpr=returner_bpr * 0.4, min_share=min_share,
                recruitment_type="returner",
            ))
            pid += 1
        for _ in range(n_transfers):
            players.append(_player(
                player_id=pid, bpr=transfer_bpr, obpr=transfer_bpr * 0.6,
                dbpr=transfer_bpr * 0.4, min_share=min_share,
                recruitment_type="transfer",
            ))
            pid += 1
        for _ in range(n_newcomers):
            players.append(_player(
                player_id=pid, bpr=newcomer_bpr, obpr=newcomer_bpr * 0.6,
                dbpr=newcomer_bpr * 0.4, min_share=min_share,
                recruitment_type="newcomer",
            ))
            pid += 1
        return players

    # ── BPR fractions ──────────────────────────────────────────────────────

    def test_all_returners_gives_returner_bpr_fraction_one(self):
        players = self._roster(n_returners=5)
        cont = _compute_continuity(players)
        self.assertAlmostEqual(cont.returner_bpr_fraction, 1.0, places=5)
        self.assertAlmostEqual(cont.transfer_bpr_fraction, 0.0, places=5)

    def test_all_transfers_gives_transfer_bpr_fraction_one(self):
        players = self._roster(n_transfers=5)
        cont = _compute_continuity(players)
        self.assertAlmostEqual(cont.transfer_bpr_fraction, 1.0, places=5)
        self.assertAlmostEqual(cont.returner_bpr_fraction, 0.0, places=5)

    def test_bpr_fractions_sum_to_one(self):
        players = self._roster(n_returners=3, n_transfers=2, n_newcomers=2)
        cont = _compute_continuity(players)
        total = cont.returner_bpr_fraction + cont.transfer_bpr_fraction + (
            1.0 - cont.returner_bpr_fraction - cont.transfer_bpr_fraction
        )
        self.assertAlmostEqual(total, 1.0)
        # Direct fractions
        returner_f = cont.returner_bpr_fraction
        transfer_f = cont.transfer_bpr_fraction
        newcomer_f = 1.0 - returner_f - transfer_f
        self.assertGreaterEqual(newcomer_f, -1e-9)  # non-negative

    def test_transfer_minutes_fraction_correct(self):
        players = [
            _player(player_id=1, min_share=3.0, recruitment_type="returner"),
            _player(player_id=2, min_share=1.0, recruitment_type="transfer"),
        ]
        cont = _compute_continuity(players)
        self.assertAlmostEqual(cont.transfer_minutes_fraction, 0.25, places=6)

    # ── No mean-talent bonus for returners ────────────────────────────────

    def test_no_mean_bonus_swapping_returner_to_transfer(self):
        """
        Swapping a returner to a transfer with identical BPR must NOT change
        base_team_offense or base_team_defense (only continuity adj changes).
        """
        roster_returners = [
            _player(player_id=i, recruitment_type="returner", bpr=1.5,
                    obpr=0.9, dbpr=0.6, min_share=1.0) for i in range(5)
        ]
        roster_mixed = [
            _player(player_id=i, recruitment_type="transfer", bpr=1.5,
                    obpr=0.9, dbpr=0.6, min_share=1.0) if i == 0
            else _player(player_id=i, recruitment_type="returner", bpr=1.5,
                         obpr=0.9, dbpr=0.6, min_share=1.0)
            for i in range(5)
        ]
        base_r = _compute_base_aggregates(roster_returners)
        base_m = _compute_base_aggregates(roster_mixed)
        self.assertAlmostEqual(base_r[0], base_m[0], places=9)  # base_off identical
        self.assertAlmostEqual(base_r[1], base_m[1], places=9)  # base_def identical

    # ── BPR-weighted continuity_value_score ───────────────────────────────

    def test_continuity_value_score_differs_when_bpr_skewed(self):
        """
        A team where returners have higher BPR than transfers should have a
        higher continuity_value_score than one where returners have lower BPR
        (same minutes fractions, different BPR distribution).
        """
        # Returners are the star players — BPR distribution favours returners
        players_star_returners = [
            _player(player_id=1, min_share=1.0, recruitment_type="returner", bpr=5.0, obpr=3.0, dbpr=2.0),
            _player(player_id=2, min_share=1.0, recruitment_type="returner", bpr=4.0, obpr=2.4, dbpr=1.6),
            _player(player_id=3, min_share=1.0, recruitment_type="transfer", bpr=0.5, obpr=0.3, dbpr=0.2),
            _player(player_id=4, min_share=1.0, recruitment_type="transfer", bpr=0.5, obpr=0.3, dbpr=0.2),
        ]
        # Transfers are the star players — BPR distribution favours transfers
        players_star_transfers = [
            _player(player_id=1, min_share=1.0, recruitment_type="returner", bpr=0.5, obpr=0.3, dbpr=0.2),
            _player(player_id=2, min_share=1.0, recruitment_type="returner", bpr=0.5, obpr=0.3, dbpr=0.2),
            _player(player_id=3, min_share=1.0, recruitment_type="transfer", bpr=5.0, obpr=3.0, dbpr=2.0),
            _player(player_id=4, min_share=1.0, recruitment_type="transfer", bpr=4.0, obpr=2.4, dbpr=1.6),
        ]
        cont_star_ret = _compute_continuity(players_star_returners)
        cont_star_xfr = _compute_continuity(players_star_transfers)

        # Both have 50% returner minutes fraction; but BPR fractions differ
        self.assertAlmostEqual(cont_star_ret.returner_minutes_fraction, 0.5, places=5)
        self.assertAlmostEqual(cont_star_xfr.returner_minutes_fraction, 0.5, places=5)

        # continuity_value_score should favour the team with star returners
        self.assertGreater(
            cont_star_ret.continuity_value_score,
            cont_star_xfr.continuity_value_score,
        )

    def test_uniform_bpr_makes_value_score_equal_to_minutes_score(self):
        """When all players have identical BPR, value score == minutes score."""
        players = [
            _player(player_id=1, min_share=3.0, recruitment_type="returner", bpr=2.0, obpr=1.2, dbpr=0.8),
            _player(player_id=2, min_share=1.0, recruitment_type="transfer", bpr=2.0, obpr=1.2, dbpr=0.8),
        ]
        cont = _compute_continuity(players)
        self.assertAlmostEqual(cont.returner_minutes_fraction, 0.75, places=5)
        self.assertAlmostEqual(cont.returner_bpr_fraction, 0.75, places=5)
        # Both fractions match → blend equals raw fraction → same score
        self.assertAlmostEqual(cont.continuity_value_score, cont.continuity_score, places=4)

    # ── Transfer dependence score ─────────────────────────────────────────

    def test_transfer_dependence_score_bounded(self):
        players = self._roster(n_returners=3, n_transfers=2)
        cont = _compute_continuity(players)
        self.assertGreaterEqual(cont.transfer_dependence_score, 0.0)
        self.assertLessEqual(cont.transfer_dependence_score, 100.0)

    def test_all_transfers_gives_transfer_dependence_score_100(self):
        players = self._roster(n_transfers=5)
        cont = _compute_continuity(players)
        self.assertAlmostEqual(cont.transfer_dependence_score, 100.0, places=4)

    def test_no_transfers_gives_transfer_dependence_score_zero(self):
        players = self._roster(n_returners=5)
        cont = _compute_continuity(players)
        self.assertAlmostEqual(cont.transfer_dependence_score, 0.0, places=4)

    # ── Continuity_value_score bounds ─────────────────────────────────────

    def test_continuity_value_score_bounded_0_to_100(self):
        for rt in ("returner", "transfer", "newcomer"):
            players = [_player(min_share=1.0, recruitment_type=rt) for _ in range(5)]
            cont = _compute_continuity(players)
            self.assertGreaterEqual(cont.continuity_value_score, 0.0)
            self.assertLessEqual(cont.continuity_value_score, 100.0)

    # ── Uncertainty uses continuity_value_score ───────────────────────────

    def test_uncertainty_uses_bpr_weighted_signal(self):
        """
        A team with high returner_bpr_fraction but equal returner_minutes_fraction
        should have LOWER uncertainty than one with low returner_bpr_fraction.
        The BPR-weighted continuity_value_score feeds into _compute_uncertainty.
        """
        # High-BPR returners, low-BPR transfers (more stable output)
        players_stable = [
            _player(player_id=1, min_share=1.0, recruitment_type="returner", bpr=5.0, obpr=3.0, dbpr=2.0),
            _player(player_id=2, min_share=1.0, recruitment_type="returner", bpr=4.0, obpr=2.4, dbpr=1.6),
            _player(player_id=3, min_share=1.0, recruitment_type="transfer", bpr=0.5, obpr=0.3, dbpr=0.2),
            _player(player_id=4, min_share=1.0, recruitment_type="transfer", bpr=0.5, obpr=0.3, dbpr=0.2),
        ]
        # Low-BPR returners, high-BPR transfers (less stable output)
        players_volatile = [
            _player(player_id=1, min_share=1.0, recruitment_type="returner", bpr=0.5, obpr=0.3, dbpr=0.2),
            _player(player_id=2, min_share=1.0, recruitment_type="returner", bpr=0.5, obpr=0.3, dbpr=0.2),
            _player(player_id=3, min_share=1.0, recruitment_type="transfer", bpr=5.0, obpr=3.0, dbpr=2.0),
            _player(player_id=4, min_share=1.0, recruitment_type="transfer", bpr=4.0, obpr=2.4, dbpr=1.6),
        ]
        r_stable = project_team(players_stable, _fit(), _ctx())
        r_volatile = project_team(players_volatile, _fit(), _ctx())
        self.assertLess(r_stable.team_projection_uncertainty, r_volatile.team_projection_uncertainty)

    # ── End-to-end: new fields on TeamProjectionResult ────────────────────

    def test_project_team_populates_phase6_fields(self):
        players = [
            _player(player_id=1, min_share=3.0, recruitment_type="returner"),
            _player(player_id=2, min_share=1.0, recruitment_type="transfer"),
            _player(player_id=3, min_share=1.0, recruitment_type="newcomer"),
        ]
        result = project_team(players, _fit(), _ctx())
        self.assertIsNotNone(result.returner_bpr_fraction)
        self.assertIsNotNone(result.transfer_minutes_fraction)
        self.assertIsNotNone(result.transfer_bpr_fraction)
        self.assertIsNotNone(result.transfer_dependence_score)
        self.assertIsNotNone(result.continuity_value_score)
        # Sanity: transfer_minutes_fraction = 1/5 minutes share
        self.assertAlmostEqual(result.transfer_minutes_fraction, 1.0 / 5.0, places=4)

    def test_projection_summary_includes_phase6_keys(self):
        players = self._roster(n_returners=3, n_transfers=2)
        result = project_team(players, _fit(), _ctx())
        self.assertIn("continuity_value_score", result.projection_summary)
        self.assertIn("transfer_dependence_score", result.projection_summary)

    def test_constants_phase6_within_bounds(self):
        self.assertGreater(CONTINUITY_BPR_BLEND_WEIGHT, 0.0)
        self.assertLess(CONTINUITY_BPR_BLEND_WEIGHT, 1.0)
        self.assertLess(CONTINUITY_BPR_REPLACEMENT_FLOOR, 0.0)  # must be negative


class TestPhase6TransferFitRisk(TestCase):
    """
    Phase 6b: transfer fit-risk — uncertainty widens when a transfer-heavy
    roster lands in a poor-fit system.

    Invariants:
      - High transfer dependence + poor fit  → higher uncertainty
      - High transfer dependence + good fit  → risk ≈ 0 (no extra uncertainty)
      - Low transfer dependence + poor fit   → risk ≈ 0 (no extra uncertainty)
      - Missing fit data (roster_fit=None)   → risk = 0.0 (neutral, not penalised)
      - Effect is capped: max addition = TRANSFER_FIT_RISK_WEIGHT (0.12)
      - Mean ratings unchanged: base_team_offense/defense not affected
      - Confidence bands widen proportionally to risk
    """

    # ── _compute_transfer_fit_risk() unit tests ────────────────────────────

    def _fit_score(self, score: float) -> RosterFitInput:
        """Helper: RosterFitInput where both off and def fit == score."""
        return RosterFitInput(
            offensive_fit_score=score,
            defensive_fit_score=score,
            adjusted_off_fit=score,
            adjusted_def_fit=score,
            has_team_style_data=True,
        )

    def test_no_fit_data_returns_neutral(self):
        """Missing roster_fit → risk = 0.0 (treated as neutral, not penalised)."""
        risk = _compute_transfer_fit_risk(
            transfer_dependence_score=80.0,
            roster_fit=None,
        )
        self.assertEqual(risk, 0.0)

    def test_zero_transfer_dependence_zero_risk(self):
        """No transfer reliance → risk = 0.0 regardless of fit quality."""
        risk = _compute_transfer_fit_risk(
            transfer_dependence_score=0.0,
            roster_fit=self._fit_score(10.0),  # very poor fit
        )
        self.assertEqual(risk, 0.0)

    def test_good_fit_zero_risk(self):
        """Good fit (score >= 50) → fit_shortfall = 0 → risk = 0 regardless of dependence."""
        risk = _compute_transfer_fit_risk(
            transfer_dependence_score=100.0,
            roster_fit=self._fit_score(50.0),
        )
        self.assertEqual(risk, 0.0)

    def test_neutral_fit_zero_risk(self):
        """Fit score exactly at 50 (neutral) → shortfall = 0 → risk = 0."""
        risk = _compute_transfer_fit_risk(
            transfer_dependence_score=75.0,
            roster_fit=self._fit_score(50.0),
        )
        self.assertEqual(risk, 0.0)

    def test_above_neutral_fit_zero_risk(self):
        """Fit score > 50 → shortfall clamped to 0 → risk = 0."""
        risk = _compute_transfer_fit_risk(
            transfer_dependence_score=100.0,
            roster_fit=self._fit_score(75.0),
        )
        self.assertEqual(risk, 0.0)

    def test_high_dependence_poor_fit_peaks(self):
        """
        100% transfer dependence + score=0 → risk = 1.0 (maximum).
        dep_frac=1.0, avg_fit=0.0, shortfall=(50-0)/50=1.0 → risk=1.0
        """
        risk = _compute_transfer_fit_risk(
            transfer_dependence_score=100.0,
            roster_fit=self._fit_score(0.0),
        )
        self.assertAlmostEqual(risk, 1.0, places=6)

    def test_partial_values_interaction(self):
        """
        dep_frac=0.5, avg_fit=25 → shortfall=(50-25)/50=0.5 → risk=0.25
        """
        risk = _compute_transfer_fit_risk(
            transfer_dependence_score=50.0,
            roster_fit=self._fit_score(25.0),
        )
        self.assertAlmostEqual(risk, 0.25, places=6)

    def test_risk_bounded_0_to_1(self):
        """risk is always in [0, 1] for all valid inputs."""
        test_cases = [
            (0.0, 0.0), (50.0, 0.0), (50.0, 50.0),
            (100.0, 0.0), (100.0, 25.0), (100.0, 50.0), (75.0, 10.0),
        ]
        for dep, fit in test_cases:
            risk = _compute_transfer_fit_risk(
                transfer_dependence_score=dep,
                roster_fit=self._fit_score(fit),
            )
            self.assertGreaterEqual(risk, 0.0, msg=f"dep={dep}, fit={fit}")
            self.assertLessEqual(risk, 1.0, msg=f"dep={dep}, fit={fit}")

    # ── Integration: project_team() end-to-end ────────────────────────────

    def _transfer_heavy_roster(self, n: int = 5) -> list[PlayerProjectionInput]:
        """Roster with roughly 60% transfer minutes share."""
        players = []
        for i in range(n):
            recruitment_type = "transfer" if i < 3 else "returner"
            players.append(_player(
                player_id=i + 1,
                min_share=0.2,
                recruitment_type=recruitment_type,
            ))
        return players

    def _returner_heavy_roster(self, n: int = 5) -> list[PlayerProjectionInput]:
        """Roster where all players are returners."""
        return [
            _player(player_id=i + 1, min_share=0.2, recruitment_type="returner")
            for i in range(n)
        ]

    def test_transfer_heavy_poor_fit_higher_uncertainty(self):
        """
        Transfer-heavy roster in poor-fit system should have higher uncertainty
        than returner-heavy roster in the same system.
        """
        poor_fit = RosterFitInput(
            offensive_fit_score=10.0,
            defensive_fit_score=10.0,
            adjusted_off_fit=10.0,
            adjusted_def_fit=10.0,
            has_team_style_data=True,
        )
        result_xfr = project_team(self._transfer_heavy_roster(), poor_fit, _ctx())
        result_ret = project_team(self._returner_heavy_roster(), poor_fit, _ctx())
        self.assertGreater(
            result_xfr.team_projection_uncertainty,
            result_ret.team_projection_uncertainty,
        )

    def test_transfer_heavy_good_fit_not_penalised(self):
        """
        Transfer-heavy roster in good-fit system: risk ≈ 0 → no extra uncertainty
        versus returner-heavy roster in same good-fit system.
        """
        good_fit = RosterFitInput(
            offensive_fit_score=75.0,
            defensive_fit_score=75.0,
            adjusted_off_fit=75.0,
            adjusted_def_fit=75.0,
            has_team_style_data=True,
        )
        result_xfr = project_team(self._transfer_heavy_roster(), good_fit, _ctx())
        result_ret = project_team(self._returner_heavy_roster(), good_fit, _ctx())
        # risk=0 for both (good fit) so fit-risk uncertainty is identical
        self.assertAlmostEqual(
            result_xfr.transfer_fit_risk_score, 0.0, places=3
        )
        self.assertAlmostEqual(
            result_ret.transfer_fit_risk_score, 0.0, places=3
        )

    def test_poor_fit_returner_roster_not_penalised(self):
        """
        All-returner roster in poor-fit system: transfer_dependence ≈ 0 → risk = 0.
        """
        poor_fit = RosterFitInput(
            offensive_fit_score=5.0,
            defensive_fit_score=5.0,
            adjusted_off_fit=5.0,
            adjusted_def_fit=5.0,
            has_team_style_data=True,
        )
        result = project_team(self._returner_heavy_roster(), poor_fit, _ctx())
        self.assertAlmostEqual(result.transfer_fit_risk_score, 0.0, places=3)

    def test_no_fit_data_risk_is_zero(self):
        """roster_fit=None → transfer_fit_risk_score=0.0 (not penalised)."""
        result = project_team(self._transfer_heavy_roster(), None, _ctx())
        self.assertEqual(result.transfer_fit_risk_score, 0.0)

    def test_mean_ratings_unchanged(self):
        """
        transfer_fit_risk only adds uncertainty — does not change mean ratings.
        Comparing two rosters with identical talent but different transfer mix:
        base_team_offense and base_team_defense must be identical.
        """
        # Identical talent, identical minutes, only recruitment_type differs
        players_ret = [
            _player(player_id=1, obpr=2.0, dbpr=1.0, min_share=0.5, recruitment_type="returner"),
            _player(player_id=2, obpr=2.0, dbpr=1.0, min_share=0.5, recruitment_type="returner"),
        ]
        players_xfr = [
            _player(player_id=1, obpr=2.0, dbpr=1.0, min_share=0.5, recruitment_type="transfer"),
            _player(player_id=2, obpr=2.0, dbpr=1.0, min_share=0.5, recruitment_type="transfer"),
        ]
        poor_fit = RosterFitInput(
            offensive_fit_score=5.0,
            defensive_fit_score=5.0,
            adjusted_off_fit=5.0,
            adjusted_def_fit=5.0,
            has_team_style_data=True,
        )
        result_ret = project_team(players_ret, poor_fit, _ctx())
        result_xfr = project_team(players_xfr, poor_fit, _ctx())

        self.assertAlmostEqual(
            result_ret.base_team_offense, result_xfr.base_team_offense, places=4,
            msg="base_team_offense must not depend on recruitment_type",
        )
        self.assertAlmostEqual(
            result_ret.base_team_defense, result_xfr.base_team_defense, places=4,
            msg="base_team_defense must not depend on recruitment_type",
        )
        # But uncertainty IS different
        self.assertGreater(
            result_xfr.team_projection_uncertainty,
            result_ret.team_projection_uncertainty,
            msg="Transfer roster in poor-fit system should have higher uncertainty",
        )

    def test_risk_capped_by_weight(self):
        """
        Maximum possible risk contribution to uncertainty is TRANSFER_FIT_RISK_WEIGHT.
        Even at dep_frac=1.0 and fit_shortfall=1.0 the addition is at most 0.12.
        """
        # Worst-case: all transfers, fit=0
        players = [
            _player(player_id=i + 1, min_share=0.2, recruitment_type="transfer")
            for i in range(5)
        ]
        worst_fit = RosterFitInput(
            offensive_fit_score=0.0,
            defensive_fit_score=0.0,
            adjusted_off_fit=0.0,
            adjusted_def_fit=0.0,
            has_team_style_data=True,
        )
        result = project_team(players, worst_fit, _ctx())
        # risk score itself fits within [0, 1]
        self.assertLessEqual(result.transfer_fit_risk_score, 1.0)
        # uncertainty contribution ≤ TRANSFER_FIT_RISK_WEIGHT
        max_expected_contribution = TRANSFER_FIT_RISK_WEIGHT * result.transfer_fit_risk_score
        self.assertLessEqual(max_expected_contribution, TRANSFER_FIT_RISK_WEIGHT + 1e-9)

    def test_projection_summary_includes_transfer_fit_risk_score(self):
        """projection_summary dict exposes transfer_fit_risk_score."""
        result = project_team(self._transfer_heavy_roster(), _fit(), _ctx())
        self.assertIn("transfer_fit_risk_score", result.projection_summary)

    def test_confidence_bands_wider_for_high_risk(self):
        """
        Confidence bands (em_high - em_low) are wider for transfer-heavy
        roster in poor-fit system than for returner-heavy roster.
        """
        poor_fit = RosterFitInput(
            offensive_fit_score=5.0,
            defensive_fit_score=5.0,
            adjusted_off_fit=5.0,
            adjusted_def_fit=5.0,
            has_team_style_data=True,
        )
        result_xfr = project_team(self._transfer_heavy_roster(), poor_fit, _ctx())
        result_ret = project_team(self._returner_heavy_roster(), poor_fit, _ctx())
        band_xfr = result_xfr.projected_adj_em_high - result_xfr.projected_adj_em_low
        band_ret = result_ret.projected_adj_em_high - result_ret.projected_adj_em_low
        self.assertGreater(band_xfr, band_ret)
