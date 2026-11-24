"""
game_site / TeamGameStats.site: the one place a game's site is decided.

ESPN-sourced rows (2008-2025) store 'N' for neutral games; NCAA-sourced rows (2026, part of 2027) keep
'H'/'A' and set Game.neutral_site. Either way the game is neutral.
"""
from datetime import date

from django.test import SimpleTestCase, TestCase

from api.resume_utils import get_quadrant
from ncaa.models import Game, Team, TeamGameStats
from ncaa.models.games import game_site


class GameSiteTests(SimpleTestCase):
    def test_values(self):
        self.assertEqual(game_site("H", False), "home")
        self.assertEqual(game_site("A", False), "away")
        self.assertEqual(game_site("N", False), "neutral")
        self.assertEqual(game_site("N", True), "neutral")
        self.assertEqual(game_site("H", True), "neutral")   # 2026-style neutral row
        self.assertEqual(game_site("A", True), "neutral")


class TeamGameStatsSiteTests(TestCase):
    def test_flagged_game_is_neutral_for_both_sides(self):
        a = Team.objects.create(slug="a", name="A", is_d1=True)
        b = Team.objects.create(slug="b", name="B", is_d1=True)
        g = Game.objects.create(season_year=2026, game_date=date(2025, 11, 28), home_team=a, away_team=b,
                                status="final", home_score=70, away_score=65, neutral_site=True,
                                source="ncaa", source_game_id="n1")
        home = TeamGameStats.objects.create(game=g, team=a, opponent=b, home_away="H", pts=70)
        away = TeamGameStats.objects.create(game=g, team=b, opponent=a, home_away="A", pts=65)
        self.assertEqual((home.site, away.site), ("neutral", "neutral"))
        self.assertEqual((home.site_code, away.site_code), ("N", "N"))
        # quadrant: a #40 opponent is Q1 on a neutral floor but Q2 at home
        self.assertEqual(get_quadrant(40, home.site_code), "Q1")
        self.assertEqual(get_quadrant(40, "H"), "Q2")


class SosNeutralSiteTests(TestCase):
    def test_flagged_neutral_game_has_no_site_adjustment(self):
        import math
        from io import StringIO
        from django.core.management import call_command
        from ncaa.models import PipelineConfig, Season, TeamSeasonRatings
        season = Season.objects.create(year=2026, display_name="2025-26", is_current=True)
        a = Team.objects.create(slug="a", name="A", is_d1=True)
        b = Team.objects.create(slug="b", name="B", is_d1=True)
        for rank, (t, em) in enumerate([(a, 6.0), (b, 2.0)], start=1):
            TeamSeasonRatings.all_objects.create(team=t, season=season, is_pre_tournament=False, adj_o=100 + em,
                                                 adj_d=100.0, adj_em=em, adj_tempo=68.0, rank_adj_em=rank)
        g = Game.objects.create(season_year=2026, game_date=date(2025, 11, 28), home_team=a, away_team=b, status="final",
                                home_score=70, away_score=65, neutral_site=True, source="ncaa", source_game_id="n1")
        TeamGameStats.objects.create(game=g, team=a, opponent=b, home_away="H", pts=70)
        TeamGameStats.objects.create(game=g, team=b, opponent=a, home_away="A", pts=65)
        call_command("compute_sos", season=2026, stdout=StringIO())
        cfg = PipelineConfig.get_config()
        expected = 1.0 / (1.0 + math.exp(-(cfg.sos_baseline_adjem - 2.0) / cfg.sos_logistic_sigma))  # no home edge
        self.assertAlmostEqual(TeamSeasonRatings.all_objects.get(team=a).sos_win_pct, expected)
