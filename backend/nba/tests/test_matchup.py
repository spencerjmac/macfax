"""
Integration tests for NBA Matchup API endpoint — GET /api/nba/matchup/

Covers: happy path, series mode, invalid params, site toggle, NCAA regression.
"""
from django.test import TestCase, Client


class NBAMatchupAPITest(TestCase):
    """Tests for /api/nba/matchup/"""

    def setUp(self):
        from nba.models import NBASeason, NBATeam, NBATeamSeasonRatings, NBAModelCalibration

        self.client = Client()

        self.season = NBASeason.objects.create(
            year=2026, display_name="2025-26", is_current=True
        )

        self.celtics = NBATeam.objects.create(
            nba_team_id=1610612738,
            slug="boston-celtics",
            name="Boston Celtics",
            abbreviation="BOS",
            city="Boston",
            conference="East",
            division="Atlantic",
        )
        self.warriors = NBATeam.objects.create(
            nba_team_id=1610612744,
            slug="golden-state-warriors",
            name="Golden State Warriors",
            abbreviation="GSW",
            city="Golden State",
            conference="West",
            division="Pacific",
        )

        # Celtics ratings — strong offense, good defense
        NBATeamSeasonRatings.objects.create(
            team=self.celtics,
            season=self.season,
            season_type="regular",
            games=60,
            adj_off=120.5,
            adj_def=108.0,
            adj_net=12.5,
            pace=98.2,
            efg_pct=0.565,
            opp_efg_pct=0.495,
            tov_rate=0.120,
            opp_tov_rate=0.145,
            oreb_pct=0.280,
            opp_oreb_pct=0.250,
            fta_rate=0.240,
            opp_fta_rate=0.210,
            efg_margin=0.070,
            tov_edge=0.025,
            oreb_edge=0.030,
            fta_margin=0.030,
            ffi=62.0,
            rank_adj_net=2,
            rank_ffi=2,
        )

        # Warriors ratings — average across the board
        NBATeamSeasonRatings.objects.create(
            team=self.warriors,
            season=self.season,
            season_type="regular",
            games=60,
            adj_off=114.0,
            adj_def=112.0,
            adj_net=2.0,
            pace=100.1,
            efg_pct=0.535,
            opp_efg_pct=0.530,
            tov_rate=0.130,
            opp_tov_rate=0.135,
            oreb_pct=0.265,
            opp_oreb_pct=0.270,
            fta_rate=0.220,
            opp_fta_rate=0.225,
            efg_margin=0.005,
            tov_edge=0.005,
            oreb_edge=-0.005,
            fta_margin=-0.005,
            ffi=51.0,
            rank_adj_net=14,
            rank_ffi=14,
        )

        NBAModelCalibration.objects.create(
            season=self.season,
            empirical_hca=2.8,
            ols_model_scale=11.5,
            ols_r_squared=0.312,
            straight_up_accuracy=0.67,
        )

    # ─── Happy path ──────────────────────────────────────────────────────────

    def test_basic_matchup_returns_200(self):
        r = self.client.get("/api/nba/matchup/", {"teamA": "boston-celtics", "teamB": "golden-state-warriors"})
        self.assertEqual(r.status_code, 200)

    def test_response_has_required_sections(self):
        r = self.client.get("/api/nba/matchup/", {"teamA": "boston-celtics", "teamB": "golden-state-warriors"})
        data = r.json()
        for key in ("season", "site", "mode", "teamA", "teamB", "forecast",
                    "four_factor_edges", "ffi_edge", "volatility",
                    "recent_form_a", "recent_form_b", "metadata"):
            self.assertIn(key, data, f"Missing key: {key}")

    def test_forecast_probabilities_sum_to_one(self):
        r = self.client.get("/api/nba/matchup/", {"teamA": "boston-celtics", "teamB": "golden-state-warriors"})
        fc = r.json()["forecast"]
        self.assertAlmostEqual(fc["prob_a"] + fc["prob_b"], 1.0, places=3)

    def test_celtics_favored_neutral(self):
        """Celtics have higher adj_net — should be favored at neutral."""
        r = self.client.get("/api/nba/matchup/", {
            "teamA": "boston-celtics", "teamB": "golden-state-warriors", "site": "neutral"
        })
        fc = r.json()["forecast"]
        self.assertGreater(fc["prob_a"], 0.5, "Celtics should be favored")
        self.assertGreater(fc["margin"], 0)

    def test_team_cards_have_expected_fields(self):
        r = self.client.get("/api/nba/matchup/", {"teamA": "boston-celtics", "teamB": "golden-state-warriors"})
        for team_key in ("teamA", "teamB"):
            team = r.json()[team_key]
            for field in ("id", "name", "slug", "conference", "division", "rank", "record",
                          "adj_em", "adj_o", "adj_d", "adj_tempo", "ffi"):
                self.assertIn(field, team, f"{team_key} missing field: {field}")

    # ─── Site toggle ─────────────────────────────────────────────────────────

    def test_home_site_boosts_team_a(self):
        neutral = self.client.get("/api/nba/matchup/", {
            "teamA": "boston-celtics", "teamB": "golden-state-warriors", "site": "neutral"
        }).json()["forecast"]["margin"]

        home = self.client.get("/api/nba/matchup/", {
            "teamA": "boston-celtics", "teamB": "golden-state-warriors", "site": "home"
        }).json()["forecast"]["margin"]

        self.assertGreater(home, neutral, "Home margin should exceed neutral")

    def test_away_site_reduces_team_a_margin(self):
        neutral = self.client.get("/api/nba/matchup/", {
            "teamA": "boston-celtics", "teamB": "golden-state-warriors", "site": "neutral"
        }).json()["forecast"]["margin"]

        away = self.client.get("/api/nba/matchup/", {
            "teamA": "boston-celtics", "teamB": "golden-state-warriors", "site": "away"
        }).json()["forecast"]["margin"]

        self.assertLess(away, neutral, "Away margin should be less than neutral")

    # ─── Series mode ─────────────────────────────────────────────────────────

    def test_series_mode_adds_series_prediction(self):
        r = self.client.get("/api/nba/matchup/", {
            "teamA": "boston-celtics", "teamB": "golden-state-warriors", "mode": "series"
        })
        data = r.json()
        self.assertIn("series_prediction", data)
        sp = data["series_prediction"]
        self.assertAlmostEqual(sp["prob_a_series"] + sp["prob_b_series"], 1.0, places=3)

    def test_series_game_probs_sum_to_series_prob(self):
        r = self.client.get("/api/nba/matchup/", {
            "teamA": "boston-celtics", "teamB": "golden-state-warriors", "mode": "series"
        })
        sp = r.json()["series_prediction"]
        a_total = sp["prob_sweep_a"] + sp["prob_a_in_5"] + sp["prob_a_in_6"] + sp["prob_a_in_7"]
        b_total = sp["prob_sweep_b"] + sp["prob_b_in_5"] + sp["prob_b_in_6"] + sp["prob_b_in_7"]
        self.assertAlmostEqual(a_total, sp["prob_a_series"], places=2)
        self.assertAlmostEqual(b_total, sp["prob_b_series"], places=2)

    def test_game_mode_has_no_series_prediction(self):
        r = self.client.get("/api/nba/matchup/", {
            "teamA": "boston-celtics", "teamB": "golden-state-warriors", "mode": "game"
        })
        self.assertIsNone(r.json()["series_prediction"])

    # ─── Error cases ─────────────────────────────────────────────────────────

    def test_missing_team_a_returns_400(self):
        r = self.client.get("/api/nba/matchup/", {"teamB": "golden-state-warriors"})
        self.assertEqual(r.status_code, 400)

    def test_missing_team_b_returns_400(self):
        r = self.client.get("/api/nba/matchup/", {"teamA": "boston-celtics"})
        self.assertEqual(r.status_code, 400)

    def test_invalid_team_slug_returns_404(self):
        r = self.client.get("/api/nba/matchup/", {"teamA": "not-a-team", "teamB": "golden-state-warriors"})
        self.assertEqual(r.status_code, 404)

    def test_invalid_site_returns_400(self):
        r = self.client.get("/api/nba/matchup/", {
            "teamA": "boston-celtics", "teamB": "golden-state-warriors", "site": "sideline"
        })
        self.assertEqual(r.status_code, 400)

    def test_invalid_mode_returns_400(self):
        r = self.client.get("/api/nba/matchup/", {
            "teamA": "boston-celtics", "teamB": "golden-state-warriors", "mode": "playoff"
        })
        self.assertEqual(r.status_code, 400)

    def test_unknown_season_returns_404(self):
        r = self.client.get("/api/nba/matchup/", {
            "teamA": "boston-celtics", "teamB": "golden-state-warriors", "season": "1899"
        })
        self.assertEqual(r.status_code, 404)

    # ─── NCAA regression guard ────────────────────────────────────────────────

    def test_ncaa_matchup_still_works(self):
        """Ensure NCAA matchup endpoint is unaffected by NBA changes."""
        r = self.client.get("/api/matchup/", {"teamA": "michigan", "teamB": "duke"})
        # 400 is fine here (no NCAA teams in DB) — we just verify it doesn't 500
        self.assertNotEqual(r.status_code, 500)


