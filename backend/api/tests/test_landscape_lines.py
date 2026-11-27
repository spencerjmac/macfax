"""
NCAA Efficiency Landscape tier lines: reference = average Adj EM of the top 3 D1 teams,
lines = reference - 4.6 / 8.4 / 15.3 rounded up to the 0.1 grid (api/landscape_lines.py).
"""
from django.test import SimpleTestCase
from django.urls import reverse

from api.landscape_lines import (
    FINAL_FOUR_DELTA,
    HIT_OR_MISS_DELTA,
    TITLE_FAVORITES_DELTA,
    landscape_lines,
    landscape_reference,
)
from api.tests.base import IsolatedCacheTestCase
from ncaa.models import Season, Team, TeamSeasonRatings

# Selection Sunday 2015, prod values to 2 decimals: Kentucky, Wisconsin, Arizona, Villanova,
# Virginia, Duke (the champion, exactly 4.6 below the reference in the API's 0.1 units).
SS_2015 = [36.61, 33.73, 31.14, 30.28, 29.35, 29.19]


class LandscapeReferenceTests(SimpleTestCase):
    def test_reference_is_top3_average_of_rounded_values(self):
        # 36.6, 33.7, 31.1 -> 33.8 (the unrounded average would be 33.83)
        self.assertAlmostEqual(landscape_reference(SS_2015), 33.8, places=9)

    def test_reference_ignores_input_order(self):
        self.assertAlmostEqual(landscape_reference(reversed(SS_2015)), 33.8, places=9)

    def test_reference_with_fewer_than_three_teams(self):
        self.assertAlmostEqual(landscape_reference([10.04, 4.0]), 7.0, places=9)
        self.assertAlmostEqual(landscape_reference([5.0]), 5.0, places=9)

    def test_reference_needs_a_team(self):
        with self.assertRaises(ValueError):
            landscape_reference([])


class LandscapeLinesTests(SimpleTestCase):
    def test_deltas(self):
        self.assertEqual((TITLE_FAVORITES_DELTA, FINAL_FOUR_DELTA, HIT_OR_MISS_DELTA), (4.6, 8.4, 15.3))

    def test_lines_2015(self):
        lines = landscape_lines(SS_2015)["lines"]
        self.assertEqual(lines, {"title": 29.2, "final4": 25.4, "hit_miss": 18.5})

    def test_team_exactly_on_title_line_stays_above(self):
        # 33.800000000000004 - 4.6 = 29.200000000000003: a plain ceil would give 29.3 and drop Duke
        lines = landscape_lines(SS_2015)["lines"]
        self.assertGreaterEqual(round(29.19, 1), lines["title"])

    def test_lines_round_up_to_tenth(self):
        # reference (32.8 + 28.8 + 25.8) / 3 = 29.1333...; a team is above a line exactly when its
        # 0.1-rounded net >= reference - delta, which on the 0.1 grid means >= the rounded-up line
        out = landscape_lines([32.8, 28.8, 25.8, 1.0])
        self.assertAlmostEqual(out["reference"], 29.1333333, places=6)
        self.assertEqual(out["lines"], {"title": 24.6, "final4": 20.8, "hit_miss": 13.9})

    def test_negative_line(self):
        self.assertEqual(landscape_lines([10.0, 10.0, 10.0])["lines"]["hit_miss"], -5.3)


def _rating(team, season, adj_em, pre):
    return TeamSeasonRatings.all_objects.create(
        team=team,
        season=season,
        is_pre_tournament=pre,
        adj_o=105.0 + adj_em / 2,
        adj_d=105.0 - adj_em / 2,
        adj_em=adj_em,
        adj_tempo=68.0,
        games_played=30,
        wins=20,
        losses=10,
    )


class LandscapeApiLinesTests(IsolatedCacheTestCase):
    def setUp(self):
        super().setUp()
        self.season = Season.objects.create(year=2015, display_name="2014-15", is_current=True)
        self.teams = [
            Team.objects.create(slug=f"team-{i}", name=f"Team {i}", is_d1=True)
            for i in range(len(SS_2015))
        ]

    def _get(self, **params):
        response = self.client.get(reverse("viz-landscape"), {"season": "2015", **params})
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_selection_sunday_lines(self):
        for team, em in zip(self.teams, SS_2015):
            _rating(team, self.season, em, pre=True)
        data = self._get()
        self.assertTrue(data["is_pre_tournament"])
        self.assertAlmostEqual(data["reference_net"], 33.8, places=2)
        self.assertEqual(data["lines"], {"title": 29.2, "final4": 25.4, "hit_miss": 18.5})
        self.assertEqual(
            data["defaults"], {"title_delta": 4.6, "final4_delta": 8.4, "hit_miss_delta": 15.3}
        )
        duke = data["teams"][-1]
        self.assertGreaterEqual(duke["net"], data["lines"]["title"])

    def test_lines_come_from_all_teams_before_top_n_filter(self):
        for team, em in zip(self.teams, SS_2015):
            _rating(team, self.season, em, pre=True)
        full = self._get()
        top2 = self._get(top=2)
        self.assertEqual(len(top2["teams"]), 2)
        self.assertEqual(top2["lines"], full["lines"])
        self.assertEqual(top2["reference_net"], full["reference_net"])

    def test_in_season_rows_flagged(self):
        for team, em in zip(self.teams, SS_2015):
            _rating(team, self.season, em, pre=False)
        data = self._get()
        self.assertFalse(data["is_pre_tournament"])
        self.assertEqual(data["lines"], {"title": 29.2, "final4": 25.4, "hit_miss": 18.5})
