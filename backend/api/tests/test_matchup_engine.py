"""
Unit tests for Matchup Prediction Engine

Tests all mathematical functions, HCA adjustments, site toggles, and edge cases.
"""

from django.test import TestCase
from api.matchup_engine import (
    compute_pace,
    compute_expected_efficiency,
    apply_hca_adjustment,
    compute_win_probability,
    compute_win_probability_with_confidence,
    forecast_game,
    compute_matchup_four_factors,
    compute_points_from_four_factors,
    identify_top_drivers,
    compute_shot_profile_edges,
    compute_volatility_score,
)
import math


class ComputePaceTestCase(TestCase):
    """Tests for compute_pace function (harmonic mean)"""
    
    def test_compute_pace_normal(self):
        """Test pace calculation with normal values"""
        # (2 * 70 * 72) / (70 + 72) = 10080 / 142 = 71.0
        pace = compute_pace(70.0, 72.0)
        self.assertAlmostEqual(pace, 71.0, places=1)
    
    def test_compute_pace_equal_tempos(self):
        """Test pace when both teams have same tempo"""
        pace = compute_pace(68.5, 68.5)
        self.assertAlmostEqual(pace, 68.5, places=1)
    
    def test_compute_pace_fast_vs_slow(self):
        """Test pace with contrasting tempos"""
        # Fast vs slow should be closer to geometric mean
        pace = compute_pace(75.0, 65.0)
        self.assertTrue(65.0 < pace < 75.0)
        # Harmonic mean: (2 * 75 * 65) / 140 = 9750 / 140 = 69.64
        self.assertAlmostEqual(pace, 69.64, places=1)
    
    def test_compute_pace_zero_tempo(self):
        """Test pace with zero tempo (edge case)"""
        pace = compute_pace(70.0, 0.0)
        self.assertEqual(pace, 70.0)  # Should default to 70.0
        
        pace = compute_pace(0.0, 72.0)
        self.assertEqual(pace, 70.0)
    
    def test_compute_pace_negative_tempo(self):
        """Test pace with negative tempo (invalid data)"""
        pace = compute_pace(-5.0, 70.0)
        self.assertEqual(pace, 70.0)  # Should default


class ComputeEfficiencyTestCase(TestCase):
    """Tests for compute_expected_efficiency function"""
    
    def test_compute_efficiency_normal(self):
        """Test efficiency calculation with normal values"""
        # (115 * 95) / 108 = 10925 / 108 = 101.2
        eff = compute_expected_efficiency(115.0, 95.0, 108.0)
        self.assertAlmostEqual(eff, 101.2, places=1)
    
    def test_compute_efficiency_elite_offense_weak_defense(self):
        """Test elite offense vs weak defense"""
        # (120 * 105) / 108 = 12600 / 108 = 116.7
        eff = compute_expected_efficiency(120.0, 105.0, 108.0)
        self.assertAlmostEqual(eff, 116.7, places=1)
        self.assertTrue(eff > 115.0)  # Should be high
    
    def test_compute_efficiency_weak_offense_elite_defense(self):
        """Test weak offense vs elite defense"""
        # (100 * 92) / 108 = 9200 / 108 = 85.2
        eff = compute_expected_efficiency(100.0, 92.0, 108.0)
        self.assertAlmostEqual(eff, 85.2, places=1)
        self.assertTrue(eff < 95.0)  # Should be low
    
    def test_compute_efficiency_zero_national_avg(self):
        """Test efficiency with zero national average (edge case)"""
        eff = compute_expected_efficiency(110.0, 100.0, 0.0)
        # Should use fallback of 108.0
        expected = (110.0 * 100.0) / 108.0
        self.assertAlmostEqual(eff, expected, places=1)


