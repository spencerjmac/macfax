"""
compute_team_metrics: raw pace counts only games with a box score.

A game with a final score but no box (2,471 in 2005-2025, 2,327 of them in 2005-07 and 2012-13) has zero possessions;
its 40 minutes used to be added anyway, pulling pace down.
"""
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from ncaa.models import Game, Season, Team, TeamGameStats, TeamSeasonMetrics, TeamSeasonRatings

BOX_A = dict(pts=80, fgm=30, fga=60, fg3m=8, fg3a=20, ftm=12, fta=16, oreb=10, dreb=25, reb=35,
             ast=15, stl=7, blk=4, tov=11, pf=18)
BOX_B = dict(pts=70, fgm=26, fga=62, fg3m=6, fg3a=22, ftm=12, fta=15, oreb=12, dreb=20, reb=32,
             ast=12, stl=5, blk=3, tov=14, pf=20)


class PaceTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2013, display_name="2012-13", is_current=True)
        self.a = Team.objects.create(slug="team-a", name="Team A", is_d1=True)
        self.b = Team.objects.create(slug="team-b", name="Team B", is_d1=True)
        self._game("g1", date(2013, 1, 5), 80, 70, BOX_A, BOX_B)          # full box, regulation
        self._game("g2", date(2013, 1, 12), 66, 60, {"pts": 66}, {"pts": 60})   # final score, no box
        for team in (self.a, self.b):
            TeamSeasonRatings.all_objects.create(
                team=team, season=self.season, is_pre_tournament=False, adj_o=105.0, adj_d=100.0,
                adj_em=5.0, adj_tempo=68.0, games_played=2, wins=1, losses=1)
        call_command("compute_team_metrics", season=2013, stdout=StringIO())

    def _game(self, sid, day, hs, as_, home_box, away_box):
        g = Game.objects.create(season_year=2013, game_date=day, home_team=self.a, away_team=self.b, status="final",
                                home_score=hs, away_score=as_, period_count=2, source="espn", source_game_id=sid)
        TeamGameStats.objects.create(game=g, team=self.a, opponent=self.b, home_away="H", **home_box)
        TeamGameStats.objects.create(game=g, team=self.b, opponent=self.a, home_away="A", **away_box)

    def test_pace_counts_only_the_game_with_a_box(self):
        m = TeamSeasonMetrics.all_objects.get(team=self.a, season=self.season, is_pre_tournament=False)
        box_row = TeamGameStats.objects.get(game__source_game_id="g1", team=self.a)
        self.assertEqual(m.games, 2)
        self.assertAlmostEqual(m.pace, 40 * box_row.possessions_est / 40, places=4)   # not halved by g2
