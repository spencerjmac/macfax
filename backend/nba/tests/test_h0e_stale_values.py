"""
H.0e: two fixes found in H.2026.

1. Audit B1 keys duplicates on window_index where it is stored, so zero-length
   stints of one player in different lineup windows within the same second
   are not duplicates; rows without a window keep the clock key.
2. nba_compute_box_bpr and nba_compute_baseline_rapm clear their fields on
   the season's regular rows before writing, so afterwards only the players
   this run produced hold values. Other seasons and playoff rows are left
   alone; bpr_last_updated is not touched by the clear. Box BPR also clears
   nba_archetype (H.2026 finish).

Real test database; model fitting and NBA-wide inputs are stood in for.
"""

import json
import tempfile
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from nba.models import (
    NBAGame, NBAPlayer, NBAPlayerGameStint, NBAPlayerSeasonStats, NBASeason, NBATeam,
)

OLD_STAMP = datetime(2026, 7, 5, tzinfo=timezone.utc)


class _Fixture(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.s2026 = NBASeason.objects.create(year=2026, display_name="2025-26")
        cls.s2025 = NBASeason.objects.create(year=2025, display_name="2024-25")
        cls.home = NBATeam.objects.create(
            nba_team_id=1610612738, slug="boston-celtics", name="Boston Celtics",
            abbreviation="BOS", city="Boston", conference="East", division="Atlantic")
        cls.away = NBATeam.objects.create(
            nba_team_id=1610612744, slug="golden-state-warriors", name="Golden State Warriors",
            abbreviation="GSW", city="Golden State", conference="West", division="Pacific")


class B1WindowKeyTests(_Fixture):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out_dir = Path(tmp.name)
        self.game = NBAGame.objects.create(
            game_id="0022500001", season=self.s2026, date=date(2026, 1, 1), home_team=self.home,
            away_team=self.away, home_score=100, away_score=90, season_type="regular",
            counts_toward_regular_season=True, status="Final")
        self.player = NBAPlayer.objects.create(player_id=101, name="Sub Twice")

    def _stint(self, index, start, end, window):
        NBAPlayerGameStint.objects.create(
            player=self.player, game=self.game, team=self.home, stint_index=index, period=1,
            clock_start_secs=start, clock_end_secs=end, secs_on=start - end, window_index=window)

    def _b1(self):
        call_command("nba_audit_bpr_data", "--seasons", "2026", "--check", "B1",
                     "--out-dir", str(self.out_dir), stdout=StringIO())
        return json.loads((self.out_dir / "nba_audit_summary.json").read_text())[0]

    def test_zero_length_stints_in_different_windows_are_not_duplicates(self):
        self._stint(0, 720, 300, 1)
        self._stint(1, 300, 300, 2)
        self._stint(2, 300, 300, 3)
        res = self._b1()
        self.assertEqual(res["metrics"]["n_exact_dupes"], 0)
        self.assertEqual(res["status"], "PASS")

    def test_same_window_twice_is_still_a_duplicate(self):
        self._stint(0, 300, 300, 2)
        self._stint(1, 300, 300, 2)
        self.assertEqual(self._b1()["metrics"]["n_exact_dupes"], 1)

    def test_rows_without_a_window_keep_the_clock_key(self):
        self._stint(0, 300, 300, None)
        self._stint(1, 300, 300, None)
        res = self._b1()
        self.assertEqual(res["metrics"]["n_exact_dupes"], 1)
        self.assertEqual(res["status"], "FAIL")


def _row(player, season, season_type="regular", **kw):
    return NBAPlayerSeasonStats.objects.create(
        player=player, season=season, team=None, season_type=season_type, gp=60, mpg=25.0, **kw)


class BoxBprClearsStaleValuesTests(_Fixture):
    MOD = "nba.management.commands.nba_compute_box_bpr"

    def setUp(self):
        # 31 players this run predicts (box BPR needs >= 30 targets) ...
        self.predicted = []
        for n in range(31):
            p = NBAPlayer.objects.create(player_id=1000 + n, name=f"Player {n}")
            _row(p, self.s2026, baseline_obpr=1.0, baseline_dbpr=0.5)
            self.predicted.append(p)
        # ... one it no longer predicts, still holding values from an old run,
        self.stale = _row(NBAPlayer.objects.create(player_id=2000, name="Old Box"), self.s2026,
                          box_obpr=2.0, box_dbpr=1.0, box_bpr=3.0, nba_archetype="scorer",
                          bpr_last_updated=OLD_STAMP)
        # ... and rows the clear must leave alone: another season and a playoff row.
        other = NBAPlayer.objects.create(player_id=3000, name="Other Season")
        self.other_season = _row(other, self.s2025, box_obpr=1.5, box_dbpr=0.5, box_bpr=2.0)
        self.playoff = _row(other, self.s2026, season_type="playoffs", box_obpr=1.5, box_dbpr=0.5, box_bpr=2.0)

        preds = {p.pk: {"box_obpr": 1.0, "box_dbpr": 0.25, "archetype": "connector"} for p in self.predicted}
        artifacts = {"off_cv_alpha": 5.0, "def_cv_alpha": 10.0, "n_train_off": 31, "n_train_def": 31,
                     "n_mpir_excluded": 0}
        for target, value in {
            "compute_opp_quality_map": mock.MagicMock(return_value={}),
            "compute_team_adj_em_map": mock.MagicMock(return_value={}),
            "build_career_stats_map": mock.MagicMock(return_value={}),
            "_load_lebron_targets": mock.MagicMock(return_value={}),
            "train_nba_box_bpr": mock.MagicMock(return_value=artifacts),
            "predict_nba_box_bpr": mock.MagicMock(return_value=preds),
        }.items():
            patcher = mock.patch(f"{self.MOD}.{target}", value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name in ("_print_top_players", "_print_fix_summary"):
            patcher = mock.patch(f"{self.MOD}.Command.{name}")
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_player_not_predicted_loses_old_box_values(self):
        call_command("nba_compute_box_bpr", "--season", "2026", stdout=StringIO())

        self.stale.refresh_from_db()
        self.assertEqual((self.stale.box_obpr, self.stale.box_dbpr, self.stale.box_bpr), (None, None, None))
        self.assertIsNone(self.stale.nba_archetype)
        self.assertEqual(self.stale.bpr_last_updated, OLD_STAMP)       # left alone
        self.assertEqual(NBAPlayerSeasonStats.objects.filter(
            season=self.s2026, season_type="regular", nba_archetype__isnull=False).count(), 31)
        self.assertEqual(NBAPlayerSeasonStats.objects.filter(
            season=self.s2026, season_type="regular", box_bpr__isnull=False).count(), 31)
        self.assertEqual(NBAPlayerSeasonStats.objects.get(player=self.predicted[0], season=self.s2026).box_bpr, 1.25)

    def test_other_seasons_and_playoff_rows_are_untouched(self):
        call_command("nba_compute_box_bpr", "--season", "2026", stdout=StringIO())

        for row in (self.other_season, self.playoff):
            row.refresh_from_db()
            self.assertEqual((row.box_obpr, row.box_dbpr, row.box_bpr), (1.5, 0.5, 2.0))

    def test_dry_run_clears_nothing(self):
        call_command("nba_compute_box_bpr", "--season", "2026", "--dry-run", stdout=StringIO())

        self.stale.refresh_from_db()
        self.assertEqual((self.stale.box_bpr, self.stale.nba_archetype), (3.0, "scorer"))


class BaselineRapmClearsStaleValuesTests(_Fixture):
    MOD = "nba.management.commands.nba_compute_baseline_rapm"

    def setUp(self):
        self.fitted = NBAPlayer.objects.create(player_id=101, name="Fitted")
        self.fitted_row = _row(self.fitted, self.s2026)
        self.stale = _row(NBAPlayer.objects.create(player_id=202, name="Not Fitted Now"), self.s2026,
                          baseline_obpr=2.0, baseline_dbpr=1.0, off_poss=900.0, def_poss=880.0)
        self.other_season = _row(NBAPlayer.objects.create(player_id=303, name="Other"), self.s2025,
                                 baseline_obpr=1.0, baseline_dbpr=1.0, off_poss=100.0, def_poss=100.0)
        obs = [{"season_year": 2026, "home_player_ids": [101], "away_player_ids": [],
                "home_poss": 10.0, "away_poss": 9.0}]
        fit = {"lambda": 500.0, "hca": 0.0, "intercept": 0.0,
               "obpr": {(101, 2026): 1.5}, "dbpr": {(101, 2026): 0.5}}
        for target, value in {
            "build_nba_observations": mock.MagicMock(return_value=obs),
            "fit_baseline_rapm": mock.MagicMock(return_value=fit),
        }.items():
            patcher = mock.patch(f"{self.MOD}.{target}", value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_player_not_fitted_loses_old_baseline_values(self):
        call_command("nba_compute_baseline_rapm", "--season", "2026", stdout=StringIO())

        self.stale.refresh_from_db()
        self.fitted_row.refresh_from_db()
        self.other_season.refresh_from_db()
        self.assertEqual((self.stale.baseline_obpr, self.stale.baseline_dbpr,
                          self.stale.off_poss, self.stale.def_poss), (None, None, None, None))
        self.assertEqual((self.fitted_row.baseline_obpr, self.fitted_row.baseline_dbpr,
                          self.fitted_row.off_poss, self.fitted_row.def_poss), (1.5, 0.5, 10.0, 9.0))
        self.assertEqual(self.other_season.baseline_obpr, 1.0)

    def test_dry_run_clears_nothing(self):
        call_command("nba_compute_baseline_rapm", "--season", "2026", "--dry-run", stdout=StringIO())

        self.stale.refresh_from_db()
        self.assertEqual(self.stale.baseline_obpr, 2.0)
