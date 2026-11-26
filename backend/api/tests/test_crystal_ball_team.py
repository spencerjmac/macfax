"""
Crystal Ball single-team scoring (?team=<slug>) and the basis flag.

The team page reads its checklist from this endpoint, so a team scored alone
must match its row in the full Crystal Ball list (season context is always
built from every D1 team).
"""
from django.urls import reverse

from api.crystal_ball_views import wab_bar
from api.tests.base import IsolatedCacheTestCase
from ncaa.models import Season, Team, TeamSeasonMetrics, TeamSeasonRatings


def _rating(team, season, adj_em, pre, wab=None, games=2):
    return TeamSeasonRatings.all_objects.create(
        team=team,
        season=season,
        is_pre_tournament=pre,
        adj_o=105.0 + adj_em / 2,
        adj_d=105.0 - adj_em / 2,
        adj_em=adj_em,
        adj_tempo=68.0 + adj_em / 10,
        games_played=games,
        wins=games - 1,
        losses=1,
        wab=wab,
    )


class CrystalBallTeamTests(IsolatedCacheTestCase):
    def setUp(self):
        super().setUp()
        self.season = Season.objects.create(year=2027, display_name="2026-27", is_current=True)
        self.teams = [
            Team.objects.create(slug=f"team-{i}", name=f"Team {i}", is_d1=True) for i in range(6)
        ]
        for i, team in enumerate(self.teams):
            _rating(team, self.season, adj_em=float(10 - 3 * i), pre=False, wab=1.0 - i * 0.5)
            TeamSeasonMetrics.all_objects.create(team=team, season=self.season, is_pre_tournament=False)

    def _get(self, **params):
        return self.client.get(reverse("viz-crystal-ball"), {"season": "2027", **params})

    def test_team_param_matches_full_list_row(self):
        full = {t["team_slug"]: t for t in self._get().json()["teams"]}
        for team in self.teams:
            with self.subTest(team=team.slug):
                response = self._get(team=team.slug)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["total_teams"], 1)
                self.assertEqual(body["teams"][0]["checklist"], full[team.slug]["checklist"])
                self.assertEqual(body["teams"][0]["rank"], full[team.slug]["rank"])

    def test_basis_live_without_snapshot(self):
        self.assertEqual(self._get().json()["basis"], "live")
        self.assertEqual(self._get(team="team-0").json()["basis"], "live")

    def test_basis_selection_sunday_with_snapshot(self):
        for i, team in enumerate(self.teams):
            _rating(team, self.season, adj_em=-5.0 - i, pre=True)
        body = self._get(team="team-0").json()
        self.assertEqual(body["basis"], "selection_sunday")
        self.assertEqual(body["teams"][0]["adj_em"], -5.0)

    def test_identical_snapshot_ratings_do_not_divide_by_zero(self):
        # Every team equal -> zero std for AdjO/AdjD/AdjEM; Balanced Dominance must not crash
        for team in self.teams:
            _rating(team, self.season, adj_em=-5.0, pre=True)
        response = self._get(team="team-0")
        self.assertEqual(response.status_code, 200)
        items = {i["key"]: i for i in response.json()["teams"][0]["checklist"]["items"]}
        self.assertIn("balanced_dominance", items)

    def test_unknown_team_404(self):
        self.assertEqual(self._get(team="no-such-team").status_code, 404)

    def test_wab_bar_scales_with_games(self):
        self.assertAlmostEqual(wab_bar(2), 0.3125)
        self.assertAlmostEqual(wab_bar(32), 5.0)
        self.assertAlmostEqual(wab_bar(40), 5.0)
        wab = {i["key"]: i for i in self._get(team="team-0").json()["teams"][0]["checklist"]["items"]}["wab"]
        self.assertEqual(wab["threshold"], "> 0.31")
        self.assertTrue(wab["pass"])  # 1.0 > 0.3125