class ApplyHCATestCase(TestCase):
    """Tests for apply_hca_adjustment function"""
    
    def test_hca_neutral_site(self):
        """Test HCA on neutral site (no adjustment)"""
        pts_a, pts_b = apply_hca_adjustment(75.0, 70.0, 'neutral', 3.5)
        self.assertEqual(pts_a, 75.0)
        self.assertEqual(pts_b, 70.0)
    
    def test_hca_team_a_home(self):
        """Test HCA when Team A is home"""
        # HCA = 3.5, so +1.75 to A, -1.75 to B
        pts_a, pts_b = apply_hca_adjustment(75.0, 70.0, 'home', 3.5)
        self.assertAlmostEqual(pts_a, 76.75, places=2)
        self.assertAlmostEqual(pts_b, 68.25, places=2)
    
    def test_hca_team_b_home(self):
        """Test HCA when Team B is home (Team A away)"""
        # HCA = 3.5, so -1.75 to A, +1.75 to B
        pts_a, pts_b = apply_hca_adjustment(75.0, 70.0, 'away', 3.5)
        self.assertAlmostEqual(pts_a, 73.25, places=2)
        self.assertAlmostEqual(pts_b, 71.75, places=2)
    
    def test_hca_symmetric(self):
        """Test HCA is symmetric (home + away = 2 * neutral)"""
        neutral_a, neutral_b = apply_hca_adjustment(80.0, 75.0, 'neutral', 4.0)
        home_a, home_b = apply_hca_adjustment(80.0, 75.0, 'home', 4.0)
        away_a, away_b = apply_hca_adjustment(80.0, 75.0, 'away', 4.0)
        
        # Check symmetry
        self.assertAlmostEqual(home_a - neutral_a, neutral_a - away_a, places=2)
        self.assertAlmostEqual(home_b - neutral_b, neutral_b - away_b, places=2)
    
    def test_hca_large_value(self):
        """Test HCA with large value"""
        pts_a, pts_b = apply_hca_adjustment(85.0, 80.0, 'home', 6.0)
        self.assertAlmostEqual(pts_a, 88.0, places=2)  # +3.0
        self.assertAlmostEqual(pts_b, 77.0, places=2)  # -3.0


class ComputeWinProbabilityTestCase(TestCase):
    """Tests for compute_win_probability function"""
    
    def test_win_probability_even_game(self):
        """Test win probability when teams are even"""
        prob_a, prob_b = compute_win_probability(0.0, 11.0)
        self.assertAlmostEqual(prob_a, 0.5, places=2)
        self.assertAlmostEqual(prob_b, 0.5, places=2)
    
    def test_win_probability_favored_by_one_sigma(self):
        """Test win probability when favored by 1 standard deviation"""
        prob_a, prob_b = compute_win_probability(11.0, 11.0)
        # P(Z < 1) ≈ 0.841
        self.assertAlmostEqual(prob_a, 0.841, places=2)
        self.assertAlmostEqual(prob_b, 0.159, places=2)
    
    def test_win_probability_favored_by_two_sigma(self):
        """Test win probability when favored by 2 standard deviations"""
        prob_a, prob_b = compute_win_probability(22.0, 11.0)
        # P(Z < 2) ≈ 0.977
        self.assertAlmostEqual(prob_a, 0.977, places=2)
        self.assertAlmostEqual(prob_b, 0.023, places=2)
    
    def test_win_probability_underdog(self):
        """Test win probability as underdog"""
        prob_a, prob_b = compute_win_probability(-8.5, 11.0)
        # Negative margin means Team A is underdog
        self.assertTrue(prob_a < 0.5)
        self.assertTrue(prob_b > 0.5)
        self.assertAlmostEqual(prob_a + prob_b, 1.0, places=5)
    
    def test_win_probability_sum_to_one(self):
        """Test probabilities always sum to 1.0"""
        for margin in [-20, -10, -5, 0, 5, 10, 20]:
            prob_a, prob_b = compute_win_probability(float(margin), 11.0)
            self.assertAlmostEqual(prob_a + prob_b, 1.0, places=10)


