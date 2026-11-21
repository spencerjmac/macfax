"""
Task 5.9: the daily pipeline picks its rating steps by data.

Invariants pinned here:
- Season Y-1 without native rows: update_nba_all / update_nba_players run today's steps
  (box BPR, final BPR), never the native ones.
- Season Y-1 with native rows: the native steps run in order (player stats, minutes check,
  team ratings, advanced, play-by-play, baseline RAPM, pooled box fit --write, native BPR
  --write, career BPR, ...), and nba_compute_box_bpr / nba_compute_final_bpr never run.
- Over 1% of players with season rows that disagree with their game logs: the rating steps
  are skipped (yesterday's ratings stay) and the run fails; a smaller share only warns.
- A failing native step is logged as keeping yesterday's ratings; later steps still run.
- Both file caches live under settings.NBA_CACHE_DIR; the possession fingerprint changes
  when a stint row is edited in place.
"""

from datetime import date
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from nba.management.commands import nba_compute_native_bpr as nb
from nba.models import (NBAGame, NBAPlayer, NBAPlayerGameStats, NBAPlayerGameStint, NBAPlayerSeasonStats,
                        NBASeason, NBATeam)
from nba.native_pipeline import minutes_check
from nba.providers import nba_api_provider

ALL_CALL = "nba.management.commands.update_nba_all.call_command"
PLAYERS_CALL = "ncaa.management.commands._pipeline_base.call_command"
LEBRON = "nba.management.commands.update_nba_all.lebron_csv_path"

NATIVE_ORDER = [
    "nba_compute_player_stats", "nba_compute_ratings", "nba_sync_player_advanced", "nba_sync_play_by_play",
    "nba_compute_baseline_rapm", "nba_fit_box_pooled", "nba_compute_native_bpr", "nba_compute_career_bpr",
    "nba_sync_injury_report",
]


def cmds(cc):
    return [c.args[0] for c in cc.call_args_list if c.args[0] != "nba_sync_teams"]


class Fixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prev = NBASeason.objects.create(year=2026, display_name="2025-26")
        cls.season = NBASeason.objects.create(year=2027, display_name="2026-27")
        cls.home = NBATeam.objects.create(
            nba_team_id=1, slug="h", name="H", abbreviation="HOM", city="H", conference="East", division="A")
        cls.away = NBATeam.objects.create(
            nba_team_id=2, slug="a", name="A", abbreviation="AWY", city="A", conference="West", division="B")
        cls.game = NBAGame.objects.create(
            game_id="g1", season=cls.season, date=date(2026, 10, 21), home_team=cls.home, away_team=cls.away,
            home_score=100, away_score=90, season_type="regular", counts_toward_regular_season=True, status="Final")
        cls.players = [NBAPlayer.objects.create(player_id=100 + i, name=f"P{i}") for i in range(10)]

    def make_native_prev(self):
        NBAPlayerSeasonStats.objects.create(player=self.players[0], team=self.home, season=self.prev, gp=50,
                                            mpg=30.0, obpr=1.0, dbpr=0.0, obpr_raw=1.0, dbpr_raw=0.0,
                                            bpr=1.0, bpr_model=nb.NATIVE_MODEL)

    def make_matching_rows(self, n=10):
        """Each player: one 30-minute game log and the season row the rollup would write."""
        for p in self.players[:n]:
            NBAPlayerGameStats.objects.create(game=self.game, player=p, team=self.home, seconds_played=1800)
            NBAPlayerSeasonStats.objects.create(player=p, team=self.home, season=self.season, gp=1, mpg=30.0)

    def run_all(self, side_effect=None):
        out, err = StringIO(), StringIO()
        with mock.patch(ALL_CALL, side_effect=side_effect) as cc, \
                mock.patch(LEBRON, return_value=Path("/nope/lebron-data-2027.csv")):
            try:
                call_command("update_nba_all", "--season", "2027", stdout=out, stderr=err)
                code = 0
            except SystemExit as e:
                code = e.code
        return cc, out.getvalue(), err.getvalue(), code