class NBASeriesEngineTest(TestCase):
    """Unit tests for compute_series_probability logic."""

    def test_equal_teams_series_prob_near_half(self):
        from nba.matchup_engine import compute_series_probability
        sp = compute_series_probability(0.5, 0.5, "a")
        self.assertAlmostEqual(sp["prob_a_series"], 0.5, places=2)

    def test_dominant_team_wins_series(self):
        from nba.matchup_engine import compute_series_probability
        sp = compute_series_probability(0.85, 0.75, "a")
        self.assertGreater(sp["prob_a_series"], 0.9)

    def test_probabilities_sum_to_one(self):
        from nba.matchup_engine import compute_series_probability
        sp = compute_series_probability(0.60, 0.45, "b")
        self.assertAlmostEqual(sp["prob_a_series"] + sp["prob_b_series"], 1.0, places=6)
        # Sum of rounded-to-3-decimal values; allow ±1% tolerance for float accumulation
        total = (
            sp["prob_sweep_a"] + sp["prob_a_in_5"] + sp["prob_a_in_6"] + sp["prob_a_in_7"] +
            sp["prob_sweep_b"] + sp["prob_b_in_5"] + sp["prob_b_in_6"] + sp["prob_b_in_7"]
        )
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_schedule_has_7_games(self):
        from nba.matchup_engine import compute_series_probability
        sp = compute_series_probability(0.6, 0.5, "a")
        self.assertEqual(len(sp["game_schedule"]), 7)

    def test_home_court_format_a(self):
        from nba.matchup_engine import compute_series_probability
        sp = compute_series_probability(0.6, 0.5, "a")
        sites = [g["site"] for g in sp["game_schedule"]]
        self.assertEqual(sites, ["home", "home", "away", "away", "away", "home", "home"])

    def test_home_court_format_b(self):
        from nba.matchup_engine import compute_series_probability
        sp = compute_series_probability(0.6, 0.5, "b")
        sites = [g["site"] for g in sp["game_schedule"]]
        self.assertEqual(sites, ["away", "away", "home", "home", "home", "away", "away"])
