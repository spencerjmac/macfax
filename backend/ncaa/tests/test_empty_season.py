"""
NCAA pipelines before the first game of a season.

The daily NCAA gate opens Nov 1 but the first tip-off is Nov 2. A run in between
must not compute on an empty season: it wrote 365 all-zero ratings rows, which put a
game-less "2026-27" in the season picker.

Invariants pinned here:
- With no final games for the season, update_ncaa_teams / update_ncaa_players compute
  nothing, exit cleanly, and say why.
- With a final game, the compute steps (including seed_conferences) run.
- /api/seasons/?has_ratings=true lists a season only if it has final games, not just
  ratings rows.
"""

from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from ncaa.models import Game, Season, Team, TeamSeasonRatings

BASE_CALL = "ncaa.management.commands._pipeline_base.call_command"
SETUP = {"ensure_ncaa_teams", "fix_team_duplicates", "sync_team_d1_status"}


def run(command, season):
    out = StringIO()
    # The pipelines close the DB connection after ingest (to free it during long
    # compute); that would kill the test transaction, so stub it out.
    with mock.patch(BASE_CALL) as cc, \
         mock.patch("ncaa.management.commands.update_ncaa_teams.connection"), \
         mock.patch("ncaa.management.commands.update_ncaa_players.connection", create=True):
        call_command(command, season=season, skip_ingest=True, stdout=out, stderr=StringIO())
    return [c.args[0] for c in cc.call_args_list], out.getvalue()


class EmptySeasonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s26 = Season.objects.create(year=2026, display_name="2025-26", is_current=True)
        cls.home = Team.objects.create(slug="home", name="Home")
        cls.away = Team.objects.create(slug="away", name="Away")

    def add_final_game(self, season_year):
        return Game.objects.create(
            season_year=season_year, game_date=date(2026, 11, 3), home_team=self.home, away_team=self.away,
            home_score=70, away_score=60, status="final", source="ncaa", source_game_id=f"g{season_year}",
        )

    def test_teams_pipeline_computes_nothing_without_games(self):
        called, out = run("update_ncaa_teams", 2027)
        self.assertEqual(set(called) - SETUP, set())
        self.assertIn("no final 2027 games yet", out)

    def test_players_pipeline_computes_nothing_without_games(self):
        called, out = run("update_ncaa_players", 2027)
        self.assertEqual(set(called) - SETUP, set())
        self.assertIn("no final 2027 games yet", out)

    def test_scheduled_games_do_not_count(self):
        Game.objects.create(
            season_year=2027, game_date=date(2026, 11, 3), home_team=self.home, away_team=self.away,
            status="scheduled", source="ncaa", source_game_id="sched",
        )
        called, _ = run("update_ncaa_teams", 2027)
        self.assertEqual(set(called) - SETUP, set())

    def test_season_with_a_final_game_runs_the_pipeline_with_conference_seeding(self):
        self.add_final_game(2027)
        called, out = run("update_ncaa_teams", 2027)
        self.assertIn("compute_team_metrics", called)
        self.assertLess(called.index("compute_team_metrics"), called.index("seed_conferences"))
        self.assertLess(called.index("seed_conferences"), called.index("compute_adjusted_ratings"))
        self.assertNotIn("no final", out)

    def test_historical_season_is_unaffected(self):
        self.add_final_game(2026)
        called, _ = run("update_ncaa_teams", 2026)
        self.assertIn("compute_adjusted_ratings", called)


class SeasonPickerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s26 = Season.objects.create(year=2026, display_name="2025-26", is_current=True)
        cls.s27 = Season.objects.create(year=2027, display_name="2026-27")
        home = Team.objects.create(slug="home", name="Home")
        away = Team.objects.create(slug="away", name="Away")
        for season in (cls.s26, cls.s27):
            TeamSeasonRatings.objects.create(team=home, season=season)
        Game.objects.create(
            season_year=2026, game_date=date(2026, 3, 1), home_team=home, away_team=away,
            home_score=70, away_score=60, status="final", source="ncaa", source_game_id="g26",
        )

    def years(self, query):
        return [s["year"] for s in self.client.get(f"/api/seasons/{query}").json()]

    def test_has_ratings_requires_final_games(self):
        self.assertEqual(self.years("?has_ratings=true"), [2026])

    def test_without_the_filter_every_season_is_listed(self):
        self.assertEqual(self.years(""), [2027, 2026])
