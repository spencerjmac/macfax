"""
ncaa.seasons — displayed season vs. season in play, and the auto-flip.

Invariants pinned here:
- activate_latest_season flips is_current only to a season with a final game;
  never backward; idempotent; scheduled games do not count.
- Pipeline season rows are never born current (a backfill or a not-yet-started
  season must not steal the flag): _ensure_season creates them as not current.
"""

from datetime import date

from django.test import TestCase

from ncaa.management.commands._pipeline_base import BasePipelineCommand
from ncaa.models import Game, Season, Team
from ncaa.seasons import (
    NoSeasonError,
    activate_latest_season,
    get_current_season,
    has_recent_final_games,
    resolve_season_year,
)
from config.season_calendar import season_in_play


class NCAASeasonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s2026 = Season.objects.create(year=2026, display_name="2025-26", is_current=True)
        cls.s2027 = Season.objects.create(year=2027, display_name="2026-27")
        cls.home = Team.objects.create(slug="home", name="Home")
        cls.away = Team.objects.create(slug="away", name="Away")

    def game(self, season_year, gid, status="final", day=date(2026, 11, 3)):
        return Game.objects.create(
            season_year=season_year, game_date=day,
            home_team=self.home, away_team=self.away,
            home_score=70 if status == "final" else None,
            away_score=60 if status == "final" else None,
            status=status, source="ncaa", source_game_id=gid,
        )

    def test_get_current_season(self):
        self.assertEqual(get_current_season(), self.s2026)

    def test_fallback_to_latest_year_when_nothing_flagged(self):
        Season.objects.update(is_current=False)
        self.assertEqual(get_current_season(), self.s2027)

    def test_raises_on_empty_database(self):
        Season.objects.all().delete()
        with self.assertRaises(NoSeasonError):
            get_current_season()

    def test_resolve_season_year(self):
        self.assertEqual(resolve_season_year(2019), 2019)
        self.assertEqual(resolve_season_year(None), season_in_play())

    def test_scheduled_games_do_not_flip(self):
        self.game(2027, "g1", status="scheduled")
        self.assertIsNone(activate_latest_season())
        self.assertTrue(Season.objects.get(year=2026).is_current)

    def test_first_final_game_flips_and_is_idempotent(self):
        self.game(2027, "g1")
        old, new = activate_latest_season()
        self.assertEqual((old, new), (self.s2026, self.s2027))
        self.assertEqual(Season.objects.filter(is_current=True).count(), 1)
        self.assertTrue(Season.objects.get(year=2027).is_current)
        self.assertIsNone(activate_latest_season())

    def test_never_moves_backward(self):
        Season.objects.update(is_current=False)
        self.s2027.is_current = True
        self.s2027.save()
        self.game(2026, "old", day=date(2026, 3, 1))
        self.assertIsNone(activate_latest_season())
        self.assertTrue(Season.objects.get(year=2027).is_current)

    def test_final_games_without_a_season_row_do_not_flip(self):
        self.game(2028, "future")
        self.assertIsNone(activate_latest_season())

    def test_has_recent_final_games(self):
        self.game(2027, "g1", day=date(2026, 11, 3))
        self.assertTrue(has_recent_final_games(14, today=date(2026, 11, 10)))
        self.assertFalse(has_recent_final_games(14, today=date(2026, 12, 1)))

    def test_ensure_season_creates_rows_not_current(self):
        cmd = BasePipelineCommand()
        season = cmd._ensure_season(2029)
        self.assertFalse(season.is_current)
        self.assertEqual(get_current_season(), self.s2026)
