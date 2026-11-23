"""
Traditional per-game stats on the rankings endpoint.

Some seasons have games with a final score but no box score (all box columns 0).
Box per-game stats divide by box_games, fouls drawn by opp_box_games, and
PTS / OPP PTS come from final scores over every counted game. Canceled games
stored as 0-0 'final' count nowhere.
"""
from datetime import date

from django.core.management import call_command
from django.urls import reverse

from api.tests.base import IsolatedCacheTestCase
from ncaa.models import Game, Season, Team, TeamGameStats, TeamSeasonMetrics, TeamSeasonRatings

BOX_A = dict(pts=80, fgm=30, fga=60, fg3m=8, fg3a=20, ftm=12, fta=16, oreb=10, dreb=25, reb=35,
             ast=15, stl=7, blk=4, tov=11, pf=18)
BOX_B = dict(pts=70, fgm=26, fga=62, fg3m=6, fg3a=22, ftm=12, fta=15, oreb=12, dreb=20, reb=32,
             ast=12, stl=5, blk=3, tov=14, pf=20)


class RankingsTraditionalStatsTests(IsolatedCacheTestCase):
    def setUp(self):
        super().setUp()
        self.season = Season.objects.create(year=2013, display_name="2012-13", is_current=True)
        self.a = Team.objects.create(slug="team-a", name="Team A", is_d1=True)
        self.b = Team.objects.create(slug="team-b", name="Team B", is_d1=True)
        # Game 1: full box. Game 2: final score, no box. Game 3: canceled 0-0 'final'.
        self._game("g1", date(2013, 1, 5), 80, 70, BOX_A, BOX_B)
        self._game("g2", date(2013, 1, 12), 66, 60, {"pts": 66}, {"pts": 60})
        self._game("g3", date(2013, 1, 19), 0, 0, {}, {})
        for team in (self.a, self.b):
            TeamSeasonRatings.all_objects.create(
                team=team, season=self.season, is_pre_tournament=False, adj_o=105.0, adj_d=100.0,
                adj_em=5.0, adj_tempo=68.0, games_played=2, wins=1, losses=1,
            )
        call_command("compute_team_metrics", season=2013, stdout=open("/dev/null", "w"))

    def _game(self, sid, day, home_score, away_score, home_box, away_box):
        game = Game.objects.create(
            season_year=2013, game_date=day, home_team=self.a, away_team=self.b, status="final",
            home_score=home_score, away_score=away_score, source="espn", source_game_id=sid,
        )
        TeamGameStats.objects.create(game=game, team=self.a, opponent=self.b, home_away="H", **home_box)
        TeamGameStats.objects.create(game=game, team=self.b, opponent=self.a, home_away="A", **away_box)

    def _row(self, slug):
        response = self.client.get(reverse("rankings-list"), {"season": "2013"})
        self.assertEqual(response.status_code, 200)
        return next(r for r in response.json()["results"] if r["team_slug"] == slug)

    def test_metrics_count_box_games_separately(self):
        m = TeamSeasonMetrics.all_objects.get(team=self.a, season=self.season, is_pre_tournament=False)
        self.assertEqual(m.games, 2)  # canceled 0-0 game excluded, box-less game kept
        self.assertEqual(m.box_games, 1)
        self.assertEqual(m.opp_box_games, 1)
        self.assertEqual(m.total_opp_pf, 20)

    def test_per_game_fields(self):
        row = self._row("team-a")
        self.assertEqual(row["ppg"], 73.0)    # (80 + 66) / 2 from final scores
        self.assertEqual(row["papg"], 65.0)   # (70 + 60) / 2
        self.assertEqual(row["fg_pct"], 50.0)
        self.assertEqual(row["rpg"], 35.0)    # box stats over the one game with a box
        self.assertEqual(row["orpg"], 10.0)
        self.assertEqual(row["drpg"], 25.0)
        self.assertEqual(row["apg"], 15.0)
        self.assertEqual(row["spg"], 7.0)
        self.assertEqual(row["bpg"], 4.0)
        self.assertEqual(row["topg"], 11.0)
        self.assertEqual(row["pfpg"], 18.0)
        self.assertEqual(row["pfdpg"], 20.0)  # opponent fouls over games with an opponent box

    def test_away_team_scores_use_its_side(self):
        row = self._row("team-b")
        self.assertEqual(row["ppg"], 65.0)
        self.assertEqual(row["papg"], 73.0)
        self.assertEqual(row["pfdpg"], 18.0)
