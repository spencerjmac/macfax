"""
Phase 2 task 2.5: nba_experiment_final_bpr --lambda-mult X multiplies every
lambda by X (the per-player tier lambdas and the 1000 fallback), in both the
LEBRON-prior mode and the native chain. No database: loaders, the fit and the
evaluation are stood in for.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase

from nba.management.commands import nba_experiment_final_bpr as harness
from nba.management.commands.nba_compute_final_bpr import LAMBDA_TIERS

MOD = "nba.management.commands.nba_experiment_final_bpr"

BOX = {2016: {1: (2.0, 1.0), 2: (-1.0, 0.0)},
       2017: {1: (3.0, 0.5), 2: (0.5, -0.5), 3: (0.0, 0.0)}}
MINUTES = {1: 2500.0, 2: 700.0, 3: 100.0}
HI, MID, LO, FRINGE = LAMBDA_TIERS["A_conservative"]
TIERS_2017 = {1: HI, 2: LO, 3: FRINGE}


class LambdaMultTests(SimpleTestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out_dir = Path(tmp.name)

        loader = mock.MagicMock()
        loader._load_priors.side_effect = lambda season: (
            {p: v[0] for p, v in BOX[season].items()},
            {p: v[1] for p, v in BOX[season].items()},
            {p: MINUTES[p] for p in BOX[season]})
        loader._load_stints.side_effect = lambda season, window: (
            [], {(p, season): i for i, p in enumerate(sorted(BOX[season]))}, len(BOX[season]))

        self.fits: list[dict] = []

        def fit(**kw):
            self.fits.append(kw)
            season = kw["target_season_year"]
            cols = [ps for ps in kw["player_season_index"] if ps[1] == season]
            return {"obpr": {ps: 0.0 for ps in cols}, "dbpr": {ps: 0.0 for ps in cols}}

        for target, new in (
            (f"{MOD}.FinalBprCommand", mock.MagicMock(return_value=loader)),
            (f"{MOD}.fit_prior_informed_rapm", fit),
            (f"{MOD}._load_lebron_priors", lambda *a, **k: {}),
        ):
            patcher = mock.patch(target, new)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(harness.Command, "_evaluate",
                                    lambda _self, src, o, d, row, opts, out_dir: row)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, *args):
        call_command("nba_experiment_final_bpr", "--source-seasons", "2017", "--run-name", "t",
                     "--out-dir", str(self.out_dir), *args, stdout=StringIO())

    def _chain(self, *extra):
        self._run("--native-chain", "--chain-start", "2016", "--w-box", "0.5", "--rho", "0.8",
                  *extra)

    def _lebron_mode(self, *extra):
        self._run("--lebron-prior-w", "0", "--lebron-lambda-scale", "0", *extra)

    def test_default_is_one(self):
        self._lebron_mode()
        self._chain()
        for f in self.fits:
            self.assertEqual(f["lambda_val"], 1000.0)
        self.assertEqual(self.fits[0]["lambda_by_nba_id"], TIERS_2017)
        self.assertEqual(self.fits[-1]["lambda_by_nba_id"], TIERS_2017)

    def test_lebron_mode_multiplies_every_lambda(self):
        self._lebron_mode("--lambda-mult", "2")
        (f,) = self.fits
        self.assertEqual(f["lambda_val"], 2000.0)
        self.assertEqual(f["lambda_by_nba_id"], {p: 2 * lam for p, lam in TIERS_2017.items()})

    def test_native_chain_multiplies_every_lambda_in_every_season(self):
        self._chain("--lambda-mult", "0.5")
        self.assertEqual([f["target_season_year"] for f in self.fits], [2016, 2017])
        for f in self.fits:
            self.assertEqual(f["lambda_val"], 500.0)
        self.assertEqual(self.fits[0]["lambda_by_nba_id"], {1: HI / 2, 2: LO / 2})
        self.assertEqual(self.fits[1]["lambda_by_nba_id"],
                         {p: lam / 2 for p, lam in TIERS_2017.items()})
