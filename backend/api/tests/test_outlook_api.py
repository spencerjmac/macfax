"""
Tests for Phase 7 Roster Outlook API views.

Covers:
  - GET /api/outlook/<slug>/         RosterOutlookView
  - POST /api/outlook/scenario/      ScenarioProjectionView
  - GET /api/outlook/player-search/  PlayerSearchView
  - _fit_grade() helper
"""

from django.test import TestCase
from django.urls import reverse

from core.models import (
    Player,
    PlayerSeasonProjection,
    Season,
    Team,
    TeamRosterFit,
    TeamSeasonProjection,
    TeamSeasonRatings,
)
from api.outlook_views import _fit_grade


# ── Fixture helpers ─────────────────────────────────────────────────────────


def _make_season(year=2025):
    return Season.objects.create(
        year=year,
        display_name=f"{year - 1}-{str(year)[2:]}",
        is_current=True,
    )


def _make_team(slug="connecticut", name="Connecticut"):
    return Team.objects.create(slug=slug, name=name)


def _make_ratings(team, season, adj_o=114.0, adj_d=99.0):
    return TeamSeasonRatings.objects.create(
        team=team,
        season=season,
        wins=20,
        losses=5,
        games_played=25,
        rank_adj_em=4,
        adj_em=adj_o - adj_d,
        adj_o=adj_o,
        adj_d=adj_d,
        adj_tempo=68.0,
        adj_efg_pct=52.0,
    )


def _make_player(n=1):
    return Player.objects.create(
        espn_athlete_id=f"test_athlete_{n}",
        display_name=f"Test Player {n}",
        short_name=f"T. Player{n}",
        position="G",
    )


def _make_player_projection(player, team, season, obpr=3.0, dbpr=1.5, rank=1, rtype="returner"):
    return PlayerSeasonProjection.objects.create(
        player=player,
        team=team,
        from_season=season,
        projected_season_year=season.year + 1,
        recruitment_type=rtype,
        projected_obpr=obpr,
        projected_dbpr=dbpr,
        projected_bpr=obpr + dbpr,
        minutes_share_p2=0.5,
        mpg_p2=20.0,
        role_bucket="G",
        projection_uncertainty=0.3,
        rotation_rank=rank,
        n_prior_seasons=2,
    )


def _make_team_projection(team, season, adj_o=114.0, adj_d=99.0):
    return TeamSeasonProjection.objects.create(
        team=team,
        from_season=season,
        projected_season_year=season.year + 1,
        base_team_offense=1.5,
        base_team_defense=0.75,
        base_team_roster_strength=2.25,
        returner_minutes_fraction=0.55,
        continuity_score=55.0,
        continuity_value_score=58.0,
        continuity_adjustment_off=0.5,
        continuity_adjustment_def=0.5,
        transfer_dependence_score=25.0,
        transfer_fit_risk_score=0.04,
        projected_adj_o=adj_o,
        projected_adj_d=adj_d,
        projected_adj_em=adj_o - adj_d,
        team_projection_uncertainty=0.28,
        projected_adj_o_low=adj_o - 3,
        projected_adj_o_high=adj_o + 3,
        projected_adj_d_low=adj_d - 3,
        projected_adj_d_high=adj_d + 3,
        projected_adj_em_low=(adj_o - 3) - (adj_d + 3),
        projected_adj_em_high=(adj_o + 3) - (adj_d - 3),
        projected_national_rank=5,
        national_rank_range_low=2,
        national_rank_range_high=10,
        projected_offense_rank=3,
        offense_rank_range_low=1,
        offense_rank_range_high=7,
        projected_defense_rank=12,
        defense_rank_range_low=6,
        defense_rank_range_high=20,
    )


def _make_roster_fit(team, season):
    return TeamRosterFit.objects.create(
        team=team,
        from_season=season,
        projected_season_year=season.year + 1,
        n_players=8,
        overall_fit_score=70.0,
        offensive_fit_score=72.0,
        defensive_fit_score=68.0,
        adjusted_off_fit=74.0,
        adjusted_def_fit=70.0,
        adjusted_overall_fit=72.0,
        has_team_style_data=True,
        offensive_strengths=["shooting_fit", "creation_fit"],
        offensive_weaknesses=["off_rebounding_fit"],
        defensive_strengths=["rim_protection_fit"],
        defensive_weaknesses=["perimeter_defense_fit"],
    )


# ── Unit tests: _fit_grade ───────────────────────────────────────────────────


