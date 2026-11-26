"""W.Add to date: the GP / 30 scaling and the valued-row match for split-season players."""

from django.test import SimpleTestCase

from ncaa.analytics.market_value.to_date import SEASON_GAMES, is_valued_row, wins_added_to_date


class WinsAddedToDateTest(SimpleTestCase):
    def test_scales_by_games_over_season(self):
        self.assertEqual(SEASON_GAMES, 30)
        self.assertAlmostEqual(wins_added_to_date(6.0, 10), 2.0)
        self.assertAlmostEqual(wins_added_to_date(-1.5, 30), -1.5)

    def test_missing_inputs_give_none(self):
        self.assertIsNone(wins_added_to_date(None, 10))
        self.assertIsNone(wins_added_to_date(3.0, None))

    def test_valued_row_matches_minutes_share(self):
        # value computed from the 30.0-mpg row: share 0.75
        self.assertTrue(is_valued_row(0.75, 30.0))
        # the same player's other-team row (12.4 mpg) is not the valued one
        self.assertFalse(is_valued_row(0.75, 12.4))
        self.assertFalse(is_valued_row(None, 30.0))
