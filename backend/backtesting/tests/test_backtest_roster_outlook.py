"""
Tests for Phase 9: Roster Outlook Backtesting Framework.

Organization:
  TestMetrics             — DB-free unit tests for metrics.py functions
  TestDataLoaderHelpers   — DB-free unit tests for data_loader.py pure helpers
  TestAblationHelpers     — DB-free unit tests for ablation.py pure helpers
  TestAblationModels      — Integration tests that run Models B-F end-to-end
  TestLeakageSafety       — Validates no target-year data enters prediction paths
  TestReportGeneration    — Tests CSV/JSON/Markdown output generation
  TestManagementCommand   — Smoke-tests the management command (uses real DB)
  TestAvailableSourceYears — Integration test for data availability detection

Run with:
    python manage.py test backtesting --keepdb -v 2
Or DB-free helpers only:
    python -m pytest backend/backtesting/tests/test_backtest_roster_outlook.py::TestMetrics -v
"""

from __future__ import annotations

import math
import os
import statistics
import tempfile
import unittest
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════════════
# TestMetrics — pure unit tests, no Django required
# ═══════════════════════════════════════════════════════════════════════════════

class TestMetrics(unittest.TestCase):
    """DB-free tests for metrics.py — all pure math, no imports of Django models."""

    def setUp(self):
        from backtesting.roster_outlook.metrics import (
            compute_point_metrics,
            compute_rank_metrics,
            compute_coverage,
            paired_comparison,
            subgroup_metrics,
        )
        self.compute_point_metrics = compute_point_metrics
        self.compute_rank_metrics = compute_rank_metrics
        self.compute_coverage = compute_coverage
        self.paired_comparison = paired_comparison
        self.subgroup_metrics = subgroup_metrics

    # ── compute_point_metrics ───────────────────────────────────────────────

    def test_perfect_predictions_rmse_zero(self):
        actuals = [1.0, 2.0, 3.0, 4.0, 5.0]
        m = self.compute_point_metrics(actuals, actuals)
        self.assertAlmostEqual(m.rmse, 0.0, places=6)
        self.assertAlmostEqual(m.mae, 0.0, places=6)
        self.assertAlmostEqual(m.bias, 0.0, places=6)
        self.assertAlmostEqual(m.r_squared, 1.0, places=4)

    def test_constant_prediction_r_squared_negative(self):
        preds = [3.0] * 10
        actuals = list(range(10))
        m = self.compute_point_metrics(preds, actuals)
        self.assertLess(m.r_squared, 0.0)  # worse than mean baseline

    def test_bias_sign(self):
        preds = [5.0, 5.0, 5.0]
        actuals = [3.0, 3.0, 3.0]
        m = self.compute_point_metrics(preds, actuals)
        self.assertAlmostEqual(m.bias, 2.0, places=6)  # systematic over-prediction

    def test_negative_bias_when_under_predicting(self):
        preds = [2.0, 2.0, 2.0]
        actuals = [5.0, 5.0, 5.0]
        m = self.compute_point_metrics(preds, actuals)
        self.assertAlmostEqual(m.bias, -3.0, places=6)

    def test_rmse_known_value(self):
        preds = [0.0, 0.0, 0.0, 0.0]
        actuals = [2.0, 2.0, 2.0, 2.0]
        m = self.compute_point_metrics(preds, actuals)
        self.assertAlmostEqual(m.rmse, 2.0, places=6)

    def test_spearman_positive_correlation(self):
        preds = [1.0, 2.0, 3.0, 4.0, 5.0]
        actuals = [1.5, 2.2, 3.1, 3.8, 5.2]
        m = self.compute_point_metrics(preds, actuals)
        self.assertGreater(m.spearman_rho, 0.9)
        self.assertLess(m.spearman_p, 0.05)

    def test_mismatched_lengths_raises(self):
        with self.assertRaises(ValueError):
            self.compute_point_metrics([1.0, 2.0], [3.0])

    def test_single_observation_raises(self):
        with self.assertRaises(ValueError):
            self.compute_point_metrics([1.0], [1.0])

    def test_as_dict_keys_present(self):
        preds = [1.0, 2.0, 3.0]
        actuals = [1.5, 2.5, 3.5]
        d = self.compute_point_metrics(preds, actuals).as_dict()
        for key in ("n", "rmse", "mae", "bias", "r_squared", "pearson_r", "spearman_rho"):
            self.assertIn(key, d)

    # ── compute_rank_metrics ─────────────────────────────────────────────────

    def test_perfect_rank_predictions(self):
        ranks = [1, 2, 3, 4, 5]
        m = self.compute_rank_metrics(ranks, ranks)
        self.assertAlmostEqual(m.mean_abs_rank_error, 0.0, places=6)

    def test_top_10_hit_rate_full_miss(self):
        # Predict rank 11+ for all actual top-10 teams
        pred = list(range(11, 21)) + [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        actual = list(range(1, 21))
        m = self.compute_rank_metrics(pred, actual)
        self.assertAlmostEqual(m.top_10_hit_rate, 0.0, places=6)

    def test_top_10_hit_rate_partial(self):
        # 20 teams total. For the 10 actually ranked top-10:
        #   teams ranked 1-5 predicted 1-5 (hits); teams ranked 6-10 predicted 11-15 (misses)
        # → hit rate = 5/10 = 0.5
        actual = list(range(1, 21))
        pred   = [1, 2, 3, 4, 5, 11, 12, 13, 14, 15, 6, 7, 8, 9, 10, 16, 17, 18, 19, 20]
        m = self.compute_rank_metrics(pred, actual)
        self.assertAlmostEqual(m.top_10_hit_rate, 0.5, places=6)

    # ── compute_coverage ────────────────────────────────────────────────────

    def test_full_coverage(self):
        actuals = [0.0, 5.0, -5.0, 10.0]
        lows = [-100.0] * 4
        highs = [100.0] * 4
        m = self.compute_coverage(lows, highs, actuals)
        self.assertAlmostEqual(m.coverage_rate, 1.0, places=6)

    def test_zero_coverage(self):
        actuals = [100.0, 200.0, 300.0]
        lows = [0.0] * 3
        highs = [1.0] * 3
        m = self.compute_coverage(lows, highs, actuals)
        self.assertAlmostEqual(m.coverage_rate, 0.0, places=6)

    def test_band_width_computed(self):
        lows = [0.0, 0.0]
        highs = [10.0, 20.0]
        actuals = [5.0, 10.0]
        m = self.compute_coverage(lows, highs, actuals)
        self.assertAlmostEqual(m.mean_band_width, 15.0, places=6)

    # ── paired_comparison ───────────────────────────────────────────────────

    def test_identical_model_returns_zero_delta(self):
        errors = [1.0, -2.0, 0.5, -0.5, 1.5, -1.5]
        cmp = self.paired_comparison(errors, errors)
        self.assertAlmostEqual(cmp.delta_mae, 0.0, places=6)

    def test_b_better_direction(self):
        err_a = [5.0, -5.0, 3.0, -3.0, 4.0, -4.0]  # large errors
        err_b = [1.0, -1.0, 0.5, -0.5, 1.5, -1.5]   # smaller errors
        cmp = self.paired_comparison(err_a, err_b)
        self.assertLess(cmp.delta_mae, 0.0)  # B improved
        self.assertGreater(cmp.b_better_fraction, 0.5)

    def test_too_few_samples_returns_none(self):
        result = self.paired_comparison([1.0, 2.0], [1.0, 2.0])
        self.assertIsNone(result)

    def test_mae_pct_change_sign(self):
        err_a = [5.0, -5.0, 5.0, -5.0, 5.0, -5.0]
        err_b = [2.5, -2.5, 2.5, -2.5, 2.5, -2.5]  # 50% improvement
        cmp = self.paired_comparison(err_a, err_b)
        self.assertAlmostEqual(cmp.mae_pct_change, -50.0, places=2)

    # ── subgroup_metrics ────────────────────────────────────────────────────

    def test_subgroup_split(self):
        records = [
            {"pred_adj_em": 1.0, "actual_adj_em": 1.5, "conf_group": "power"},
            {"pred_adj_em": 2.0, "actual_adj_em": 2.5, "conf_group": "power"},
            {"pred_adj_em": -1.0, "actual_adj_em": -1.5, "conf_group": "mid_major"},
            {"pred_adj_em": -2.0, "actual_adj_em": -2.5, "conf_group": "mid_major"},
        ]
        result = self.subgroup_metrics(records, "conf_group")
        self.assertIn("power", result)
        self.assertIn("mid_major", result)
        self.assertEqual(result["power"].n, 2)

    def test_subgroup_skips_under_minimum(self):
        records = [{"pred_adj_em": 1.0, "actual_adj_em": 1.5, "group": "x"}]
        result = self.subgroup_metrics(records, "group")
        self.assertNotIn("x", result)  # n < 2, skipped


# ═══════════════════════════════════════════════════════════════════════════════
# TestDataLoaderHelpers — pure unit tests, no Django required
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataLoaderHelpers(unittest.TestCase):
    """DB-free tests for standalone helper functions in data_loader.py."""

    def setUp(self):
        from backtesting.roster_outlook.data_loader import (
            _derive_recruitment_type,
            _build_player_rows,
            MINUTES_SHARE_SCALE,
        )
        self._derive_recruitment_type = _derive_recruitment_type
        self._build_player_rows = _build_player_rows
        self.MINUTES_SHARE_SCALE = MINUTES_SHARE_SCALE

    def test_recruitment_type_returner(self):
        prior = {101: "duke"}
        rt = self._derive_recruitment_type(101, "duke", prior)
        self.assertEqual(rt, "returner")

    def test_recruitment_type_transfer(self):
        prior = {101: "unc"}
        rt = self._derive_recruitment_type(101, "duke", prior)
        self.assertEqual(rt, "transfer")

    def test_recruitment_type_newcomer(self):
        rt = self._derive_recruitment_type(101, "duke", {})
        self.assertEqual(rt, "newcomer")

    def test_recruitment_type_newcomer_non_d1_prior(self):
        """A player whose prior team had no slug (non-D1) should be a newcomer."""
        prior = {101: ""}  # empty slug = non-D1
        rt = self._derive_recruitment_type(101, "duke", prior)
        self.assertEqual(rt, "newcomer")

    def test_minutes_share_sums_to_scale(self):
        rows = [
            {"player_id": 1, "team__slug": "duke", "obpr": 2.0, "dbpr": -1.0, "bpr": 1.0, "mpg": 30.0, "gp": 30},
            {"player_id": 2, "team__slug": "duke", "obpr": 1.0, "dbpr": -0.5, "bpr": 0.5, "mpg": 20.0, "gp": 25},
            {"player_id": 3, "team__slug": "duke", "obpr": 0.5, "dbpr": -0.3, "bpr": 0.2, "mpg": 10.0, "gp": 20},
        ]
        players = self._build_player_rows(rows, "duke", {1: "duke", 2: "duke"})
        total_share = sum(p.minutes_share_p2 for p in players)
        self.assertAlmostEqual(total_share, self.MINUTES_SHARE_SCALE, places=4)

    def test_empty_rows_returns_empty(self):
        result = self._build_player_rows([], "duke", {})
        self.assertEqual(result, [])

    def test_null_obpr_treated_as_zero(self):
        rows = [
            {"player_id": 1, "team__slug": "duke", "obpr": None, "dbpr": None, "bpr": None, "mpg": 30.0, "gp": 20},
            {"player_id": 2, "team__slug": "duke", "obpr": 1.0, "dbpr": -0.5, "bpr": 0.5, "mpg": 10.0, "gp": 20},
        ]
        players = self._build_player_rows(rows, "duke", {})
        self.assertEqual(len(players), 2)
        p0 = players[0]
        self.assertAlmostEqual(p0.obpr, 0.0, places=6)
        self.assertAlmostEqual(p0.dbpr, 0.0, places=6)

    def test_high_mpg_player_gets_higher_share(self):
        rows = [
            {"player_id": 1, "team__slug": "duke", "obpr": 0.0, "dbpr": 0.0, "bpr": 0.0, "mpg": 30.0, "gp": 30},
            {"player_id": 2, "team__slug": "duke", "obpr": 0.0, "dbpr": 0.0, "bpr": 0.0, "mpg": 10.0, "gp": 30},
        ]
        players = self._build_player_rows(rows, "duke", {})
        shares = {p.player_id: p.minutes_share_p2 for p in players}
        self.assertGreater(shares[1], shares[2])

    def test_bpr_computed_when_null(self):
        rows = [
            {"player_id": 1, "team__slug": "duke", "obpr": 2.0, "dbpr": -1.0, "bpr": None, "mpg": 30.0, "gp": 30},
        ]
        players = self._build_player_rows(rows, "duke", {})
        self.assertAlmostEqual(players[0].bpr, 1.0, places=6)


# ═══════════════════════════════════════════════════════════════════════════════
# TestAblationHelpers — DB-free tests for ablation.py pure functions
# ═══════════════════════════════════════════════════════════════════════════════

class TestAblationHelpers(unittest.TestCase):
    """DB-free tests for ablation helper functions."""

    def setUp(self):
        from backtesting.roster_outlook.ablation import _compute_returner_frac
        from backtesting.roster_outlook.data_loader import PlayerRow
        self._compute_returner_frac = _compute_returner_frac
        self.PlayerRow = PlayerRow

    def _make_player(self, pid, team, obpr, dbpr, bpr, mpg, gp, rtype, share):
        return self.PlayerRow(
            player_id=pid, team_slug=team,
            obpr=obpr, dbpr=dbpr, bpr=bpr,
            mpg=mpg, gp=gp,
            recruitment_type=rtype,
            minutes_share_p2=share,
        )

    def test_returner_frac_all_returners(self):
        players = [
            self._make_player(1, "duke", 1.0, -0.5, 0.5, 30, 30, "returner", 2.0),
            self._make_player(2, "duke", 2.0, -1.0, 1.0, 20, 30, "returner", 1.5),
        ]
        frac = self._compute_returner_frac(players)
        self.assertAlmostEqual(frac, 1.0, places=6)

    def test_returner_frac_no_returners(self):
        players = [
            self._make_player(1, "duke", 1.0, -0.5, 0.5, 30, 30, "newcomer", 2.0),
            self._make_player(2, "duke", 2.0, -1.0, 1.0, 20, 30, "transfer", 1.5),
        ]
        frac = self._compute_returner_frac(players)
        self.assertAlmostEqual(frac, 0.0, places=6)

    def test_returner_frac_mixed(self):
        players = [
            self._make_player(1, "duke", 1.0, -0.5, 0.5, 30, 30, "returner", 2.0),
            self._make_player(2, "duke", 2.0, -1.0, 1.0, 20, 30, "newcomer", 2.0),
        ]
        frac = self._compute_returner_frac(players)
        self.assertAlmostEqual(frac, 0.5, places=6)

    def test_returner_frac_empty_returns_zero(self):
        frac = self._compute_returner_frac([])
        self.assertAlmostEqual(frac, 0.0, places=6)


# ═══════════════════════════════════════════════════════════════════════════════
# TestAblationModels — integration tests for model variants (needs DB)
# ═══════════════════════════════════════════════════════════════════════════════

try:
    import django
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False

try:
    from django.test import TestCase as DjangoTestCase
    _django_test_base = DjangoTestCase
except ImportError:
    _django_test_base = unittest.TestCase


class TestAblationModels(_django_test_base):
    """
    Integration tests for ablation model variants using synthetic in-memory data.
    These tests do NOT hit the database — they build BacktestPair manually.
    """

    def _make_pair(self, source_year: int = 2023) -> "BacktestPair":
        """Build a synthetic BacktestPair with controlled team/player data."""
        from backtesting.roster_outlook.data_loader import (
            BacktestPair, TeamPlayerPool, PlayerRow, ActualOutcome
        )

        # Two synthetic teams
        players_duke = [
            PlayerRow(1, "duke", obpr=5.0, dbpr=-3.0, bpr=2.0, mpg=30, gp=30,
                      recruitment_type="returner", minutes_share_p2=2.5),
            PlayerRow(2, "duke", obpr=3.0, dbpr=-2.0, bpr=1.0, mpg=25, gp=30,
                      recruitment_type="returner", minutes_share_p2=2.0),
            PlayerRow(3, "duke", obpr=1.0, dbpr=-0.5, bpr=0.5, mpg=15, gp=25,
                      recruitment_type="newcomer", minutes_share_p2=0.5),
        ]
        players_unc = [
            PlayerRow(4, "unc", obpr=4.0, dbpr=-2.5, bpr=1.5, mpg=28, gp=30,
                      recruitment_type="returner", minutes_share_p2=2.5),
            PlayerRow(5, "unc", obpr=2.0, dbpr=-1.5, bpr=0.5, mpg=22, gp=30,
                      recruitment_type="transfer", minutes_share_p2=2.0),
            PlayerRow(6, "unc", obpr=0.5, dbpr=-0.3, bpr=0.2, mpg=10, gp=20,
                      recruitment_type="newcomer", minutes_share_p2=0.5),
        ]

        pair = BacktestPair(
            source_year=source_year,
            target_year=source_year + 1,
            team_pools={
                "duke": TeamPlayerPool("duke", source_year, players_duke),
                "unc": TeamPlayerPool("unc", source_year, players_unc),
            },
            actual_outcomes={
                "duke": ActualOutcome("duke", adj_o=115.0, adj_d=100.0, adj_em=15.0,
                                      rank_adj_em=5),
                "unc": ActualOutcome("unc", adj_o=112.0, adj_d=103.0, adj_em=9.0,
                                     rank_adj_em=20),
            },
            source_outcomes={
                "duke": ActualOutcome("duke", adj_o=114.0, adj_d=101.0, adj_em=13.0),
                "unc": ActualOutcome("unc", adj_o=111.0, adj_d=104.0, adj_em=7.0),
            },
            d1_avg_o=105.0,
            d1_avg_d=105.0,
            n_d1_teams=2,
        )
        return pair

    def test_model_a_uses_source_year_adj_em(self):
        from backtesting.roster_outlook.ablation import run_all_models
        pair = self._make_pair()
        result = run_all_models(pair, models=["A"])
        duke_pred = result.get("duke", "A")
        self.assertIsNotNone(duke_pred)
        self.assertAlmostEqual(duke_pred.pred_adj_em, 13.0, places=6)
        self.assertAlmostEqual(duke_pred.pred_adj_o, 114.0, places=6)

    def test_model_b_uses_equal_weights(self):
        from backtesting.roster_outlook.ablation import run_all_models
        pair = self._make_pair()
        result = run_all_models(pair, models=["B"])
        # Should produce a prediction without crashing
        self.assertIsNotNone(result.get("duke", "B"))

    def test_model_c_minutes_weighted_vs_b_equal(self):
        from backtesting.roster_outlook.ablation import run_all_models
        pair = self._make_pair()
        result = run_all_models(pair, models=["B", "C"])
        # Models B and C should differ when player minutes are unequal
        duke_b = result.get("duke", "B")
        duke_c = result.get("duke", "C")
        self.assertIsNotNone(duke_b)
        self.assertIsNotNone(duke_c)
        # High-BPR player (pid=1) has more minutes → C should differ from B
        self.assertNotAlmostEqual(duke_b.pred_adj_em, duke_c.pred_adj_em, places=2)

    def test_model_d_returns_continuity_score(self):
        from backtesting.roster_outlook.ablation import run_all_models
        pair = self._make_pair()
        result = run_all_models(pair, models=["D"])
        duke_d = result.get("duke", "D")
        self.assertIsNotNone(duke_d)
        self.assertIsNotNone(duke_d.continuity_score)
        # Duke has 2 returners + 1 newcomer; continuity should reflect this
        self.assertGreater(duke_d.continuity_score, 0.0)

    def test_model_f_bumped_bpr_shifts_rating(self):
        from backtesting.roster_outlook.ablation import run_all_models, RETURNER_BUMP_FACTOR
        pair = self._make_pair()
        result = run_all_models(pair, models=["C", "F"])
        # Model F applies returner bump — should produce a DIFFERENT prediction
        # (because returners have higher BPR, bump pushes rating up for high-returner teams)
        duke_c = result.get("duke", "C")
        duke_f = result.get("duke", "F")
        self.assertIsNotNone(duke_c)
        self.assertIsNotNone(duke_f)
        # Duke has returners (pid 1, 2 with positive BPR) → bump increases base_off
        self.assertNotAlmostEqual(duke_c.pred_adj_em, duke_f.pred_adj_em, places=3)

    def test_all_models_run_without_crash(self):
        from backtesting.roster_outlook.ablation import run_all_models, ALL_MODELS
        pair = self._make_pair()
        result = run_all_models(pair, models=ALL_MODELS)
        for team_slug in ["duke", "unc"]:
            for model in ALL_MODELS:
                pred = result.get(team_slug, model)
                self.assertIsNotNone(pred, f"Model {model} missing for {team_slug}")

    def test_predictions_have_finite_values(self):
        from backtesting.roster_outlook.ablation import run_all_models, ALL_MODELS
        pair = self._make_pair()
        result = run_all_models(pair, models=ALL_MODELS)
        for team_slug in result.teams():
            for model in ALL_MODELS:
                pred = result.get(team_slug, model)
                if pred is None:
                    continue
                self.assertTrue(math.isfinite(pred.pred_adj_em),
                                f"{model}/{team_slug} pred_adj_em is not finite")

    def test_model_subsets_work(self):
        from backtesting.roster_outlook.ablation import run_all_models
        pair = self._make_pair()
        result = run_all_models(pair, models=["A", "C"])
        self.assertIn("A", result.models)
        self.assertIn("C", result.models)


# ═══════════════════════════════════════════════════════════════════════════════
# TestLeakageSafety — validates leakage-free data boundaries
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeakageSafety(unittest.TestCase):
    """
    Leakage-safety tests.  These do NOT hit the DB — they validate that
    the BacktestPair structure keeps target-year data separate from predictions.
    """

    def test_actual_outcomes_not_in_team_pools(self):
        """Verify that target-year adj_em values do NOT appear as model inputs."""
        from backtesting.roster_outlook.data_loader import (
            BacktestPair, TeamPlayerPool, PlayerRow, ActualOutcome
        )
        from backtesting.roster_outlook.ablation import run_all_models

        actual_em = 99.9  # Conspicuous sentinel value
        players = [
            PlayerRow(1, "duke", 2.0, -1.0, 1.0, 30, 30, "returner", 2.0),
            PlayerRow(2, "duke", 1.0, -0.5, 0.5, 20, 30, "returner", 1.5),
            PlayerRow(3, "duke", 0.5, -0.2, 0.3, 10, 20, "newcomer", 0.5),
        ]
        pair = BacktestPair(
            source_year=2023,
            target_year=2024,
            team_pools={"duke": TeamPlayerPool("duke", 2023, players)},
            actual_outcomes={"duke": ActualOutcome("duke", adj_o=110.0, adj_d=100.0, adj_em=actual_em)},
            source_outcomes={"duke": ActualOutcome("duke", adj_o=108.0, adj_d=102.0, adj_em=5.0)},
            d1_avg_o=105.0,
            d1_avg_d=105.0,
        )
        result = run_all_models(pair, models=["A", "B", "C", "D"])
        for model in ["B", "C", "D"]:
            pred = result.get("duke", model)
            if pred is None:
                continue
            # No model input (except sentinel) should produce exactly actual_em
            self.assertNotAlmostEqual(
                pred.pred_adj_em, actual_em, places=2,
                msg=f"Model {model} prediction suspiciously matches actual_em={actual_em}",
            )

    def test_model_a_uses_source_not_target(self):
        """Model A should use source_outcomes (prior year), not actual_outcomes (target year)."""
        from backtesting.roster_outlook.data_loader import (
            BacktestPair, TeamPlayerPool, PlayerRow, ActualOutcome
        )
        from backtesting.roster_outlook.ablation import run_all_models

        players = [
            PlayerRow(1, "duke", 2.0, -1.0, 1.0, 30, 30, "returner", 2.0),
            PlayerRow(2, "duke", 1.0, -0.5, 0.5, 20, 30, "returner", 1.5),
            PlayerRow(3, "duke", 0.5, -0.2, 0.3, 10, 20, "newcomer", 0.5),
        ]
        pair = BacktestPair(
            source_year=2023,
            target_year=2024,
            team_pools={"duke": TeamPlayerPool("duke", 2023, players)},
            actual_outcomes={"duke": ActualOutcome("duke", adj_o=115.0, adj_d=99.0, adj_em=16.0)},
            source_outcomes={"duke": ActualOutcome("duke", adj_o=112.0, adj_d=101.0, adj_em=11.0)},
            d1_avg_o=105.0,
            d1_avg_d=105.0,
        )
        result = run_all_models(pair, models=["A"])
        pred = result.get("duke", "A")
        self.assertAlmostEqual(pred.pred_adj_em, 11.0, places=6,
                               msg="Model A must use source-year adj_em, not target!")


# ═══════════════════════════════════════════════════════════════════════════════
# TestReportGeneration — tests output generation (no DB required)
# ═══════════════════════════════════════════════════════════════════════════════

class TestReportGeneration(unittest.TestCase):
    """Tests for report.py output generation."""

    def _build_minimal_pair_and_result(self):
        from backtesting.roster_outlook.data_loader import (
            BacktestPair, TeamPlayerPool, PlayerRow, ActualOutcome
        )
        from backtesting.roster_outlook.ablation import AblationResult, TeamPrediction

        source_year = 2023
        players = [
            PlayerRow(1, "duke", 2.0, -1.0, 1.0, 30, 30, "returner", 2.0),
            PlayerRow(2, "duke", 1.0, -0.5, 0.5, 20, 30, "returner", 1.5),
            PlayerRow(3, "duke", 0.5, -0.2, 0.3, 10, 20, "newcomer", 0.5),
        ]
        pair = BacktestPair(
            source_year=source_year,
            target_year=source_year + 1,
            team_pools={"duke": TeamPlayerPool("duke", source_year, players)},
            actual_outcomes={"duke": ActualOutcome("duke", adj_o=115.0, adj_d=100.0, adj_em=15.0)},
            source_outcomes={"duke": ActualOutcome("duke", adj_o=113.0, adj_d=101.0, adj_em=12.0)},
            d1_avg_o=105.0,
            d1_avg_d=105.0,
        )
        ablation_result = AblationResult(
            source_year=source_year,
            target_year=source_year + 1,
            predictions={
                "duke": {
                    "A": TeamPrediction("duke", "A", pred_adj_o=113.0, pred_adj_d=101.0, pred_adj_em=12.0),
                    "C": TeamPrediction("duke", "C", pred_adj_o=114.0, pred_adj_d=100.5, pred_adj_em=13.5,
                                        n_players=3, returner_fraction=0.8,
                                        pred_adj_em_low=9.0, pred_adj_em_high=18.0, uncertainty=0.3),
                }
            },
            models=["A", "C"],
        )
        return ablation_result, pair

    def test_generate_reports_creates_files(self):
        from backtesting.roster_outlook.report import generate_reports
        ablation_result, pair = self._build_minimal_pair_and_result()

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_reports(
                [(ablation_result, pair)],
                output_dir=tmpdir,
                include_subgroups=False,
                model_order=["A", "C"],
            )
            self.assertIn("csv", paths)
            self.assertIn("json", paths)
            self.assertIn("markdown", paths)
            for path in paths.values():
                self.assertTrue(os.path.exists(path), f"Missing output: {path}")

    def test_csv_has_rows(self):
        import csv
        from backtesting.roster_outlook.report import generate_reports
        ablation_result, pair = self._build_minimal_pair_and_result()

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_reports(
                [(ablation_result, pair)],
                output_dir=tmpdir,
                include_subgroups=False,
                model_order=["A", "C"],
            )
            with open(paths["csv"]) as fh:
                reader = list(csv.DictReader(fh))
            # 1 team × 2 models = 2 rows
            self.assertEqual(len(reader), 2)

    def test_json_has_model_keys(self):
        import json
        from backtesting.roster_outlook.report import generate_reports
        ablation_result, pair = self._build_minimal_pair_and_result()

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_reports(
                [(ablation_result, pair)],
                output_dir=tmpdir,
                include_subgroups=False,
                model_order=["A", "C"],
            )
            summary = json.loads(open(paths["json"]).read())
            self.assertIn("models", summary)
            self.assertIn("A", summary["models"])
            self.assertIn("C", summary["models"])

    def test_markdown_contains_ablation_table(self):
        from backtesting.roster_outlook.report import generate_reports
        ablation_result, pair = self._build_minimal_pair_and_result()

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_reports(
                [(ablation_result, pair)],
                output_dir=tmpdir,
                include_subgroups=False,
                model_order=["A", "C"],
            )
            content = open(paths["markdown"]).read()
            # The heading is always rendered regardless of metric availability
            self.assertIn("Ablation Ladder", content)
            # The table header row is always rendered
            self.assertIn("| Model |", content)

    def test_error_column_in_csv(self):
        import csv
        from backtesting.roster_outlook.report import generate_reports
        ablation_result, pair = self._build_minimal_pair_and_result()

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_reports(
                [(ablation_result, pair)],
                output_dir=tmpdir,
                include_subgroups=False,
                model_order=["A"],
            )
            with open(paths["csv"]) as fh:
                row = list(csv.DictReader(fh))[0]
            self.assertIn("error_adj_em", row)
            expected_err = round(12.0 - 15.0, 4)  # pred_A - actual
            self.assertAlmostEqual(float(row["error_adj_em"]), expected_err, places=4)


# ═══════════════════════════════════════════════════════════════════════════════
# TestAvailableSourceYears — integration test (uses real DB)
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from django.test import TestCase as DjTestCase

    class TestAvailableSourceYears(DjTestCase):
        """Test available_source_years() detects valid backtest pairs from real DB."""

        def test_returns_list(self):
            from backtesting.roster_outlook.data_loader import available_source_years
            result = available_source_years()
            self.assertIsInstance(result, list)

        def test_years_are_sorted(self):
            from backtesting.roster_outlook.data_loader import available_source_years
            years = available_source_years()
            self.assertEqual(years, sorted(years))

        def test_adjacent_tsr_exists_for_each(self):
            """For every source year Y returned, TSR must exist for Y+1."""
            from backtesting.roster_outlook.data_loader import available_source_years
            from core.models import TeamSeasonRatings
            years = available_source_years()
            tsr_years = set(
                TeamSeasonRatings.objects.values_list("season__year", flat=True).distinct()
            )
            for yr in years:
                self.assertIn(yr + 1, tsr_years,
                              f"TSR for {yr + 1} not found (required for {yr}→{yr + 1})")

    class TestLoadBacktestPairIntegration(DjTestCase):
        """Integration test: load a real backtest pair and validate structure."""

        def test_load_smallest_available_pair(self):
            from backtesting.roster_outlook.data_loader import available_source_years, load_backtest_pair
            years = available_source_years()
            if not years:
                self.skipTest("No available source years in database.")
            yr = min(years)
            pair = load_backtest_pair(yr)
            self.assertEqual(pair.source_year, yr)
            self.assertEqual(pair.target_year, yr + 1)
            self.assertGreater(len(pair.team_pools), 0, "Expected at least some team pools")
            self.assertGreater(len(pair.actual_outcomes), 0, "Expected target-year outcomes")

        def test_evaluable_teams_nonempty(self):
            from backtesting.roster_outlook.data_loader import available_source_years, load_backtest_pair
            years = available_source_years()
            if not years:
                self.skipTest("No available source years.")
            pair = load_backtest_pair(min(years))
            evaluable = pair.evaluable_teams()
            self.assertGreater(len(evaluable), 50,
                               f"Expected 100+ evaluable teams; got {len(evaluable)}")

        def test_no_target_year_data_in_source_pools(self):
            """
            Verify that the actual_outcomes dict is logically separated:
            source player data comes from source_year, not target_year.
            """
            from backtesting.roster_outlook.data_loader import available_source_years, load_backtest_pair
            years = available_source_years()
            if not years:
                self.skipTest("No available source years.")
            pair = load_backtest_pair(min(years))
            # Check that all player rows reference source_year
            for team_slug, pool in pair.team_pools.items():
                self.assertEqual(pool.source_year, pair.source_year)

        def test_recruitment_types_valid(self):
            """All player recruitment types must be one of the three valid values."""
            from backtesting.roster_outlook.data_loader import available_source_years, load_backtest_pair
            years = available_source_years()
            if not years:
                self.skipTest("No available source years.")
            pair = load_backtest_pair(min(years))
            valid_types = {"returner", "transfer", "newcomer"}
            sample = list(pair.team_pools.values())[:10]
            for pool in sample:
                for player in pool.players:
                    self.assertIn(player.recruitment_type, valid_types,
                                  f"Invalid recruitment_type: {player.recruitment_type}")

        def test_minutes_shares_sum_to_scale(self):
            """Each team's minutes shares should sum to approximately MINUTES_SHARE_SCALE."""
            from backtesting.roster_outlook.data_loader import (
                available_source_years, load_backtest_pair, MINUTES_SHARE_SCALE
            )
            years = available_source_years()
            if not years:
                self.skipTest("No available source years.")
            pair = load_backtest_pair(min(years))
            sample = list(pair.team_pools.values())[:20]
            for pool in sample:
                total_share = sum(p.minutes_share_p2 for p in pool.players)
                self.assertAlmostEqual(
                    total_share, MINUTES_SHARE_SCALE, places=3,
                    msg=f"{pool.team_slug}: minutes_share sum={total_share:.4f} ≠ {MINUTES_SHARE_SCALE}",
                )

    class TestRunAllModelsIntegration(DjTestCase):
        """Integration test: run full ablation on real data."""

        def _get_pair(self):
            from backtesting.roster_outlook.data_loader import available_source_years, load_backtest_pair
            years = available_source_years()
            if not years:
                return None
            return load_backtest_pair(min(years))

        def test_ablation_runs_without_error(self):
            from backtesting.roster_outlook.ablation import run_all_models, ALL_MODELS
            pair = self._get_pair()
            if pair is None:
                self.skipTest("No available source years.")
            result = run_all_models(pair, models=ALL_MODELS)
            self.assertGreater(len(result.teams()), 0)

        def test_all_predictions_finite(self):
            from backtesting.roster_outlook.ablation import run_all_models, ALL_MODELS
            pair = self._get_pair()
            if pair is None:
                self.skipTest("No available source years.")
            result = run_all_models(pair, models=ALL_MODELS)
            for team_slug in result.teams()[:30]:
                for model in ALL_MODELS:
                    pred = result.get(team_slug, model)
                    if pred is None:
                        continue
                    self.assertTrue(
                        math.isfinite(pred.pred_adj_em),
                        f"{model}/{team_slug}: pred_adj_em is not finite",
                    )

        def test_model_c_and_d_may_differ(self):
            """
            Models C and D should differ for at least some teams in a pair where
            prior_year_has_data=True (i.e., where recruitment types are reliable).

            Pairs where prior_year_has_data=False (e.g., 2023 source year in dbs
            without 2022 PSS) will have D=C by design — skip those.
            """
            from backtesting.roster_outlook.ablation import run_all_models
            from backtesting.roster_outlook.data_loader import available_source_years, load_backtest_pair
            years = available_source_years()
            # Find a year with prior_year_has_data=True
            valid_pair = None
            for yr in sorted(years):
                p = load_backtest_pair(yr)
                if p.prior_year_has_data:
                    valid_pair = p
                    break
            if valid_pair is None:
                self.skipTest("No backtest pair with prior_year_has_data=True available.")
            result = run_all_models(valid_pair, models=["C", "D"])
            diffs = []
            for slug in result.teams():
                c = result.get(slug, "C")
                d = result.get(slug, "D")
                if c and d:
                    diffs.append(abs(c.pred_adj_em - d.pred_adj_em))
            self.assertTrue(
                any(d > 0.001 for d in diffs),
                "Models C and D should differ for at least some teams (continuity effect)",
            )

        def test_full_report_generation(self):
            """Smoke test: generate all reports for the smallest available pair."""
            from backtesting.roster_outlook.ablation import run_all_models, ALL_MODELS
            from backtesting.roster_outlook.report import generate_reports
            pair = self._get_pair()
            if pair is None:
                self.skipTest("No available source years.")
            result = run_all_models(pair, models=ALL_MODELS)
            with tempfile.TemporaryDirectory() as tmpdir:
                paths = generate_reports(
                    [(result, pair)],
                    output_dir=tmpdir,
                    include_subgroups=True,
                    model_order=ALL_MODELS,
                )
                for kind, path in paths.items():
                    self.assertTrue(os.path.exists(path), f"Missing {kind} output: {path}")

except ImportError:
    pass  # Django not available; skip DB-dependent test classes


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9b: Continuity Recalibration Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestContinuityPriorYearFallback(unittest.TestCase):
    """
    DB-free tests validating 'prior_year_has_data=False' fallback behavior.

    When source_year-1 PlayerSeasonStats are absent from the DB, every player
    is classified as 'newcomer', making returner_fraction=0 for all teams.
    Models D/E/F detect this via pair.prior_year_has_data=False and fall back
    to Model C output, avoiding a spurious maximum continuity penalty.
    """

    def _make_pair(self, prior_year_has_data: bool = True, returner_type: str = "returner"):
        """Build a BacktestPair with controlled prior_year_has_data flag."""
        from backtesting.roster_outlook.data_loader import (
            BacktestPair, TeamPlayerPool, PlayerRow, ActualOutcome
        )
        players = [
            PlayerRow(1, "duke", obpr=4.0, dbpr=-2.0, bpr=2.0, mpg=30, gp=30,
                      recruitment_type=returner_type, minutes_share_p2=2.5),
            PlayerRow(2, "duke", obpr=2.0, dbpr=-1.0, bpr=1.0, mpg=20, gp=30,
                      recruitment_type=returner_type, minutes_share_p2=2.0),
            PlayerRow(3, "duke", obpr=1.0, dbpr=-0.5, bpr=0.5, mpg=10, gp=20,
                      recruitment_type="newcomer", minutes_share_p2=0.5),
            PlayerRow(4, "unc", obpr=3.0, dbpr=-1.5, bpr=1.5, mpg=28, gp=30,
                      recruitment_type="returner", minutes_share_p2=2.5),
            PlayerRow(5, "unc", obpr=1.5, dbpr=-1.0, bpr=0.5, mpg=20, gp=30,
                      recruitment_type="transfer", minutes_share_p2=2.0),
            PlayerRow(6, "unc", obpr=0.5, dbpr=-0.3, bpr=0.2, mpg=10, gp=20,
                      recruitment_type="newcomer", minutes_share_p2=0.5),
        ]
        return BacktestPair(
            source_year=2023,
            target_year=2024,
            team_pools={
                "duke": TeamPlayerPool("duke", 2023, players[:3]),
                "unc": TeamPlayerPool("unc", 2023, players[3:]),
            },
            actual_outcomes={
                "duke": ActualOutcome("duke", adj_o=115.0, adj_d=100.0, adj_em=15.0),
                "unc": ActualOutcome("unc", adj_o=112.0, adj_d=104.0, adj_em=8.0),
            },
            source_outcomes={
                "duke": ActualOutcome("duke", adj_o=114.0, adj_d=101.0, adj_em=13.0),
                "unc": ActualOutcome("unc", adj_o=110.0, adj_d=105.0, adj_em=5.0),
            },
            d1_avg_o=108.0,
            d1_avg_d=108.0,
            n_d1_teams=2,
            prior_year_has_data=prior_year_has_data,
        )

    def test_model_d_no_prior_year_data_matches_c_exactly(self):
        """When prior_year_has_data=False, Model D must output same pred_adj_em as Model C."""
        from backtesting.roster_outlook.ablation import run_all_models
        pair = self._make_pair(prior_year_has_data=False)
        result = run_all_models(pair, models=["C", "D"])
        for slug in ["duke", "unc"]:
            c = result.get(slug, "C")
            d = result.get(slug, "D")
            self.assertIsNotNone(c)
            self.assertIsNotNone(d)
            self.assertAlmostEqual(
                c.pred_adj_em, d.pred_adj_em, places=6,
                msg=f"{slug}: D should equal C when prior_year_has_data=False",
            )

    def test_model_e_no_prior_year_data_matches_c_exactly(self):
        """When prior_year_has_data=False, Model E must output same pred_adj_em as Model C."""
        from backtesting.roster_outlook.ablation import run_all_models
        pair = self._make_pair(prior_year_has_data=False)
        result = run_all_models(pair, models=["C", "E"])
        for slug in ["duke", "unc"]:
            c = result.get(slug, "C")
            e = result.get(slug, "E")
            self.assertAlmostEqual(c.pred_adj_em, e.pred_adj_em, places=6,
                                   msg=f"{slug}: E should equal C when prior_year_has_data=False")

    def test_model_f_no_prior_year_data_matches_c_exactly(self):
        """When prior_year_has_data=False, Model F (returner bump) should equal C."""
        from backtesting.roster_outlook.ablation import run_all_models
        pair = self._make_pair(prior_year_has_data=False)
        result = run_all_models(pair, models=["C", "F"])
        for slug in ["duke", "unc"]:
            c = result.get(slug, "C")
            f = result.get(slug, "F")
            self.assertAlmostEqual(c.pred_adj_em, f.pred_adj_em, places=6,
                                   msg=f"{slug}: F should equal C when prior_year_has_data=False")

    def test_model_d_no_prior_year_data_has_none_returner_fraction(self):
        """When D falls back (no prior data), returner_fraction should be None (not 0)."""
        from backtesting.roster_outlook.ablation import run_all_models
        pair = self._make_pair(prior_year_has_data=False)
        result = run_all_models(pair, models=["D"])
        d = result.get("duke", "D")
        self.assertIsNone(d.returner_fraction,
                          "returner_fraction should be None (not 0) when prior data absent")

    def test_model_d_with_prior_data_differs_from_c_for_high_returner_team(self):
        """When prior_year_has_data=True and returners dominate, D should differ from C."""
        from backtesting.roster_outlook.ablation import run_all_models
        # All 'returner' typed → returner_fraction >> NEUTRAL → positive continuity adj
        pair = self._make_pair(prior_year_has_data=True, returner_type="returner")
        result = run_all_models(pair, models=["C", "D"])
        c = result.get("duke", "C")
        d = result.get("duke", "D")
        self.assertIsNotNone(c)
        self.assertIsNotNone(d)
        # D should give a higher (continuity-boosted) prediction for high-returner teams
        # (because returner_fraction > CONTINUITY_NEUTRAL_FRACTION)
        self.assertNotAlmostEqual(c.pred_adj_em, d.pred_adj_em, places=3,
                                  msg="D should differ from C when returners dominate")

    def test_default_prior_year_has_data_is_true(self):
        """BacktestPair.prior_year_has_data defaults to True."""
        from backtesting.roster_outlook.data_loader import BacktestPair
        pair = BacktestPair(
            source_year=2023, target_year=2024,
            team_pools={}, actual_outcomes={}, source_outcomes={},
            d1_avg_o=108.0, d1_avg_d=108.0,
        )
        self.assertTrue(pair.prior_year_has_data)


class TestContinuityFormula(unittest.TestCase):
    """
    DB-free tests validating the continuity adjustment formula
    in team_projection/engine.py.

    Verifies that:
    - The adjustment is zero at the neutral fraction
    - Higher returner fraction → positive adjustment (benefits offense + defense)
    - Lower returner fraction → negative adjustment
    - Adjustment is bounded by MAX_CONTINUITY_ADJ_OFF and MAX_CONTINUITY_ADJ_DEF
    - projected_adj_em = projected_adj_o − projected_adj_d after continuity (identity holds)
    """

    def _make_inputs(self, returner_share: float, total_share: float = 5.0):
        """
        Build a minimal PlayerProjectionInput list with a controlled returner fraction.

        Args:
            returner_share: Minutes share going to 'returner' players.
            total_share:    Total minutes share (default 5.0 = full team).
        """
        from core.analytics.player_value.team_projection.engine import PlayerProjectionInput

        newcomer_share = total_share - returner_share
        players = []
        if returner_share > 0:
            players.append(PlayerProjectionInput(
                player_id=1,
                projected_obpr=2.0,
                projected_dbpr=-1.0,
                projected_bpr=1.0,
                minutes_share_p2=returner_share,
                recruitment_type="returner",
                projection_uncertainty=0.35,
            ))
        if newcomer_share > 0:
            players.append(PlayerProjectionInput(
                player_id=2,
                projected_obpr=2.0,
                projected_dbpr=-1.0,
                projected_bpr=1.0,
                minutes_share_p2=newcomer_share,
                recruitment_type="newcomer",
                projection_uncertainty=0.35,
            ))
        return players

    def _get_constants(self):
        from core.analytics.player_value.team_projection.constants import (
            CONTINUITY_NEUTRAL_FRACTION,
            MAX_CONTINUITY_ADJ_OFF,
            MAX_CONTINUITY_ADJ_DEF,
        )
        return CONTINUITY_NEUTRAL_FRACTION, MAX_CONTINUITY_ADJ_OFF, MAX_CONTINUITY_ADJ_DEF

    def test_continuity_zero_at_neutral_point(self):
        """
        When the blended returner fraction equals CONTINUITY_NEUTRAL_FRACTION,
        the continuity adjustment should be (near) zero.
        """
        from core.analytics.player_value.team_projection.engine import _compute_continuity

        neutral, _, _ = self._get_constants()
        # Set returner_share so minutes fraction = neutral (BPR blend will also ≈ neutral
        # since all players have same BPR)
        players = self._make_inputs(returner_share=neutral * 5.0, total_share=5.0)
        cont = _compute_continuity(players)
        self.assertAlmostEqual(cont.continuity_adjustment_off, 0.0, places=4,
                               msg="Continuity off-adj should be ~0 at neutral point")
        self.assertAlmostEqual(cont.continuity_adjustment_def, 0.0, places=4,
                               msg="Continuity def-adj should be ~0 at neutral point")

    def test_continuity_positive_above_neutral(self):
        """Returner fraction well above neutral → positive continuity adj."""
        from core.analytics.player_value.team_projection.engine import _compute_continuity

        neutral, _, _ = self._get_constants()
        # Use 90% returner share (well above any reasonable neutral)
        players = self._make_inputs(returner_share=4.5, total_share=5.0)
        cont = _compute_continuity(players)
        self.assertGreater(cont.continuity_adjustment_off, 0.0,
                           "High returner fraction should give positive off-adj")
        self.assertGreater(cont.continuity_adjustment_def, 0.0,
                           "High returner fraction should give positive def-adj")

    def test_continuity_negative_below_neutral(self):
        """Returner fraction well below neutral → negative continuity adj."""
        from core.analytics.player_value.team_projection.engine import _compute_continuity

        # Use 100% newcomers (0% returners — well below any reasonable neutral)
        players = self._make_inputs(returner_share=0.0, total_share=5.0)
        cont = _compute_continuity(players)
        self.assertLess(cont.continuity_adjustment_off, 0.0,
                        "Zero returner fraction should give negative off-adj")
        self.assertLess(cont.continuity_adjustment_def, 0.0,
                        "Zero returner fraction should give negative def-adj")

    def test_continuity_bounded_by_caps(self):
        """Continuity adjustment cannot exceed MAX_CONTINUITY_ADJ constants."""
        from core.analytics.player_value.team_projection.engine import _compute_continuity

        _, max_off, max_def = self._get_constants()

        # Test at 0% returners (maximum penalty)
        players_low = self._make_inputs(returner_share=0.0, total_share=5.0)
        cont_low = _compute_continuity(players_low)
        self.assertGreaterEqual(cont_low.continuity_adjustment_off, -max_off,
                                "off-adj must not exceed -MAX_CONTINUITY_ADJ_OFF")
        self.assertGreaterEqual(cont_low.continuity_adjustment_def, -max_def,
                                "def-adj must not exceed -MAX_CONTINUITY_ADJ_DEF")

        # Test at 100% returners (maximum bonus)
        players_high = self._make_inputs(returner_share=5.0, total_share=5.0)
        cont_high = _compute_continuity(players_high)
        self.assertLessEqual(cont_high.continuity_adjustment_off, max_off,
                             "off-adj must not exceed +MAX_CONTINUITY_ADJ_OFF")
        self.assertLessEqual(cont_high.continuity_adjustment_def, max_def,
                             "def-adj must not exceed +MAX_CONTINUITY_ADJ_DEF")

    def test_adj_em_identity_with_continuity(self):
        """projected_adj_em must equal projected_adj_o − projected_adj_d (always)."""
        from core.analytics.player_value.team_projection.engine import (
            project_team, PlayerProjectionInput, D1Context
        )

        players = [
            PlayerProjectionInput(1, 4.0, -2.0, 2.0, 2.5, "returner", 0.3),
            PlayerProjectionInput(2, 2.0, -1.0, 1.0, 2.0, "transfer", 0.4),
            PlayerProjectionInput(3, 0.5, -0.3, 0.2, 0.5, "newcomer", 0.35),
        ]
        ctx = D1Context(
            avg_adj_o=108.0,
            avg_adj_d=108.0,
            league_mean_base_off=0.0,
            league_mean_base_def=0.0,
            n_projected_teams=360,
        )
        result = project_team(players, roster_fit=None, d1_context=ctx)
        self.assertAlmostEqual(
            result.projected_adj_em,
            result.projected_adj_o - result.projected_adj_d,
            places=6,
            msg="projected_adj_em must equal projected_adj_o − projected_adj_d",
        )


class TestContinuityProductionConstants(unittest.TestCase):
    """
    Tests that production continuity constants match Phase 9b calibration results.

    These tests are intentionally brittle — if a constant changes without
    updating the corresponding backtest analysis, they will fail.
    """

    def test_neutral_fraction_at_calibrated_value(self):
        """
        CONTINUITY_NEUTRAL_FRACTION should be 0.50 after Phase 9c recalibration.
        (Phase 9b set it to 0.45 using 2 valid pairs; Phase 9c re-expanded to 4 valid
        pairs by ingesting 2021+2022 historical gamelogs, and 0.50 minimizes combined
        bias across the 4-pair window — D_bias = +0.036, AvgRetFrac = 0.518 ≈ 0.50.)
        """
        from core.analytics.player_value.team_projection.constants import (
            CONTINUITY_NEUTRAL_FRACTION,
        )
        self.assertAlmostEqual(
            CONTINUITY_NEUTRAL_FRACTION, 0.50, places=4,
            msg=(
                "CONTINUITY_NEUTRAL_FRACTION changed from Phase 9c calibration result (0.50). "
                "If intentional, update this test and backtest_report.md with new evidence."
            ),
        )

    def test_max_adj_caps_unchanged_from_phase5(self):
        """
        MAX_CONTINUITY_ADJ_OFF and MAX_CONTINUITY_ADJ_DEF should remain at Phase 5
        calibration values (1.5 / 2.0).  Phase 9b found no backtest evidence to
        change the amplitude (the structural backtest limitation means cap calibration
        would require forward-looking roster data).
        """
        from core.analytics.player_value.team_projection.constants import (
            MAX_CONTINUITY_ADJ_OFF,
            MAX_CONTINUITY_ADJ_DEF,
        )
        self.assertAlmostEqual(MAX_CONTINUITY_ADJ_OFF, 1.5, places=4,
                               msg="MAX_CONTINUITY_ADJ_OFF changed without backtest evidence.")
        self.assertAlmostEqual(MAX_CONTINUITY_ADJ_DEF, 2.0, places=4,
                               msg="MAX_CONTINUITY_ADJ_DEF changed without backtest evidence.")


# ═══════════════════════════════════════════════════════════════════════════════
# TestFitUsedTracking — tests for fit_used flag on TeamPrediction (Phase 9c)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFitUsedTracking(unittest.TestCase):
    """
    DB-free tests verifying that fit_used is correctly set on TeamPrediction:
      - False for all non-E models (A, B, C, D, F)
      - False for Model E when _load_roster_fit returns None
      - True for Model E when _load_roster_fit returns a real RosterFitInput
    Also verifies that _run_engine no longer accepts use_fit and that the
    roster_fit parameter is passed through correctly.
    """

    def _make_players(self, team_slug: str = "duke"):
        from backtesting.roster_outlook.data_loader import PlayerRow
        return [
            PlayerRow(1, team_slug, 2.0, -1.0, 1.0, 30, 30, "returner", 2.0),
            PlayerRow(2, team_slug, 1.0, -0.5, 0.5, 20, 30, "returner", 1.5),
            PlayerRow(3, team_slug, 0.5, -0.2, 0.3, 10, 20, "newcomer", 0.5),
        ]

    def _make_pair(self, team_slug: str = "duke"):
        from backtesting.roster_outlook.data_loader import (
            BacktestPair, TeamPlayerPool, ActualOutcome,
        )
        players = self._make_players(team_slug)
        return BacktestPair(
            source_year=2023,
            target_year=2024,
            team_pools={team_slug: TeamPlayerPool(team_slug, 2023, players)},
            actual_outcomes={team_slug: ActualOutcome(team_slug, adj_o=115.0, adj_d=100.0, adj_em=15.0)},
            source_outcomes={team_slug: ActualOutcome(team_slug, adj_o=113.0, adj_d=101.0, adj_em=12.0)},
            d1_avg_o=105.0,
            d1_avg_d=105.0,
        )

    def test_fit_used_defaults_to_false(self):
        """TeamPrediction.fit_used should default to False."""
        from backtesting.roster_outlook.ablation import TeamPrediction
        pred = TeamPrediction("duke", "D", pred_adj_o=105.0, pred_adj_d=105.0, pred_adj_em=0.0)
        self.assertFalse(pred.fit_used)

    def test_model_e_fit_used_false_when_no_roster_fit(self):
        """Model E sets fit_used=False when _load_roster_fit returns None."""
        from backtesting.roster_outlook.ablation import run_all_models

        pair = self._make_pair()
        with patch("backtesting.roster_outlook.ablation._load_roster_fit", return_value=None):
            result = run_all_models(pair, models=["E"])

        pred_e = result.get("duke", "E")
        self.assertIsNotNone(pred_e)
        self.assertFalse(pred_e.fit_used)

    def test_model_e_fit_used_true_when_roster_fit_exists(self):
        """Model E sets fit_used=True when _load_roster_fit returns a RosterFitInput."""
        from backtesting.roster_outlook.ablation import run_all_models
        from core.analytics.player_value.team_projection.engine import RosterFitInput

        fake_fit = RosterFitInput(
            offensive_fit_score=52.0,
            defensive_fit_score=48.0,
            adjusted_off_fit=53.0,
            adjusted_def_fit=47.0,
            has_team_style_data=True,
        )
        pair = self._make_pair()
        with patch("backtesting.roster_outlook.ablation._load_roster_fit", return_value=fake_fit):
            result = run_all_models(pair, models=["E"])

        pred_e = result.get("duke", "E")
        self.assertIsNotNone(pred_e)
        self.assertTrue(pred_e.fit_used)

    def test_model_d_never_has_fit_used_true(self):
        """Model D always has fit_used=False — it calls _run_engine with roster_fit=None."""
        from backtesting.roster_outlook.ablation import run_all_models
        from core.analytics.player_value.team_projection.engine import RosterFitInput

        fake_fit = RosterFitInput(
            offensive_fit_score=60.0,
            defensive_fit_score=40.0,
            adjusted_off_fit=60.0,
            adjusted_def_fit=40.0,
            has_team_style_data=True,
        )
        pair = self._make_pair()
        # Even if _load_roster_fit returns something, Model D should not call it
        with patch("backtesting.roster_outlook.ablation._load_roster_fit", return_value=fake_fit):
            result = run_all_models(pair, models=["D"])

        pred_d = result.get("duke", "D")
        self.assertIsNotNone(pred_d)
        self.assertFalse(pred_d.fit_used)

    def test_model_e_with_fit_differs_from_d(self):
        """
        When fit actually adjusts the rating (non-50 adjusted_off/def_fit),
        Model E prediction must differ from Model D.
        """
        from backtesting.roster_outlook.ablation import run_all_models
        from core.analytics.player_value.team_projection.engine import RosterFitInput

        # Strong non-neutral fit scores → should produce a real adjustment
        strong_fit = RosterFitInput(
            offensive_fit_score=60.0,
            defensive_fit_score=60.0,
            adjusted_off_fit=60.0,
            adjusted_def_fit=60.0,
            has_team_style_data=True,
        )
        pair = self._make_pair()
        with patch("backtesting.roster_outlook.ablation._load_roster_fit", return_value=strong_fit):
            result = run_all_models(pair, models=["D", "E"])

        pred_d = result.get("duke", "D")
        pred_e = result.get("duke", "E")
        self.assertIsNotNone(pred_d)
        self.assertIsNotNone(pred_e)
        # When fit_adj is non-zero, E must not equal D
        self.assertNotAlmostEqual(pred_e.pred_adj_em, pred_d.pred_adj_em, places=4,
                                   msg="Model E should differ from D when TeamRosterFit provides signal")

    def test_model_e_without_fit_equals_d(self):
        """
        When no TeamRosterFit exists (_load_roster_fit=None), Model E ≡ D.
        This is the standard behaviour for backtest pairs where fit hasn't been backfilled.
        """
        from backtesting.roster_outlook.ablation import run_all_models

        pair = self._make_pair()
        with patch("backtesting.roster_outlook.ablation._load_roster_fit", return_value=None):
            result = run_all_models(pair, models=["D", "E"])

        pred_d = result.get("duke", "D")
        pred_e = result.get("duke", "E")
        self.assertIsNotNone(pred_d)
        self.assertIsNotNone(pred_e)
        self.assertAlmostEqual(pred_e.pred_adj_em, pred_d.pred_adj_em, places=6,
                               msg="Model E must equal D when no TeamRosterFit exists")

    def test_fit_used_in_csv_for_model_e(self):
        """fit_used column in CSV should be True/False for model E, None for others."""
        import csv
        import tempfile
        from backtesting.roster_outlook.ablation import AblationResult, TeamPrediction
        from backtesting.roster_outlook.data_loader import (
            BacktestPair, TeamPlayerPool, PlayerRow, ActualOutcome,
        )
        from backtesting.roster_outlook.report import generate_reports

        players = self._make_players()
        pair = BacktestPair(
            source_year=2023,
            target_year=2024,
            team_pools={"duke": TeamPlayerPool("duke", 2023, players)},
            actual_outcomes={"duke": ActualOutcome("duke", adj_o=115.0, adj_d=100.0, adj_em=15.0)},
            source_outcomes={"duke": ActualOutcome("duke", adj_o=113.0, adj_d=101.0, adj_em=12.0)},
            d1_avg_o=105.0, d1_avg_d=105.0,
        )
        ablation_result = AblationResult(
            source_year=2023, target_year=2024,
            predictions={
                "duke": {
                    "D": TeamPrediction("duke", "D", pred_adj_o=106.0, pred_adj_d=104.0,
                                       pred_adj_em=2.0, fit_used=False),
                    "E": TeamPrediction("duke", "E", pred_adj_o=107.0, pred_adj_d=104.0,
                                       pred_adj_em=3.0, fit_used=True),
                }
            },
            models=["D", "E"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_reports(
                [(ablation_result, pair)],
                output_dir=tmpdir,
                include_subgroups=False,
                model_order=["D", "E"],
            )
            with open(paths["csv"]) as fh:
                rows = {r["model"]: r for r in csv.DictReader(fh)}

        # Model D: fit_used should be empty string or '' (None → no value)
        self.assertIn("fit_used", rows["D"])
        d_val = rows["D"]["fit_used"]
        self.assertFalse(d_val and d_val.lower() not in ("none", ""),
                         msg=f"Model D fit_used should be empty/None, got {d_val!r}")

        # Model E with fit_used=True
        self.assertIn("fit_used", rows["E"])
        e_val = rows["E"]["fit_used"]
        self.assertEqual(e_val, "True", msg=f"Expected 'True' for E fit_used, got {e_val!r}")

    def test_fit_capable_window_in_json(self):
        """generate_reports includes fit_capable_window in JSON when fit_capable_source_years provided."""
        import json
        import tempfile
        from backtesting.roster_outlook.ablation import AblationResult, TeamPrediction
        from backtesting.roster_outlook.data_loader import (
            BacktestPair, TeamPlayerPool, PlayerRow, ActualOutcome,
        )
        from backtesting.roster_outlook.report import generate_reports

        players = self._make_players()
        pair = BacktestPair(
            source_year=2023, target_year=2024,
            team_pools={"duke": TeamPlayerPool("duke", 2023, players)},
            actual_outcomes={"duke": ActualOutcome("duke", adj_o=115.0, adj_d=100.0, adj_em=15.0)},
            source_outcomes={"duke": ActualOutcome("duke", adj_o=113.0, adj_d=101.0, adj_em=12.0)},
            d1_avg_o=105.0, d1_avg_d=105.0,
        )
        ablation_result = AblationResult(
            source_year=2023, target_year=2024,
            predictions={
                "duke": {
                    "D": TeamPrediction("duke", "D", pred_adj_o=106.0, pred_adj_d=104.0, pred_adj_em=2.0),
                    "E": TeamPrediction("duke", "E", pred_adj_o=107.0, pred_adj_d=104.0, pred_adj_em=3.0,
                                        fit_used=True),
                }
            },
            models=["D", "E"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_reports(
                [(ablation_result, pair)],
                output_dir=tmpdir,
                include_subgroups=False,
                model_order=["D", "E"],
                fit_capable_source_years={2023},
            )
            with open(paths["json"]) as fh:
                summary = json.load(fh)

        self.assertIn("fit_capable_source_years", summary)
        self.assertEqual(summary["fit_capable_source_years"], [2023])
        self.assertIn("fit_capable_window", summary)
        fc = summary["fit_capable_window"]
        self.assertIn("D", fc)
        self.assertIn("E", fc)
        self.assertEqual(fc["D"]["n"], 1)
        self.assertEqual(fc["E"]["n"], 1)

    def test_fit_capable_window_in_markdown(self):
        """Markdown report includes fit-capable window section when provided."""
        import tempfile
        from backtesting.roster_outlook.ablation import AblationResult, TeamPrediction
        from backtesting.roster_outlook.data_loader import (
            BacktestPair, TeamPlayerPool, PlayerRow, ActualOutcome,
        )
        from backtesting.roster_outlook.report import generate_reports

        players = self._make_players()
        pair = BacktestPair(
            source_year=2023, target_year=2024,
            team_pools={"duke": TeamPlayerPool("duke", 2023, players)},
            actual_outcomes={"duke": ActualOutcome("duke", adj_o=115.0, adj_d=100.0, adj_em=15.0)},
            source_outcomes={"duke": ActualOutcome("duke", adj_o=113.0, adj_d=101.0, adj_em=12.0)},
            d1_avg_o=105.0, d1_avg_d=105.0,
        )
        ablation_result = AblationResult(
            source_year=2023, target_year=2024,
            predictions={
                "duke": {
                    "D": TeamPrediction("duke", "D", pred_adj_o=106.0, pred_adj_d=104.0, pred_adj_em=2.0),
                    "E": TeamPrediction("duke", "E", pred_adj_o=107.0, pred_adj_d=104.0, pred_adj_em=3.0,
                                        fit_used=True),
                }
            },
            models=["D", "E"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_reports(
                [(ablation_result, pair)],
                output_dir=tmpdir,
                include_subgroups=False,
                model_order=["D", "E"],
                fit_capable_source_years={2023},
            )
            content = open(paths["markdown"]).read()

        self.assertIn("Fit-Capable Window", content)
        self.assertIn("2023", content)  # source year appears in the section

    def test_fit_capable_window_absent_when_not_provided(self):
        """Without fit_capable_source_years, the JSON has no fit_capable_source_years key."""
        import json
        import tempfile
        from backtesting.roster_outlook.ablation import AblationResult, TeamPrediction
        from backtesting.roster_outlook.data_loader import (
            BacktestPair, TeamPlayerPool, PlayerRow, ActualOutcome,
        )
        from backtesting.roster_outlook.report import generate_reports

        players = self._make_players()
        pair = BacktestPair(
            source_year=2023, target_year=2024,
            team_pools={"duke": TeamPlayerPool("duke", 2023, players)},
            actual_outcomes={"duke": ActualOutcome("duke", adj_o=115.0, adj_d=100.0, adj_em=15.0)},
            source_outcomes={"duke": ActualOutcome("duke", adj_o=113.0, adj_d=101.0, adj_em=12.0)},
            d1_avg_o=105.0, d1_avg_d=105.0,
        )
        ablation_result = AblationResult(
            source_year=2023, target_year=2024,
            predictions={
                "duke": {
                    "D": TeamPrediction("duke", "D", pred_adj_o=106.0, pred_adj_d=104.0, pred_adj_em=2.0),
                }
            },
            models=["D"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = generate_reports(
                [(ablation_result, pair)],
                output_dir=tmpdir,
                include_subgroups=False,
                model_order=["D"],
                # No fit_capable_source_years
            )
            with open(paths["json"]) as fh:
                summary = json.load(fh)

        self.assertNotIn("fit_capable_source_years", summary)
        self.assertNotIn("fit_capable_window", summary)


# ═══════════════════════════════════════════════════════════════════════════════
# TestBackfillRosterFitCommand — DB integration tests for backfill command
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from django.test import TestCase as DjTestCase

    class TestBackfillRosterFitHelpers(DjTestCase):
        """
        Integration test: bpr_capable_seasons() detects seasons from real DB.
        Does NOT run the full backfill pipeline (that is tested via manual runs).
        """

        def test_bpr_capable_seasons_returns_sorted_list(self):
            """bpr_capable_seasons() should return a sorted list of ints."""
            from core.management.commands.backfill_roster_fit import bpr_capable_seasons
            result = bpr_capable_seasons()
            self.assertIsInstance(result, list)
            self.assertEqual(result, sorted(result))

        def test_bpr_capable_seasons_not_empty(self):
            """At least one BPR-capable season should be found if PlayerGameStints exist in DB."""
            from core.models import PlayerGameStint
            if not PlayerGameStint.objects.exists():
                self.skipTest(
                    "No PlayerGameStint rows in test DB — skipping. "
                    "Populate the live DB and run with --keepdb against real data."
                )
            from core.management.commands.backfill_roster_fit import bpr_capable_seasons
            result = bpr_capable_seasons()
            self.assertGreater(len(result), 0,
                               msg="No PlayerGameStint rows found; BPR-capable detection broken")

        def test_bpr_capable_seasons_all_have_stints(self):
            """Every year returned by bpr_capable_seasons() must have PlayerGameStint rows."""
            from core.management.commands.backfill_roster_fit import bpr_capable_seasons
            from core.models import PlayerGameStint
            for yr in bpr_capable_seasons():
                count = PlayerGameStint.objects.filter(game__season_year=yr).count()
                self.assertGreater(count, 0,
                                   msg=f"Season {yr} returned by bpr_capable_seasons() but has no stints")

        def test_team_roster_fit_exists_for_backfilled_seasons(self):
            """
            After running backfill_roster_fit --seasons 2023 2024 2025, each season
            should have TeamRosterFit rows with non-null adjusted_off_fit (Phase 4 ran).
            """
            from core.models import TeamRosterFit
            for yr in [2023, 2024, 2025]:
                n_total = TeamRosterFit.objects.filter(from_season__year=yr).count()
                if n_total == 0:
                    self.skipTest(
                        f"TeamRosterFit not yet backfilled for {yr}. "
                        f"Run: python manage.py backfill_roster_fit --seasons {yr}"
                    )
                n_phase4 = TeamRosterFit.objects.filter(
                    from_season__year=yr,
                    adjusted_off_fit__isnull=False,
                ).count()
                self.assertGreater(n_phase4, 0,
                                   msg=f"Season {yr}: TeamRosterFit exists but adjusted_off_fit=null "
                                       f"(Phase 4 didn't run or failed)")

        def test_backfill_command_dry_run_succeeds(self):
            """Dry run should succeed without writing any data."""
            from io import StringIO
            from django.core.management import call_command
            out = StringIO()
            call_command(
                "backfill_roster_fit",
                "--dry-run",
                stdout=out,
            )
            output = out.getvalue()
            self.assertIn("DRY RUN", output)
            self.assertIn("BPR-capable seasons", output)

        def test_backfill_command_rejects_non_bpr_capable_season(self):
            """Requesting a non-BPR-capable season should raise CommandError."""
            from io import StringIO
            from django.core.management import call_command
            from django.core.management.base import CommandError
            from core.management.commands.backfill_roster_fit import bpr_capable_seasons
            # 2021 and 2022 have no PlayerGameStint → not BPR capable
            capable = set(bpr_capable_seasons())
            non_capable = [yr for yr in [2021, 2022] if yr not in capable]
            if not non_capable:
                self.skipTest("No known non-BPR-capable test seasons available in DB")
            with self.assertRaises(CommandError):
                call_command(
                    "backfill_roster_fit",
                    "--seasons", str(non_capable[0]),
                    stdout=StringIO(),
                )

except ImportError:
    pass  # Django not configured in this test run


if __name__ == "__main__":
    unittest.main()