class ComputeWinProbabilityWithConfidenceTestCase(TestCase):
    """Tests for compute_win_probability_with_confidence function"""
    
    def test_confidence_interval_contains_margin(self):
        """Test 95% CI contains expected margin"""
        result = compute_win_probability_with_confidence(10.0, 11.0)
        self.assertTrue(result['ci_low'] < 10.0 < result['ci_high'])
    
    def test_confidence_interval_width(self):
        """Test 95% CI is approximately 4 sigma wide"""
        result = compute_win_probability_with_confidence(5.0, 11.0)
        width = result['ci_high'] - result['ci_low']
        # 95% CI ≈ ±1.96σ = 3.92σ total width
        expected_width = 3.92 * 11.0
        self.assertAlmostEqual(width, expected_width, places=0)
    
    def test_confidence_interval_symmetric_for_even_game(self):
        """Test CI is symmetric around 0 for even game"""
        result = compute_win_probability_with_confidence(0.0, 11.0)
        self.assertAlmostEqual(result['ci_low'], -result['ci_high'], places=2)


class ComputeFourFactorsTestCase(TestCase):
    """Tests for compute_matchup_four_factors function"""
    
    def test_four_factors_normal(self):
        """Test four factors with normal values"""
        result = compute_matchup_four_factors(
            efg_a=53.0, tov_a=16.5, orb_a=28.0, ftr_a=32.0,
            efg_b=51.0, tov_b=18.0, orb_b=30.0, ftr_b=35.0
        )
        
        self.assertAlmostEqual(result['efg_edge'], 2.0, places=1)
        self.assertAlmostEqual(result['tov_edge'], -1.5, places=1)  # Lower is better
        self.assertAlmostEqual(result['reb_edge'], -2.0, places=1)
        self.assertAlmostEqual(result['ftr_edge'], -3.0, places=1)
    
    def test_four_factors_edges_are_differences(self):
        """Test edges are simple differences"""
        result = compute_matchup_four_factors(
            efg_a=55.0, tov_a=15.0, orb_a=32.0, ftr_a=40.0,
            efg_b=50.0, tov_b=20.0, orb_b=25.0, ftr_b=30.0
        )
        
        # Positive edge = Team A advantage
        self.assertGreater(result['efg_edge'], 0)
        self.assertGreater(result['tov_edge'], 0)  # Lower TOV% is better
        self.assertGreater(result['reb_edge'], 0)
        self.assertGreater(result['ftr_edge'], 0)


class ComputePointsFromFourFactorsTestCase(TestCase):
    """Tests for compute_points_from_four_factors function"""
    
    def test_points_breakdown_with_regression(self):
        """Test points breakdown using regression coefficients"""
        ff_edges = {
            'efg_edge': 5.0,
            'tov_edge': 3.0,
            'reb_edge': 4.0,
            'ftr_edge': 2.0,
        }
        
        result = compute_points_from_four_factors(
            ff_edges,
            game_pace=70.0,
            coef_efg=0.995,
            coef_tov=0.912,
            coef_orb=0.464,
            coef_ftr=0.084,
            coef_intercept=0.0,
            nat_avg_ortg=108.0
        )
        
        # Each factor should have points_a, points_b, edge
        self.assertIn('efg', result)
        self.assertIn('tov', result)
        self.assertIn('reb', result)
        self.assertIn('ftr', result)
        
        # eFG should have largest coefficient
        efg_impact = abs(result['efg']['edge'])
        tov_impact = abs(result['tov']['edge'])
        self.assertGreater(efg_impact, tov_impact * 0.8)  # eFG should dominate
    
    def test_points_breakdown_sum_meaningful(self):
        """Test points breakdown sums are reasonable"""
        ff_edges = {
            'efg_edge': 4.0,
            'tov_edge': 2.0,
            'reb_edge': 3.0,
            'ftr_edge': 1.0,
        }
        
        result = compute_points_from_four_factors(
            ff_edges,
            game_pace=70.0,
            coef_efg=0.995,
            coef_tov=0.912,
            coef_orb=0.464,
            coef_ftr=0.084,
            coef_intercept=0.0,
            nat_avg_ortg=108.0
        )
        
        # Total edge should be sum of individual edges
        total_edge = (result['efg']['edge'] + result['tov']['edge'] + 
                     result['reb']['edge'] + result['ftr']['edge'])
        
        # Should be non-zero if there are edges
        self.assertNotEqual(total_edge, 0.0)