class FitGradeHelperTests(TestCase):
    """Tests for the _fit_grade() helper function."""

    def _assert_grade(self, score, expected_letter, expected_label):
        result = _fit_grade(score)
        self.assertEqual(result["letter"], expected_letter, f"score={score}")
        self.assertEqual(result["label"], expected_label, f"score={score}")
        self.assertEqual(result["score"], round(score, 1))

    def test_a_plus(self):
        self._assert_grade(85.0, "A+", "Elite")
        self._assert_grade(82.0, "A+", "Elite")

    def test_a(self):
        self._assert_grade(78.0, "A", "Elite")
        self._assert_grade(74.0, "A", "Elite")

    def test_b_plus(self):
        self._assert_grade(68.0, "B+", "Strong")
        self._assert_grade(66.0, "B+", "Strong")

    def test_b(self):
        self._assert_grade(60.0, "B", "Strong")
        self._assert_grade(58.0, "B", "Strong")

    def test_c_plus(self):
        self._assert_grade(52.0, "C+", "Solid")
        self._assert_grade(50.0, "C+", "Solid")

    def test_c(self):
        self._assert_grade(44.0, "C", "Solid")
        self._assert_grade(42.0, "C", "Solid")

    def test_d(self):
        self._assert_grade(36.0, "D", "Weak")
        self._assert_grade(34.0, "D", "Weak")

    def test_f(self):
        self._assert_grade(0.0, "F", "Poor")
        self._assert_grade(33.9, "F", "Poor")

    def test_none_returns_unknown(self):
        result = _fit_grade(None)
        self.assertEqual(result["letter"], "?")
        self.assertIsNone(result["score"])

    def test_boundary_below_a_plus(self):
        self._assert_grade(81.9, "A", "Elite")

    def test_score_is_rounded(self):
        result = _fit_grade(72.555)
        self.assertEqual(result["score"], 72.6)


# ── Integration tests: RosterOutlookView ────────────────────────────────────


class RosterOutlookViewTests(TestCase):
    """Tests for GET /api/outlook/<slug>/"""

    def setUp(self):
        self.season = _make_season(2025)
        self.team = _make_team("connecticut", "Connecticut")
        _make_ratings(self.team, self.season)

        # Two players
        p1 = _make_player(1)
        p2 = _make_player(2)
        self.pp1 = _make_player_projection(p1, self.team, self.season, obpr=4.0, dbpr=2.0, rank=1)
        self.pp2 = _make_player_projection(p2, self.team, self.season, obpr=2.0, dbpr=1.0, rank=2, rtype="transfer")

        self.proj = _make_team_projection(self.team, self.season)
        self.fit = _make_roster_fit(self.team, self.season)

    def _get(self, slug="connecticut", season=None):
        url = f"/api/outlook/{slug}/"
        if season:
            url += f"?season={season}"
        return self.client.get(url)

    def test_returns_200(self):
        res = self._get()
        self.assertEqual(res.status_code, 200)

    def test_team_metadata(self):
        data = self._get().json()
        self.assertEqual(data["team"]["slug"], "connecticut")
        self.assertEqual(data["team"]["name"], "Connecticut")

    def test_season_metadata(self):
        data = self._get().json()
        self.assertEqual(data["season"]["year"], 2025)
        self.assertEqual(data["season"]["projected_season_year"], 2026)

    def test_projection_shape(self):
        data = self._get().json()
        proj = data["projection"]
        self.assertIn("projected_adj_o", proj)
        self.assertIn("projected_adj_d", proj)
        self.assertIn("projected_adj_em", proj)
        self.assertIn("projected_national_rank", proj)
        self.assertIn("team_projection_uncertainty", proj)
        self.assertIn("continuity_score", proj)
        self.assertIn("transfer_dependence_score", proj)
        self.assertIn("transfer_fit_risk_score", proj)

    def test_players_list(self):
        data = self._get().json()
        players = data["players"]
        self.assertEqual(len(players), 2)
        # Sorted by rotation_rank
        self.assertEqual(players[0]["rotation_rank"], 1)
        self.assertEqual(players[1]["rotation_rank"], 2)

    def test_player_fields(self):
        data = self._get().json()
        p = data["players"][0]
        for field in ["player_id", "player_name", "position", "projected_obpr",
                      "projected_dbpr", "projected_bpr", "minutes_share_p2",
                      "mpg_p2", "role_bucket", "recruitment_type",
                      "projection_uncertainty", "rotation_rank", "n_prior_seasons"]:
            self.assertIn(field, p, f"Missing field: {field}")

    def test_player_recruitment_types(self):
        data = self._get().json()
        types = {p["recruitment_type"] for p in data["players"]}
        self.assertIn("returner", types)
        self.assertIn("transfer", types)

    def test_fit_block(self):
        data = self._get().json()
        fit = data["fit"]
        self.assertIsNotNone(fit)
        self.assertIn("offensive_fit_score", fit)
        self.assertIn("adjusted_off_fit", fit)
        self.assertIn("off_grade", fit)
        self.assertIn("def_grade", fit)

    def test_fit_grade_computed(self):
        data = self._get().json()
        off_grade = data["fit"]["off_grade"]
        # adjusted_off_fit=74.0 → A grade
        self.assertEqual(off_grade["letter"], "A")
        self.assertEqual(off_grade["score"], 74.0)

    def test_fit_strengths_weaknesses(self):
        data = self._get().json()
        fit = data["fit"]
        self.assertIn("shooting_fit", fit["offensive_strengths"])
        self.assertIn("off_rebounding_fit", fit["offensive_weaknesses"])

    def test_invalid_slug_returns_404(self):
        res = self._get("no-such-team")
        self.assertEqual(res.status_code, 404)

    def test_no_projection_returns_404(self):
        other_team = _make_team("auburn", "Auburn")
        res = self._get("auburn")
        self.assertEqual(res.status_code, 404)

    def test_season_filter(self):
        res = self._get(season=2025)
        self.assertEqual(res.status_code, 200)

    def test_wrong_season_returns_404(self):
        res = self._get(season=1999)
        self.assertEqual(res.status_code, 404)

    def test_no_fit_returns_none(self):
        # Remove the fit and check fit=null in response
        self.fit.delete()
        data = self._get().json()
        self.assertIsNone(data["fit"])


