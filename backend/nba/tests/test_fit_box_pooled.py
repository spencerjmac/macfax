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
        self.assertIn(info["off_alpha"], pooled.alpha_grid())
        self.assertIn(info["def_alpha"], pooled.alpha_grid())
        self.assertEqual(len(info["off_cv_mean"]), len(pooled.alpha_grid()))

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

        def load(season, career_floor, targets=None):
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


def _wide_season(season, n=60):
    """Full-width feature rows (OFF_FEATURES / DEF_FEATURES columns)."""
    rng = np.random.default_rng(season)
    n_off, n_def = len(pooled.OFF_FEATURES), len(pooled.DEF_FEATURES)
    Xo, Xd = rng.normal(size=(n, n_off)), rng.normal(size=(n, n_def))
    return {"X_off": Xo, "X_def": Xd, "y_off": Xo[:, 0] + rng.normal(0, 0.3, n),
            "y_def": Xd[:, 0] + rng.normal(0, 0.3, n), "poss": rng.uniform(500, 5000, n),
            "pids": [season * 1000 + i for i in range(n)], "inputs": ("stats", "opp", "team", "career")}


class BoxOnlyFeatureTests(SimpleTestCase):
    """Task 3.5b: --features box_only drops the features built from on-court results."""

    def test_dropped_features(self):
        off = [pooled.OFF_FEATURES[i] for i in pooled.feature_index("off", "box_only")]
        dfn = [pooled.DEF_FEATURES[i] for i in pooled.feature_index("def", "box_only")]
        on_court_off = {"on_off_adj_em_delta", "ortg_vs_team"}
        on_court_def = {"d_mpir", "on_court_adj_d", "on_off_adj_em_delta", "d_vs_team"}
        d_mpir_arch = {"arch_three_and_d", "arch_stretch", "arch_connector"}
        self.assertEqual(set(pooled.OFF_FEATURES) - set(off), on_court_off | d_mpir_arch)
        self.assertEqual(set(pooled.DEF_FEATURES) - set(dfn), on_court_def | d_mpir_arch)
        for kept in ("pts100", "ts_pct", "usg_pct", "opp_quality", "arch_creator", "arch_interior"):
            self.assertIn(kept, off)
        self.assertIsNone(pooled.feature_index("off", "all"))

    def test_box_only_fit_ignores_on_court_columns(self):
        data = {s: _wide_season(s) for s in range(2016, 2020)}
        art, info = pooled.fit_season(2019, data, False, features="box_only")
        self.assertEqual(info["off_n_features"], len(pooled.feature_index("off", "box_only")))
        self.assertEqual(info["def_n_features"], len(pooled.feature_index("def", "box_only")))
        # Prediction takes full-width rows; changing a dropped column changes nothing.
        row_o = np.ones((1, len(pooled.OFF_FEATURES)))
        row_d = np.ones((1, len(pooled.DEF_FEATURES)))
        base_o, base_d = art["off_pipeline"].predict(row_o)[0], art["def_pipeline"].predict(row_d)[0]
        row_o[0, pooled.OFF_FEATURES.index("ortg_vs_team")] = 50.0
        row_d[0, pooled.DEF_FEATURES.index("d_mpir")] = -50.0
        self.assertEqual(art["off_pipeline"].predict(row_o)[0], base_o)
        self.assertEqual(art["def_pipeline"].predict(row_d)[0], base_d)

    def test_default_uses_every_feature(self):
        data = {s: _wide_season(s) for s in range(2016, 2020)}
        art, info = pooled.fit_season(2019, data, False)
        self.assertEqual((info["features"], info["off_n_features"], info["def_n_features"]),
                         ("all", len(pooled.OFF_FEATURES), len(pooled.DEF_FEATURES)))
        row = np.ones((1, len(pooled.OFF_FEATURES)))
        before = art["off_pipeline"].predict(row)[0]
        row[0, pooled.OFF_FEATURES.index("ortg_vs_team")] = 50.0
        self.assertNotEqual(art["off_pipeline"].predict(row)[0], before)

    def test_command_passes_feature_set(self):
        seen = []
        real = pooled.fit_season

        def spy(*a, **k):
            seen.append(k.get("features"))
            return real(*a, **k)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch(f"{MOD}.load_season", lambda s, c, t=None: _wide_season(s)), \
             mock.patch(f"{MOD}.predict_nba_box_bpr", lambda *a: {}), \
             mock.patch(f"{MOD}.nba_ids_for", lambda pks: {}), \
             mock.patch(f"{MOD}.fit_season", spy):
            call_command("nba_fit_box_pooled", "--seasons", "2017", "--features", "box_only",
                         "--out-dir", tmp.name, stdout=StringIO())
        self.assertEqual(seen, ["box_only"])
        self.assertEqual(json.loads((Path(tmp.name) / "alphas.json").read_text())[0]["features"], "box_only")


