"""
Phase P P.4a: RAPM lineup observations group stints by their stored lineup
window. Several lineup changes inside one clock second leave zero-length
windows with identical (period, clock_start, clock_end); grouped by clock,
two such fives merge into one 10-v-10 group and are dropped.
"""

from datetime import date
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from nba.analytics.rapm import build_nba_observations
from nba.models import NBAPlayerGameStint

HOME_TEAM_ID, AWAY_TEAM_ID = 1610612737, 1610612738
GAME_PK = 7

_GAME = SimpleNamespace(
    pk=GAME_PK, game_id="0029900001", date=date(2026, 1, 1),
    home_team=SimpleNamespace(nba_team_id=HOME_TEAM_ID),
    away_team=SimpleNamespace(nba_team_id=AWAY_TEAM_ID),
)


def _stint(player_id, team_id, window_index, pts_scored, pts_allowed):
    # Two field-goal attempts a side so each window clears MIN_OBS_POSS.
    return SimpleNamespace(
        player=SimpleNamespace(player_id=player_id),
        game=_GAME, game_id=GAME_PK,
        team=SimpleNamespace(nba_team_id=team_id),
        period=1, clock_start_secs=300, clock_end_secs=300, window_index=window_index,
        pts_scored=pts_scored, pts_allowed=pts_allowed,
        team_fga=2, team_oreb=0, team_tov=0, team_fta=0,
    )


def _two_zero_length_windows(first_window, second_window):
    """Two fives on court within the same second: home 101 is replaced by 106."""
    stints = []
    for window, home_ids, home_pts in ((first_window, [101, 102, 103, 104, 105], 2),
                                       (second_window, [106, 102, 103, 104, 105], 3)):
        stints += [_stint(pid, HOME_TEAM_ID, window, home_pts, 0) for pid in home_ids]
        stints += [_stint(pid, AWAY_TEAM_ID, window, 0, home_pts) for pid in range(201, 206)]
    return stints


class WindowGroupingTests(SimpleTestCase):

    def _observations(self, stints):
        objects = mock.MagicMock()
        objects.filter.return_value.select_related.return_value.only.return_value = stints
        with mock.patch.object(NBAPlayerGameStint, "objects", objects):
            return build_nba_observations(2026)

    def test_zero_length_windows_in_the_same_second_stay_separate(self):
        obs = self._observations(_two_zero_length_windows(5, 6))

        self.assertEqual(len(obs), 2)
        self.assertEqual(sorted(o["home_player_ids"] for o in obs),
                         [[101, 102, 103, 104, 105], [106, 102, 103, 104, 105]])
        self.assertEqual(sorted(o["home_pts"] for o in obs), [2, 3])

    def test_rows_without_a_window_keep_the_clock_key(self):
        # Older rows: grouped by clock, the two fives merge into 10 v 10 and drop.
        obs = self._observations(_two_zero_length_windows(None, None))

        self.assertEqual(obs, [])
