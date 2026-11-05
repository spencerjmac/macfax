"""
Phase P P.4b: nba_sync_play_by_play's rotation options.

--rotation-tries N caps NBA.com attempts for each game's rotation data
(default 3, so an outage can't stall the daily run). --retry-rotation takes
games whose lineups came from the parser, tries rotation again, and when it
returns deletes the game's stints and rebuilds them from rotation.

The command's models, provider and parser are stood in for: no database,
no NBA.com.
"""

from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

MOD = "nba.management.commands.nba_sync_play_by_play"
GAME_ID = "0022500748"

_STINT = {
    "player_pk": 1, "team_pk": 1, "stint_index": 0, "period": 1,
    "clock_start_secs": 720, "clock_end_secs": 0, "secs_on": 720,
    "pts_scored": 0, "pts_allowed": 0, "plus_minus": 0, "window": 1,
    **{f"{side}_{k}": 0 for side in ("team", "opp")
       for k in ("fgm", "fga", "fg3m", "fta", "tov", "oreb", "dreb")},
}


class SyncOptionsTests(SimpleTestCase):

    def setUp(self):
        self.game = SimpleNamespace(pk=7, game_id=GAME_ID)
        self.provider = mock.MagicMock()
        self.provider.get_play_by_play.return_value = []
        self.provider.get_game_rotation.return_value = ["rotation rows"]
        self.parsed_source = "rotation"

        # Game selection: every filter/exclude keeps the chain and yields this game.
        self.qs = mock.MagicMock()
        self.qs.filter.return_value = self.qs
        self.qs.exclude.return_value = self.qs
        self.qs.__iter__.side_effect = lambda: iter([self.game])
        game_model = mock.MagicMock()
        game_model.objects.filter.return_value.select_related.return_value.order_by.return_value = self.qs
        self.game_model = game_model
        self.stint_model = mock.MagicMock()

        for target, value in {
            "NBAApiProvider": mock.MagicMock(return_value=self.provider),
            "NBAGame": game_model,
            "NBAPlayer": mock.MagicMock(),
            "NBATeam": mock.MagicMock(),
            "NBAPlayerGameStats": mock.MagicMock(),
            "NBAPlayerGameStint": self.stint_model,
            "transaction": mock.MagicMock(),
            "_parse_game": mock.MagicMock(side_effect=self._parse),
        }.items():
            patcher = mock.patch(f"{MOD}.{target}", value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _parse(self, game, events, player_pk_map, team_pk_map, roster, rotation):
        source = self.parsed_source if rotation is not None else "parser"
        return [dict(_STINT)], False, f"lineups={source}", [], source

    def _run(self, *args):
        out = StringIO()
        call_command("nba_sync_play_by_play", "--season", "2026", *args, stdout=out)
        return out.getvalue()

    def _rotation_tries(self):
        return self.provider.get_game_rotation.call_args.kwargs["tries"]

    def test_rotation_tries_defaults_to_3(self):
        self._run("--dry-run")

        self.assertEqual(self._rotation_tries(), 3)
        self.assertFalse(self.provider.get_game_rotation.call_args.kwargs["retry_failed"])

    def test_rotation_tries_option(self):
        self._run("--dry-run", "--rotation-tries", "8")

        self.assertEqual(self._rotation_tries(), 8)

    def test_daily_run_skips_synced_games_and_keeps_existing_stints(self):
        self._run()

        self.qs.exclude.assert_called_once_with(pbp_synced=True)
        self.stint_model.objects.filter.assert_not_called()   # no delete
        self.stint_model.objects.bulk_create.assert_called_once()

    def test_retry_rotation_rebuilds_parser_games_from_rotation(self):
        out = self._run("--retry-rotation")

        self.qs.filter.assert_any_call(lineup_source="parser")
        self.qs.exclude.assert_not_called()
        self.assertTrue(self.provider.get_game_rotation.call_args.kwargs["retry_failed"])
        self.stint_model.objects.filter.assert_called_once_with(game=self.game)
        self.stint_model.objects.filter.return_value.delete.assert_called_once()
        self.stint_model.objects.bulk_create.assert_called_once()
        update = self.game_model.objects.filter.return_value.update
        self.assertEqual(update.call_args.kwargs["lineup_source"], "rotation")
        self.assertIn("1/1 games processed", out)

    def test_retry_rotation_keeps_parser_stints_when_rotation_still_fails(self):
        self.provider.get_game_rotation.side_effect = RuntimeError("gamerotation failed after 3 tries")

        out = self._run("--retry-rotation")

        self.stint_model.objects.filter.assert_not_called()
        self.stint_model.objects.bulk_create.assert_not_called()
        self.assertIn("[SKIP]", out)
        self.assertIn("parser stints kept", out)

    def test_retry_rotation_keeps_parser_stints_when_rotation_is_unusable(self):
        self.parsed_source = "parser"     # rotation returned, but not 5 v 5 throughout

        out = self._run("--retry-rotation")

        self.stint_model.objects.filter.assert_not_called()
        self.stint_model.objects.bulk_create.assert_not_called()
        self.assertIn("parser stints kept", out)

    def test_retry_rotation_and_force_do_not_combine(self):
        with self.assertRaises(CommandError):
            self._run("--retry-rotation", "--force")
        self.provider.get_game_rotation.assert_not_called()
