"""
Phase 3 task 3.2: nba_experiment_final_bpr --box-json-dir DIR reads each
season's box prior from DIR/box_<season>.json (string keys -> int nba_id)
instead of stored box values, in both modes. Minutes still come from the
database. No database: loaders, the fit and the evaluation are stood in for.
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

JSON_BOX = {2016: {"1": [2.0, 1.0], "2": [-1.0, 0.0]},
            2017: {"1": [3.0, 0.5], "3": [0.5, -0.5]}}
STORED_BOX = {2016: ({1: 9.0, 2: 9.0}, {1: 9.0, 2: 9.0}, {1: 2500.0, 2: 700.0}),
              2017: ({1: 9.0, 3: 9.0}, {1: 9.0, 3: 9.0}, {1: 2500.0, 3: 100.0})}
MINUTES = {1: 2500.0, 2: 700.0, 3: 100.0}


class BoxJsonDirTests(SimpleTestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out_dir = Path(tmp.name) / "out"
        self.box_dir = Path(tmp.name) / "box"
        self.box_dir.mkdir()
        for season, box in JSON_BOX.items():
            (self.box_dir / f"box_{season}.json").write_text(json.dumps(box))

        self.loader = mock.MagicMock()
        self.loader._load_priors.side_effect = lambda season: STORED_BOX[season]
        self.loader._load_stints.side_effect = lambda season, window: (
            [], {(p, season): i for i, p in enumerate(sorted(STORED_BOX[season][0]))},
            len(STORED_BOX[season][0]))
        self.loader._blend_lebron_priors.side_effect = lambda src, o, d, w, **k: (o, d)

        self.fits: list[dict] = []
        self.minutes_calls: list[tuple] = []

        def fit(**kw):
            self.fits.append(kw)
            season = kw["target_season_year"]
            cols = [ps for ps in kw["player_season_index"] if ps[1] == season]
            return {"obpr": {ps: 0.0 for ps in cols}, "dbpr": {ps: 0.0 for ps in cols}}

        def load_minutes(season, ids):
            self.minutes_calls.append((season, sorted(ids)))
            return {p: MINUTES[p] for p in ids}

        for target, new in (
            (f"{MOD}.FinalBprCommand", mock.MagicMock(return_value=self.loader)),
            (f"{MOD}.fit_prior_informed_rapm", fit),
            (f"{MOD}._load_lebron_priors", lambda *a, **k: {}),
        ):
            patcher = mock.patch(target, new)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, new in (("_evaluate", lambda _s, src, o, d, row, opts, out_dir: row),
                          ("_load_minutes", staticmethod(load_minutes))):
            patcher = mock.patch.object(harness.Command, name, new)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run(self, *args):
        call_command("nba_experiment_final_bpr", "--source-seasons", "2017", "--run-name", "t",
                     "--out-dir", str(self.out_dir), *args, stdout=StringIO())

    def _chain(self, *extra):
        self._run("--native-chain", "--chain-start", "2016", "--w-box", "0.5", "--rho", "0.8", *extra)

    def test_native_chain_reads_box_from_json_with_int_keys(self):
        self._chain("--box-json-dir", str(self.box_dir))
        self.loader._load_priors.assert_not_called()
        first = self.fits[0]   # 2016: box only
        self.assertEqual(first["prior_obpr"], {1: 2.0, 2: -1.0})
        self.assertEqual(first["prior_dbpr"], {1: 1.0, 2: 0.0})
        self.assertEqual(self.minutes_calls, [(2016, [1, 2]), (2017, [1, 3])])
        self.assertAlmostEqual(self.fits[1]["prior_obpr"][3], 0.5)   # 2017 box only

    def test_lebron_mode_reads_box_from_json(self):
        self._run("--lebron-prior-w", "0", "--lebron-lambda-scale", "0", "--box-json-dir", str(self.box_dir))
        self.loader._load_priors.assert_not_called()
        (fit,) = self.fits
        self.assertEqual(fit["prior_obpr"], {1: 3.0, 3: 0.5})
        self.assertEqual(fit["prior_dbpr"], {1: 0.5, 3: -0.5})

    def test_lebron_blend_starts_from_json_box(self):
        with mock.patch(f"{MOD}._load_lebron_priors", lambda *a, **k: {1: (1.0, 1.0)}):
            self._run("--lebron-prior-w", "0.75", "--box-json-dir", str(self.box_dir))
        args = self.loader._blend_lebron_priors.call_args.args
        self.assertEqual((args[1], args[2]), ({1: 3.0, 3: 0.5}, {1: 0.5, 3: -0.5}))

    def test_without_flag_stored_box_is_used(self):
        self._chain()
        self.assertEqual([c.args for c in self.loader._load_priors.call_args_list], [(2016,), (2017,)])
        self.assertEqual(self.fits[0]["prior_obpr"], {1: 9.0, 2: 9.0})
        self.assertEqual(self.minutes_calls, [])

    def test_missing_json_file_is_an_error(self):
        (self.box_dir / "box_2016.json").unlink()
        with self.assertRaises(CommandError):
            self._chain("--box-json-dir", str(self.box_dir))
