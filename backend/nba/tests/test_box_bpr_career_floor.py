"""
nba_compute_box_bpr's --career-floor sets the oldest season in the
career-stabilized stats window. Default 2016, the value it used to hard-code.

The run is stopped at the career-map call: no database.
"""

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase

MOD = "nba.management.commands.nba_compute_box_bpr"


class _AtCareerMap(Exception):
    pass


class CareerFloorTests(SimpleTestCase):

    def setUp(self):
        stats = mock.MagicMock()
        stats.objects.filter.return_value.select_related.return_value.values.return_value = [{"player_id": 1}]
        self.career = mock.MagicMock(side_effect=_AtCareerMap)
        for target, value in {
            "NBAPlayerSeasonStats": stats,
            "compute_opp_quality_map": mock.MagicMock(return_value={}),
            "compute_team_adj_em_map": mock.MagicMock(return_value={}),
            "build_career_stats_map": self.career,
        }.items():
            patcher = mock.patch(f"{MOD}.{target}", value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _floor(self, *args):
        with self.assertRaises(_AtCareerMap):
            call_command("nba_compute_box_bpr", "--season", "2026", "--dry-run", *args, stdout=StringIO())
        return self.career.call_args.kwargs

    def test_default_floor_is_2016(self):
        self.assertEqual(self._floor(), {"target_season_year": 2026, "min_season_year": 2016})

    def test_career_floor_option(self):
        self.assertEqual(self._floor("--career-floor", "2001")["min_season_year"], 2001)
