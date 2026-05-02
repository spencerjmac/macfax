"""
BT-6 pure-Python tests — no Django, no DB.

Tests validate the _compute_sigma_recommendation() logic and that compute_coverage()
from metrics.py produces expected output from synthetic data.
"""

import unittest

from backtesting.roster_outlook.bt6_coverage_calibration import _compute_sigma_recommendation
from backtesting.roster_outlook.metrics import compute_coverage
from ncaa.analytics.player_value.team_projection.constants import (
    UNCERTAINTY_SIGMA_SCALE,
    UNCERTAINTY_SIGMA_MAX,
)


class TestComputeSigmaRecommendation(unittest.TestCase):

    def test_coverage_too_low_recommends_increase(self):
        rec_scale, rec_max, recommendation = _compute_sigma_recommendation(0.45)
        self.assertEqual(recommendation, "increase")
        self.assertGreater(rec_scale, UNCERTAINTY_SIGMA_SCALE)

    def test_coverage_too_high_recommends_decrease(self):
        rec_scale, rec_max, recommendation = _compute_sigma_recommendation(0.85)
        self.assertEqual(recommendation, "decrease")
        self.assertLess(rec_scale, UNCERTAINTY_SIGMA_SCALE)

    def test_coverage_in_target_range_no_change(self):
        rec_scale, rec_max, recommendation = _compute_sigma_recommendation(0.68)
        self.assertEqual(recommendation, "no_change")
        self.assertAlmostEqual(rec_scale, UNCERTAINTY_SIGMA_SCALE)

    def test_recommended_scale_never_below_floor(self):
        # Very high coverage → wants to decrease a lot
        rec_scale, _, _ = _compute_sigma_recommendation(0.95)
        self.assertGreaterEqual(rec_scale, 1.5)

    def test_recommended_scale_never_exceeds_max(self):
        # Very low coverage → wants to increase a lot
        rec_scale, rec_max, _ = _compute_sigma_recommendation(0.10)
        self.assertLess(rec_scale, rec_max)

    def test_boundary_at_target_low(self):
        # Exactly at lower boundary (0.55) → recommend increase
        _, _, recommendation = _compute_sigma_recommendation(0.549)
        self.assertEqual(recommendation, "increase")

    def test_boundary_at_target_high(self):
        # Exactly at upper boundary (0.80) → no change (at boundary)
        _, _, recommendation = _compute_sigma_recommendation(0.80)
        self.assertEqual(recommendation, "no_change")


class TestComputeCoverageFromMetrics(unittest.TestCase):

    def test_50_pct_coverage(self):
        pred_low  = [-5.0, -5.0, -5.0, -5.0]
        pred_high = [ 5.0,  5.0,  5.0,  5.0]
        actuals   = [ 0.0,  3.0,  6.0, -6.0]   # 2/4 inside → 50% coverage
        result = compute_coverage(pred_low, pred_high, actuals)
        self.assertAlmostEqual(result.coverage_rate, 0.50, places=2)

    def test_100_pct_coverage(self):
        pred_low  = [-10.0, -10.0]
        pred_high = [ 10.0,  10.0]
        actuals   = [  2.0,  -3.0]
        result = compute_coverage(pred_low, pred_high, actuals)
        self.assertAlmostEqual(result.coverage_rate, 1.0, places=6)

    def test_band_width_computed(self):
        pred_low  = [0.0, 0.0]
        pred_high = [8.0, 10.0]
        actuals   = [4.0,  5.0]
        result = compute_coverage(pred_low, pred_high, actuals)
        self.assertAlmostEqual(result.mean_band_width, 9.0, places=5)


if __name__ == "__main__":
    unittest.main()
