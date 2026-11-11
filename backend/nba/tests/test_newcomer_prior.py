"""
Phase 3 task 3.7: nba_experiment_final_bpr --newcomer-prior. In the native chain,
players with no box prior, no previous chain result and no regular-season minutes
the season before start at that season's newcomer mean (DIR/newcomer_means.json)
instead of 0. Default off. No database: loaders and the fit are stood in for.
"""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from nba.management.commands import nba_experiment_final_bpr as harness

MOD = "nba.management.commands.nba_experiment_final_bpr"

# Box players per season; stint players per season (5 = newcomer in 2017, 6 had 2016 minutes).
BOX = {2016: {"1": [1.0, 0.5]}, 2017: {"1": [2.0, 0.5]}}
STINTS = {2016: [1, 2], 2017: [1, 2, 5, 6]}
MINUTES = {(2015, 1): 2000.0, (2016, 1): 2000.0, (2016, 2): 300.0, (2016, 6): 50.0, (2017, 1): 2000.0}
MEANS = {"2016": {"obpr": -0.5, "dbpr": -0.25}, "2017": {"obpr": -1.25, "dbpr": -0.75},
         "per_season": {}}


class NewcomerPriorTests(SimpleTestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.box = self.dir / "box"
        self.box.mkdir()
        for season, b in BOX.items():
            (self.box / f"box_{season}.json").write_text(json.dumps(b))
        (self.box / "newcomer_means.json").write_text(json.dumps(MEANS))

        loader = mock.MagicMock()
        loader._load_stints.side_effect = lambda season, window: (
            [], {(p, season): i for i, p in enumerate(STINTS[season])}, len(STINTS[season]))
        self.fits = []

        def fit(**kw):
            self.fits.append(kw)
            season = kw["target_season_year"]
            cols = [ps for ps in kw["player_season_index"] if ps[1] == season]
            return {"obpr": {ps: 0.1 for ps in cols}, "dbpr": {ps: 0.1 for ps in cols}}

        def load_minutes(season, ids):
            return {p: MINUTES[(season, p)] for p in ids if (season, p) in MINUTES}

        for target, new in ((f"{MOD}.FinalBprCommand", mock.MagicMock(return_value=loader)),
                            (f"{MOD}.fit_prior_informed_rapm", fit)):
            patcher = mock.patch(target, new)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.rows = []
        for name, new in (("_evaluate", lambda _s, src, o, d, row, opts, out_dir: self.rows.append(row) or row),
                          ("_load_minutes", staticmethod(load_minutes))):
            patcher = mock.patch.object(harness.Command, name, new)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run(self, *extra, box=True):
        args = ["--native-chain", "--chain-start", "2016", "--source-seasons", "2017", "--w-box", "0.5",
                "--rho", "0.8", "--run-name", "t", "--out-dir", str(self.dir / "out")]
        if box:
            args += ["--box-json-dir", str(self.box)]
        call_command("nba_experiment_final_bpr", *args, *extra, stdout=StringIO())

    def test_newcomers_start_at_the_season_mean(self):
        self._run("--newcomer-prior")
        f16, f17 = self.fits
        # 2016 (chain start): 2 has no box, no prev and no 2015 minutes -> newcomer.
        self.assertEqual(f16["prior_obpr"][2], -0.5)
        self.assertEqual(f16["prior_dbpr"][2], -0.25)
        # 2017: 5 is a newcomer; 6 played in 2016 (minutes) so stays at 0 (no prior entry);
        # 2 has a previous chain result; 1 has a box prior.
        self.assertEqual((f17["prior_obpr"][5], f17["prior_dbpr"][5]), (-1.25, -0.75))
        self.assertNotIn(6, f17["prior_obpr"])
        self.assertAlmostEqual(f17["prior_obpr"][2], 0.8 * 0.1)
        self.assertAlmostEqual(f17["prior_obpr"][1], 0.5 * 2.0 + 0.5 * 0.8 * 0.1)
        row = self.rows[0]
        self.assertEqual((row["n_newcomers"], row["n_no_prior"], row["newcomer_o"]), (1, 2, -1.25))

    def test_default_leaves_newcomers_at_zero(self):
        self._run()
        self.assertNotIn(5, self.fits[1]["prior_obpr"])
        self.assertNotIn("newcomer_prior", self.rows[0])

    def test_needs_box_json_dir_and_means_file(self):
        with self.assertRaises(CommandError):
            self._run("--newcomer-prior", box=False)
        (self.box / "newcomer_means.json").unlink()
        with self.assertRaises(CommandError):
            self._run("--newcomer-prior")