# ── Integration tests: RosterOutlookView URL ordering ───────────────────────


class OutlookUrlOrderingTests(TestCase):
    """Ensure 'scenario' and 'player-search' don't get matched as slugs."""

    def test_scenario_path_not_matched_as_slug(self):
        # GET to scenario URL should not 404 as team slug; it should POST-only → 405
        res = self.client.get("/api/outlook/scenario/")
        self.assertNotEqual(res.status_code, 200, "GET /scenario/ should not return 200")
        # DRF returns 405 Method Not Allowed for wrong method on APIView
        self.assertEqual(res.status_code, 405)

    def test_player_search_path_not_matched_as_slug(self):
        # player-search with empty q → should return 200 with [] (or 200)
        # Either way, it should NOT be treated as a slug lookup (which would be 404)
        res = self.client.get("/api/outlook/player-search/?q=abc")
        # Could be 200 or redirect; what it must NOT be is a TeamSeasonProjection 404
        self.assertIn(res.status_code, [200, 400], "player-search should be handled by PlayerSearchView")


# ── Integration tests: ScenarioProjectionView ───────────────────────────────


class ScenarioProjectionViewTests(TestCase):
    """Tests for POST /api/outlook/scenario/"""

    def setUp(self):
        self.season = _make_season(2025)
        self.team = _make_team("connecticut", "Connecticut")
        _make_ratings(self.team, self.season, adj_o=114.0, adj_d=99.0)
        # Need some stored projections for D1 context (avg of base_off/def)
        _make_team_projection(self.team, self.season, adj_o=114.0, adj_d=99.0)

    def _post(self, body):
        return self.client.post(
            "/api/outlook/scenario/",
            data=body,
            content_type="application/json",
        )

    def _valid_body(self, n_players=3):
        players = []
        for i in range(n_players):
            players.append({
                "player_id": 100 + i,
                "player_name": f"Player {i}",
                "projected_obpr": 3.0,
                "projected_dbpr": 1.5,
                "projected_bpr": 4.5,
                "minutes_share": 1.0,
                "recruitment_type": "returner",
                "projection_uncertainty": 0.3,
            })
        return {
            "from_season_year": 2025,
            "team_slug": "connecticut",
            "players": players,
        }

    def test_valid_request_returns_200(self):
        res = self._post(self._valid_body())
        self.assertEqual(res.status_code, 200)

    def test_response_shape(self):
        data = self._post(self._valid_body()).json()
        for key in [
            "projected_adj_o", "projected_adj_d", "projected_adj_em",
            "projected_adj_em_low", "projected_adj_em_high",
            "approx_national_rank", "team_projection_uncertainty",
            "returner_minutes_fraction", "continuity_value_score",
            "transfer_dependence_score", "transfer_fit_risk_score",
        ]:
            self.assertIn(key, data, f"Missing key: {key}")

    def test_missing_season_returns_400(self):
        body = self._valid_body()
        del body["from_season_year"]
        res = self._post(body)
        self.assertEqual(res.status_code, 400)

    def test_missing_team_slug_returns_400(self):
        body = self._valid_body()
        del body["team_slug"]
        res = self._post(body)
        self.assertEqual(res.status_code, 400)

    def test_empty_players_returns_400(self):
        body = self._valid_body()
        body["players"] = []
        res = self._post(body)
        self.assertEqual(res.status_code, 400)

    def test_invalid_season_returns_404(self):
        body = self._valid_body()
        body["from_season_year"] = 1890
        res = self._post(body)
        self.assertEqual(res.status_code, 404)

    def test_invalid_team_slug_returns_404(self):
        body = self._valid_body()
        body["team_slug"] = "no-such-team"
        res = self._post(body)
        self.assertEqual(res.status_code, 404)

    def test_projected_values_are_floats(self):
        data = self._post(self._valid_body()).json()
        for key in ["projected_adj_o", "projected_adj_d", "projected_adj_em"]:
            self.assertIsInstance(data[key], float)

    def test_approx_rank_is_integer(self):
        data = self._post(self._valid_body()).json()
        self.assertIsInstance(data["approx_national_rank"], int)
        self.assertGreaterEqual(data["approx_national_rank"], 1)

    def test_uncertainty_in_range(self):
        data = self._post(self._valid_body()).json()
        u = data["team_projection_uncertainty"]
        self.assertGreaterEqual(u, 0.0)
        self.assertLessEqual(u, 1.0)

    def test_single_player_scenario(self):
        res = self._post(self._valid_body(n_players=1))
        self.assertEqual(res.status_code, 200)

    def test_returner_minutes_fraction_in_range(self):
        data = self._post(self._valid_body()).json()
        fraction = data["returner_minutes_fraction"]
        self.assertGreaterEqual(fraction, 0.0)
        self.assertLessEqual(fraction, 1.0)

    def test_all_transfers_scenario(self):
        """All transfers → high transfer_dependence_score."""
        body = self._valid_body(n_players=3)
        for p in body["players"]:
            p["recruitment_type"] = "transfer"
        data = self._post(body).json()
        self.assertGreater(data["transfer_dependence_score"], 0.0)


