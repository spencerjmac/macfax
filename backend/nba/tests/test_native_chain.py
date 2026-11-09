"""
Phase 2 task 2.2: nba_experiment_final_bpr --native-chain solves seasons
--chain-start up to the last source season in order, in memory. Each season's
prior is native_prior(box, previous chain result); the first season's is box
only. Lambda is minutes tiers only, and nothing on the path touches LEBRON.
No database: the loaders, the fit and the evaluation are stood in for.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from nba.management.commands import nba_experiment_final_bpr as harness
from nba.management.commands.nba_compute_final_bpr import LAMBDA_TIERS

MOD = "nba.management.commands.nba_experiment_final_bpr"
FINAL = "nba.management.commands.nba_compute_final_bpr"

# Box per season: {nba_id: (box_obpr, box_dbpr)}; minutes put 1 in the top tier.
BOX = {
    2016: {1: (2.0, 1.0), 2: (-1.0, 0.0)},
    2017: {1: (3.0, 0.5), 3: (0.5, -0.5)},
    2018: {1: (1.0, 1.0), 2: (0.0, 2.0), 3: (1.0, 0.0)},
}
MINUTES = {1: 2500.0, 2: 700.0, 3: 100.0}


def _fake_fit(**kw):
    """Fit result = prior + 1 (offense) / prior - 1 (defense) for the target season's columns."""
    season = kw["target_season_year"]
    cols = [ps for ps in kw["player_season_index"] if ps[1] == season]
    return {"obpr": {ps: kw["prior_obpr"].get(ps[0], 0.0) + 1.0 for ps in cols},
            "dbpr": {ps: kw["prior_dbpr"].get(ps[0], 0.0) - 1.0 for ps in cols}}


def _no_lebron(*_a, **_k):
    raise AssertionError("LEBRON touched on the native chain path")


class NativeChainTests(SimpleTestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out_dir = Path(tmp.name)

        self.loaded: list[int] = []
        loader = mock.MagicMock()

        def load_priors(season):
            self.loaded.append(season)
            box = BOX[season]
            return ({p: v[0] for p, v in box.items()}, {p: v[1] for p, v in box.items()},
                    {p: MINUTES[p] for p in box})

        def load_stints(season, window):
            index = {(p, season): i for i, p in enumerate(sorted(BOX[season]))}
            return [], index, len(index)

        loader._load_priors.side_effect = load_priors
        loader._load_stints.side_effect = load_stints
        loader._blend_lebron_priors.side_effect = _no_lebron

        self.fits: list[dict] = []

        def fit(**kw):
            self.fits.append(kw)
            return _fake_fit(**kw)

        self.evaluated: list[tuple] = []

        def evaluate(_self, src, variant, row, opts, out_dir):
            self.evaluated.append((src, dict(variant), dict(row)))
            return row

        for target, new in (
            (f"{MOD}.FinalBprCommand", mock.MagicMock(return_value=loader)),
            (f"{MOD}.fit_prior_informed_rapm", fit),
            (f"{MOD}._load_lebron_priors", _no_lebron),
            (f"{FINAL}._load_lebron_priors", _no_lebron),
            (f"{FINAL}.lebron_csv_path", _no_lebron),
            (f"{FINAL}.check_all_lebron_files", _no_lebron),
        ):
            patcher = mock.patch(target, new)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(harness.Command, "_evaluate", evaluate)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, *extra):
        out = StringIO()
        call_command("nba_experiment_final_bpr", "--native-chain", "--chain-start", "2016",
                     "--source-seasons", "2017", "2018", "--w-box", "0.5", "--rho", "0.8",
                     "--run-name", "t", "--out-dir", str(self.out_dir), *extra, stdout=out)
        return out.getvalue()

    def test_seasons_are_solved_in_order_from_chain_start(self):
        self._run()
        self.assertEqual(self.loaded, [2016, 2017, 2018])
        self.assertEqual([f["target_season_year"] for f in self.fits], [2016, 2017, 2018])

    def test_only_source_seasons_are_evaluated(self):
        self._run()
        self.assertEqual([src for src, _, _ in self.evaluated], [2017, 2018])
        row = self.evaluated[0][2]
        self.assertEqual((row["mode"], row["chain_start"], row["w_box"], row["rho"]),
                         ("native_chain", 2016, 0.5, 0.8))

    def test_first_season_prior_is_box_only(self):
        self._run()
        first = self.fits[0]
        self.assertEqual(first["prior_obpr"], {1: 2.0, 2: -1.0})
        self.assertEqual(first["prior_dbpr"], {1: 1.0, 2: 0.0})

    def test_next_season_prior_uses_previous_chain_result(self):
        self._run()
        # 2016 result: obpr = box + 1, dbpr = box - 1 -> {1: 3, 2: 0} / {1: 0, 2: -1}
        prior_o, prior_d = self.fits[1]["prior_obpr"], self.fits[1]["prior_dbpr"]
        self.assertAlmostEqual(prior_o[1], 0.5 * 3.0 + 0.5 * 0.8 * 3.0)   # box + prev
        self.assertAlmostEqual(prior_o[3], 0.5)                           # box only
        self.assertAlmostEqual(prior_o[2], 0.8 * 0.0)                     # prev only
        self.assertAlmostEqual(prior_d[1], 0.5 * 0.5 + 0.5 * 0.8 * 0.0)
        self.assertAlmostEqual(prior_d[2], 0.8 * -1.0)
        self.assertEqual(set(prior_o), {1, 2, 3})

    def test_variant_is_the_chain_result_for_that_season(self):
        self._run()
        src, variant, _ = self.evaluated[0]
        prior_o, prior_d = self.fits[1]["prior_obpr"], self.fits[1]["prior_dbpr"]
        self.assertEqual(set(variant), {1, 3})
        self.assertAlmostEqual(variant[1], (prior_o[1] + 1) + (prior_d[1] - 1))

    def test_lambda_is_minutes_tiers_only(self):
        self._run()
        hi, mid, lo, fringe = LAMBDA_TIERS["A_conservative"]
        self.assertEqual(self.fits[2]["lambda_by_nba_id"], {1: hi, 2: lo, 3: fringe})

    def test_no_lebron_on_the_path(self):
        out = self._run()   # every LEBRON entry point raises if called
        self.assertIn("LEBRON: not used", out)

    def test_needs_chain_start_w_box_and_rho(self):
        with self.assertRaises(CommandError):
            call_command("nba_experiment_final_bpr", "--native-chain", "--source-seasons", "2017",
                         "--run-name", "t", "--out-dir", str(self.out_dir), stdout=StringIO())

    def test_chain_start_after_first_source_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command("nba_experiment_final_bpr", "--native-chain", "--chain-start", "2018",
                         "--source-seasons", "2017", "--w-box", "0.5", "--rho", "0.8",
                         "--run-name", "t", "--out-dir", str(self.out_dir), stdout=StringIO())
