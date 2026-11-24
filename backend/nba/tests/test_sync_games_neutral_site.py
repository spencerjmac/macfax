"""
nba_sync_games: neutral-site games keep their stored home team.

For neutral-site games (international games, NBA Cup knockouts in Las Vegas)
LeagueGameLog gives both teams' rows as "X @ Y". The old fallback read the home
team from whichever row came first, and NBA.com doesn't keep that order, so a
re-sync could swap home and away. A game already stored keeps its home team; a
new game still takes it from the first row's matchup.

Real test database; NBA.com is stood in for.
"""

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from nba.models import NBAGame, NBATeamGameStats, NBATeam
from nba.providers.base import RawLeagueGameLog

GAME = "0022600189"
IND, DEN = 1610612754, 1610612743


def _row(team_id, abbr, matchup, pts):
    return RawLeagueGameLog(
        game_id=GAME, date="2026-11-07", season_id="22026", team_id=team_id,
        team_abbreviation=abbr, is_home=False, matchup=matchup, wl="W" if pts > 110 else "L",
        pts=pts, fgm=40, fga=85, fg3m=12, fg3a=33, ftm=15, fta=20, oreb=10, dreb=33, tov=13)


IND_ROW = _row(IND, "IND", "IND @ DEN", 115)
DEN_ROW = _row(DEN, "DEN", "DEN @ IND", 109)


class NeutralSiteHomeTeamTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        NBATeam.objects.create(nba_team_id=IND, slug="indiana-pacers", name="Indiana Pacers",
                               abbreviation="IND", city="Indiana", conference="East", division="Central")
        NBATeam.objects.create(nba_team_id=DEN, slug="denver-nuggets", name="Denver Nuggets",
                               abbreviation="DEN", city="Denver", conference="West", division="Northwest")

    def _sync(self, rows):
        provider = mock.MagicMock()
        provider.get_league_game_log.return_value = rows
        with mock.patch("nba.management.commands.nba_sync_games.NBAApiProvider", return_value=provider):
            call_command("nba_sync_games", season=2027, stdout=StringIO())
        return NBAGame.objects.select_related("home_team", "away_team").get(game_id=GAME)

    def _assert_ind_home(self, game):
        self.assertEqual((game.home_team.abbreviation, game.away_team.abbreviation), ("IND", "DEN"))
        self.assertEqual((game.home_score, game.away_score), (115, 109))
        sides = dict(NBATeamGameStats.objects.filter(game=game).values_list("team__abbreviation", "is_home"))
        self.assertEqual(sides, {"IND": True, "DEN": False})

    def test_new_game_takes_home_from_first_row(self):
        # DEN's row first: "DEN @ IND" -> IND home
        self._assert_ind_home(self._sync([DEN_ROW, IND_ROW]))

    def test_resync_in_either_row_order_keeps_stored_home(self):
        self._sync([DEN_ROW, IND_ROW])
        # IND's row first now: the old fallback would read "IND @ DEN" and make DEN home.
        self._assert_ind_home(self._sync([IND_ROW, DEN_ROW]))
        self._assert_ind_home(self._sync([DEN_ROW, IND_ROW]))
