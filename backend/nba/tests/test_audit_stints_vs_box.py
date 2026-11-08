"""
Phase P P.5: nba_audit_bpr_data's B5-B7 compare stints with the box score.
On a one-game fixture a clean game passes each check and a game with one
wrong stint fails it. Quality-flagged games are reported on their own line,
outside the headline. No database: the three querysets are stood in for.

P.7: B6 allows 120 seconds when the season's box scores hold only whole
minutes; B7 passes one-point misses and lists games missing by more.

H.0f: B7 leaves out games whose box plus-minus doesn't add up (a team's
total more than 2 off 5 x its final margin) and lists them on their own.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase

from nba.management.commands.nba_audit_bpr_data import Command
from nba.models import NBAGame, NBAPlayerGameStats, NBAPlayerGameStint

GAME_PK, GAME_ID, HOME, AWAY = 7, "0029900001", 1, 2
HOME_PLAYERS, AWAY_PLAYERS = range(101, 106), range(201, 206)


def _one_game(flagged=False, box_with_seconds=False, box_pm_off=0, game_pk=GAME_PK,
              game_id=GAME_ID, **wrong):
    """
    A 4-2 game with one lineup window all game. `wrong` changes the first
    home player's stint: pts_scored, secs_on or plus_minus. Box seconds are
    whole minutes unless box_with_seconds, which gives the second home player
    (box and stint alike) 2875 seconds. box_pm_off adds to the first home
    player's box plus-minus only.
    """
    game = (game_pk, game_id, HOME, 4, 2, "rotation", flagged)
    stints, box = [], []
    for team, players, scored, allowed in ((HOME, HOME_PLAYERS, 4, 2), (AWAY, AWAY_PLAYERS, 2, 4)):
        for pid in players:
            stint = {"pts_scored": scored, "pts_allowed": allowed, "secs_on": 2880,
                     "plus_minus": scored - allowed}
            box_secs = 2880
            if box_with_seconds and pid == HOME_PLAYERS[1]:
                box_secs = stint["secs_on"] = 2875
            if pid == HOME_PLAYERS[0]:
                stint.update(wrong)
            stints.append((game_pk, pid, team, 1, 720, 0, 1, stint["secs_on"], stint["plus_minus"],
                           stint["pts_scored"], stint["pts_allowed"]))
            box_pm = scored - allowed + (box_pm_off if pid == HOME_PLAYERS[0] else 0)
            box.append((game_pk, pid, team, box_secs, box_pm))
    return [game], stints, box


class StintsVsBoxAuditTests(SimpleTestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out_dir = Path(tmp.name)

    def _patch(self, games, stints, box):
        game_objects, stint_objects, box_objects = mock.MagicMock(), mock.MagicMock(), mock.MagicMock()
        game_objects.filter.return_value.values_list.return_value = games
        stint_objects.filter.return_value.values_list.return_value.iterator.side_effect = lambda **_: iter(stints)
        box_objects.filter.return_value.values_list.return_value = box
        for model, objects in ((NBAGame, game_objects), (NBAPlayerGameStint, stint_objects),
                               (NBAPlayerGameStats, box_objects)):
            patcher = mock.patch.object(model, "objects", objects)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _check(self, name, **fixture):
        self._patch(*_one_game(**fixture))
        return getattr(Command(), f"check_{name}")(2026, self.out_dir)

    def test_b5_clean_game_passes(self):
        res = self._check("b5")
        self.assertEqual(res["status"], "PASS", res)
        self.assertEqual(res["metrics"]["rotation.pts_ratio"], 1.0)

    def test_b5_one_wrong_stint_fails(self):
        res = self._check("b5", pts_scored=10)
        self.assertEqual(res["status"], "WARN", res)
        self.assertEqual(res["metrics"]["rotation.n_off_gt2"], 1)

    def test_b6_clean_game_passes(self):
        res = self._check("b6")
        self.assertEqual(res["status"], "PASS", res)
        self.assertEqual(res["metrics"]["rotation.median_abs_err_secs"], 0)

    def test_b6_one_wrong_stint_fails(self):
        res = self._check("b6", secs_on=2000)
        self.assertEqual(res["status"], "WARN", res)
        self.assertEqual(res["metrics"]["rotation.share_over_tol"], 0.1)

    def test_b6_whole_minute_box_scores_allow_120_seconds(self):
        res = self._check("b6", secs_on=2880 - 90)
        self.assertEqual(res["status"], "PASS", res)
        self.assertEqual(res["metrics"]["tolerance_secs"], 120)

    def test_b6_box_scores_with_seconds_keep_60_seconds(self):
        res = self._check("b6", box_with_seconds=True, secs_on=2880 - 90)
        self.assertEqual(res["status"], "WARN", res)
        self.assertEqual(res["metrics"]["tolerance_secs"], 60)
        self.assertEqual(res["metrics"]["rotation.share_over_tol"], 0.1)

    def test_b7_clean_game_passes(self):
        res = self._check("b7")
        self.assertEqual(res["status"], "PASS", res)
        self.assertEqual(res["metrics"]["rotation.share_pm_equal"], 1.0)

    def test_b7_one_wrong_stint_fails(self):
        res = self._check("b7", plus_minus=5)
        self.assertEqual(res["status"], "WARN", res)
        self.assertEqual(res["metrics"]["rotation.share_pm_equal"], 0.9)
        self.assertEqual(res["metrics"]["rotation.share_off_gt1"], 0.1)
        self.assertEqual(res["metrics"]["rotation.games_off_gt1"], [GAME_ID])

    def test_b7_one_point_miss_passes(self):
        res = self._check("b7", plus_minus=3)
        self.assertEqual(res["status"], "PASS", res)
        self.assertEqual(res["metrics"]["rotation.share_pm_equal"], 0.9)
        self.assertEqual(res["metrics"]["rotation.games_off_gt1"], [])

    def test_flagged_game_is_reported_on_its_own_line(self):
        self._patch(*_one_game(flagged=True, plus_minus=5))
        out = StringIO()
        call_command("nba_audit_bpr_data", "--seasons", "2026", "--check", "B7",
                     "--out-dir", str(self.out_dir), stdout=out)

        lines = out.getvalue().splitlines()
        headline = next(line for line in lines if line.startswith("  2026: "))
        flagged = next(line for line in lines if line.startswith("  2026 quality-flagged games: "))
        self.assertIn("no unflagged games", headline)
        self.assertIn("quality-flagged games: 1  WARN", flagged)
        self.assertIn("rotation.share_pm_equal=0.9", flagged)

    def test_console_shows_games_off_gt1_as_count_and_first_10(self):
        ids = [f"00299000{n:02d}" for n in range(1, 13)]
        line = Command._console_metric("rotation.games_off_gt1", ids)
        self.assertEqual(line, f"rotation.games_off_gt1=12 [{', '.join(ids[:10])}, ...]")
        self.assertEqual(Command._console_metric("rotation.games_off_gt1", []), "rotation.games_off_gt1=0 []")

    def test_b7_writes_every_game_off_by_more_than_1_to_csv(self):
        self._check("b7", plus_minus=5)
        rows = (self.out_dir / "b7_games_off_gt1_2026.csv").read_text().splitlines()
        self.assertEqual(rows, ["game_id,source,flagged,n_player_games_off_gt1,max_miss",
                                f"{GAME_ID},rotation,False,1,3"])

    def test_b7_clean_box_lists_no_inconsistent_games(self):
        res = self._check("b7")
        self.assertEqual(res["box_pm_inconsistent"], {"n_games": 0, "games": []})
        self.assertFalse((self.out_dir / "b7_box_pm_inconsistent_2026.csv").exists())

    def test_b7_box_off_by_2_still_adds_up(self):
        res = self._check("b7", box_pm_off=2)
        self.assertEqual(res["box_pm_inconsistent"]["n_games"], 0)
        self.assertEqual(res["metrics"]["rotation.n_player_games"], 10)

    def test_b7_leaves_out_and_lists_a_game_whose_box_does_not_add_up(self):
        # Game A: our stints match a box that doesn't add up (home total 10+8, want 10).
        # Game B: clean. Only B is judged; A is listed with its miss count.
        a_games, a_stints, a_box = _one_game(box_pm_off=8)
        b_games, b_stints, b_box = _one_game(game_pk=8, game_id="0029900002")
        self._patch(a_games + b_games, a_stints + b_stints, a_box + b_box)
        res = Command().check_b7(2026, self.out_dir)

        self.assertEqual(res["status"], "PASS", res)
        self.assertEqual(res["metrics"]["rotation.n_player_games"], 10)
        self.assertEqual(res["metrics"]["rotation.games_off_gt1"], [])
        self.assertEqual(res["box_pm_inconsistent"], {"n_games": 1, "games": [GAME_ID]})
        rows = (self.out_dir / "b7_box_pm_inconsistent_2026.csv").read_text().splitlines()
        self.assertEqual(rows, ["game_id,source,flagged,home_margin,home_box_pm_total,"
                                "away_box_pm_total,n_player_games_off_gt1",
                                f"{GAME_ID},rotation,False,2,18,-10,1"])
        self.assertFalse((self.out_dir / "b7_games_off_gt1_2026.csv").exists())

    def test_console_reports_games_whose_box_does_not_add_up(self):
        self._patch(*_one_game(box_pm_off=8))
        out = StringIO()
        call_command("nba_audit_bpr_data", "--seasons", "2026", "--check", "B7",
                     "--out-dir", str(self.out_dir), stdout=out)
        lines = out.getvalue().splitlines()
        self.assertIn(f"  2026 games whose box plus-minus doesn't add up (left out): 1 [{GAME_ID}]", lines)
        headline = next(line for line in lines if line.startswith("  2026: "))
        self.assertIn("no stints", headline)
