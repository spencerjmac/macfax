"""
Phase 2 task 2.2b: _load_priors sums a traded player's minutes over all his
regular-season rows, so his lambda tier reflects his full season. No database:
the season-stats queryset is stood in for.
"""

from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from nba.management.commands.nba_compute_final_bpr import (
    Command,
    LAMBDA_TIERS,
    _build_lambda_array,
)
from nba.models import NBAPlayerSeasonStats


def _row(nba_id, mpg, gp, box_o=1.0, box_d=0.5):
    return SimpleNamespace(player=SimpleNamespace(player_id=nba_id),
                           box_obpr=box_o, box_dbpr=box_d, mpg=mpg, gp=gp)


class TradedMinutesTests(SimpleTestCase):

    def _load(self, rows):
        objects = mock.MagicMock()
        objects.filter.return_value.select_related.return_value.only.return_value = rows
        with mock.patch.object(NBAPlayerSeasonStats, "objects", objects):
            cmd = Command()
            cmd.stdout = StringIO()
            return cmd._load_priors(2026)

    def test_traded_player_minutes_are_summed(self):
        # 30 mpg x 40 gp + 30 mpg x 30 gp = 2100: the top tier; either row alone is not.
        _, _, minutes = self._load([_row(7, 30.0, 40), _row(7, 30.0, 30), _row(8, 20.0, 50)])
        self.assertEqual(minutes, {7: 2100.0, 8: 1000.0})

    def test_traded_player_gets_the_tier_of_combined_minutes(self):
        _, _, minutes = self._load([_row(7, 30.0, 40), _row(7, 30.0, 30)])
        hi, mid, lo, fringe = LAMBDA_TIERS["A_conservative"]
        lam = _build_lambda_array([(7, 2026)], minutes, LAMBDA_TIERS["A_conservative"])
        self.assertEqual(list(lam), [hi, hi])
        # The last row alone (900 min) would have put him in the 600-1199 tier.
        last_row_only = _build_lambda_array([(7, 2026)], {7: 900.0}, LAMBDA_TIERS["A_conservative"])
        self.assertEqual(list(last_row_only), [lo, lo])
        self.assertNotEqual(lo, hi)

    def test_single_row_player_unchanged(self):
        prior_o, prior_d, minutes = self._load([_row(9, 25.0, 60, box_o=2.0, box_d=-1.0)])
        self.assertEqual(minutes, {9: 1500.0})
        self.assertEqual((prior_o, prior_d), ({9: 2.0}, {9: -1.0}))

    def test_missing_mpg_or_gp_counts_as_zero(self):
        _, _, minutes = self._load([_row(7, None, 40), _row(7, 30.0, None), _row(7, 10.0, 10)])
        self.assertEqual(minutes, {7: 100.0})
