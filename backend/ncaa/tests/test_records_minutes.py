"""
Records from Game scores, the zero-valid-games warning, and overtime minutes (Task 7c).

Invariants pinned here:
- A game whose opponent has no box row still counts: the team that scored more gets the win (records come
  from Game.home_score/away_score; 0-0 is excluded; the pre-tournament cutoff applies to pre rows).
- A team with box rows but no valid rating game falls back to the prior, and compute_adjusted_ratings names it.
- game_minutes = 40 + 5 per overtime period (a double-OT game is 50), falling back to went_to_ot.
"""

from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from ncaa.management.commands.compute_adjusted_ratings import season_records
from ncaa.models import (Game, NationalAverages, Season, Team, TeamGameStats, TeamSeasonMembership,
                         TeamSeasonMetrics, TeamSeasonRatings)
from ncaa.models.games import game_minutes_for


def box(game, team, opp, ha, pts, fga=60, fta=20, oreb=10, tov=12):
    return TeamGameStats.objects.create(game=game, team=team, opponent=opp, home_away=ha, pts=pts,
                                        fgm=pts // 2 - 5, fga=fga, fta=fta, ftm=10, oreb=oreb, dreb=25, tov=tov)


class RecordsAndMinutesTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2010, display_name="2009-10", is_current=False,
                                            selection_sunday_date=date(2010, 3, 14))
        self.a = Team.objects.create(name="Alpha", slug="alpha", is_d1=True)
        self.b = Team.objects.create(name="Beta", slug="beta", is_d1=True)
        self.c = Team.objects.create(name="Gamma", slug="gamma", is_d1=True)
        for t in (self.a, self.b, self.c):
            TeamSeasonMembership.objects.create(season=self.season, team=t, is_d1=True, is_reclassifying=False,
                                                source="manual")
            TeamSeasonMetrics.all_objects.create(team=t, season=self.season, is_pre_tournament=False, games=1,
                                                 ortg=100.0, drtg=100.0, pace=68.0)
        NationalAverages.objects.create(season=self.season, avg_ortg=100.0, avg_pace=68.0, avg_efg=50.0, avg_tov=18.0,
                                        avg_orb=30.0, avg_ftr=33.0, total_possessions=1000.0, total_games=10)
        g = lambda d, h, a, hs, as_, **kw: Game.objects.create(season_year=2010, game_date=d, home_team=h, away_team=a,
                                                                status="final", home_score=hs, away_score=as_,
                                                                source="espn", source_game_id=f"{d}{h.id}{a.id}", **kw)
        # A beats B: both box rows
        self.g1 = g(date(2010, 1, 5), self.a, self.b, 80, 70, period_count=2)
        box(self.g1, self.a, self.b, "H", 80); box(self.g1, self.b, self.a, "A", 70)
        # C beats A 75-72, but A has no box row for this game
        self.g2 = g(date(2010, 1, 9), self.c, self.a, 75, 72, period_count=4, went_to_ot=True)
        box(self.g2, self.c, self.a, "H", 75)
        # canceled 0-0 game: not a game; post-cutoff game: not in pre records
        g(date(2010, 1, 12), self.b, self.c, 0, 0)
        g(date(2010, 3, 20), self.b, self.c, 60, 50)

    def test_missing_opponent_box_row_counts_as_win(self):
        rec = season_records(2010, cutoff=date(2010, 3, 14))
        self.assertEqual(rec[self.c.id], (1, 1))      # C won the game whose opponent row is missing
        self.assertEqual(rec[self.a.id], (2, 1))      # A's loss counts although A has no box row there
        self.assertEqual(rec[self.b.id], (1, 0))      # 0-0 and post-cutoff games excluded
        self.assertEqual(season_records(2010)[self.b.id], (2, 1))
        c_row = TeamGameStats.objects.get(game=self.g2, team=self.c)
        self.assertTrue(c_row.won)
        self.assertEqual((c_row.score_for, c_row.score_against), (75, 72))

    def test_ratings_records_and_zero_valid_games_warning(self):
        out = StringIO()
        with self.assertLogs("ncaa.management.commands.compute_adjusted_ratings", level="WARNING") as logs:
            call_command("compute_adjusted_ratings", season=2010, stdout=out, iterations=5)
        self.assertTrue(any("Gamma 2010" in m and "fell back to the prior" in m for m in logs.output))
        self.assertIn("Teams with box rows that fell back to the prior: 1", out.getvalue())
        rows = {r.team_id: r for r in TeamSeasonRatings.all_objects.filter(season=self.season, is_pre_tournament=False)}
        # post-tournament row: the 3/20 loss to Beta counts too (no cutoff)
        self.assertEqual((rows[self.c.id].wins, rows[self.c.id].losses, rows[self.c.id].games_played), (1, 1, 2))
        self.assertEqual((rows[self.a.id].wins, rows[self.a.id].losses, rows[self.a.id].games_played), (1, 1, 2))

    def test_double_overtime_is_50_minutes(self):
        self.assertEqual(game_minutes_for(4, True), 50)
        self.assertEqual(game_minutes_for(2, False), 40)
        self.assertEqual(game_minutes_for(3, True), 45)
        self.assertEqual(game_minutes_for(None, True), 45)    # fallback
        self.assertEqual(game_minutes_for(None, False), 40)
        self.assertEqual(TeamGameStats.objects.get(game=self.g2, team=self.c).game_minutes, 50)
        self.assertEqual(TeamGameStats.objects.get(game=self.g1, team=self.a).game_minutes, 40)
