"""
Phase 3 task 3.4: --weight-by-poss (default off) passes each player's
on_court_poss as sample_weight to both ridge fits in train_nba_box_bpr.
"""

from io import StringIO
from unittest import mock

import numpy as np
from django.core.management import call_command
from django.test import SimpleTestCase

from nba.analytics import box_bpr
from nba.tests.test_box_bpr_blend_dump import MOD, _BoxFixture

N = 40


def _synthetic():
    """Features for N players (one heavy-possession player who doesn't fit the others)."""
    rng = np.random.default_rng(0)
    feats, stats, t_o, t_d = {}, [], {}, {}
    for pid in range(1, N + 1):
        off = rng.normal(size=len(box_bpr.OFF_FEATURES))
        dfn = rng.normal(size=len(box_bpr.DEF_FEATURES))
        feats[pid] = {"off": list(off), "def": list(dfn), "archetype": "connector"}
        stats.append({"player_id": pid, "on_court_poss": 9000.0 if pid == 1 else 600.0 + pid})
        t_o[pid] = float(off[0]) + (8.0 if pid == 1 else 0.0)
        t_d[pid] = float(dfn[0]) - (8.0 if pid == 1 else 0.0)
    return feats, stats, t_o, t_d


class TrainWeightByPossTests(SimpleTestCase):

    def setUp(self):
        self.feats, self.stats, self.t_o, self.t_d = _synthetic()
        patcher = mock.patch.object(box_bpr, "extract_nba_box_features", lambda *a, **k: self.feats)
        patcher.start()
        self.addCleanup(patcher.stop)

        real = box_bpr._build_pipeline
        self.pipes = []

        def spy(alphas):
            pipe = real(alphas)
            pipe.fit = mock.MagicMock(wraps=pipe.fit)
            self.pipes.append(pipe)
            return pipe

        patcher = mock.patch.object(box_bpr, "_build_pipeline", spy)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _train(self, **kw):
        self.pipes.clear()
        return box_bpr.train_nba_box_bpr(self.stats, {}, {}, self.t_o, self.t_d, **kw)

    def test_default_fits_without_weights(self):
        self._train()
        for pipe in self.pipes:
            self.assertEqual(pipe.fit.call_args.kwargs, {})

    def test_weight_by_poss_passes_on_court_poss_to_both_ridge_fits(self):
        self._train(weight_by_poss=True)
        expected = [9000.0] + [600.0 + pid for pid in range(2, N + 1)]
        off_pipe, def_pipe = self.pipes
        for pipe in (off_pipe, def_pipe):
            self.assertEqual(set(pipe.fit.call_args.kwargs), {"ridge__sample_weight"})
            np.testing.assert_array_equal(pipe.fit.call_args.kwargs["ridge__sample_weight"], expected)

    def test_weights_change_the_fit(self):
        plain = self._train()
        weighted = self._train(weight_by_poss=True)
        X1 = np.array([self.feats[1]["off"]])
        self.assertNotAlmostEqual(float(plain["off_pipeline"].predict(X1)[0]),
                                  float(weighted["off_pipeline"].predict(X1)[0]), places=3)


class CommandWeightByPossTests(_BoxFixture):

    def test_flag_reaches_training(self):
        call_command("nba_compute_box_bpr", "--season", "2026", "--dry-run", stdout=StringIO())
        self.assertIs(self.train.call_args.kwargs["weight_by_poss"], False)
        call_command("nba_compute_box_bpr", "--season", "2026", "--dry-run", "--weight-by-poss",
                     stdout=StringIO())
        self.assertIs(self.train.call_args.kwargs["weight_by_poss"], True)
