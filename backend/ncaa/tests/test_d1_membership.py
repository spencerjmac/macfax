"""
Season-level D1 decisions read TeamSeasonMembership through ncaa.utils.d1 (Task 6f.2).

Invariants pinned here:
- A current D1 program's pre-D1 season is not D1 (Team.is_d1 = "D1 today" is ignored when the season has rows).
- A former D1 program (Centenary, is_d1=False today) is D1 in its D1 seasons (2008).
- A season with no membership rows falls back to Team.is_d1 and logs a warning.
- exclude_reclassifying drops programs in a transition; off by default.
- d1_q works on Team itself and on FK paths (team / opponent).
"""

from datetime import date

from django.test import TestCase

from ncaa.models import Game, Season, Team, TeamGameStats, TeamSeasonMembership
from ncaa.utils import d1 as d1mod
from ncaa.utils.d1 import d1_q, d1_team_ids


class D1MembershipTests(TestCase):
    def setUp(self):
        d1mod._warned.clear()
        self.s2008 = Season.objects.create(year=2008, display_name="2007-08", is_current=False)
        self.s2026 = Season.objects.create(year=2026, display_name="2025-26", is_current=False)
        self.s2030 = Season.objects.create(year=2030, display_name="2029-30", is_current=False)   # no rows
        self.uc = Team.objects.create(name="UC San Diego", slug="ucsd", is_d1=True)          # D1 today, not in 2008
        self.cent = Team.objects.create(name="Centenary (LA)", slug="centenary", is_d1=False)  # D1 in 2008, not today
        self.duke = Team.objects.create(name="Duke", slug="duke", is_d1=True)
        self.newp = Team.objects.create(name="New Haven", slug="new-haven", is_d1=True)
        m = TeamSeasonMembership.objects.create
        m(season=self.s2008, team=self.uc, is_d1=False, is_reclassifying=None, source="derived_games")
        m(season=self.s2008, team=self.cent, is_d1=True, is_reclassifying=False, source="espn_group50")
        m(season=self.s2008, team=self.duke, is_d1=True, is_reclassifying=False, source="espn_group50")
        m(season=self.s2026, team=self.duke, is_d1=True, is_reclassifying=False, source="espn_group50")
        m(season=self.s2026, team=self.newp, is_d1=True, is_reclassifying=True, source="espn_group50")

    def test_pre_d1_season_of_current_program_is_not_d1(self):
        self.assertNotIn(self.uc.id, d1_team_ids(2008))
        self.assertFalse(Team.objects.filter(d1_q(self.s2008, ""), pk=self.uc.pk).exists())

    def test_centenary_2008_is_d1(self):
        self.assertIn(self.cent.id, d1_team_ids(self.s2008))
        self.assertTrue(Team.objects.filter(d1_q(2008, ""), pk=self.cent.pk).exists())

    def test_fallback_to_team_is_d1_with_warning(self):
        with self.assertLogs("ncaa.utils.d1", level="WARNING") as logs:
            ids = d1_team_ids(self.s2030)
        self.assertEqual(ids, {self.uc.id, self.duke.id, self.newp.id})   # Team.is_d1 today
        self.assertIn("2030", logs.output[0])
        self.assertTrue(Team.objects.filter(d1_q(2030, ""), pk=self.uc.pk).exists())

    def test_exclude_reclassifying(self):
        self.assertEqual(d1_team_ids(2026), {self.duke.id, self.newp.id})
        self.assertEqual(d1_team_ids(2026, exclude_reclassifying=True), {self.duke.id})

    def test_fk_paths_filter_d1_vs_d1_games(self):
        g1 = Game.objects.create(season_year=2008, game_date=date(2008, 1, 5), home_team=self.duke, away_team=self.cent,
                                 status="final", home_score=80, away_score=60, source="espn", source_game_id="a")
        g2 = Game.objects.create(season_year=2008, game_date=date(2008, 1, 9), home_team=self.duke, away_team=self.uc,
                                 status="final", home_score=90, away_score=50, source="espn", source_game_id="b")
        for g, opp in ((g1, self.cent), (g2, self.uc)):
            TeamGameStats.objects.create(game=g, team=self.duke, opponent=opp, home_away="H", pts=g.home_score)
        rows = TeamGameStats.objects.filter(d1_q(2008, "team"), d1_q(2008, "opponent"))
        self.assertEqual([r.game_id for r in rows], [g1.id])   # vs Centenary (D1 in 2008) kept; vs UCSD (not yet) dropped