class IdentifyTopDriversTestCase(TestCase):
    """Tests for identify_top_drivers function"""
    
    def test_top_drivers_sorted_by_impact(self):
        """Test top drivers are sorted by absolute impact"""
        points_breakdown = {
            'efg': {'edge': 5.2, 'points_a': 78.0, 'points_b': 72.8},
            'tov': {'edge': -2.1, 'points_a': 75.0, 'points_b': 77.1},
            'reb': {'edge': 1.5, 'points_a': 76.5, 'points_b': 75.0},
            'ftr': {'edge': 0.8, 'points_a': 75.8, 'points_b': 75.0},
        }
        
        drivers = identify_top_drivers(points_breakdown, 'Duke', 'UNC')
        
        # Should return top 3
        self.assertEqual(len(drivers), 3)
        
        # First driver should be eFG (largest impact)
        self.assertEqual(drivers[0]['factor'], 'Effective FG%')
        self.assertAlmostEqual(drivers[0]['impact'], 5.2, places=1)
        
        # Should be sorted by |impact|
        impacts = [abs(d['impact']) for d in drivers]
        self.assertEqual(impacts, sorted(impacts, reverse=True))


class ComputeShotProfileTestCase(TestCase):
    """Tests for compute_shot_profile_edges function"""
    
    def test_shot_profile_normal(self):
        """Test shot profile with normal values"""
        result = compute_shot_profile_edges(
            fg3_rate_a=40.0, fg3_pct_a=36.5, fg2_pct_a=52.0,
            fg3_rate_b=35.0, fg3_pct_b=34.0, fg2_pct_b=50.0
        )
        
        self.assertAlmostEqual(result['fg3_rate_edge'], 5.0, places=1)
        self.assertAlmostEqual(result['fg3_pct_edge'], 2.5, places=1)
        self.assertAlmostEqual(result['fg2_pct_edge'], 2.0, places=1)
        
        # Individual values should be preserved
        self.assertAlmostEqual(result['fg3_rate_a'], 40.0, places=1)
        self.assertAlmostEqual(result['fg3_rate_b'], 35.0, places=1)
    
    def test_shot_profile_three_point_team_vs_two_point_team(self):
        """Test contrasting shot profiles"""
        result = compute_shot_profile_edges(
            fg3_rate_a=50.0, fg3_pct_a=38.0, fg2_pct_a=48.0,  # 3P team
            fg3_rate_b=30.0, fg3_pct_b=32.0, fg2_pct_b=55.0   # 2P team
        )
        
        self.assertGreater(result['fg3_rate_edge'], 15.0)  # Large difference
        self.assertGreater(result['fg2_pct_edge'], -10.0)  # 2P team better inside


class ComputeVolatilityTestCase(TestCase):
    """Tests for compute_volatility_score function"""
    
    def test_volatility_low(self):
        """Test low volatility game (slow, few 3s, consistent)"""
        result = compute_volatility_score(
            tempo_a=65.0, tempo_b=66.0,
            fg3_rate_a=30.0, fg3_rate_b=32.0,
            recent_variance_a=6.0, recent_variance_b=7.0
        )
        
        self.assertLess(result['score'], 40.0)  # Should be low
        self.assertIn('reasons', result)
    
    def test_volatility_high(self):
        """Test high volatility game (fast, lots of 3s, inconsistent)"""
        result = compute_volatility_score(
            tempo_a=74.0, tempo_b=75.0,
            fg3_rate_a=48.0, fg3_rate_b=50.0,
            recent_variance_a=16.0, recent_variance_b=18.0
        )
        
        self.assertGreater(result['score'], 65.0)  # Should be high
        self.assertGreater(result['pace_score'], 70.0)
        self.assertGreater(result['three_pt_score'], 70.0)
        self.assertGreater(result['variance_score'], 60.0)
    
    def test_volatility_components_weighted(self):
        """Test volatility components are weighted (30/40/30)"""
        result = compute_volatility_score(
            tempo_a=70.0, tempo_b=70.0,
            fg3_rate_a=40.0, fg3_rate_b=40.0,
            recent_variance_a=12.0, recent_variance_b=12.0
        )
        
        # Score should be weighted average
        weighted = (0.30 * result['pace_score'] + 
                   0.40 * result['three_pt_score'] + 
                   0.30 * result['variance_score'])
        
        self.assertAlmostEqual(result['score'], weighted, places=1)
    
    def test_volatility_no_variance_data(self):
        """Test volatility when recent variance not provided"""
        result = compute_volatility_score(
            tempo_a=70.0, tempo_b=70.0,
            fg3_rate_a=40.0, fg3_rate_b=40.0,
            recent_variance_a=None, recent_variance_b=None
        )
        
        # Should use default variance score of 50
        self.assertEqual(result['variance_score'], 50.0)
    
    def test_volatility_reasons_generated(self):
        """Test volatility generates contextual reasons"""
        result = compute_volatility_score(
            tempo_a=74.5, tempo_b=75.0,  # Very fast
            fg3_rate_a=30.0, fg3_rate_b=31.0,  # Low 3P
            recent_variance_a=8.0, recent_variance_b=7.5
        )
        
        self.assertIsInstance(result['reasons'], list)
        # Should mention fast pace
        reasons_text = ' '.join(result['reasons']).lower()
        self.assertIn('pace', reasons_text)
    
    def test_volatility_pace_contrast(self):
        """Test volatility identifies pace mismatch"""
        result = compute_volatility_score(
            tempo_a=75.0, tempo_b=65.0,  # 10 possession gap
            fg3_rate_a=40.0, fg3_rate_b=40.0,
            recent_variance_a=10.0, recent_variance_b=10.0
        )
        
        reasons_text = ' '.join(result['reasons']).lower()
        self.assertIn('pace', reasons_text)
        self.assertIn('mismatch', reasons_text)


