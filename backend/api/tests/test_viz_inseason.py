"""
NCAA viz endpoints during the regular season.

Before Selection Sunday a season has only full-season rating rows
(is_pre_tournament=False). The viz endpoints used to read only the Selection
Sunday snapshot, so every chart 404'd ("No teams found") until March.
"""
from django.urls import reverse

from api.tests.base import IsolatedCacheTestCase
from ncaa.models import Season, Team, TeamSeasonMetrics, TeamSeasonRatings

VIZ_URLS = ["viz-landscape", "viz-trapezoid", "viz-crystal-ball", "viz-cinderella"]


def _rating(team, season, adj_em, pre):
    return TeamSeasonRatings.all_objects.create(
        team=team,
        season=season,
        is_pre_tournament=pre,
        adj_o=105.0 + adj_em / 2,
        adj_d=105.0 - adj_em / 2,
        adj_em=adj_em,
        adj_tempo=68.0 + adj_em / 10,
        games_played=2,
        wins=1,
        losses=1,
    )


class VizInSeasonTests(IsolatedCacheTestCase):
    def setUp(self):
        super().setUp()
        self.season = Season.objects.create(year=2027, display_name="2026-27", is_current=True)
        self.teams = [
            Team.objects.create(slug=f"team-{i}", name=f"Team {i}", is_d1=True) for i in range(6)
        ]
        for i, team in enumerate(self.teams):
            _rating(team, self.season, adj_em=float(10 - 3 * i), pre=False)
            TeamSeasonMetrics.all_objects.create(team=team, season=self.season, is_pre_tournament=False)

    def test_regular_season_uses_full_season_rows(self):
        for name in VIZ_URLS:
            with self.subTest(endpoint=name):
                response = self.client.get(reverse(name), {"season": "2027"})
                self.assertEqual(response.status_code, 200, response.content[:300])
                self.assertEqual(len(response.json()["teams"]), len(self.teams))

    def test_selection_sunday_snapshot_wins_when_present(self):
        # Snapshot only for the first two teams, with a distinct rating
        for team in self.teams[:2]:
            _rating(team, self.season, adj_em=-20.0, pre=True)

        response = self.client.get(reverse("viz-landscape"), {"season": "2027"})

        self.assertEqual(response.status_code, 200)
        teams = response.json()["teams"]
        self.assertEqual(len(teams), 2)
        self.assertTrue(all(abs(t["net"] - -20.0) < 0.01 for t in teams))
