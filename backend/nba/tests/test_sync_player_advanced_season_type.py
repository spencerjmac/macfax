"""
PO.4: nba_sync_player_advanced --season-type. playoffs asks NBA.com for
"Playoffs" on every LeagueDashPlayerStats call and updates only playoff
NBAPlayerSeasonStats rows; regular (default) asks for "Regular Season" and
updates only regular rows.

Real test database; the NBA.com endpoint is stood in for.
"""

from io import StringIO
from unittest import mock

import pandas as pd
from django.core.management import call_command
from django.test import TestCase

from nba.models import NBAPlayer, NBAPlayerSeasonStats, NBASeason, NBATeam

PLAYER_ID, TEAM_ID = 1628983, 1610612760


def _frame(e_off):
    return pd.DataFrame([{
        "PLAYER_ID": PLAYER_ID, "TEAM_ID": TEAM_ID, "POSS": 1000.0,
        "E_OFF_RATING": e_off, "E_DEF_RATING": 108.0, "E_NET_RATING": e_off - 108.0,
        "EFG_PCT": 0.55, "TS_PCT": 0.60, "USG_PCT": 0.30,
    }])


class AdvancedSyncSeasonTypeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        season = NBASeason.objects.create(year=2025, display_name="2024-25")
        team = NBATeam.objects.create(
            nba_team_id=TEAM_ID, slug="oklahoma-city-thunder", name="Oklahoma City Thunder",
            abbreviation="OKC", city="Oklahoma City", conference="West", division="Northwest")
        player = NBAPlayer.objects.create(player_id=PLAYER_ID, name="Test Player")
        cls.regular = NBAPlayerSeasonStats.objects.create(
            player=player, season=season, team=team, season_type="regular", gp=76, mpg=34.0)
        cls.playoffs = NBAPlayerSeasonStats.objects.create(
            player=player, season=season, team=team, season_type="playoffs", gp=23, mpg=36.0)

    def _run(self, *args):
        endpoint = mock.MagicMock()
        # NBA.com answers with a different E_OFF_RATING per season type.
        endpoint.side_effect = lambda **kw: mock.MagicMock(get_data_frames=lambda: [
            _frame(118.0 if kw["season_type_all_star"] == "Playoffs" else 121.0)])
        with mock.patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats", endpoint):
            call_command("nba_sync_player_advanced", "--season", "2025", "--sleep", "0", *args, stdout=StringIO())
        return [c.kwargs["season_type_all_star"] for c in endpoint.call_args_list]

    def test_playoffs_requests_playoffs_and_touches_only_playoff_rows(self):
        self.assertEqual(self._run("--season-type", "playoffs"), ["Playoffs"] * 3)
        self.playoffs.refresh_from_db()
        self.regular.refresh_from_db()
        self.assertEqual(self.playoffs.on_court_adj_o, 118.0)
        self.assertIsNone(self.regular.on_court_adj_o)

    def test_default_requests_regular_season_and_touches_only_regular_rows(self):
        self.assertEqual(self._run(), ["Regular Season"] * 3)
        self.playoffs.refresh_from_db()
        self.regular.refresh_from_db()
        self.assertEqual(self.regular.on_court_adj_o, 121.0)
        self.assertIsNone(self.playoffs.on_court_adj_o)
