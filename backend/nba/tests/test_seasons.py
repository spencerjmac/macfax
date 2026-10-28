"""
nba.seasons — which season the site displays vs. which one the pipeline ingests.

Invariants pinned here:
- season_in_play rolls over on Oct 1 and is shared with the NCAA helpers.
- get_current_season falls back to a season WITH GAMES, never an empty future
  outlook row (2027/2028 exist as outlook targets).
- activate_latest_season flips is_current only to a season with a final
  regular-season game; never backward, never to an empty/future row; idempotent.
- The /api/nba/seasons/ list hides empty future rows.
"""

from datetime import date

from django.test import SimpleTestCase, TestCase

from config.season_calendar import NBA_WINDOW, NCAA_WINDOW, in_window, season_in_play
from nba.models import NBAGame, NBASeason, NBATeam
from nba.seasons import (
    NoSeasonError,
    activate_latest_season,
    get_current_season,
    has_recent_final_games,
    resolve_season_year,
)


class CalendarTests(SimpleTestCase):
    def test_season_in_play_rolls_over_on_oct_1(self):
        self.assertEqual(season_in_play(date(2026, 9, 30)), 2026)
        self.assertEqual(season_in_play(date(2026, 10, 1)), 2027)
        self.assertEqual(season_in_play(date(2026, 12, 31)), 2027)
        self.assertEqual(season_in_play(date(2027, 1, 1)), 2027)
        self.assertEqual(season_in_play(date(2027, 6, 30)), 2027)
        self.assertEqual(season_in_play(date(2027, 9, 30)), 2027)
        self.assertEqual(season_in_play(date(2027, 10, 1)), 2028)

    def test_nba_window_wraps_the_new_year(self):
        self.assertFalse(in_window(NBA_WINDOW, date(2026, 9, 30)))
        self.assertTrue(in_window(NBA_WINDOW, date(2026, 10, 1)))
        self.assertTrue(in_window(NBA_WINDOW, date(2027, 1, 15)))
        self.assertTrue(in_window(NBA_WINDOW, date(2027, 6, 30)))
        self.assertFalse(in_window(NBA_WINDOW, date(2027, 7, 1)))

    def test_ncaa_window(self):
        self.assertFalse(in_window(NCAA_WINDOW, date(2026, 10, 31)))
        self.assertTrue(in_window(NCAA_WINDOW, date(2026, 11, 1)))
        self.assertTrue(in_window(NCAA_WINDOW, date(2027, 4, 15)))
        self.assertFalse(in_window(NCAA_WINDOW, date(2027, 4, 16)))

    def test_resolve_season_year_prefers_explicit(self):
        self.assertEqual(resolve_season_year(2021), 2021)
        self.assertEqual(resolve_season_year(None), season_in_play())


class _NBAData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s2026 = NBASeason.objects.create(year=2026, display_name="2025-26", is_current=True)
        cls.s2027 = NBASeason.objects.create(year=2027, display_name="2026-27")
        cls.s2028 = NBASeason.objects.create(year=2028, display_name="2027-28")
        cls.home = NBATeam.objects.create(
            nba_team_id=1, slug="home", name="Home", abbreviation="HOM",
            city="H", conference="East", division="A",
        )
        cls.away = NBATeam.objects.create(
            nba_team_id=2, slug="away", name="Away", abbreviation="AWY",
            city="A", conference="West", division="B",
        )

    def game(self, season, gid, **kw):
        defaults = dict(
            game_id=gid, season=season, date=date(2026, 10, 22),
            home_team=self.home, away_team=self.away,
            home_score=100, away_score=90,
            season_type="regular", counts_toward_regular_season=True, status="Final",
        )
        defaults.update(kw)
        return NBAGame.objects.create(**defaults)


class GetCurrentSeasonTests(_NBAData):
    def test_returns_flagged_season(self):
        self.assertEqual(get_current_season(), self.s2026)

    def test_fallback_skips_empty_future_rows(self):
        NBASeason.objects.update(is_current=False)
        self.game(self.s2026, "g1")
        self.assertEqual(get_current_season(), self.s2026)  # not 2028

    def test_raises_on_empty_database(self):
        NBASeason.objects.all().delete()
        with self.assertRaises(NoSeasonError):
            get_current_season()


class ActivateLatestSeasonTests(_NBAData):
    def test_no_games_in_newer_season_means_no_flip(self):
        self.game(self.s2026, "g1", date=date(2026, 4, 1))
        self.assertIsNone(activate_latest_season())
        self.assertEqual(get_current_season(), self.s2026)

    def test_first_final_regular_season_game_flips(self):
        self.game(self.s2026, "g1", date=date(2026, 4, 1))
        self.game(self.s2027, "g2")
        old, new = activate_latest_season()
        self.assertEqual((old, new), (self.s2026, self.s2027))
        self.s2026.refresh_from_db()
        self.s2027.refresh_from_db()
        self.assertFalse(self.s2026.is_current)
        self.assertTrue(self.s2027.is_current)
        self.assertEqual(NBASeason.objects.filter(is_current=True).count(), 1)

    def test_idempotent(self):
        self.game(self.s2027, "g2")
        self.assertIsNotNone(activate_latest_season())
        self.assertIsNone(activate_latest_season())

    def test_scheduled_preseason_and_playoff_games_do_not_flip(self):
        self.game(self.s2027, "sched", status="Scheduled", home_score=None, away_score=None)
        self.game(self.s2027, "pre", season_type="preseason")
        self.game(self.s2027, "cup-final", counts_toward_regular_season=False)
        self.assertIsNone(activate_latest_season())
        self.assertTrue(NBASeason.objects.get(year=2026).is_current)

    def test_never_moves_backward(self):
        NBASeason.objects.update(is_current=False)
        self.s2027.is_current = True
        self.s2027.save()
        self.game(self.s2026, "old", date=date(2026, 4, 1))
        self.assertIsNone(activate_latest_season())
        self.assertTrue(NBASeason.objects.get(year=2027).is_current)

    def test_empty_database_is_a_noop(self):
        NBAGame.objects.all().delete()
        self.assertIsNone(activate_latest_season())


class RecentFinalGamesTests(_NBAData):
    def test_window(self):
        self.game(self.s2027, "g1", date=date(2026, 10, 22))
        self.assertTrue(has_recent_final_games(14, today=date(2026, 10, 27)))
        self.assertFalse(has_recent_final_games(14, today=date(2026, 11, 20)))


class SeasonsEndpointTests(_NBAData):
    def test_hides_empty_future_rows_but_keeps_current(self):
        self.game(self.s2027, "g1")
        resp = self.client.get("/api/nba/seasons/")
        self.assertEqual(resp.status_code, 200)
        years = [s["year"] for s in resp.json()]
        self.assertEqual(sorted(years), [2026, 2027])  # 2026 current (no games), 2027 has games; no 2028

    def test_all_flag_includes_everything(self):
        resp = self.client.get("/api/nba/seasons/?all=true")
        self.assertEqual(sorted(s["year"] for s in resp.json()), [2026, 2027, 2028])
