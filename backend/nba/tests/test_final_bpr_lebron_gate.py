"""
nba_compute_final_bpr's LEBRON freshness gate runs only when LEBRON is used
(prior weight, defensive prior weight or lambda scale above 0). With all
three at 0, a missing CSV must not stop the run.

The run is stopped right after the gate, where loading box-BPR priors from
the database would begin: no database, no CSVs.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from nba.management.commands.nba_compute_final_bpr import Command

MOD = "nba.management.commands.nba_compute_final_bpr"


class _PastTheGate(Exception):
    """Raised where the command starts loading priors."""


class LebronGateTests(SimpleTestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for patcher in (
            mock.patch(f"{MOD}.LEBRON_DATA_DIR", Path(tmp.name)),   # no lebron-data-*.csv here
            mock.patch.object(Command, "_load_priors", side_effect=_PastTheGate),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run(self, *weights):
        call_command("nba_compute_final_bpr", "--season", "2027", "--dry-run", *weights, stdout=StringIO())

    def test_all_lebron_weights_zero_and_no_csv_runs_past_the_gate(self):
        with self.assertRaises(_PastTheGate):
            self._run("--lebron-prior-weight", "0", "--lebron-prior-def-weight", "0",
                      "--lebron-lambda-scale", "0")

    def test_any_lebron_weight_above_zero_and_no_csv_raises(self):
        for flag in ("--lebron-prior-weight", "--lebron-prior-def-weight", "--lebron-lambda-scale"):
            others = [f for f in ("--lebron-prior-weight", "--lebron-prior-def-weight",
                                  "--lebron-lambda-scale") if f != flag]
            with self.subTest(flag=flag), self.assertRaisesMessage(CommandError, "LEBRON data missing"):
                self._run(flag, "0.5", others[0], "0", others[1], "0")
