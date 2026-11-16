"""
Task 5.2: nba_fit_box_pooled as the production box BPR.

- The final recipe is the default: box_only features, a 3-season pooled RAPM
  target at lambda 300, alphas up to 1000, opp_quality, history start and
  career floor 2006.
- --season Y --write fits Y on the seasons before Y, then clears box_obpr,
  box_dbpr, box_bpr and nba_archetype on Y's regular rows and writes the fit
  (box_bpr = box_obpr + box_dbpr, archetype from the box model's assignment)
  to every row of each predicted player. Other seasons, playoff rows and
  bpr_last_updated are left alone.
- --season Y --dry-run writes nothing and prints the top 20, whose values are
  the ones --seasons Y --out-dir writes to box_<Y>.json.

Real test database for the write; loading, targets and fitting are stood in for.
"""

import json
import re
import tempfile
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest import mock

import numpy as np
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from nba.management.commands import nba_fit_box_pooled as pooled
from nba.models import NBAPlayer, NBAPlayerSeasonStats, NBASeason, NBATeam

MOD = "nba.management.commands.nba_fit_box_pooled"
OLD_STAMP = datetime(2026, 7, 5, tzinfo=timezone.utc)


def _wide_season(season, n=40):
    rng = np.random.default_rng(season)
    n_off, n_def = len(pooled.OFF_FEATURES), len(pooled.DEF_FEATURES)
    Xo, Xd = rng.normal(size=(n, n_off)), rng.normal(size=(n, n_def))
    return {"X_off": Xo, "X_def": Xd, "y_off": Xo[:, 0] + rng.normal(0, 0.3, n),
            "y_def": Xd[:, 0] + rng.normal(0, 0.3, n), "poss": rng.uniform(500, 5000, n),
            "pids": [season * 1000 + i for i in range(n)], "inputs": ("stats", "opp", "team", "career")}


class RecipeDefaultsTests(SimpleTestCase):
    """With no options the command runs the final recipe."""

    def test_defaults_reach_targets_loading_and_fit(self):
        loads, windows, fits = [], [], []

        def load(season, career_floor, targets=None, team_feature="opp_quality"):
            loads.append((season, career_floor, team_feature))
            return _wide_season(season)

        def window(season, start, k, lam=None):
            windows.append((season, start, k, lam))
            return {"obpr": {}, "dbpr": {}, "lambda": lam, "years": pooled.window_years(season, start, k)}

        real = pooled.fit_season

        def spy(*a, **k):
            fits.append((a, k))
            return real(*a, **k)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch(f"{MOD}.load_season", load), mock.patch(f"{MOD}.window_targets", window), \
             mock.patch(f"{MOD}.fit_season", spy), mock.patch(f"{MOD}.predict_nba_box_bpr", lambda *a: {}), \
             mock.patch(f"{MOD}.nba_ids_for", lambda pks: {}):
            call_command("nba_fit_box_pooled", "--seasons", "2009", "--out-dir", tmp.name, stdout=StringIO())
        self.assertEqual(windows, [(2006, 2006, 3, 300.0), (2007, 2006, 3, 300.0), (2008, 2006, 3, 300.0)])
        self.assertEqual({(c, t) for _s, c, t in loads}, {(2006, "opp_quality")})   # career floor 2006
        self.assertEqual(sorted({s for s, _c, _t in loads}), [2006, 2007, 2008, 2009])
        (args, kw), = fits
        self.assertEqual(args[0], 2009)
        self.assertEqual(args[3], 2006)                      # history start
        self.assertEqual(kw["features"], "box_only")
        self.assertEqual(kw["team_feature"], "opp_quality")
        self.assertEqual(kw["alphas"][-1], 1000.0)
        info = json.loads((Path(tmp.name) / "alphas.json").read_text())[0]
        self.assertEqual((info["target"], info["target_lambda_fixed"], info["train_seasons"]),
                         ("window3", 300.0, [2006, 2007, 2008]))


class ArgumentTests(SimpleTestCase):

    def _call(self, *args):
        call_command("nba_fit_box_pooled", *args, stdout=StringIO())

    def test_mode_errors(self):
        with self.assertRaises(CommandError):
            self._call("--season", "2026")                                # neither --write nor --dry-run
        with self.assertRaises(CommandError):
            self._call("--season", "2026", "--write", "--dry-run")
        with self.assertRaises(CommandError):
            self._call("--seasons", "2026", "--write", "--out-dir", "x")
        with self.assertRaises(CommandError):
            self._call("--seasons", "2026")                               # no --out-dir
        with self.assertRaises(CommandError):
            self._call("--season", "2026", "--dry-run", "--out-dir", "x")
        with self.assertRaises(CommandError):
            self._call("--season", "2026", "--write", "--newcomer-means")
        with self.assertRaises(CommandError):
            self._call("--out-dir", "x")                                  # neither --season nor --seasons


def _row(player, season, team=None, season_type="regular", **kw):
    return NBAPlayerSeasonStats.objects.create(
        player=player, season=season, team=team, season_type=season_type, gp=60, mpg=25.0, **kw)


class WriteTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.s2026 = NBASeason.objects.create(year=2026, display_name="2025-26")
        cls.s2025 = NBASeason.objects.create(year=2025, display_name="2024-25")
        cls.bos = NBATeam.objects.create(
            nba_team_id=1610612738, slug="boston-celtics", name="Boston Celtics",
            abbreviation="BOS", city="Boston", conference="East", division="Atlantic")
        cls.gsw = NBATeam.objects.create(
            nba_team_id=1610612744, slug="golden-state-warriors", name="Golden State Warriors",
            abbreviation="GSW", city="Golden State", conference="West", division="Pacific")

    def setUp(self):
        # 25 predicted players (one traded: two rows), one not predicted holding old values,
        # and rows the write must leave alone: another season and a playoff row.
        self.players = [NBAPlayer.objects.create(player_id=1000 + n, name=f"Player {n:02d}") for n in range(25)]
        for p in self.players[1:]:
            _row(p, self.s2026, bpr_last_updated=OLD_STAMP)
        self.traded = [_row(self.players[0], self.s2026, team=self.bos), _row(self.players[0], self.s2026, team=self.gsw)]
        self.stale = _row(NBAPlayer.objects.create(player_id=2000, name="Old Box"), self.s2026,
                          box_obpr=2.0, box_dbpr=1.0, box_bpr=3.0, nba_archetype="scorer",
                          bpr_last_updated=OLD_STAMP)
        self.other_season = _row(self.players[1], self.s2025, box_obpr=1.5, box_dbpr=0.5, box_bpr=2.0,
                                 nba_archetype="creator")
        self.playoff = _row(self.players[1], self.s2026, season_type="playoffs", box_obpr=1.5, box_dbpr=0.5,
                            box_bpr=2.0, nba_archetype="creator")
        # Distinct totals so the top 20 order is fixed; values with more than 4 decimals.
        self.preds = {p.pk: {"box_obpr": 0.123456 * n - 1.0, "box_dbpr": 0.5 - 0.011111 * n,
                             "archetype": ("creator", "interior", "scorer")[n % 3]}
                      for n, p in enumerate(self.players)}
        self.fit_calls = []

        def fit(season, data, weighted, start, **kw):
            self.fit_calls.append((season, sorted(data)))
            return {}, {"season": season, "train_seasons": sorted(data), "method": "loso",
                        "n_train": 1, "off_alpha": 100.0, "def_alpha": 300.0}

        for target, value in {
            "load_season": lambda s, c, t=None, **_: {"inputs": ("stats", "opp", "team", "career")},
            "window_targets": lambda s, start, k, lam=None: {"obpr": {}, "dbpr": {}, "lambda": lam,
                                                             "years": [s]},
            "fit_season": fit,
            "predict_nba_box_bpr": lambda *a: self.preds,
        }.items():
            patcher = mock.patch(f"{MOD}.{target}", value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _call(self, *args):
        out = StringIO()
        call_command("nba_fit_box_pooled", *args, "--history-start", "2024", stdout=out)
        return out.getvalue()

    def test_write_clears_then_writes_regular_rows(self):
        self._call("--season", "2026", "--write")
        self.assertEqual(self.fit_calls, [(2026, [2024, 2025])])      # seasons before Y only

        self.stale.refresh_from_db()
        self.assertEqual((self.stale.box_obpr, self.stale.box_dbpr, self.stale.box_bpr, self.stale.nba_archetype),
                         (None, None, None, None))
        self.assertEqual(self.stale.bpr_last_updated, OLD_STAMP)
        for n, p in enumerate(self.players):
            pred = self.preds[p.pk]
            for row in NBAPlayerSeasonStats.objects.filter(player=p, season=self.s2026, season_type="regular"):
                self.assertEqual(row.box_obpr, pred["box_obpr"])
                self.assertEqual(row.box_dbpr, pred["box_dbpr"])
                self.assertEqual(row.box_bpr, round(pred["box_obpr"] + pred["box_dbpr"], 3))
                self.assertEqual(row.nba_archetype, pred["archetype"])
        for row in self.traded:                                        # both teams' rows
            row.refresh_from_db()
            self.assertIsNotNone(row.box_bpr)
        self.assertEqual(NBAPlayerSeasonStats.objects.filter(
            season=self.s2026, season_type="regular", box_bpr__isnull=False).count(), 26)
        self.assertEqual(NBAPlayerSeasonStats.objects.get(pk=self.traded[0].pk).bpr_last_updated, None)

    def test_other_seasons_and_playoff_rows_are_untouched(self):
        self._call("--season", "2026", "--write")
        for row in (self.other_season, self.playoff):
            row.refresh_from_db()
            self.assertEqual((row.box_obpr, row.box_dbpr, row.box_bpr, row.nba_archetype), (1.5, 0.5, 2.0, "creator"))

    def test_dry_run_writes_nothing_and_prints_top_20_matching_the_json(self):
        printed = self._call("--season", "2026", "--dry-run")
        self.stale.refresh_from_db()
        self.assertEqual((self.stale.box_bpr, self.stale.nba_archetype), (3.0, "scorer"))
        self.assertEqual(NBAPlayerSeasonStats.objects.filter(season=self.s2026, box_obpr__isnull=False).count(), 2)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self._call("--seasons", "2026", "--out-dir", tmp.name)
        dumped = json.loads((Path(tmp.name) / "box_2026.json").read_text())

        rows = re.findall(r"^\s+(\d+)\. (.+?)\s+nba_id=(\d+)\s+obpr=([-+.\d]+)\s+dbpr=([-+.\d]+)\s+box_bpr=([-+.\d]+)",
                          printed, flags=re.M)
        self.assertEqual(len(rows), 20)
        expected = sorted(dumped.items(), key=lambda kv: kv[1][0] + kv[1][1], reverse=True)[:20]
        for (rank, _name, nba_id, o, d, tot), (exp_id, (exp_o, exp_d)) in zip(rows, expected):
            self.assertEqual(nba_id, exp_id)
            self.assertEqual(float(o), round(exp_o, 4))
            self.assertEqual(float(d), round(exp_d, 4))
            self.assertAlmostEqual(float(tot), exp_o + exp_d, places=4)
        self.assertEqual([int(r[0]) for r in rows], list(range(1, 21)))
        self.assertIn("Player 24", rows[0][1])