class AlphaGridTests(SimpleTestCase):
    """Task 3.5c: the alpha grid runs from 1 to 30000."""

    def test_grid(self):
        self.assertEqual(pooled.ALPHAS, [1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0, 30000.0])

    def test_alpha_above_1000_can_be_chosen(self):
        # Pure-noise targets: every alpha predicts about equally badly, so the
        # one-SE rule takes the largest, now 30000.
        rng = np.random.default_rng(7)
        data = {}
        for s in range(2016, 2020):
            d = _season_data(s)
            d["y_off"] = rng.normal(size=len(d["pids"]))
            d["y_def"] = rng.normal(size=len(d["pids"]))
            data[s] = d
        _, info = pooled.fit_season(2019, data, False, alphas=pooled.alpha_grid(30000))
        self.assertEqual((info["off_alpha"], info["def_alpha"]), (30000.0, 30000.0))
        self.assertEqual(len(info["off_cv_mean"]), 10)
        # Default grid (task 3.6): capped at 1000.
        _, info = pooled.fit_season(2019, data, False)
        self.assertEqual((info["off_alpha"], info["def_alpha"]), (1000.0, 1000.0))
        self.assertEqual(len(info["off_cv_mean"]), 7)



class _CommandRunMixin:
    """Runs the command with loading, window targets, prediction and fitting stood in for."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name)

    def _run(self, *args):
        self.loads, self.windows, self.fits = [], [], []

        def load(season, career_floor, targets=None):
            self.loads.append((season, targets is not None))
            return _season_data(season)

        def window(season, start, k, lam=None):
            self.lams = getattr(self, "lams", []) + [lam]
            self.windows.append((season, k) if k != 3 else season)
            return {"obpr": {1: 0.0}, "dbpr": {1: 0.0}, "lambda": 500.0, "years": pooled.window_years(season, start, k)}

        real = pooled.fit_season

        def spy(*a, **k):
            self.fits.append(k["alphas"])
            return real(*a, **k)

        with mock.patch(f"{MOD}.load_season", load), mock.patch(f"{MOD}.window_targets", window), \
             mock.patch(f"{MOD}.predict_nba_box_bpr", lambda *a: {}), \
             mock.patch(f"{MOD}.nba_ids_for", lambda pks: {}), mock.patch(f"{MOD}.fit_season", spy):
            call_command("nba_fit_box_pooled", "--out-dir", str(self.out), *args, stdout=StringIO())
        return json.loads((self.out / "alphas.json").read_text())



class AlphaMaxAndWindow3Tests(_CommandRunMixin, SimpleTestCase):
    """Task 3.6: --alpha-max (default 1000) and --target window3."""

    def test_alpha_grid(self):
        self.assertEqual(pooled.alpha_grid(), [1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0])
        self.assertEqual(pooled.alpha_grid(30000), pooled.ALPHAS)
        self.assertEqual(pooled.alpha_grid(3000)[-1], 3000.0)
        with self.assertRaises(ValueError):
            pooled.alpha_grid(0.5)

    def test_window_years(self):
        self.assertEqual(pooled.window_years(2016), [2016])
        self.assertEqual(pooled.window_years(2017), [2016, 2017])
        self.assertEqual(pooled.window_years(2020), [2018, 2019, 2020])

    def test_window3_targets_only_for_training_seasons(self):
        info = self._run("--seasons", "2019", "--target", "window3")
        self.assertEqual(self.windows, [2016, 2017, 2018])          # never 2019
        self.assertIn((2019, False), self.loads)                     # Y's inputs, no target
        self.assertTrue(all(t for s, t in self.loads if s < 2019))   # training seasons carry targets
        self.assertEqual(info[0]["target"], "window3")
        self.assertEqual(info[0]["target_windows"]["2018"]["years"], [2016, 2017, 2018])

    def test_baseline_target_never_fits_windows(self):
        info = self._run("--seasons", "2019")
        self.assertEqual(self.windows, [])
        self.assertEqual(info[0]["target"], "baseline")

    def test_alpha_max_reaches_the_fit(self):
        self._run("--seasons", "2019")
        self.assertEqual(self.fits[-1][-1], 1000.0)
        self._run("--seasons", "2019", "--alpha-max", "30000")
        self.assertEqual(self.fits[-1], pooled.ALPHAS)



class TargetWindowTests(_CommandRunMixin, SimpleTestCase):
    """Task 3.6b: --target-window K; window3 is an alias for K=3."""

    def test_window_years_k(self):
        self.assertEqual(pooled.window_years(2020, k=2), [2019, 2020])
        self.assertEqual(pooled.window_years(2020, k=5), [2016, 2017, 2018, 2019, 2020])
        self.assertEqual(pooled.window_years(2021, k=5), [2017, 2018, 2019, 2020, 2021])
        self.assertEqual(pooled.window_years(2018, k=1), [2018])

    def test_resolve_window(self):
        self.assertIsNone(pooled.resolve_window("baseline", None))
        self.assertEqual(pooled.resolve_window("window3", None), 3)
        self.assertEqual(pooled.resolve_window("window3", 3), 3)
        self.assertEqual(pooled.resolve_window("baseline", 5), 5)
        with self.assertRaises(CommandError):
            pooled.resolve_window("window3", 4)
        with self.assertRaises(CommandError):
            pooled.resolve_window("baseline", 0)

    def test_target_window_k_reaches_targets(self):
        info = self._run("--seasons", "2019", "--target-window", "5")
        self.assertEqual(self.windows, [(2016, 5), (2017, 5), (2018, 5)])   # never 2019
        self.assertEqual(info[0]["target"], "window5")
        self.assertEqual(info[0]["target_windows"]["2018"]["years"], [2016, 2017, 2018])

    def test_window3_alias_matches_k3(self):
        a = self._run("--seasons", "2019", "--target", "window3")
        windows_a = list(self.windows)
        b = self._run("--seasons", "2019", "--target-window", "3")
        self.assertEqual(windows_a, self.windows)
        self.assertEqual(a[0]["target"], b[0]["target"])



class TargetLambdaTests(_CommandRunMixin, SimpleTestCase):
    """Task 3.6c: --target-lambda X fixes the window target's pooled RAPM lambda."""

    def test_fixed_lambda_reaches_every_window(self):
        self.lams = []
        info = self._run("--seasons", "2019", "--target-window", "3", "--target-lambda", "600")
        self.assertEqual(self.lams, [600.0, 600.0, 600.0])
        self.assertEqual(info[0]["target_lambda_fixed"], 600.0)

    def test_default_is_cv(self):
        self.lams = []
        info = self._run("--seasons", "2019", "--target-window", "3")
        self.assertEqual(self.lams, [None, None, None])
        self.assertIsNone(info[0]["target_lambda_fixed"])

    def test_needs_a_window_target(self):
        with self.assertRaises(CommandError):
            self._run("--seasons", "2019", "--target-lambda", "600")
        with self.assertRaises(CommandError):
            self._run("--seasons", "2019", "--target-window", "3", "--target-lambda", "0")

    def test_window_targets_passes_lambda_override(self):
        calls = []

        def fake_fit(obs, lambda_override=None):
            calls.append(lambda_override)
            return {"obpr": {}, "dbpr": {}, "lambda": lambda_override or 2500.0}

        with mock.patch(f"{MOD}.build_nba_observations", lambda season, rapm_years: []), \
             mock.patch(f"{MOD}.fit_pooled_player_rapm", fake_fit):
            fixed = pooled.window_targets(2020, 2016, 3, 1000.0)
            cv = pooled.window_targets(2020, 2016, 3)
        self.assertEqual(calls, [1000.0, None])
        self.assertEqual((fixed["lambda"], fixed["years"]), (1000.0, [2018, 2019, 2020]))
        self.assertEqual(cv["lambda"], 2500.0)