class UpdateNBAAllPathTests(Fixture):
    def test_earlier_path_without_native_last_season(self):
        self.make_matching_rows()
        cc, out, _, code = self.run_all()
        called = cmds(cc)
        self.assertNotIn("nba_compute_native_bpr", called)
        self.assertNotIn("nba_fit_box_pooled", called)
        self.assertNotIn("nba_sync_play_by_play", called)        # only with --with-pbp, as today
        self.assertIn("missing LEBRON prior", out)               # today's final BPR gate still applies
        self.assertNotIn("[NATIVE]", out)
        self.assertEqual(code, 0)

    def test_native_path_order(self):
        self.make_native_prev()
        self.make_matching_rows()
        cc, out, _, code = self.run_all()
        called = [c for c in cmds(cc) if c not in ("nba_sync_games", "nba_sync_team_logs")]
        self.assertEqual(called, NATIVE_ORDER)
        kw = {c.args[0]: c.kwargs for c in cc.call_args_list}
        self.assertEqual(kw["nba_fit_box_pooled"], {"season": 2027, "write": True})
        self.assertEqual(kw["nba_compute_native_bpr"], {"season": 2027, "write": True})
        self.assertNotIn("--force", str(kw["nba_sync_play_by_play"]))
        self.assertIn("0 of 10 players mismatch", out)
        self.assertIn("ALL STEPS SUCCESSFUL", out)
        self.assertEqual(code, 0)

    def test_ingest_runs_before_native_steps(self):
        self.make_native_prev()
        self.make_matching_rows()
        cc, _, _, _ = self.run_all()
        called = cmds(cc)
        self.assertEqual(called[:2], ["nba_sync_games", "nba_sync_team_logs"])
        self.assertNotIn("nba_compute_box_bpr", called)
        self.assertNotIn("nba_compute_final_bpr", called)

    def test_minutes_mismatch_over_one_percent_skips_rating_steps(self):
        self.make_native_prev()
        self.make_matching_rows()
        NBAPlayerSeasonStats.objects.filter(player=self.players[3], season=self.season).update(gp=2)
        cc, out, err, code = self.run_all()
        called = cmds(cc)
        for skipped in ("nba_compute_baseline_rapm", "nba_fit_box_pooled", "nba_compute_native_bpr"):
            self.assertNotIn(skipped, called)
        self.assertIn("nba_compute_career_bpr", called)
        self.assertIn("1 of 10 players mismatch (10.0%)", err)
        self.assertIn("P3: season rows 2 games", out)
        self.assertEqual(code, 1)

    def test_native_failure_keeps_ratings_and_continues(self):
        self.make_native_prev()
        self.make_matching_rows()

        def fake(name, **kwargs):
            if name == "nba_compute_native_bpr":
                raise RuntimeError("no stints")

        cc, _, err, code = self.run_all(side_effect=fake)
        self.assertIn("[KEEP] native BPR failed for 2027", err)
        self.assertIn("nba_compute_career_bpr", cmds(cc))
        self.assertEqual(code, 1)


class UpdateNBAPlayersPathTests(Fixture):
    def run_players(self):
        out, err = StringIO(), StringIO()
        with mock.patch(PLAYERS_CALL) as cc:
            call_command("update_nba_players", "--season", "2027", "--skip-ingest", stdout=out, stderr=err)
        return cmds(cc), out.getvalue()

    def test_earlier_path(self):
        self.make_matching_rows()
        called, _ = self.run_players()
        self.assertEqual(called, ["nba_compute_player_stats", "nba_sync_player_advanced", "nba_compute_box_bpr",
                                  "nba_compute_final_bpr", "nba_compute_career_bpr"])

    def test_native_path(self):
        self.make_native_prev()
        self.make_matching_rows()
        called, out = self.run_players()
        self.assertEqual(called, ["nba_compute_player_stats", "nba_sync_player_advanced",
                                  "nba_compute_baseline_rapm", "nba_fit_box_pooled", "nba_compute_native_bpr",
                                  "nba_compute_career_bpr"])
        self.assertIn("0 of 10 players mismatch", out)


class MinutesCheckTests(Fixture):
    def test_matching_rows(self):
        self.make_matching_rows()
        check = minutes_check(2027)
        self.assertEqual((check.players, check.mismatches), (10, []))

    def test_minutes_off_and_player_missing_a_row(self):
        self.make_matching_rows(9)
        NBAPlayerSeasonStats.objects.filter(player=self.players[0], season=self.season).update(mpg=29.0)
        NBAPlayerGameStats.objects.create(game=self.game, player=self.players[9], team=self.home,
                                          seconds_played=600)
        check = minutes_check(2027)
        self.assertEqual(check.players, 10)
        self.assertEqual([m["nba_id"] for m in check.mismatches], [100, 109])
        self.assertTrue(check.too_many)

    def test_dnp_game_logs_are_not_games_played(self):
        self.make_matching_rows()
        game2 = NBAGame.objects.create(
            game_id="g2", season=self.season, date=date(2026, 10, 23), home_team=self.home, away_team=self.away,
            home_score=100, away_score=90, season_type="regular", counts_toward_regular_season=True, status="Final")
        NBAPlayerGameStats.objects.create(game=game2, player=self.players[0], team=self.home, seconds_played=None)
        self.assertEqual(minutes_check(2027).mismatches, [])


class CacheTests(Fixture):
    def test_both_caches_under_one_configurable_directory(self):
        self.assertEqual(nb.POSS_CACHE_DIR, settings.NBA_CACHE_DIR / "native_poss_cache")
        self.assertEqual(nba_api_provider.PBP_CACHE_DIR, settings.NBA_CACHE_DIR / "pbp_cache")
        repo = Path(__file__).resolve().parents[3]
        self.assertFalse(settings.NBA_CACHE_DIR.resolve().is_relative_to(repo))

    def test_fingerprint_sees_an_edit_in_place(self):
        stint = NBAPlayerGameStint.objects.create(
            player=self.players[0], game=self.game, team=self.home, stint_index=0, period=1,
            clock_start_secs=720, clock_end_secs=0, secs_on=720, pts_scored=20, pts_allowed=18, window_index=1)
        before = nb.stint_fingerprint(2027)
        NBAPlayerGameStint.objects.filter(id=stint.id).update(pts_scored=25)
        after = nb.stint_fingerprint(2027)
        self.assertEqual({k: before[k] for k in ("n", "secs", "max_id")}, {k: after[k] for k in ("n", "secs", "max_id")})
        self.assertNotEqual(before["content"], after["content"])
        self.assertIsNotNone(before["content"])
