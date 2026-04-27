"""
Phase 5 Testing - Comprehensive Matchup Engine Tests

Tests focus on:
1. Math function correctness (unit tests)  
2. Site toggle validation (home/away/neutral)
3. Edge cases (missing data, limited games)
"""

from django.test import TestCase, Client
from django.urls import reverse
from ncaa.models import (
    Season, Conference, Team, TeamSeasonRatings, 
    TeamSeasonStats, NationalAverages, TeamGameStats, Game
)
from api.matchup_engine import (
    compute_pace,
    compute_expected_efficiency,
    apply_hca_adjustment,
    compute_win_probability,
    compute_shot_profile_edges,
    compute_volatility_score,
    forecast_game,
)
from decimal import Decimal
from datetime import date, datetime
import json


# =============================================================================
# UNIT TESTS: Math Functions
# =============================================================================

class MathFunctionsTestCase(TestCase):
    """Unit tests for core mathematical functions"""
    
    def test_compute_pace_harmonic_mean(self):
        """Test pace uses harmonic mean correctly"""
        # (2 * 70 * 72) / (70 + 72) = 71.01
        pace = compute_pace(70.0, 72.0)
        self.assertAlmostEqual(pace, 71.0, places=1)
        
        # Equal tempos
        pace = compute_pace(68.5, 68.5)
        self.assertEqual(pace, 68.5)
        
        # Edge case: zero tempo defaults to 70
        pace = compute_pace(0.0, 75.0)
        self.assertEqual(pace, 70.0)
    
    def test_compute_efficiency_multiplicative(self):
        """Test efficiency uses multiplicative formula"""
        # (115 * 95) / 108 = 101.2
        eff = compute_expected_efficiency(115.0, 95.0, 108.0)
        self.assertAlmostEqual(eff, 101.2, places=1)
        
        # Elite offense vs weak defense
        eff = compute_expected_efficiency(120.0, 105.0, 108.0)
        self.assertTrue(eff > 115.0)
        
        # Weak offense vs elite defense
        eff = compute_expected_efficiency(100.0, 92.0, 108.0)
        self.assertTrue(eff < 95.0)
    
    def test_hca_adjustments(self):
        """Test home court advantage adjustments"""
        hca = 3.5
        
        # Neutral: no change
        a, b = apply_hca_adjustment(75.0, 70.0, 'neutral', hca)
        self.assertEqual(a, 75.0)
        self.assertEqual(b, 70.0)
        
        # Home: Team A gets +HCA/2, Team B gets -HCA/2
        a, b = apply_hca_adjustment(75.0, 70.0, 'home', hca)
        self.assertAlmostEqual(a, 75.0 + hca/2, places=2)
        self.assertAlmostEqual(b, 70.0 - hca/2, places=2)
        
        # Away: Team B gets +HCA/2, Team A gets -HCA/2
        a, b = apply_hca_adjustment(75.0, 70.0, 'away', hca)
        self.assertAlmostEqual(a, 75.0 - hca/2, places=2)
        self.assertAlmostEqual(b, 70.0 + hca/2, places=2)
    
    def test_win_probability_bounds(self):
        """Test win probabilities are valid"""
        # Even game
        prob_a, prob_b = compute_win_probability(0.0, 11.0)
        self.assertAlmostEqual(prob_a, 0.5, places=2)
        self.assertAlmostEqual(prob_b, 0.5, places=2)
        
        # Favored team
        prob_a, prob_b = compute_win_probability(11.0, 11.0)
        self.assertTrue(prob_a > 0.80)
        self.assertTrue(prob_b < 0.20)
        
        # Probabilities sum to 1
        self.assertAlmostEqual(prob_a + prob_b, 1.0, places=6)
    
    def test_shot_profile_edges(self):
        """Test shot profile calculations"""
        result = compute_shot_profile_edges(
            fg3_rate_a=42.0, fg3_pct_a=36.5, fg2_pct_a=52.0,
            fg3_rate_b=35.0, fg3_pct_b=33.0, fg2_pct_b=50.0
        )
        
        self.assertAlmostEqual(result['fg3_rate_edge'], 7.0, places=1)
        self.assertAlmostEqual(result['fg3_pct_edge'], 3.5, places=1)
        self.assertAlmostEqual(result['fg2_pct_edge'], 2.0, places=1)
    
    def test_volatility_score_range(self):
        """Test volatility score is 0-100"""
        # Low volatility: FAST (talent prevails), few 3s, consistent
        result = compute_volatility_score(
            tempo_a=74.0, tempo_b=75.0,  # Fast pace (low volatility with new logic)
            fg3_rate_a=30.0, fg3_rate_b=32.0,
            recent_variance_a=6.0, recent_variance_b=7.0
        )
        self.assertTrue(0 <= result['volatility_score'] <= 100)
        self.assertLess(result['volatility_score'], 50)
        
        # High volatility: SLOW (upset potential), lots of 3s, inconsistent
        result = compute_volatility_score(
            tempo_a=64.0, tempo_b=65.0,  # Slow pace (high volatility with new logic)
            fg3_rate_a=48.0, fg3_rate_b=50.0,
            recent_variance_a=18.0, recent_variance_b=20.0
        )
        self.assertTrue(0 <= result['volatility_score'] <= 100)
        self.assertGreater(result['volatility_score'], 65)


