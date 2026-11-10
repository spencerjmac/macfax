"""
Phase 3 task 3.5: nba_fit_box_pooled trains each season Y's box model on the
seasons before Y only, picks alpha by CV with the one-standard-error rule
(leave-one-season-out with 3+ training seasons, 5-fold over players
otherwise; the first season fits itself), optionally weights rows by
on_court_poss / mean, and writes {nba_id: [box_obpr, box_dbpr]} JSON.
No database: loading and prediction inputs are stood in for.
"""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

import numpy as np
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from nba.management.commands import nba_fit_box_pooled as pooled

MOD = "nba.management.commands.nba_fit_box_pooled"


def _season_data(season, n=60, seed=None):
    rng = np.random.default_rng(season if seed is None else seed)
    X = rng.normal(size=(n, 4))
    beta = np.array([1.0, -0.5, 0.25, 0.0])
    pids = [season * 1000 + i for i in range(n)]
    return {"X_off": X, "X_def": X * 0.5, "y_off": X @ beta + rng.normal(0, 0.5, n),
            "y_def": X @ -beta + rng.normal(0, 0.5, n), "poss": rng.uniform(500, 5000, n),
            "pids": pids, "inputs": ("stats", "opp", "team", "career")}


class PlanTests(SimpleTestCase):

    def test_training_seasons_are_before_y(self):
        self.assertEqual(pooled.plan_training(2016), ([2016], "player_5fold"))   # no history: itself
        self.assertEqual(pooled.plan_training(2017), ([2016], "player_5fold"))
        self.assertEqual(pooled.plan_training(2018), ([2016, 2017], "player_5fold"))
        self.assertEqual(pooled.plan_training(2019), ([2016, 2017, 2018], "loso"))
        self.assertEqual(pooled.plan_training(2025)[0], list(range(2016, 2025)))


class OneSeRuleTests(SimpleTestCase):

    def test_largest_alpha_within_one_se_of_the_best(self):
        alphas = [1.0, 10.0, 100.0, 1000.0]
        errs = np.array([[1.00, 1.02, 0.98],    # mean 1.00
                         [0.90, 0.92, 0.88],    # mean 0.90 (best), SE 0.01155
                         [0.91, 0.90, 0.92],    # mean 0.91: within one SE
                         [1.20, 1.25, 1.30]])
        alpha, mean, se = pooled.one_se_choice(alphas, errs)
        self.assertEqual(alpha, 100.0)
        self.assertAlmostEqual(mean[1], 0.90)
        self.assertAlmostEqual(se[1], np.std([0.90, 0.92, 0.88], ddof=1) / np.sqrt(3))

    def test_best_alpha_when_nothing_else_is_close(self):
        errs = np.array([[2.0, 2.1], [1.0, 1.01], [3.0, 3.1]])
        self.assertEqual(pooled.one_se_choice([1.0, 3.0, 10.0], errs)[0], 3.0)


class FoldAndWeightTests(SimpleTestCase):

    def test_loso_folds_are_seasons(self):
        seasons = np.array([2016, 2016, 2017, 2018])
        np.testing.assert_array_equal(pooled.fold_labels("loso", seasons, np.arange(4)), seasons)

    def test_player_folds_keep_a_player_together(self):
        players = np.array([1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 2])
        labels = pooled.fold_labels("player_5fold", np.zeros(12), players)
        self.assertEqual(len(set(labels)), 5)
        for p in set(players):
            self.assertEqual(len(set(labels[players == p])), 1)

    def test_poss_weights_average_one(self):
        w = pooled.poss_weights(np.array([500.0, 1000.0, 4500.0]))
        self.assertAlmostEqual(w.mean(), 1.0)
        np.testing.assert_allclose(w, [0.25, 0.5, 2.25])


class FitSeasonTests(SimpleTestCase):

    def setUp(self):
        self.data = {s: _season_data(s) for s in range(2016, 2021)}

    def test_only_seasons_before_y_are_used(self):
        _, info = pooled.fit_season(2020, self.data, False)
        self.assertEqual(info["train_seasons"], [2016, 2017, 2018, 2019])
        self.assertEqual(info["n_train"], 4 * 60)
        # Changing season Y's own (or later) data does not change Y's model.
        a1, _ = pooled.fit_season(2019, self.data, False)
        changed = dict(self.data)
        changed[2019] = _season_data(2019, seed=99)
        changed[2020] = _season_data(2020, seed=98)
        a2, _ = pooled.fit_season(2019, changed, False)
        X = np.ones((1, 4))
        self.assertEqual(a1["off_pipeline"].predict(X)[0], a2["off_pipeline"].predict(X)[0])

    def test_alpha_from_grid_and_loso_folds(self):
        _, info = pooled.fit_season(2020, self.data, False)
        self.assertEqual(info["method"], "loso")
        self.assertIn(info["off_alpha"], pooled.ALPHAS)
        self.assertIn(info["def_alpha"], pooled.ALPHAS)
        self.assertEqual(len(info["off_cv_mean"]), len(pooled.ALPHAS))

    def test_first_season_fits_itself(self):
        _, info = pooled.fit_season(2016, self.data, False)
        self.assertEqual((info["train_seasons"], info["method"]), ([2016], "player_5fold"))

    def test_weighting_passes_normalized_poss(self):
        calls = []
        real = pooled.fit_ridge

        def spy(X, y, w, alpha):
            calls.append(w)
            return real(X, y, w, alpha)

        with mock.patch.object(pooled, "fit_ridge", spy):
            pooled.fit_season(2018, self.data, True)
        final_w = calls[-1]   # the last fit is the final defense model on all training rows
        expected = pooled.poss_weights(np.concatenate([self.data[2016]["poss"], self.data[2017]["poss"]]))
        np.testing.assert_allclose(final_w, expected)
        self.assertAlmostEqual(final_w.mean(), 1.0)
        with mock.patch.object(pooled, "fit_ridge", spy):
            calls.clear()
            pooled.fit_season(2018, self.data, False)
        self.assertTrue(all(w is None for w in calls))


class CommandTests(SimpleTestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name) / "box_pooled"
        self.loaded = []

        def load(season, career_floor):
            self.loaded.append(season)
            return _season_data(season)

        def predict(stats, opp, team, artifacts, career):
            return {1: {"box_obpr": 1.5, "box_dbpr": -0.25, "archetype": "x"},
                    2: {"box_obpr": 0.0, "box_dbpr": 0.75, "archetype": "y"}}

        for target, new in (("load_season", load), ("predict_nba_box_bpr", predict),
                            ("nba_ids_for", lambda pks: {1: 201939, 2: 2544})):
            patcher = mock.patch(f"{MOD}.{target}", new)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_writes_json_per_season_and_alphas(self):
        call_command("nba_fit_box_pooled", "--seasons", "2017", "2016", "--out-dir", str(self.out),
                     stdout=StringIO())
        self.assertEqual(json.loads((self.out / "box_2017.json").read_text()),
                         {"201939": [1.5, -0.25], "2544": [0.0, 0.75]})
        self.assertTrue((self.out / "box_2016.json").exists())
        info = json.loads((self.out / "alphas.json").read_text())
        self.assertEqual([i["season"] for i in info], [2016, 2017])
        self.assertEqual(info[1]["train_seasons"], [2016])
        self.assertEqual(sorted(set(self.loaded)), [2016, 2017])   # nothing after the last season

    def test_season_before_history_start_is_an_error(self):
        with self.assertRaises(CommandError):
            call_command("nba_fit_box_pooled", "--seasons", "2015", "--out-dir", str(self.out),
                         stdout=StringIO())
