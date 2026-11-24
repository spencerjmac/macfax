"""
NBA Traditional tab, backend.

- LeagueGameLog's AST / STL / BLK / PF reach NBATeamGameStats through nba_sync_games.
- The rankings API adds per-game traditional stats for the row's season and
  season type. Each stat divides by the games that have it; PFD is the
  opponent's PF in the same game; a stat no game has is null, not an error.

Real test database; NBA.com is stood in for.
"""

from datetime import date
from io import StringIO
from unittest import mock

import pandas as pd
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from nba.models import NBAGame, NBASeason, NBATeam, NBATeamGameStats, NBATeamSeasonRatings
from nba.providers.base import RawLeagueGameLog
from nba.providers.nba_api_provider import NBAApiProvider

BOX = ("pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "tov")


def _team(nba_id, slug, abbr):
    return NBATeam.objects.create(
        nba_team_id=nba_id, slug=slug, name=slug.title(), abbreviation=abbr,
        city=slug, conference="West", division="Pacific")


class ProviderParsesTraditionalTests(TestCase):
    def test_league_game_log_reads_ast_stl_blk_pf(self):
        df = pd.DataFrame([{
            "GAME_ID": "0022500001", "GAME_DATE": "2025-10-21", "SEASON_ID": "22025",
            "TEAM_ID": 1610612747, "TEAM_ABBREVIATION": "LAL", "MATCHUP": "LAL vs. GSW",
            "WL": "W", "PTS": 110, "FGM": 40, "FGA": 85, "FG3M": 12, "FG3A": 35, "FTM": 18,
            "FTA": 22, "OREB": 10, "DREB": 34, "TOV": 13, "AST": 27, "STL": 8, "BLK": 5, "PF": 19,
        }, {
            "GAME_ID": "0022500001", "GAME_DATE": "2025-10-21", "SEASON_ID": "22025",
            "TEAM_ID": 1610612744, "TEAM_ABBREVIATION": "GSW", "MATCHUP": "GSW @ LAL",
            "WL": "L", "PTS": 100, "FGM": 37, "FGA": 88, "FG3M": 14, "FG3A": 40, "FTM": 12,
            "FTA": 15, "OREB": 9, "DREB": 30, "TOV": 15, "AST": None, "STL": 6, "BLK": 3, "PF": 21,
        }])
        endpoint = mock.MagicMock()
        endpoint.get_data_frames.return_value = [df]
        with mock.patch("nba_api.stats.endpoints.leaguegamelog.LeagueGameLog", return_value=endpoint):
            rows = NBAApiProvider(sleep_seconds=0).get_league_game_log(2026)
        lal, gsw = rows
        self.assertEqual((lal.ast, lal.stl, lal.blk, lal.pf), (27, 8, 5, 19))
        self.assertEqual((gsw.ast, gsw.stl, gsw.blk, gsw.pf), (None, 6, 3, 21))


class SyncWritesTraditionalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _team(1610612747, "los-angeles-lakers", "LAL")
        _team(1610612744, "golden-state-warriors", "GSW")

    def _row(self, team_id, abbr, is_home, **traditional):
        return RawLeagueGameLog(
            game_id="0022500001", date="2025-10-21", season_id="22025", team_id=team_id,
            team_abbreviation=abbr, is_home=is_home, wl="W" if is_home else "L",
            matchup=f"{abbr} vs. X" if is_home else f"{abbr} @ X",
            **{k: 10 for k in BOX}, **traditional)

    def test_sync_stores_traditional_fields(self):
        provider = mock.MagicMock()
        provider.get_league_game_log.return_value = [
            self._row(1610612747, "LAL", True, ast=27, stl=8, blk=5, pf=19),
            self._row(1610612744, "GSW", False, ast=22, stl=6, blk=3, pf=21),
        ]
        with mock.patch("nba.management.commands.nba_sync_games.NBAApiProvider", return_value=provider):
            call_command("nba_sync_games", season=2026, stdout=StringIO())
        lal = NBATeamGameStats.objects.get(team__abbreviation="LAL")
        gsw = NBATeamGameStats.objects.get(team__abbreviation="GSW")
        self.assertEqual((lal.ast, lal.stl, lal.blk, lal.pf), (27, 8, 5, 19))
        self.assertEqual((gsw.ast, gsw.stl, gsw.blk, gsw.pf), (22, 6, 3, 21))


class RankingsTraditionalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = NBASeason.objects.create(year=2026, display_name="2025-26", is_current=True)
        cls.a = _team(1, "team-a", "AAA")
        cls.b = _team(2, "team-b", "BBB")
        cls.c = _team(3, "team-c", "CCC")
        full_a = dict(pts=110, opp_pts=100, fgm=40, fga=80, fg3m=10, fg3a=30, ftm=20, fta=25,
                      oreb=10, dreb=30, tov=12, ast=25, stl=8, blk=5, pf=18)
        full_b = dict(pts=100, opp_pts=110, fgm=36, fga=84, fg3m=12, fg3a=36, ftm=16, fta=20,
                      oreb=8, dreb=32, tov=14, ast=20, stl=6, blk=4, pf=22)
        # Game 2: box stats only, traditional fields not filled yet (pre-0034 row).
        old_a = dict(pts=120, opp_pts=90, fgm=44, fga=80, fg3m=14, fg3a=30, ftm=18, fta=20,
                     oreb=12, dreb=34, tov=10)
        old_b = dict(pts=90, opp_pts=120, fgm=34, fga=88, fg3m=8, fg3a=32, ftm=14, fta=18,
                     oreb=10, dreb=30, tov=16)
        cls._game("0022500001", "regular", full_a, full_b)
        cls._game("0022500002", "regular", old_a, old_b)
        # A playoff game must not reach the regular-season row.
        cls._game("0042500001", "playoffs", dict(full_a, pts=200, ast=99), full_b)
        for team in (cls.a, cls.b, cls.c):
            NBATeamSeasonRatings.objects.create(team=team, season=cls.season, season_type="regular")
        NBATeamSeasonRatings.objects.create(team=cls.a, season=cls.season, season_type="playoffs")

    @classmethod
    def _game(cls, game_id, season_type, home, away):
        game = NBAGame.objects.create(
            game_id=game_id, season=cls.season, date=date(2025, 11, int(game_id[-1])),
            home_team=cls.a, away_team=cls.b, home_score=home["pts"], away_score=away["pts"],
            season_type=season_type, status="Final")
        NBATeamGameStats.objects.create(game=game, team=cls.a, is_home=True, **home)
        NBATeamGameStats.objects.create(game=game, team=cls.b, is_home=False, **away)

    def _rows(self, **params):
        response = self.client.get(reverse("nba-rankings-list"), {"season": 2026, **params})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        rows = body["results"] if isinstance(body, dict) else body
        return {r["team_slug"]: r for r in rows}

    def test_each_stat_divides_by_games_that_have_it(self):
        a = self._rows()["team-a"]
        self.assertEqual(a["gp"], 2)
        self.assertEqual(a["ppg"], 115.0)     # (110 + 120) / 2
        self.assertEqual(a["papg"], 95.0)
        self.assertEqual(a["rpg"], 43.0)      # (40 + 46) / 2
        self.assertEqual(a["topg"], 11.0)
        self.assertEqual(a["fg_pct"], 52.5)   # 84 / 160
        self.assertEqual(a["fg2_pct"], 60.0)  # 60 / 100
        self.assertEqual(a["fg3_pct"], 40.0)  # 24 / 60
        self.assertEqual(a["ft_pct"], 84.4)   # 38 / 45
        self.assertEqual(a["fga_pg"], 80.0)
        # AST / STL / BLK / PF exist in game 1 only
        self.assertEqual(a["apg"], 25.0)
        self.assertEqual(a["spg"], 8.0)
        self.assertEqual(a["bpg"], 5.0)
        self.assertEqual(a["pfpg"], 18.0)

    def test_fouls_drawn_are_opponent_fouls(self):
        rows = self._rows()
        self.assertEqual(rows["team-a"]["pfdpg"], 22.0)
        self.assertEqual(rows["team-b"]["pfdpg"], 18.0)

    def test_season_type_scopes_games(self):
        a = self._rows(season_type="playoffs")["team-a"]
        self.assertEqual(a["gp"], 1)
        self.assertEqual(a["ppg"], 200.0)
        self.assertEqual(a["apg"], 99.0)

    def test_unfilled_is_null(self):
        NBATeamGameStats.objects.update(ast=None)
        rows = self._rows()
        self.assertIsNone(rows["team-a"]["apg"])
        self.assertEqual(rows["team-a"]["spg"], 8.0)
        c = rows["team-c"]                    # no games at all
        self.assertIsNone(c["gp"])
        self.assertIsNone(c["ppg"])
        self.assertIsNone(c["pfdpg"])
