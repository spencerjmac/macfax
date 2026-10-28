"""2026–27 affiliations must not alter prior-season results."""
from django.test import SimpleTestCase, TestCase
from django.core.management import call_command

from ncaa.conf_utils import get_season_conference
from ncaa.models import Season
from nba.models import NBASeason


class ConferenceRealignmentTests(SimpleTestCase):
    def test_pac_12_moves_are_season_specific(self):
        for slug, prior in (
            ("utah-state", "MWC"),
            ("gonzaga", "WCC"),
            ("texas-state", "SB"),
            ("oregon-st", "WCC"),
        ):
            with self.subTest(slug=slug):
                self.assertEqual(get_season_conference(slug, 2026), prior)
                self.assertEqual(get_season_conference(slug, 2027), "P12")

    def test_other_2027_moves(self):
        expected = {
            "hawaii": "MWC",
            "uc-davis": "MWC",
            "utep": "MWC",
            "denver": "WCC",
            "cal-baptist": "BW",
            "utah-valley": "BW",
            "southern-utah": "BSky",
            "northern-illinois": "Horz",
            "tennessee-tech": "SC",
            "austin-peay": "UAC",
            "abilene-christian": "UAC",
            "west-florida": "ASun",
            "iona": "Metro",
        }
        for slug, conference in expected.items():
            with self.subTest(slug=slug):
                self.assertEqual(get_season_conference(slug, 2027), conference)

    def test_historical_wac_and_maac_are_preserved(self):
        self.assertEqual(get_season_conference("abilene-christian", 2026), "WAC")
        self.assertEqual(get_season_conference("iona", 2026), "MAAC")
        self.assertEqual(get_season_conference("duke", 2027), "ACC")
        self.assertEqual(get_season_conference("not-a-real-school", 2027), "Unknown")


class ActivateBasketballSeasonsTests(TestCase):
    def test_activation_updates_both_leagues_and_keeps_history(self):
        Season.objects.create(year=2026, display_name="2025-26", is_current=True)
        NBASeason.objects.create(year=2026, display_name="2025-26", is_current=True)

        call_command("activate_basketball_seasons", season=2027, dry_run=True)
        self.assertFalse(Season.objects.filter(year=2027).exists())
        self.assertFalse(NBASeason.objects.filter(year=2027).exists())

        call_command("activate_basketball_seasons", season=2027)
        self.assertTrue(Season.objects.get(year=2027).is_current)
        self.assertTrue(NBASeason.objects.get(year=2027).is_current)
        self.assertFalse(Season.objects.get(year=2026).is_current)
        self.assertFalse(NBASeason.objects.get(year=2026).is_current)

        # Idempotent and historical rows are retained.
        call_command("activate_basketball_seasons", season=2027)
        self.assertEqual(Season.objects.count(), 2)
        self.assertEqual(NBASeason.objects.count(), 2)