class ForecastGameIntegrationTestCase(TestCase):
    """Integration tests for forecast_game function"""
    
    def test_forecast_game_complete(self):
        """Test complete game forecast"""
        result = forecast_game(
            adj_o_a=115.0, adj_d_a=95.0, adj_tempo_a=70.0,
            adj_o_b=110.0, adj_d_b=98.0, adj_tempo_b=72.0,
            site='neutral',
            nat_avg_ortg=108.0,
            hca_points=1.85,
            sigma=11.08
        )
        
        # Should return all required fields
        self.assertIn('predicted_score_a', result)
        self.assertIn('predicted_score_b', result)
        self.assertIn('predicted_margin', result)
        self.assertIn('win_probability_a', result)
        self.assertIn('win_probability_b', result)
        self.assertIn('confidence_interval_low', result)
        self.assertIn('confidence_interval_high', result)
        self.assertIn('game_pace', result)
        
        # Scores should be reasonable (60-90 range)
        self.assertTrue(60 < result['predicted_score_a'] < 90)
        self.assertTrue(60 < result['predicted_score_b'] < 90)
        
        # Probabilities sum to 1
        self.assertAlmostEqual(
            result['win_probability_a'] + result['win_probability_b'],
            1.0, places=5
        )
    
    def test_forecast_game_home_site(self):
        """Test forecast with home site advantage"""
        neutral = forecast_game(
            adj_o_a=115.0, adj_d_a=95.0, adj_tempo_a=70.0,
            adj_o_b=110.0, adj_d_b=98.0, adj_tempo_b=72.0,
            site='neutral',
            nat_avg_ortg=108.0,
            hca_points=3.0,
            sigma=11.08
        )
        
        home = forecast_game(
            adj_o_a=115.0, adj_d_a=95.0, adj_tempo_a=70.0,
            adj_o_b=110.0, adj_d_b=98.0, adj_tempo_b=72.0,
            site='home',
            nat_avg_ortg=108.0,
            hca_points=3.0,
            sigma=11.08
        )
        
        # Home team should score more
        self.assertGreater(home['predicted_score_a'], neutral['predicted_score_a'])
        self.assertLess(home['predicted_score_b'], neutral['predicted_score_b'])
        
        # Margin should increase by HCA
        margin_diff = home['predicted_margin'] - neutral['predicted_margin']
        self.assertAlmostEqual(margin_diff, 3.0, places=1)
    
    def test_forecast_game_away_site(self):
        """Test forecast with away site (Team B home)"""
        neutral = forecast_game(
            adj_o_a=115.0, adj_d_a=95.0, adj_tempo_a=70.0,
            adj_o_b=110.0, adj_d_b=98.0, adj_tempo_b=72.0,
            site='neutral',
            nat_avg_ortg=108.0,
            hca_points=3.0,
            sigma=11.08
        )
        
        away = forecast_game(
            adj_o_a=115.0, adj_d_a=95.0, adj_tempo_a=70.0,
            adj_o_b=110.0, adj_d_b=98.0, adj_tempo_b=72.0,
            site='away',
            nat_avg_ortg=108.0,
            hca_points=3.0,
            sigma=11.08
        )
        
        # Away team (A) should score less, home team (B) more
        self.assertLess(away['predicted_score_a'], neutral['predicted_score_a'])
        self.assertGreater(away['predicted_score_b'], neutral['predicted_score_b'])
    
    def test_forecast_game_site_symmetry(self):
        """Test that home/away/neutral sites are mathematically consistent"""
        neutral_margin = forecast_game(
            adj_o_a=115.0, adj_d_a=95.0, adj_tempo_a=70.0,
            adj_o_b=110.0, adj_d_b=98.0, adj_tempo_b=72.0,
            site='neutral',
            nat_avg_ortg=108.0,
            hca_points=4.0,
            sigma=11.08
        )['predicted_margin']
        
        home_margin = forecast_game(
            adj_o_a=115.0, adj_d_a=95.0, adj_tempo_a=70.0,
            adj_o_b=110.0, adj_d_b=98.0, adj_tempo_b=72.0,
            site='home',
            nat_avg_ortg=108.0,
            hca_points=4.0,
            sigma=11.08
        )['predicted_margin']
        
        away_margin = forecast_game(
            adj_o_a=115.0, adj_d_a=95.0, adj_tempo_a=70.0,
            adj_o_b=110.0, adj_d_b=98.0, adj_tempo_b=72.0,
            site='away',
            nat_avg_ortg=108.0,
            hca_points=4.0,
            sigma=11.08
        )['predicted_margin']
        
        # Verify symmetry: home - neutral = neutral - away = HCA
        self.assertAlmostEqual(home_margin - neutral_margin, 4.0, places=1)
        self.assertAlmostEqual(neutral_margin - away_margin, 4.0, places=1)


