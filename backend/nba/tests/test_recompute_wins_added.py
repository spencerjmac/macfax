"""
nba_recompute_wins_added: native-1 regular rows get (bpr - R) x mpg x gp / 48 / WA_DIVISOR and the
season's rating scale records the divisor; other rows, other seasons and --dry-run are untouched.
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from nba.models import NBAPlayer, NBAPlayerSeasonStats, NBASeason, NBASeasonRatingScale, NBATeam
from nba.rating_scale import WA_DIVISOR

R = -1.918


class RecomputeWinsAddedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.native = NBASeason.objects.create(year=2026, display_name="2025-26")
        cls.legacy = NBASeason.objects.create(year=2025, display_name="2024-25")
        team = NBATeam.objects.create(nba_team_id=1610612743, slug="denver-nuggets", name="Denver Nuggets",
                                      abbreviation="DEN", city="Denver", conference="West", division="Northwest")
        star = NBAPlayer.objects.create(player_id=203999, name="Star")
        cls.rated = NBAPlayerSeasonStats.objects.create(
            player=star, season=cls.native, team=team, season_type="regular", gp=70, mpg=30.0,
            obpr=6.0, dbpr=2.0, bpr=8.0, bpr_model="native-1", wins_added=99.0)
        cls.playoff = NBAPlayerSeasonStats.objects.create(
            player=star, season=cls.native, team=team, season_type="playoffs", gp=10, mpg=35.0,
            obpr=6.0, dbpr=2.0, bpr=8.0, bpr_model="native-1", wins_added=5.0)
        cls.old = NBAPlayerSeasonStats.objects.create(
            player=star, season=cls.legacy, team=team, season_type="regular", gp=70, mpg=30.0,
            obpr=5.0, dbpr=1.0, bpr=6.0, bpr_model="lebron", wins_added=7.0)
        NBASeasonRatingScale.objects.create(season=cls.native, centre_obpr=1.0, centre_dbpr=0.5,
                                            wins_divisor=37.73, replacement=R)

    def test_all_recomputes_native_regular_rows_and_records_the_divisor(self):
        call_command("nba_recompute_wins_added", "--all", stdout=StringIO())
        self.rated.refresh_from_db()
        self.assertAlmostEqual(self.rated.wins_added, (8.0 - R) * 30.0 * 70 / 48.0 / WA_DIVISOR, places=10)
        self.assertEqual(NBASeasonRatingScale.objects.get(season=self.native).wins_divisor, WA_DIVISOR)
        for row, before in ((self.playoff, 5.0), (self.old, 7.0)):
            row.refresh_from_db()
            self.assertEqual(row.wins_added, before)

    def test_dry_run_writes_nothing(self):
        out = StringIO()
        call_command("nba_recompute_wins_added", "--season", "2026", "--dry-run", stdout=out)
        self.rated.refresh_from_db()
        self.assertEqual(self.rated.wins_added, 99.0)
        self.assertEqual(NBASeasonRatingScale.objects.get(season=self.native).wins_divisor, 37.73)
        self.assertIn("Would update 1 rows over 1 seasons", out.getvalue())

    def test_needs_a_selection_and_a_native_season(self):
        with self.assertRaises(CommandError):
            call_command("nba_recompute_wins_added", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("nba_recompute_wins_added", "--season", "2025", stdout=StringIO())
