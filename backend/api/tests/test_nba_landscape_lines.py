"""
NBA Efficiency Landscape tier lines: each line is halfway between the Nth and (N+1)th team's adj_net
(Champion top 7, Contender top 10, Playoff top 15; api/nba_landscape_config.py).
"""
from django.test import SimpleTestCase
from django.urls import reverse

from api.nba_landscape_config import (
    CHAMPION_RANK,
    CONTENDER_RANK,
    PLAYOFF_RANK,
    landscape_lines,
    rank_line,
)
from api.tests.base import IsolatedCacheTestCase
from nba.models import NBASeason, NBATeam, NBATeamSeasonRatings

# 30 distinct nets, 10.0 down to -19.0 in steps of 1.0, in scrambled order.
NETS_30 = [10.0 - i for i in range(30)]
SCRAMBLED = NETS_30[1::2] + NETS_30[::2]


class RankLineTests(SimpleTestCase):
    def test_ranks(self):
        self.assertEqual((CHAMPION_RANK, CONTENDER_RANK, PLAYOFF_RANK), (7, 10, 15))

    def test_midpoint_between_nth_and_next(self):
        # 7th = 4.0, 8th = 3.0
        self.assertEqual(rank_line(NETS_30, 7), 3.5)
        self.assertEqual(rank_line([5.0, 4.2, 1.0], 1), 4.6)

    def test_order_of_input_does_not_matter(self):
        self.assertEqual(rank_line(SCRAMBLED, 10), rank_line(NETS_30, 10))

    def test_exactly_top_n_above(self):
        for n in (7, 10, 15):
            line = rank_line(SCRAMBLED, n)
            self.assertEqual(sum(1 for v in SCRAMBLED if v > line), n)

    def test_tie_at_boundary_line_passes_through_both(self):
        nets = [9.0, 8.0, 7.0, 7.0, 1.0]
        self.assertEqual(rank_line(nets, 3), 7.0)

    def test_tie_inside_top_n_does_not_move_line(self):
        nets = [9.0, 9.0, 7.0, 5.0]
        self.assertEqual(rank_line(nets, 3), 6.0)

    def test_fewer_than_n_plus_one_teams(self):
        self.assertIsNone(rank_line([3.0] * 7, 7))
        self.assertIsNone(rank_line([], 1))
        self.assertEqual(rank_line([3.0] * 7 + [1.0], 7), 2.0)

    def test_negative_nets(self):
        self.assertEqual(rank_line([-1.0, -2.0, -4.0], 2), -3.0)

    def test_landscape_lines_shape(self):
        self.assertEqual(
            landscape_lines(SCRAMBLED),
            {
                "champion": {"n": 7, "net": 3.5},
                "contender": {"n": 10, "net": 0.5},
                "playoff": {"n": 15, "net": -4.5},
            },
        )

    def test_landscape_lines_short_season(self):
        lines = landscape_lines([5.0 - i for i in range(12)])
        self.assertEqual(lines["champion"], {"n": 7, "net": -1.5})
        self.assertEqual(lines["contender"], {"n": 10, "net": -4.5})
        self.assertEqual(lines["playoff"], {"n": 15, "net": None})

    def test_not_rounded(self):
        # 7th and 8th 0.0004 apart: a line rounded to 3 places (5.0) would put the 7th on it
        lines = landscape_lines([9.0] * 6 + [5.0004, 5.0] + [0.0] * 8)
        self.assertAlmostEqual(lines["champion"]["net"], 5.0002, places=9)


class NBALandscapeApiLinesTests(IsolatedCacheTestCase):
    def setUp(self):
        super().setUp()
        self.season = NBASeason.objects.create(year=2026, display_name="2025-26", is_current=True)

    def _team(self, i):
        return NBATeam.objects.create(
            nba_team_id=1610612700 + i, slug=f"team-{i}", name=f"Team {i}", abbreviation=f"T{i}",
            city=f"City {i}", conference="East" if i % 2 else "West", division="Atlantic",
        )

    def _rate(self, nets, season_type="regular"):
        for i, net in enumerate(nets):
            NBATeamSeasonRatings.objects.create(
                team=self._team(i) if season_type == "regular" else NBATeam.objects.get(slug=f"team-{i}"),
                season=self.season, season_type=season_type,
                adj_off=112.0 + net / 2, adj_def=112.0 - net / 2, adj_net=net,
                rank_adj_net=sorted(nets, reverse=True).index(net) + 1,
            )

    def _get(self, **params):
        response = self.client.get(reverse("viz-nba-landscape"), params)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_lines_and_ranks_in_response(self):
        self._rate(SCRAMBLED)
        data = self._get(season=2026)
        self.assertEqual(
            data["lines"],
            {
                "champion": {"n": 7, "net": 3.5},
                "contender": {"n": 10, "net": 0.5},
                "playoff": {"n": 15, "net": -4.5},
            },
        )
        self.assertNotIn("tier_lines", data)
        above = [t for t in data["teams"] if t["net"] > data["lines"]["champion"]["net"]]
        self.assertEqual(len(above), 7)

    def test_dots_plot_at_full_precision(self):
        # 7th (4.06) and 8th (4.0) are 0.06 apart, so the Champion line is 4.03. With o/d rounded to
        # 0.1 the 7th (114.03 / 109.97) would plot at 114.0 - 110.0 = 4.0, below its own line.
        nets = [10.0 - i for i in range(6)] + [4.06, 4.0] + [-i for i in range(8)]
        self._rate(nets)
        data = self._get(season=2026)
        line = data["lines"]["champion"]["net"]
        self.assertAlmostEqual(line, 4.03, places=9)
        above = [t for t in data["teams"] if t["o_rate"] - t["d_rate"] > line]
        self.assertEqual(sorted(t["rank"] for t in above), list(range(1, 8)))
        seventh = next(t for t in data["teams"] if t["rank"] == 7)
        self.assertAlmostEqual(seventh["o_rate"], 114.03, places=9)
        self.assertEqual(seventh["net"], 4.1)

    def test_current_season_by_default(self):
        self._rate(SCRAMBLED)
        self.assertEqual(self._get()["lines"]["contender"], {"n": 10, "net": 0.5})

    def test_playoff_rows_ignored(self):
        self._rate(SCRAMBLED)
        self._rate([50.0 - i for i in range(30)], season_type="playoffs")
        self.assertEqual(self._get(season=2026)["lines"]["champion"]["net"], 3.5)

    def test_short_season_leaves_line_out(self):
        self._rate([5.0 - i for i in range(12)])
        self.assertIsNone(self._get(season=2026)["lines"]["playoff"]["net"])
