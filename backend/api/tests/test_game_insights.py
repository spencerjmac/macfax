"""
load_or_generate_insights: a failed generation must never be saved on the game.

No database needed: the game is a stand-in object with the same two things the
helper touches (a game_insights attribute and save()).
"""
import json
from unittest import mock

from django.test import SimpleTestCase

from api.game_insights import load_or_generate_insights


class FakeGame:
    def __init__(self, game_insights=None):
        self.game_insights = game_insights
        self.save = mock.Mock()


def _call(game):
    return load_or_generate_insights(game, {}, {}, [])


class LoadOrGenerateInsightsTest(SimpleTestCase):
    @mock.patch("api.game_insights.generate_game_insights")
    def test_saved_insights_are_returned_without_calling_claude(self, gen):
        game = FakeGame(json.dumps(["a", "b", "c"]))
        self.assertEqual(_call(game), ["a", "b", "c"])
        gen.assert_not_called()
        game.save.assert_not_called()

    @mock.patch("api.game_insights.generate_game_insights")
    def test_unparseable_saved_text_is_returned_as_single_insight(self, gen):
        game = FakeGame("plain text, not json")
        self.assertEqual(_call(game), ["plain text, not json"])
        gen.assert_not_called()

    @mock.patch("api.game_insights.generate_game_insights", return_value=["x", "y", "z"])
    def test_success_is_saved(self, gen):
        game = FakeGame()
        self.assertEqual(_call(game), ["x", "y", "z"])
        self.assertEqual(game.game_insights, json.dumps(["x", "y", "z"]))
        game.save.assert_called_once_with(update_fields=["game_insights"])

    @mock.patch("api.game_insights.generate_game_insights", return_value=None)
    def test_failure_returns_placeholder_and_is_not_saved(self, gen):
        game = FakeGame()
        result = _call(game)
        self.assertEqual(result, ["Game insights temporarily unavailable."])
        self.assertIsNone(game.game_insights)
        game.save.assert_not_called()
