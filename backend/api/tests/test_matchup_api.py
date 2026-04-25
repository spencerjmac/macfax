"""
Integration tests for Matchup API endpoint

Tests API behavior, site toggle, edge cases, and data validation.
"""

from django.test import TestCase, Client
from django.urls import reverse
from ncaa.models import (
    Season, Conference, Team, TeamSeasonRatings, 
    TeamSeasonStats, NationalAverages, TeamGameStats, Game
)
from decimal import Decimal
from datetime import date, datetime


class MatchupAPITestCase(TestCase):
    """Integration tests for /api/matchup/ endpoint"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create season
        self.season = Season.objects.create(
            year=2026,
            display_name="2025-26",
            is_current=True
        )
        
        # Create conferences
        self.b10 = Conference.objects.create(code="B10", name="Big Ten")
        self.acc = Conference.objects.create(code="ACC", name="ACC")
        
        # Create teams
        self.michigan = Team.objects.create(
            slug="michigan",
            name="Michigan",
            aliases=["Wolverines"]
        )
        
        self.duke = Team.objects.create(
            slug="duke",
            name="Duke",
            aliases=["Blue Devils"]
        )
        
        # Create ratings for Michigan
        self.michigan_ratings = TeamSeasonRatings.objects.create(
            team=self.michigan,
            season=self.season,
            wins=20,
            losses=5,
            games_played=25,
            rank_adj_em=10,
            adj_em=18.5,
            adj_o=115.0,
            adj_d=96.5,
            adj_tempo=70.0,
            adj_efg_pct=53.5,
            adj_tov_pct=16.0,
            adj_orb_pct=30.0,
            adj_ftr=35.0,
            adj_opp_efg_pct=48.5,
            adj_opp_tov_pct=19.0,
            adj_drb_pct=72.0,
            adj_opp_ftr=30.0,
            adj_efg_margin=5.0,
            adj_tov_edge=3.0,
            adj_reb_edge=2.0,
            adj_ftr_margin=5.0,
            ffi_adj=55.0,
            ffi_raw=52.0,
            total_possessions=1750
        )
        
        # Create ratings for Duke
        self.duke_ratings = TeamSeasonRatings.objects.create(
            team=self.duke,
            season=self.season,
            wins=22,
            losses=3,
            games_played=25,
            rank_adj_em=3,
            adj_em=22.0,
            adj_o=118.0,
            adj_d=96.0,
            adj_tempo=72.0,
            adj_efg_pct=54.0,
            adj_tov_pct=15.5,
            adj_orb_pct=32.0,
            adj_ftr=38.0,
            adj_opp_efg_pct=49.0,
            adj_opp_tov_pct=20.0,
            adj_drb_pct=70.0,
            adj_opp_ftr=32.0,
            adj_efg_margin=5.0,
            adj_tov_edge=4.5,
            adj_reb_edge=2.0,
            adj_ftr_margin=6.0,
            ffi_adj=58.0,
            ffi_raw=55.0,
            total_possessions=1800
        )
        
        # Create TeamSeasonStats for shot profile data
        self.michigan_stats = TeamSeasonStats.objects.create(
            team=self.michigan,
            season=self.season,
            conference=self.b10,
            games=25,
            wins=20,
            losses=5,
            adj_em=18.5,
            adj_o=115.0,
            adj_d=96.5,
            adj_tempo=70.0,
            efg_pct=53.5,
            tov_pct=16.0,
            orb_pct=30.0,
            ftr=35.0,
            efg_pct_d=48.5,
            tov_pct_d=19.0,
            drb_pct=72.0,
            ftr_d=30.0,
            fg3_rate=38.0,
            fg3_pct=36.5,
            fg2_pct=52.0
        )
        
        self.duke_stats = TeamSeasonStats.objects.create(
            team=self.duke,
            season=self.season,
            conference=self.acc,
            games=25,
            wins=22,
            losses=3,
            adj_em=22.0,
            adj_o=118.0,
            adj_d=96.0,
            adj_tempo=72.0,
            efg_pct=54.0,
            tov_pct=15.5,
            orb_pct=32.0,
            ftr=38.0,
            efg_pct_d=49.0,
            tov_pct_d=20.0,
            drb_pct=70.0,
            ftr_d=32.0,
            fg3_rate=40.0,
            fg3_pct=38.0,
            fg2_pct=54.0
        )
        
        # Create national averages with regression coefficients
        self.nat_avg = NationalAverages.objects.create(
            season=self.season,
            avg_ortg=108.0,
            avg_pace=69.5,
            avg_efg=51.5,
            avg_tov=17.5,
            avg_orb=28.0,
            avg_ftr=33.0,
            hca_points=1.85,
            prediction_sigma=11.08,
            total_possessions=100000,
            total_games=5000,
            coef_efg=Decimal('0.995'),
            coef_tov=Decimal('0.912'),
            coef_orb=Decimal('0.464'),
            coef_ftr=Decimal('0.084'),
            coef_intercept=Decimal('0.0'),
            coef_r_squared=Decimal('0.951')
        )
        
        # Create some recent games for Michigan (for recent form)
        self._create_recent_games(self.michigan, 10)
        self._create_recent_games(self.duke, 10)
    
    def _create_recent_games(self, team, count=10):
        """Helper to create recent games for a team"""
        for i in range(count):
            opponent = Team.objects.create(
                slug=f"opponent-{team.slug}-{i}",
                name=f"Opponent {i}"
            )
            
            game = Game.objects.create(
                source_game_id=f"test-{team.slug}-{i}",
                season_year=2026,
                game_date=date(2026, 2, 25 - i),
                home_team=team if i % 2 == 0 else opponent,
                away_team=opponent if i % 2 == 0 else team,
                home_score=75 + i,
                away_score=70 + i,
                status='final',
                neutral_site=False
            )
            
            # Create TeamGameStats
            TeamGameStats.objects.create(
                game=game,
                team=team,
                opponent=opponent,
                home_away='H' if i % 2 == 0 else 'A',
                pts=75 + i if i % 2 == 0 else 70 + i
            )
    
    def test_matchup_api_basic(self):
        """Test basic matchup API call"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Check structure
        self.assertIn('forecast', data)
        self.assertIn('four_factor_edges', data)
        self.assertIn('points_breakdown', data)
        self.assertIn('top_drivers', data)
        self.assertIn('shot_profile', data)
        self.assertIn('volatility', data)
        self.assertIn('recent_form_a', data)
        self.assertIn('recent_form_b', data)
        self.assertIn('metadata', data)
    
    def test_matchup_api_neutral_site(self):
        """Test matchup at neutral site"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data['site'], 'neutral')
        # Duke should be favored (higher adj_em)
        self.assertLess(data['forecast']['margin'], 0)
        self.assertLess(data['forecast']['prob_a'], 0.5)
    
    def test_matchup_api_home_site(self):
        """Test matchup with Team A at home"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'home'
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data['site'], 'home')
        
        # Get neutral site for comparison
        neutral_response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        neutral_data = neutral_response.json()
        
        # Michigan should have better odds at home
        self.assertGreater(
            data['forecast']['prob_a'],
            neutral_data['forecast']['prob_a']
        )
        
        # Margin should improve by HCA
        margin_diff = (data['forecast']['margin'] - 
                      neutral_data['forecast']['margin'])
        self.assertAlmostEqual(margin_diff, 1.85, delta=0.1)
    
    def test_matchup_api_away_site(self):
        """Test matchup with Team A away (Team B home)"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'away'
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data['site'], 'away')
        
        # Get neutral site for comparison
        neutral_response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        neutral_data = neutral_response.json()
        
        # Michigan should have worse odds playing away
        self.assertLess(
            data['forecast']['prob_a'],
            neutral_data['forecast']['prob_a']
        )
    
    def test_matchup_api_site_toggle_symmetry(self):
        """Test that site toggle produces symmetric HCA effects"""
        neutral = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        }).json()
        
        home = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'home'
        }).json()
        
        away = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'away'
        }).json()
        
        hca = self.nat_avg.hca_points
        
        # Home margin - Neutral margin ≈ HCA
        home_boost = home['forecast']['margin'] - neutral['forecast']['margin']
        self.assertAlmostEqual(home_boost, hca, delta=0.1)
        
        # Neutral margin - Away margin ≈ HCA
        away_penalty = neutral['forecast']['margin'] - away['forecast']['margin']
        self.assertAlmostEqual(away_penalty, hca, delta=0.1)
    
    def test_matchup_api_four_factor_breakdown(self):
        """Test four factor breakdown is included"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        
        data = response.json()
        ff = data['four_factor_edges']
        
        # Check all four factors present
        self.assertIn('efg_edge', ff)
        self.assertIn('tov_edge', ff)
        self.assertIn('orb_edge', ff)
        self.assertIn('ftr_edge', ff)
        
        # Check individual values
        self.assertIn('exp_efg_a', ff)
        self.assertIn('exp_efg_b', ff)
    
    def test_matchup_api_points_breakdown(self):
        """Test points breakdown from regression"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        
        data = response.json()
        pb = data['points_breakdown']
        
        # Check structure
        self.assertIn('pts_from_efg', pb)
        self.assertIn('pts_from_tov', pb)
        self.assertIn('pts_from_orb', pb)
        self.assertIn('pts_from_ftr', pb)
        self.assertIn('total_margin', pb)
    
    def test_matchup_api_top_drivers(self):
        """Test top drivers identification"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        
        data = response.json()
        drivers = data['top_drivers']
        
        # Should return 3 drivers
        self.assertEqual(len(drivers), 3)
        
        # Each driver should have required fields
        for driver in drivers:
            self.assertIn('factor', driver)
            self.assertIn('edge', driver)
            self.assertIn('points', driver)
            self.assertIn('team', driver)
        
        # Should be sorted by absolute impact
        impacts = [abs(d['points']) for d in drivers]
        self.assertEqual(impacts, sorted(impacts, reverse=True))
    
    def test_matchup_api_shot_profile(self):
        """Test shot profile is included"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        
        data = response.json()
        sp = data['shot_profile']
        
        self.assertIsNotNone(sp)
        self.assertIn('fg3_rate_edge', sp)
        self.assertIn('fg3_pct_edge', sp)
        self.assertIn('fg2_pct_edge', sp)
    
    def test_matchup_api_volatility(self):
        """Test volatility score is computed"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        
        data = response.json()
        vol = data['volatility']
        
        # Check structure
        self.assertIn('volatility_score', vol)
        self.assertIn('pace_component', vol)
        self.assertIn('three_pt_component', vol)
        self.assertIn('variance_component', vol)
        self.assertIn('reasons', vol)
        
        # Score should be 0-100
        self.assertGreaterEqual(vol['volatility_score'], 0)
        self.assertLessEqual(vol['volatility_score'], 100)
    
    def test_matchup_api_recent_form(self):
        """Test recent form analysis is included"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        
        data = response.json()
        form_a = data['recent_form_a']
        form_b = data['recent_form_b']
        
        # Check structure
        for form in [form_a, form_b]:
            self.assertIn('games_analyzed', form)
            self.assertIn('record', form)
            self.assertIn('avg_margin', form)
            self.assertIn('variance', form)
            self.assertIn('games', form)
        
        # Should have analyzed 10 games (or fewer if not available)
        self.assertLessEqual(form_a['games_analyzed'], 10)
        self.assertLessEqual(form_b['games_analyzed'], 10)
    
    def test_matchup_api_metadata(self):
        """Test metadata is included"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        
        data = response.json()
        meta = data['metadata']
        
        self.assertIn('hca_points', meta)
        self.assertIn('prediction_sigma', meta)
        self.assertIn('nat_avg_ortg', meta)
        self.assertIn('coefficients', meta)
        
        # Check coefficients
        coefs = meta['coefficients']
        self.assertIsNotNone(coefs['efg'])
        self.assertIsNotNone(coefs['tov'])
        self.assertIsNotNone(coefs['orb'])
        self.assertIsNotNone(coefs['ftr'])
        self.assertIsNotNone(coefs['r_squared'])
    
    def test_matchup_api_missing_team(self):
        """Test API handles missing team gracefully"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'nonexistent',
            'teamB': 'duke',
            'site': 'neutral'
        })
        
        self.assertEqual(response.status_code, 404)
    
    def test_matchup_api_invalid_site(self):
        """Test API handles invalid site parameter"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'invalid'
        })
        
        self.assertEqual(response.status_code, 400)
    
    def test_matchup_api_missing_parameters(self):
        """Test API requires teamA and teamB"""
        response = self.client.get('/api/matchup/', {
            'teamA': 'michigan'
        })
        
        self.assertEqual(response.status_code, 400)
        
        response = self.client.get('/api/matchup/', {
            'teamB': 'duke'
        })
        
        self.assertEqual(response.status_code, 400)
    
    def test_matchup_api_case_insensitive_teams(self):
        """Test API handles case-insensitive team names"""
        response1 = self.client.get('/api/matchup/', {
            'teamA': 'MICHIGAN',
            'teamB': 'DUKE',
            'site': 'neutral'
        })
        
        response2 = self.client.get('/api/matchup/', {
            'teamA': 'michigan',
            'teamB': 'duke',
            'site': 'neutral'
        })
        
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)
        
        # Should produce same results
        data1 = response1.json()
        data2 = response2.json()
        
        self.assertAlmostEqual(
            data1['forecast']['margin'],
            data2['forecast']['margin'],
            places=2
        )


