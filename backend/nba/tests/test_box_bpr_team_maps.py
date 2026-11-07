"""
Box BPR's team maps read regular-season ratings only. A team with both a
regular and a playoff NBATeamSeasonRatings row used to get whichever came
last in rank_adj_net order; here the playoff rows rank last, so reading by
season alone would return the playoff ratings.
"""

from datetime import date

from django.test import TestCase

from nba.analytics.box_bpr import compute_opp_quality_map, compute_team_adj_em_map
from nba.models import NBAGame, NBASeason, NBATeam, NBATeamSeasonRatings


class TeamMapsReadRegularRatingsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.season = NBASeason.objects.create(year=2026, display_name="2025-26")
        cls.bos = NBATeam.objects.create(
            nba_team_id=1610612738, slug="boston-celtics", name="Boston Celtics",
            abbreviation="BOS", city="Boston", conference="East", division="Atlantic")
        cls.gsw = NBATeam.objects.create(
            nba_team_id=1610612744, slug="golden-state-warriors", name="Golden State Warriors",
            abbreviation="GSW", city="Golden State", conference="West", division="Pacific")
        for team, regular, playoff in ((cls.bos, 8.0, -3.0), (cls.gsw, -2.0, 6.0)):
            NBATeamSeasonRatings.objects.create(
                team=team, season=cls.season, season_type="regular", games=82,
                adj_net=regular, rank_adj_net=1)
            NBATeamSeasonRatings.objects.create(
                team=team, season=cls.season, season_type="playoffs", games=10,
                adj_net=playoff, rank_adj_net=30)
        NBAGame.objects.create(
            game_id="0022500001", season=cls.season, date=date(2025, 11, 1),
            home_team=cls.bos, away_team=cls.gsw, home_score=110, away_score=100,
            season_type="regular", counts_toward_regular_season=True, status="Final")

    def test_team_adj_em_map_uses_regular_ratings(self):
        self.assertEqual(compute_team_adj_em_map(2026), {self.bos.pk: 8.0, self.gsw.pk: -2.0})

    def test_opp_quality_map_uses_regular_ratings(self):
        # Each team's only opponent is the other: opp quality = the other's regular adj_net.
        self.assertEqual(compute_opp_quality_map(2026), {self.bos.pk: -2.0, self.gsw.pk: 8.0})