class NewcomerMeansTests(_CommandRunMixin, SimpleTestCase):
    """Task 3.7: possession-weighted newcomer means over seasons before Y only."""

    def test_season_possessions(self):
        obs = [{"season_year": 2018, "home_player_ids": [1, 2], "away_player_ids": [3], "home_poss": 4.0, "away_poss": 6.0},
               {"season_year": 2018, "home_player_ids": [1], "away_player_ids": [4], "home_poss": 2.0, "away_poss": 2.0},
               {"season_year": 2017, "home_player_ids": [9], "away_player_ids": [1], "home_poss": 10.0, "away_poss": 10.0}]
        self.assertEqual(pooled.season_possessions(obs, 2018), {1: 7.0, 2: 5.0, 3: 5.0, 4: 2.0})

    def test_newcomer_stats(self):
        poss = {1: 100.0, 2: 300.0, 3: 50.0, 4: 80.0, 5: 0.0}
        targets = {"obpr": {1: -2.0, 2: -1.0, 3: 5.0, 4: 9.0, 5: 9.0}, "dbpr": {1: -1.0, 2: 0.0, 3: 5.0, 4: 9.0, 5: 9.0}}
        # 3 has a box prediction, 4 had minutes last season, 5 has no possessions.
        st = pooled.newcomer_stats(poss, box_ids={3}, prev_minute_ids={4}, targets=targets)
        self.assertEqual((st["n"], st["poss"]), (2, 400.0))
        self.assertAlmostEqual(st["obpr"], (100 * -2.0 + 300 * -1.0) / 400)
        self.assertAlmostEqual(st["dbpr"], (100 * -1.0) / 400)

    def test_mean_uses_only_seasons_before_y(self):
        stats = {2016: {"n": 2, "poss": 100.0, "sum_o": -100.0, "sum_d": -50.0},
                 2017: {"n": 3, "poss": 300.0, "sum_o": -150.0, "sum_d": 0.0},
                 2018: {"n": 9, "poss": 9e9, "sum_o": 9e9, "sum_d": 9e9}}
        first = pooled.newcomer_mean_for(2016, stats)
        self.assertEqual((first["n"], first["obpr"], first["dbpr"], first["from_seasons"]), (0, 0.0, 0.0, []))
        y18 = pooled.newcomer_mean_for(2018, stats)
        self.assertEqual((y18["n"], y18["from_seasons"]), (5, [2016, 2017]))
        self.assertAlmostEqual(y18["obpr"], -250.0 / 400)
        self.assertAlmostEqual(y18["dbpr"], -50.0 / 400)
        with self.assertRaises(ValueError):
            pooled.newcomer_mean_for(2018, {2016: stats[2016]})

    def _run_nc(self, *args):
        def load(season, career_floor, targets=None):
            d = _season_data(season)
            d["feature_nba_ids"] = {1} if targets is not None else None
            return d

        def window(season, start, k, lam=None):
            self.windows.append(season)
            return {"obpr": {1: 0.0, 2: -1.0 * (season - 2015), 3: -3.0},
                    "dbpr": {1: 0.0, 2: -0.5, 3: -1.0}, "lambda": lam or 500.0,
                    "years": pooled.window_years(season, start, k),
                    "poss_season": {1: 900.0, 2: 100.0, 3: 300.0}}

        self.windows = []
        with mock.patch(f"{MOD}.load_season", load), mock.patch(f"{MOD}.window_targets", window), \
             mock.patch(f"{MOD}.prev_minute_ids", lambda season: {3}), \
             mock.patch(f"{MOD}.predict_nba_box_bpr", lambda *a: {}), \
             mock.patch(f"{MOD}.nba_ids_for", lambda pks: {}):
            call_command("nba_fit_box_pooled", "--out-dir", str(self.out), *args, stdout=StringIO())

    def test_command_writes_means_from_earlier_seasons(self):
        self._run_nc("--seasons", "2016", "2018", "--target-window", "3", "--target-lambda", "300", "--newcomer-means")
        means = json.loads((self.out / "newcomer_means.json").read_text())
        self.assertNotIn(2018, self.windows)   # Y's own window is never fitted
        # Only player 2 is a newcomer each season (1 has a box prediction, 3 had minutes).
        self.assertEqual(means["2016"]["n"], 0)
        self.assertEqual(means["2018"]["from_seasons"], [2016, 2017])
        self.assertAlmostEqual(means["2018"]["obpr"], (-1.0 + -2.0) / 2)   # equal possessions
        self.assertAlmostEqual(means["2018"]["dbpr"], -0.5)
        self.assertEqual(means["per_season"]["2017"]["n"], 1)

    def test_default_writes_no_means_and_baseline_target_is_rejected(self):
        self._run_nc("--seasons", "2018", "--target-window", "3")
        self.assertFalse((self.out / "newcomer_means.json").exists())
        with self.assertRaises(CommandError):
            self._run_nc("--seasons", "2018", "--newcomer-means")
