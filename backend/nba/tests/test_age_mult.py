"""
Phase 4 task 4.5: age-adjusted memory. nba.analytics.aging fits a quadratic
aging curve on chain ratings; nba_experiment_final_bpr --age-mult M shifts a
returning player's previous rating by M * curve(age at Y) before native_prior,
the curve fitted on this run's chain ratings from seasons before Y only.
M = 0 (default) leaves the chain exactly as it was.
"""

import tempfile
from datetime import date
from io import StringIO
from pathlib import Path
from unittest import mock

import numpy as np
from django.core.management import call_command
from django.test import SimpleTestCase

from nba.analytics import aging
from nba.management.commands import nba_experiment_final_bpr as harness

MOD = "nba.management.commands.nba_experiment_final_bpr"


class AgingCurveTests(SimpleTestCase):

    def test_age_at_is_mid_season(self):
        self.assertAlmostEqual(aging.age_at(date(2000, 2, 1), 2025), (date(2025, 2, 1) - date(2000, 2, 1)).days / 365.25)
        self.assertAlmostEqual(aging.age_at(date(2000, 2, 1), 2025), 25.0, places=2)
        self.assertIsNone(aging.age_at(None, 2025))

    def test_fit_recovers_a_known_quadratic(self):
        rng = np.random.default_rng(1)
        ages = rng.uniform(19, 37, 400)
        truth = (6.0, -0.4, 0.006)
        deltas = truth[0] + truth[1] * ages + truth[2] * ages ** 2
        coefs = aging.fit_aging_curve(ages, deltas, rng.uniform(100, 3000, 400))
        for got, want in zip(coefs, truth):
            self.assertAlmostEqual(got, want, places=6)
        self.assertAlmostEqual(aging.curve_value(coefs, 25.0), 6.0 - 10.0 + 3.75, places=6)

    def test_too_few_pairs_gives_no_curve(self):
        self.assertIsNone(aging.fit_aging_curve(np.ones(5), np.ones(5), np.ones(5)))
        self.assertEqual(aging.curve_value(None, 25.0), 0.0)

    def test_pairs_use_only_seasons_up_to_the_limit(self):
        dobs = {1: date(1995, 1, 1), 2: date(1990, 1, 1), 3: None}
        hist = {2016: {1: 0.0, 2: 1.0, 3: 0.0}, 2017: {1: 0.5, 2: 0.5, 3: 9.0}, 2018: {1: 9.0, 2: 9.0}}
        poss = {2016: {1: 100.0, 2: 500.0, 3: 50.0}, 2017: {1: 300.0, 2: 200.0, 3: 50.0},
                2018: {1: 900.0, 2: 900.0}}
        a, d, w = aging.aging_pairs(hist, poss, dobs, upto=2017)
        # Only 2016->2017, players 1 and 2 (3 has no birth date); weight = min possessions.
        self.assertEqual(sorted(d.tolist()), [-0.5, 0.5])
        self.assertEqual(sorted(w.tolist()), [100.0, 200.0])
        np.testing.assert_allclose(sorted(a.tolist()),
                                   sorted([aging.age_at(dobs[1], 2017), aging.age_at(dobs[2], 2017)]))
        a2, d2, _ = aging.aging_pairs(hist, poss, dobs, upto=2018)
        self.assertEqual(len(d2), 4)


BOX = {2016: {1: (1.0, 0.5), 2: (0.0, 0.0)}, 2017: {1: (1.0, 0.5), 2: (0.0, 0.0)},
       2018: {1: (1.0, 0.5), 2: (0.0, 0.0), 3: (0.5, 0.5)}}
MINUTES = {1: 2500.0, 2: 1500.0, 3: 900.0}
DOBS = {1: date(1996, 1, 1), 2: date(1990, 1, 1)}