class MatchupEdgeCasesTestCase(TestCase):
    """Tests for edge cases in matchup predictions"""
    
    def setUp(self):
        """Set up minimal test data"""
        self.client = Client()
        
        self.season = Season.objects.create(
            year=2026,
            display_name="2025-26",
            is_current=True
        )
        
        self.conf = Conference.objects.create(code="B10", name="Big Ten")
        
        self.team_a = Team.objects.create(slug="team-a", name="Team A")
        self.team_b = Team.objects.create(slug="team-b", name="Team B")
        
        self.nat_avg = NationalAverages.objects.create(
            season=self.season,
            avg_ortg=108.0,
            avg_pace=69.5,
            avg_efg=51.5,
            avg_tov=17.5,
            avg_orb=28.0,
            avg_ftr=33.0,
            hca_points=1.85,
            prediction_sigma=11.08,
            total_possessions=100000,
            total_games=5000,
            coef_efg=Decimal('0.995'),
            coef_tov=Decimal('0.912'),
            coef_orb=Decimal('0.464'),
            coef_ftr=Decimal('0.084'),
            coef_r_squared=Decimal('0.951')
        )
    
    def test_team_with_no_recent_games(self):
        """Test matchup when teams have no recent game data"""
        # Create ratings but no games
        TeamSeasonRatings.objects.create(
            team=self.team_a,
            season=self.season,
            wins=15,
            losses=10,
            games_played=25,
            rank_adj_em=50,
            adj_em=10.0,
            adj_o=110.0,
            adj_d=100.0,
            adj_tempo=70.0,
            adj_efg_pct=52.0,
            adj_tov_pct=17.0,
            adj_orb_pct=29.0,
            adj_ftr=34.0,
            adj_opp_efg_pct=50.0,
            adj_opp_tov_pct=18.0,
            adj_drb_pct=71.0,
            adj_opp_ftr=33.0,
            ffi_adj=50.0,
            total_possessions=1750
        )
        
        TeamSeasonRatings.objects.create(
            team=self.team_b,
            season=self.season,
            wins=18,
            losses=7,
            games_played=25,
            rank_adj_em=30,
            adj_em=12.0,
            adj_o=112.0,
            adj_d=100.0,
            adj_tempo=68.0,
            adj_efg_pct=53.0,
            adj_tov_pct=16.0,
            adj_orb_pct=30.0,
            adj_ftr=35.0,
            adj_opp_efg_pct=51.0,
            adj_opp_tov_pct=19.0,
            adj_drb_pct=70.0,
            adj_opp_ftr=34.0,
            ffi_adj=52.0,
            total_possessions=1700
        )
        
        # No TeamSeasonStats or TeamGameStats created
        
        response = self.client.get('/api/matchup/', {
            'teamA': 'team-a',
            'teamB': 'team-b',
            'site': 'neutral'
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should still return forecast
        self.assertIn('forecast', data)
        
        # Recent form should show 0 games analyzed
        self.assertEqual(data['recent_form_a']['games_analyzed'], 0)
        self.assertEqual(data['recent_form_b']['games_analyzed'], 0)
        
        # Shot profile might be None or have default values
        # Volatility should use default variance score
        self.assertEqual(data['volatility']['variance_component'], 50.0)
    
    def test_team_with_limited_games(self):
        """Test matchup when teams have few games"""
        TeamSeasonRatings.objects.create(
            team=self.team_a,
            season=self.season,
            wins=3,
            losses=0,
            games_played=3,
            rank_adj_em=1,
            adj_em=20.0,
            adj_o=120.0,
            adj_d=100.0,
            adj_tempo=72.0,
            adj_efg_pct=55.0,
            adj_tov_pct=15.0,
            adj_orb_pct=32.0,
            adj_ftr=38.0,
            adj_opp_efg_pct=48.0,
            adj_opp_tov_pct=20.0,
            adj_drb_pct=68.0,
            adj_opp_ftr=30.0,
            ffi_adj=60.0,
            total_possessions=216  # ~72 per game * 3
        )
        
        TeamSeasonRatings.objects.create(
            team=self.team_b,
            season=self.season,
            wins=2,
            losses=1,
            games_played=3,
            rank_adj_em=100,
            adj_em=5.0,
            adj_o=105.0,
            adj_d=100.0,
            adj_tempo=68.0,
            adj_efg_pct=50.0,
            adj_tov_pct=18.0,
            adj_orb_pct=28.0,
            adj_ftr=32.0,
            adj_opp_efg_pct=52.0,
            adj_opp_tov_pct=17.0,
            adj_drb_pct=72.0,
            adj_opp_ftr=35.0,
            ffi_adj=45.0,
            total_possessions=204
        )
        
        # Create 3 games for each team
        for i in range(3):
            opponent = Team.objects.create(
                slug=f"opp-a-{i}",
                name=f"Opponent A {i}"
            )
            game = Game.objects.create(
                source_game_id=f"test-limited-{i}",
                season_year=2026,
                game_date=date(2026, 11, 10 + i),
                home_team=self.team_a,
                away_team=opponent,
                home_score=85,
                away_score=70,
                status='final',
                neutral_site=False
            )
            TeamGameStats.objects.create(
                game=game,
                team=self.team_a,
                opponent=opponent,
                home_away='H',
                pts=85
            )
        
        response = self.client.get('/api/matchup/', {
            'teamA': 'team-a',
            'teamB': 'team-b',
            'site': 'neutral'
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should still work with limited data
        self.assertIn('forecast', data)
        
        # Recent form should show actual games
        self.assertEqual(data['recent_form_a']['games_analyzed'], 3)
        self.assertEqual(data['recent_form_b']['games_analyzed'], 0)
    
    def test_extreme_matchup(self):
        """Test matchup between elite and weak teams"""
        # Elite team
        TeamSeasonRatings.objects.create(
            team=self.team_a,
            season=self.season,
            wins=25,
            losses=0,
            games_played=25,
            rank_adj_em=1,
            adj_em=30.0,
            adj_o=125.0,
            adj_d=95.0,
            adj_tempo=75.0,
            adj_efg_pct=58.0,
            adj_tov_pct=14.0,
            adj_orb_pct=35.0,
            adj_ftr=42.0,
            adj_opp_efg_pct=46.0,
            adj_opp_tov_pct=22.0,
            adj_opp_orb_pct=20.0,
            adj_drb_pct=65.0,
            adj_opp_ftr=28.0,
            ffi_adj=70.0,
            total_possessions=1875
        )
        
        # Weak team
        TeamSeasonRatings.objects.create(
            team=self.team_b,
            season=self.season,
            wins=5,
            losses=20,
            games_played=25,
            rank_adj_em=350,
            adj_em=-15.0,
            adj_o=95.0,
            adj_d=110.0,
            adj_tempo=65.0,
            adj_efg_pct=46.0,
            adj_tov_pct=20.0,
            adj_orb_pct=25.0,
            adj_ftr=28.0,
            adj_opp_efg_pct=56.0,
            adj_opp_tov_pct=15.0,
            adj_opp_orb_pct=35.0,
            adj_drb_pct=75.0,
            adj_opp_ftr=40.0,
            ffi_adj=30.0,
            total_possessions=1625
        )
        
        response = self.client.get('/api/matchup/', {
            'teamA': 'team-a',
            'teamB': 'team-b',
            'site': 'neutral'
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Elite team should dominate
        self.assertGreater(data['forecast']['margin'], 25.0)
        self.assertGreater(data['forecast']['prob_a'], 0.95)
        
        # Four factors should all favor elite team
        ff = data['four_factor_edges']
        self.assertGreater(ff['efg_edge'], 8.0)
        self.assertGreater(ff['tov_edge'], 4.0)
        self.assertGreater(ff['orb_edge'], 5.0)
        self.assertGreater(ff['ftr_edge'], 10.0)
