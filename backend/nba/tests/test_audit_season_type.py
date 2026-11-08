"""
PO.3: nba_audit_bpr_data --season-type. Each check reads one sector: regular
(default) uses games with counts_toward_regular_season=True and season stats
with season_type="regular"; playoffs / play_in use that season_type, skip B3,
report only B4's flagged-game count, and put the type in output filenames.

Real test database: one regular, one playoff and one play-in game, each with
the same ten players on court the whole game.
"""

import json
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from nba.models import (
    NBAGame, NBAPlayer, NBAPlayerGameStats, NBAPlayerGameStint, NBASeason, NBATeam,
)


class AuditSeasonTypeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        season = NBASeason.objects.create(year=2026, display_name="2025-26")
        home = NBATeam.objects.create(
            nba_team_id=1610612738, slug="boston-celtics", name="Boston Celtics",
            abbreviation="BOS", city="Boston", conference="East", division="Atlantic")
        away = NBATeam.objects.create(
            nba_team_id=1610612744, slug="golden-state-warriors", name="Golden State Warriors",
            abbreviation="GSW", city="Golden State", conference="West", division="Pacific")
        players = [(NBAPlayer.objects.create(player_id=100 + n, name=f"Home {n}"), home) for n in range(5)]
        players += [(NBAPlayer.objects.create(player_id=200 + n, name=f"Away {n}"), away) for n in range(5)]

        # Regular: stints match the box score. Playoffs: every stint plus-minus off
        # by 3 (the box stays consistent, so B7 judges the game).
        for game_id, season_type, counts, pm_off in (
            ("0022500001", "regular", True, 0),
            ("0042500001", "playoffs", False, 3),
            ("0052500001", "play_in", False, 0),
        ):
            game = NBAGame.objects.create(
                game_id=game_id, season=season, date=date(2026, 4, 1), home_team=home,
                away_team=away, home_score=4, away_score=2, season_type=season_type,
                counts_toward_regular_season=counts, status="Final", pbp_synced=True,
                lineup_source="rotation")
            for player, team in players:
                scored, allowed = (4, 2) if team == home else (2, 4)
                NBAPlayerGameStint.objects.create(
                    player=player, game=game, team=team, stint_index=0, period=1,
                    clock_start_secs=720, clock_end_secs=0, secs_on=2880,
                    pts_scored=scored, pts_allowed=allowed, plus_minus=scored - allowed + pm_off,
                    window_index=1)
                NBAPlayerGameStats.objects.create(
                    game=game, player=player, team=team, seconds_played=2880,
                    plus_minus=scored - allowed)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out_dir = Path(tmp.name)

    def _audit(self, *args):
        call_command("nba_audit_bpr_data", "--seasons", "2026", "--out-dir", str(self.out_dir),
                     *args, stdout=StringIO())
        suffix = "" if "--season-type" not in args or "regular" in args else f"_{args[args.index('--season-type') + 1]}"
        results = json.loads((self.out_dir / f"nba_audit_summary{suffix}.json").read_text())
        return {r["check"]: r for r in results}

    def test_regular_reads_only_regular_games(self):
        res = self._audit()
        self.assertEqual(res["B1"]["metrics"]["n_stints"], 10)
        self.assertEqual(res["B4"]["metrics"]["n_final_games"], 1)
        self.assertEqual(res["B7"]["metrics"]["rotation.n_player_games"], 10)
        self.assertEqual(res["B7"]["metrics"]["rotation.share_pm_equal"], 1.0)
        self.assertEqual(res["B7"]["status"], "PASS")
        self.assertEqual(res["B5"]["metrics"]["rotation.n_games"], 1)

    def test_playoffs_read_only_playoff_games(self):
        res = self._audit("--season-type", "playoffs")
        self.assertEqual(res["B1"]["metrics"]["n_stints"], 10)
        self.assertEqual(res["B7"]["metrics"]["rotation.share_pm_equal"], 0.0)
        self.assertEqual(res["B7"]["metrics"]["rotation.games_off_gt1"], ["0042500001"])
        self.assertEqual(res["B7"]["status"], "WARN")
        self.assertEqual(res["B3"]["status"], "SKIP")
        self.assertEqual(res["B4"]["status"], "INFO")
        self.assertEqual(res["B4"]["metrics"], {"n_final_games": 1, "n_pbp_flagged": 0, "pbp_flagged_frac": 0.0})
        self.assertTrue((self.out_dir / "b7_games_off_gt1_2026_playoffs.csv").exists())
        self.assertFalse((self.out_dir / "b7_games_off_gt1_2026.csv").exists())

    def test_play_in_reads_only_play_in_games(self):
        res = self._audit("--season-type", "play_in")
        self.assertEqual(res["B7"]["metrics"]["rotation.n_player_games"], 10)
        self.assertEqual(res["B7"]["metrics"]["rotation.share_pm_equal"], 1.0)
        self.assertEqual(res["B4"]["metrics"]["n_final_games"], 1)

    def test_regular_keeps_todays_filenames(self):
        self._audit("--check", "B7")
        self.assertTrue((self.out_dir / "nba_audit_summary.json").exists())
        self.assertEqual(sorted(p.name for p in self.out_dir.iterdir()), ["nba_audit_summary.json"])