class AgeMultChainTests(SimpleTestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name)
        loader = mock.MagicMock()
        loader._load_priors.side_effect = lambda season: (
            {p: v[0] for p, v in BOX[season].items()}, {p: v[1] for p, v in BOX[season].items()},
            {p: MINUTES[p] for p in BOX[season]})

        def stints(season, window):
            players = sorted(BOX[season])
            obs = [{"season_year": season, "home_player_ids": players, "away_player_ids": [],
                    "home_poss": 100.0, "away_poss": 100.0}]
            return obs, {(p, season): i for i, p in enumerate(players)}, len(players)

        loader._load_stints.side_effect = stints
        self.fits = []

        def fit(**kw):
            self.fits.append(kw)
            season = kw["target_season_year"]
            cols = [ps for ps in kw["player_season_index"] if ps[1] == season]
            return {"obpr": {ps: kw["prior_obpr"].get(ps[0], 0.0) + 1.0 for ps in cols},
                    "dbpr": {ps: kw["prior_dbpr"].get(ps[0], 0.0) for ps in cols}}

        self.pair_limits = []
        real_pairs = aging.aging_pairs

        def pairs(hist, poss, dobs, upto):
            self.pair_limits.append((upto, max(hist) if hist else None))
            return real_pairs(hist, poss, dobs, upto)

        # Constant curve (+1 per season) whenever there is any history at all.
        def curve(ages, deltas, weights, min_pairs=aging.MIN_AGE_PAIRS):
            return (1.0, 0.0, 0.0) if len(ages) else None

        self.dob_calls = []
        for target, new in ((f"{MOD}.FinalBprCommand", mock.MagicMock(return_value=loader)),
                            (f"{MOD}.fit_prior_informed_rapm", fit),
                            ("nba.analytics.aging.aging_pairs", pairs),
                            ("nba.analytics.aging.fit_aging_curve", curve)):
            patcher = mock.patch(target, new)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, new in (("_evaluate", lambda _s, src, o, d, row, opts, out_dir: row),
                          ("_load_birth_dates", staticmethod(lambda: self.dob_calls.append(1) or DOBS))):
            patcher = mock.patch.object(harness.Command, name, new)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _chain(self, *extra):
        call_command("nba_experiment_final_bpr", "--native-chain", "--chain-start", "2016",
                     "--source-seasons", "2018", "--w-box", "0.5", "--rho", "1.0",
                     "--run-name", "t", "--out-dir", str(self.out), *extra, stdout=StringIO())

    def test_m0_reproduces_the_chain_exactly(self):
        self._chain()
        plain = [(f["prior_obpr"], f["prior_dbpr"]) for f in self.fits]
        self.fits.clear()
        self._chain("--age-mult", "0")
        self.assertEqual(plain, [(f["prior_obpr"], f["prior_dbpr"]) for f in self.fits])
        self.assertEqual(self.dob_calls, [])
        self.assertEqual(self.pair_limits, [])

    def test_curve_uses_only_seasons_before_y(self):
        self._chain("--age-mult", "2")
        # Seasons 2016, 2017, 2018: the curve for Y sees history up to Y-1 and nothing later.
        self.assertEqual([u for u, _ in self.pair_limits[::2]], [2015, 2016, 2017])
        for upto, latest in self.pair_limits:
            self.assertTrue(latest is None or latest <= upto)

    def test_returning_players_shift_by_m_times_curve(self):
        self._chain("--age-mult", "2")
        f17, f18 = self.fits[1], self.fits[2]
        # 2017: history is only 2016 (no pairs) -> no curve -> no shift.
        # 2016 result: O = prior + 1 = box + 1 -> {1: 2.0, 2: 1.0}.
        self.assertAlmostEqual(f17["prior_obpr"][1], 0.5 * 1.0 + 0.5 * 1.0 * 2.0)
        # 2018: curve exists (+1); 2017 result O = prior17 + 1 -> {1: 2.5, 2: 1.5}.
        prev = {1: f17["prior_obpr"][1] + 1.0, 2: f17["prior_obpr"][2] + 1.0}
        self.assertAlmostEqual(f18["prior_obpr"][1], 0.5 * 1.0 + 0.5 * (prev[1] + 2 * 1.0))
        self.assertAlmostEqual(f18["prior_obpr"][2], 0.5 * 0.0 + 0.5 * (prev[2] + 2 * 1.0))
        self.assertAlmostEqual(f18["prior_obpr"][3], 0.5)   # box only: no memory, no shift
        self.assertTrue((self.out / "t" / "age_curves.json").exists())