# ── Integration tests: PlayerSearchView ─────────────────────────────────────


class PlayerSearchViewTests(TestCase):
    """Tests for GET /api/outlook/player-search/"""

    def setUp(self):
        self.season = _make_season(2025)
        self.team = _make_team("connecticut", "Connecticut")

        # Players with recognizable names
        p1 = Player.objects.create(
            espn_athlete_id="search_001",
            display_name="Alex Johnson",
            short_name="A. Johnson",
            position="G",
        )
        p2 = Player.objects.create(
            espn_athlete_id="search_002",
            display_name="Alex Williams",
            short_name="A. Williams",
            position="F",
        )
        p3 = Player.objects.create(
            espn_athlete_id="search_003",
            display_name="Chris Smith",
            short_name="C. Smith",
            position="C",
        )
        _make_player_projection(p1, self.team, self.season, obpr=3.0, rank=1)
        _make_player_projection(p2, self.team, self.season, obpr=2.0, rank=2)
        _make_player_projection(p3, self.team, self.season, obpr=1.5, rank=3)

    def _get(self, q="", season=None):
        params = f"?q={q}"
        if season:
            params += f"&season={season}"
        return self.client.get(f"/api/outlook/player-search/{params}")

    def test_short_query_returns_empty_list(self):
        res = self._get("a")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])

    def test_empty_query_returns_empty_list(self):
        res = self._get("")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])

    def test_matching_query(self):
        res = self._get("Alex", season=2025)
        self.assertEqual(res.status_code, 200)
        players = res.json()
        self.assertEqual(len(players), 2)
        names = {p["player_name"] for p in players}
        self.assertIn("Alex Johnson", names)
        self.assertIn("Alex Williams", names)

    def test_case_insensitive(self):
        res = self._get("alex", season=2025)
        self.assertEqual(len(res.json()), 2)

    def test_no_match_returns_empty(self):
        res = self._get("Zzzxxx", season=2025)
        self.assertEqual(res.json(), [])

    def test_result_fields(self):
        res = self._get("Chris", season=2025)
        player = res.json()[0]
        for field in ["player_id", "player_name", "position", "team_name",
                      "projected_bpr", "role_bucket", "recruitment_type",
                      "minutes_share_p2", "mpg_p2", "rotation_rank"]:
            self.assertIn(field, player, f"Missing field: {field}")

    def test_results_sorted_by_bpr_desc(self):
        res = self._get("Alex", season=2025)
        bprs = [p["projected_bpr"] for p in res.json()]
        self.assertEqual(bprs, sorted(bprs, reverse=True))

    def test_max_25_results(self):
        # Create 30 players with matching names
        for i in range(30):
            p = Player.objects.create(
                espn_athlete_id=f"bulk_{i}",
                display_name=f"Testname Player{i}",
                short_name=f"T. Player{i}",
                position="G",
            )
            _make_player_projection(p, self.team, self.season, rank=i + 10)
        res = self._get("Testname", season=2025)
        self.assertLessEqual(len(res.json()), 25)

    def test_no_season_param_still_returns_results(self):
        # Without explicit season, uses default (most recent with projections)
        res = self._get("Alex")
        self.assertEqual(res.status_code, 200)
