"""
PO.2: nba_sync_play_by_play --season-type. regular (default) keeps the
original selection (Final games with counts_toward_regular_season=True);
playoffs and play_in select Final games of that season_type. --retry-rotation
follows the same flag.

Real test database; the NBA.com provider is stood in for and returns no
events, so each selected game is fetched once and then skipped.
"""

from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from nba.models import NBAGame, NBASeason, NBATeam

MOD = "nba.management.commands.nba_sync_play_by_play"


class SeasonTypeSelectionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        season = NBASeason.objects.create(year=2026, display_name="2025-26")
        home = NBATeam.objects.create(
            nba_team_id=1610612738, slug="boston-celtics", name="Boston Celtics",
            abbreviation="BOS", city="Boston", conference="East", division="Atlantic")
        away = NBATeam.objects.create(
            nba_team_id=1610612744, slug="golden-state-warriors", name="Golden State Warriors",
            abbreviation="GSW", city="Golden State", conference="West", division="Pacific")

        def game(game_id, season_type, counts, status="Final", **kw):
            return NBAGame.objects.create(
                game_id=game_id, season=season, date=date(2026, 1, 1), home_team=home,
                away_team=away, home_score=100, away_score=90, season_type=season_type,
                counts_toward_regular_season=counts, status=status, **kw)

        game("0022500001", "regular", True)
        game("0022500002", "regular", True, pbp_synced=True)          # already synced
        game("0062500001", "regular", False)                          # NBA Cup final
        game("0052500001", "play_in", False)
        game("0042500001", "playoffs", False)
        game("0042500002", "playoffs", False, lineup_source="parser", pbp_synced=True)
        game("0042500003", "playoffs", False, status="Scheduled")

    def setUp(self):
        self.provider = mock.MagicMock()
        self.provider.get_play_by_play.return_value = []
        patcher = mock.patch(f"{MOD}.NBAApiProvider", return_value=self.provider)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fetched(self, *args):
        call_command("nba_sync_play_by_play", "--season", "2026", "--dry-run", *args, stdout=StringIO())
        return sorted(c.args[0] for c in self.provider.get_play_by_play.call_args_list)

    def test_default_selection_is_unchanged(self):
        expected = sorted(NBAGame.objects.filter(
            season__year=2026, status="Final", counts_toward_regular_season=True,
        ).exclude(pbp_synced=True).values_list("game_id", flat=True))
        self.assertEqual(self._fetched(), expected)
        self.assertEqual(expected, ["0022500001"])

    def test_explicit_regular_matches_the_default(self):
        self.assertEqual(self._fetched("--season-type", "regular"), ["0022500001"])

    def test_playoffs_selects_only_final_playoff_games(self):
        self.assertEqual(self._fetched("--season-type", "playoffs"), ["0042500001"])

    def test_play_in_selects_only_play_in_games(self):
        self.assertEqual(self._fetched("--season-type", "play_in"), ["0052500001"])

    def test_retry_rotation_follows_the_season_type(self):
        self.assertEqual(self._fetched("--season-type", "playoffs", "--retry-rotation"), ["0042500002"])
        self.provider.get_play_by_play.reset_mock()
        self.assertEqual(self._fetched("--retry-rotation"), [])
