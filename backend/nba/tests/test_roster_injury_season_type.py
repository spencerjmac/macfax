"""
PO.1c: two NBAPlayerSeasonStats readers read one season type. The team
roster endpoint returns regular rows by default and playoff rows on
request (a playoff team's players used to appear twice); the serializer
says which. The injury engine uses regular-season rows only.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from nba.injury_engine import compute_nba_injury_adjustment
from nba.models import NBAPlayer, NBAPlayerAvailability, NBAPlayerSeasonStats, NBASeason, NBATeam


class OneSeasonTypeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.season = NBASeason.objects.create(year=2026, display_name="2025-26")
        cls.team = NBATeam.objects.create(
            nba_team_id=1610612743, slug="denver-nuggets", name="Denver Nuggets",
            abbreviation="DEN", city="Denver", conference="West", division="Northwest")
        cls.star = NBAPlayer.objects.create(player_id=203999, name="Star Center")
        cls.bench = NBAPlayer.objects.create(player_id=1630000, name="Bench Guard")
        # The playoff row's BPR sorts after the regular one, so a reader that
        # ignored season type would end up with the playoff values.
        for season_type, gp, pts, obpr, dbpr, mpg in (("regular", 70, 29.6, 6.0, 2.0, 34.6),
                                                      ("playoffs", 11, 25.0, 9.0, 4.0, 40.0)):
            NBAPlayerSeasonStats.objects.create(
                player=cls.star, season=cls.season, team=cls.team, season_type=season_type,
                gp=gp, mpg=mpg, pts=pts, obpr=obpr, dbpr=dbpr)
        NBAPlayerSeasonStats.objects.create(
            player=cls.bench, season=cls.season, team=cls.team, season_type="regular",
            gp=60, mpg=12.0, pts=4.1)

    def _roster(self, **params):
        return self.client.get(reverse("nba-team-roster", args=[self.team.slug]), {"season": 2026, **params})

    def test_roster_returns_regular_rows_by_default(self):
        res = self._roster()
        self.assertEqual(res.status_code, 200)
        rows = res.json()
        self.assertEqual(sorted(r["player_name"] for r in rows), ["Bench Guard", "Star Center"])
        self.assertEqual({r["season_type"] for r in rows}, {"regular"})
        self.assertEqual(next(r["gp"] for r in rows if r["player_name"] == "Star Center"), 70)

    def test_roster_returns_playoff_rows_on_request(self):
        rows = self._roster(season_type="playoffs").json()
        self.assertEqual([(r["player_name"], r["season_type"], r["gp"]) for r in rows],
                         [("Star Center", "playoffs", 11)])

    def test_roster_rejects_other_season_types(self):
        self.assertEqual(self._roster(season_type="play_in").status_code, 400)

    def test_injury_engine_ignores_playoff_rows(self):
        NBAPlayerAvailability.objects.create(
            player=self.star, team=self.team, season=self.season,
            game_date=date(2026, 5, 10), status="out")

        result = compute_nba_injury_adjustment(self.team, self.season, date(2026, 5, 10))

        self.assertEqual([(p["obpr"], p["dbpr"], p["mpg"]) for p in result["players"]], [(6.0, 2.0, 34.6)])