class EdgeCaseTestCase(TestCase):
    """Tests for edge cases and error handling"""
    
    def test_extreme_efficiency_values(self):
        """Test with extreme but valid efficiency values"""
        result = forecast_game(
            adj_o_a=130.0, adj_d_a=85.0, adj_tempo_a=75.0,  # Elite team
            adj_o_b=95.0, adj_d_b=115.0, adj_tempo_b=65.0,   # Weak team
            site='neutral',
            nat_avg_ortg=108.0,
            hca_points=1.85,
            sigma=11.08
        )
        
        # Elite team should dominate
        self.assertGreater(result['predicted_margin'], 20.0)
        self.assertGreater(result['win_probability_a'], 0.9)
    
    def test_very_slow_pace(self):
        """Test with very slow pace"""
        result = forecast_game(
            adj_o_a=110.0, adj_d_a=98.0, adj_tempo_a=60.0,
            adj_o_b=108.0, adj_d_b=100.0, adj_tempo_b=62.0,
            site='neutral',
            nat_avg_ortg=108.0,
            hca_points=1.85,
            sigma=11.08
        )
        
        # Pace should be slow
        self.assertLess(result['game_pace'], 65.0)
        # Scores should be lower due to fewer possessions
        self.assertLess(result['predicted_score_a'], 70.0)
    
    def test_very_fast_pace(self):
        """Test with very fast pace"""
        result = forecast_game(
            adj_o_a=115.0, adj_d_a=95.0, adj_tempo_a=78.0,
            adj_o_b=113.0, adj_d_b=97.0, adj_tempo_b=76.0,
            site='neutral',
            nat_avg_ortg=108.0,
            hca_points=1.85,
            sigma=11.08
        )
        
        # Pace should be fast
        self.assertGreater(result['game_pace'], 75.0)
        # Scores should be higher due to more possessions
        self.assertGreater(result['predicted_score_a'], 75.0)