# =============================================================================
# INTEGRATION TESTS: Site Toggle
# =============================================================================

class SiteToggleTestCase(TestCase):
    """Tests that site toggle changes predictions correctly"""
    
    def setUp(self):
        """Set up test database with Michigan vs Duke"""
        self.season = Season.objects.create(
            year=2026, display_name="2025-26", is_current=True
        )
        
        self.b10 = Conference.objects.create(code="B10", name="Big Ten")
        self.acc = Conference.objects.create(code="ACC", name="ACC")
        
        self.michigan = Team.objects.create(slug="michigan", name="Michigan", aliases=["Wolverines"])
        self.duke = Team.objects.create(slug="duke", name="Duke", aliases=["Blue Devils"])
        
        # Michigan ratings
        TeamSeasonRatings.objects.create(
            team=self.michigan, season=self.season,
            wins=20, losses=5, games_played=25, rank_adj_em=10,
            adj_em=18.5, adj_o=115.0, adj_d=96.5, adj_tempo=70.0,
            adj_efg_pct=53.5, adj_tov_pct=16.0, adj_orb_pct=30.0, adj_ftr=35.0,
            adj_opp_efg_pct=48.5, adj_opp_tov_pct=19.0, adj_drb_pct=72.0, adj_opp_ftr=30.0,
            adj_efg_margin=5.0, adj_tov_edge=3.0, adj_reb_edge=2.0, adj_ftr_margin=5.0,
            ffi_adj=55.0, ffi_raw=52.0, total_possessions=1750
        )
        
        # Duke ratings
        TeamSeasonRatings.objects.create(
            team=self.duke, season=self.season,
            wins=22, losses=3, games_played=25, rank_adj_em=3,
            adj_em=22.0, adj_o=118.0, adj_d=96.0, adj_tempo=72.0,
            adj_efg_pct=54.0, adj_tov_pct=15.5, adj_orb_pct=32.0, adj_ftr=38.0,
            adj_opp_efg_pct=49.0, adj_opp_tov_pct=20.0, adj_drb_pct=70.0, adj_opp_ftr=32.0,
            adj_efg_margin=5.0, adj_tov_edge=4.5, adj_reb_edge=2.0, adj_ftr_margin=6.0,
            ffi_adj=58.0, ffi_raw=55.0, total_possessions=1800
        )
        
        # National averages
        NationalAverages.objects.create(
            season=self.season,
            avg_ortg=108.0, avg_pace=68.0,
            avg_efg=50.0, avg_tov=18.0, avg_orb=28.0, avg_ftr=32.0,
            total_possessions=100000, total_games=5000,
            coef_efg=0.995, coef_tov=0.912, coef_orb=0.464, coef_ftr=0.084,
            coef_intercept=0.0, coef_r_squared=0.951,
            hca_points=1.85, prediction_sigma=11.08
        )
        
        # Note: Not creating TeamSeasonStats - shot_profile will be None (which is fine)
        
        self.client = Client()
    
    def test_site_neutral(self):
        """Test neutral site prediction"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Duke should be favored (they have higher adj_em)
        self.assertGreater(data['forecast']['prob_b'], 0.5)
        self.assertLess(data['forecast']['margin'], 0)  # Negative = Team B favored
    
    def test_site_home_advantage(self):
        """Test Team A home advantage"""
        neutral = self.client.get('/api/matchup/', {
            'teamA': 'michigan', 'teamB': 'duke', 'site': 'neutral'
        }).json()
        
        home = self.client.get('/api/matchup/', {
            'teamA': 'michigan', 'teamB': 'duke', 'site': 'home'
        }).json()
        
        # Michigan should do better at home
        self.assertGreater(home['forecast']['pts_a'], neutral['forecast']['pts_a'])
        self.assertLess(home['forecast']['pts_b'], neutral['forecast']['pts_b'])
        self.assertGreater(home['forecast']['prob_a'], neutral['forecast']['prob_a'])
    
    def test_site_away_disadvantage(self):
        """Test Team A away disadvantage"""
        neutral = self.client.get('/api/matchup/', {
            'teamA': 'michigan', 'teamB': 'duke', 'site': 'neutral'
        }).json()
        
        away = self.client.get('/api/matchup/', {
            'teamA': 'michigan', 'teamB': 'duke', 'site': 'away'
        }).json()
        
        # Michigan should do worse on road (at Duke)
        self.assertLess(away['forecast']['pts_a'], neutral['forecast']['pts_a'])
        self.assertGreater(away['forecast']['pts_b'], neutral['forecast']['pts_b'])
        self.assertLess(away['forecast']['prob_a'], neutral['forecast']['prob_a'])
    
    def test_site_toggle_symmetry(self):
        """Test home/away/neutral are mathematically consistent"""
        neutral = self.client.get('/api/matchup/', {
            'teamA': 'michigan', 'teamB': 'duke', 'site': 'neutral'
        }).json()
        
        home = self.client.get('/api/matchup/', {
            'teamA': 'michigan', 'teamB': 'duke', 'site': 'home'
        }).json()
        
        away = self.client.get('/api/matchup/', {
            'teamA': 'michigan', 'teamB': 'duke', 'site': 'away'
        }).json()
        
        # HCA should be symmetric
        nat_avgs = NationalAverages.objects.get(season=self.season)
        hca = nat_avgs.hca_points
        
        # Home - Neutral should equal -(Away - Neutral)
        home_boost = home['forecast']['margin'] - neutral['forecast']['margin']
        away_penalty = away['forecast']['margin'] - neutral['forecast']['margin']
        
        self.assertAlmostEqual(home_boost, -away_penalty, delta=0.2)
        self.assertAlmostEqual(abs(home_boost), hca, delta=0.2)


# =============================================================================
# EDGE CASE TESTS: Missing Data & Limited Games
# =============================================================================

class EdgeCaseTestCase(TestCase):
    """Tests for edge cases and missing data scenarios"""
    
    def setUp(self):
        """Set up minimal test data"""
        self.season = Season.objects.create(
            year=2026, display_name="2025-26", is_current=True
        )
        self.conf = Conference.objects.create(code="TEST", name="Test Conference")
        
        NationalAverages.objects.create(
            season=self.season,
            avg_ortg=108.0, avg_pace=68.0,
            avg_efg=50.0, avg_tov=18.0, avg_orb=28.0, avg_ftr=32.0,
            total_possessions=100000, total_games=5000,
            coef_efg=0.995, coef_tov=0.912, coef_orb=0.464, coef_ftr=0.084,
            coef_intercept=0.0, coef_r_squared=0.951,
            hca_points=1.85, prediction_sigma=11.08
        )
        
        self.client = Client()
    
    def test_missing_team(self):
        """Test API with non-existent team"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'nonexistent-team',
            'teamB': 'duke',
            'site': 'neutral'
        })
        self.assertEqual(response.status_code, 404)
    
    def test_team_without_ratings(self):
        """Test team exists but has no ratings"""
        team = Team.objects.create(slug="new-team", name="New Team", aliases=[])
        
        # Create opponent with ratings
        opponent = Team.objects.create(slug="opponent", name="Opponent", aliases=[])
        TeamSeasonRatings.objects.create(
            team=opponent, season=self.season,
            wins=10, losses=10, games_played=20, rank_adj_em=100,
            adj_em=0.0, adj_o=108.0, adj_d=108.0, adj_tempo=68.0,
            adj_efg_pct=50.0, adj_tov_pct=18.0, adj_orb_pct=28.0, adj_ftr=32.0,
            adj_opp_efg_pct=50.0, adj_opp_tov_pct=18.0, adj_drb_pct=72.0, adj_opp_ftr=32.0,
            adj_efg_margin=0.0, adj_tov_edge=0.0, adj_reb_edge=0.0, adj_ftr_margin=0.0,
            ffi_adj=50.0, ffi_raw=50.0, total_possessions=1400
        )
        
        response = self.client.get('/api/matchup/', {
            'teamA': 'new-team',
            'teamB': 'opponent',
            'site': 'neutral'
        })
        self.assertEqual(response.status_code, 404)
    
    def test_missing_shot_profile_data(self):
        """Test when shot profile data is missing"""
        team_a = Team.objects.create(slug="team-a", name="Team A", aliases=[])
        team_b = Team.objects.create(slug="team-b", name="Team B", aliases=[])
        
        # Create ratings but NO TeamSeasonStats (no shot profile)
        for team in [team_a, team_b]:
            TeamSeasonRatings.objects.create(
                team=team, season=self.season,
                wins=15, losses=10, games_played=25, rank_adj_em=50,
                adj_em=5.0, adj_o=110.0, adj_d=105.0, adj_tempo=68.0,
                adj_efg_pct=51.0, adj_tov_pct=17.0, adj_orb_pct=29.0, adj_ftr=33.0,
                adj_opp_efg_pct=49.0, adj_opp_tov_pct=19.0, adj_drb_pct=71.0, adj_opp_ftr=31.0,
                adj_efg_margin=2.0, adj_tov_edge=2.0, adj_reb_edge=2.0, adj_ftr_margin=2.0,
                ffi_adj=52.0, ffi_raw=50.0, total_possessions=1500
            )
        
        response = self.client.get('/api/matchup/', {
            'teamA': 'team-a',
            'teamB': 'team-b',
            'site': 'neutral'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should have forecast but shot_profile should be None
        self.assertIn('forecast', data)
        self.assertIsNone(data['shot_profile'])
    
    def test_limited_recent_games(self):
        """Test when teams have fewer than 10 recent games"""
        team_a = Team.objects.create(slug="early-season-a", name="Early Season A", aliases=[])
        team_b = Team.objects.create(slug="early-season-b", name="Early Season B", aliases=[])
        
        # Create ratings for both teams
        for team in [team_a, team_b]:
            TeamSeasonRatings.objects.create(
                team=team, season=self.season,
                wins=3, losses=2, games_played=5, rank_adj_em=50,
                adj_em=5.0, adj_o=110.0, adj_d=105.0, adj_tempo=68.0,
                adj_efg_pct=51.0, adj_tov_pct=17.0, adj_orb_pct=29.0, adj_ftr=33.0,
                adj_opp_efg_pct=49.0, adj_opp_tov_pct=19.0, adj_drb_pct=71.0, adj_opp_ftr=31.0,
                adj_efg_margin=2.0, adj_tov_edge=2.0, adj_reb_edge=2.0, adj_ftr_margin=2.0,
                ffi_adj=52.0, ffi_raw=50.0, total_possessions=350
            )
        
        # Create only 3 games for Team A
        for i in range(3):
            game = Game.objects.create(
                source_game_id=f"test-game-{i}",
                season_year=2026,
                game_date=date(2025, 11, 10 + i),
                home_team=team_a,
                away_team=team_b,
                home_score=70 + i,
                away_score=68,
                status='final',
                neutral_site=False
            )
            TeamGameStats.objects.create(
                team=team_a,
                game=game,
                opponent=team_b,
                home_away='H',
                pts=70 + i
            )
        
        response = self.client.get('/api/matchup/', {
            'teamA': 'early-season-a',
            'teamB': 'early-season-b',
            'site': 'neutral'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should still work with limited games
        self.assertEqual(data['recent_form_a']['games_analyzed'], 3)
        self.assertLessEqual(len(data['recent_form_a']['games']), 5)
    
    def test_forecast_with_extreme_values(self):
        """Test forecast handles extreme but valid ratings"""
        result = forecast_game(
            adj_o_a=130.0, adj_d_a=85.0, adj_em_a=45.0, tempo_a=75.0,  # Elite team
            adj_o_b=95.0, adj_d_b=115.0, adj_em_b=-20.0, tempo_b=65.0,  # Weak team
            nat_avg_ortg=108.0,
            hca_points=3.5,
            sigma=11.08,
            site='neutral'
        )
        
        # Should produce valid results
        self.assertGreater(result['pts_a'], result['pts_b'])
        self.assertGreater(result['prob_a'], 0.95)  # Elite team heavily favored
        self.assertLess(result['prob_b'], 0.05)
        
        # Scores should be reasonable
        self.assertTrue(50 < result['pts_a'] < 150)
        self.assertTrue(50 < result['pts_b'] < 150)


# =============================================================================
# RUN ALL TESTS
# =============================================================================

if __name__ == '__main__':
    import unittest
    unittest.main()
