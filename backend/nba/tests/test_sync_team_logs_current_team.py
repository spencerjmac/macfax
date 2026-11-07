"""
H.0a: nba_sync_team_logs sets a player's current_team and is_active only
when the season being synced is the season in play. Re-syncing an old season
(Phase H) must not move today's players back to their old teams or
reactivate retired ones; a player first seen in an old season starts
inactive with no team.

Real test database; NBA.com is stood in for.
"""

from datetime import date
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from nba.models import NBAGame, NBAPlayer, NBAPlayerGameStats, NBASeason, NBATeam

MOD = "nba.management.commands.nba_sync_team_logs"
IN_PLAY = 2027


def _box_row(player_id, team_id):
    return SimpleNamespace(
        player_id=player_id, team_id=team_id, minutes_clock="30:00", plus_minus=4,
        **{k: 1 for k in ("pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov",
                          "fgm", "fga", "fg3m", "fg3a", "ftm", "fta")})


class CurrentTeamOnlyFromSeasonInPlayTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.old_team = NBATeam.objects.create(
            nba_team_id=1610612742, slug="dallas-mavericks", name="Dallas Mavericks",
            abbreviation="DAL", city="Dallas", conference="West", division="Southwest")
        cls.new_team = NBATeam.objects.create(
            nba_team_id=1610612747, slug="los-angeles-lakers", name="Los Angeles Lakers",
            abbreviation="LAL", city="Los Angeles", conference="West", division="Pacific")
        cls.retired_team = NBATeam.objects.create(
            nba_team_id=1610612738, slug="boston-celtics", name="Boston Celtics",
            abbreviation="BOS", city="Boston", conference="East", division="Atlantic")
        cls.traded = NBAPlayer.objects.create(
            player_id=1629029, name="Traded Star", current_team=cls.new_team, is_active=True)
        cls.retired = NBAPlayer.objects.create(
            player_id=1717, name="Retired Vet", current_team=None, is_active=False)
        for year, display in ((2019, "2018-19"), (IN_PLAY, "2026-27")):
            NBAGame.objects.create(
                game_id=f"002{year % 100:02d}00001", date=date(year - 1, 11, 1),
                season=NBASeason.objects.create(year=year, display_name=display),
                home_team=cls.old_team, away_team=cls.retired_team, home_score=100,
                away_score=90, season_type="regular", counts_toward_regular_season=True,
                status="Final")

    def _sync(self, year, rows):
        provider = mock.MagicMock()
        provider.get_box_score_traditional.return_value = (None, rows)
        provider.get_all_players.return_value = []
        with mock.patch(f"{MOD}.NBAApiProvider", return_value=provider), \
                mock.patch(f"{MOD}.season_in_play", return_value=IN_PLAY, create=True):
            call_command("nba_sync_team_logs", "--season", str(year), "--sleep", "0", stdout=StringIO())

    def test_past_season_leaves_current_team_and_active_flag(self):
        self._sync(2019, [_box_row(1629029, 1610612742), _box_row(1717, 1610612738),
                          _box_row(9999, 1610612742)])

        self.traded.refresh_from_db()
        self.retired.refresh_from_db()
        self.assertEqual((self.traded.current_team, self.traded.is_active), (self.new_team, True))
        self.assertEqual((self.retired.current_team, self.retired.is_active), (None, False))
        first_seen = NBAPlayer.objects.get(player_id=9999)
        self.assertEqual((first_seen.current_team, first_seen.is_active), (None, False))
        # The box rows themselves still carry the team they played for then.
        self.assertEqual(NBAPlayerGameStats.objects.get(player=self.traded).team, self.old_team)

    def test_season_in_play_still_sets_current_team_and_active_flag(self):
        self._sync(IN_PLAY, [_box_row(1629029, 1610612742), _box_row(1717, 1610612738)])

        self.traded.refresh_from_db()
        self.retired.refresh_from_db()
        self.assertEqual((self.traded.current_team, self.traded.is_active), (self.old_team, True))
        self.assertEqual((self.retired.current_team, self.retired.is_active), (self.retired_team, True))
