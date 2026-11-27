"""
Pipeline run log (ncaa/pipeline_log.py): every update_* run appends one JSON line with its steps, rc and
timings to $PIPELINE_LOG_DIR/pipeline_runs.jsonl, so the nightly's result survives container recreation.

- a run records each step's name, ok, rc, seconds and note, the options, and an overall rc;
- the fatal-step exit path writes the run once;
- update_daily records the real exit code of the NBA subprocess and of a failed NCAA pipeline;
- each run records the prod lock holder and wait: from the nightly's environment, else the lock file
  (wait 0), else null;
- without PIPELINE_LOG_DIR nothing is written and nothing fails.
"""
import json
import os
import subprocess
import tempfile
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from ncaa import prod_lock
from ncaa.management.commands._pipeline_base import BasePipelineCommand
from ncaa.pipeline_log import FILENAME, append_run

BASE_CALL = "ncaa.management.commands._pipeline_base.call_command"


class _Demo(BasePipelineCommand):
    """A three-step pipeline: one ok, one failing, one skipped (or a fatal failure)."""

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, default=2027)
        parser.add_argument("--fatal", action="store_true")

    def handle(self, *args, **options):
        steps = []
        self._run_step("Step one", "noop_one", {}, steps)
        self._run_step("Step two", "noop_two", {}, steps, fatal=options["fatal"])
        self._skip_step("Step three", steps, "Skipped (--skip-ingest)")
        self._print_summary(timezone.now(), timezone.now(), 1.0, steps, title="DEMO")


def _fake_call(name, **kw):
    if name == "noop_two":
        raise RuntimeError("boom")


class RunLogTests(TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"PIPELINE_LOG_DIR": self.dir})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _records(self):
        with open(os.path.join(self.dir, FILENAME)) as f:
            return [json.loads(line) for line in f]

    def test_steps_rc_and_timings(self):
        with mock.patch(BASE_CALL, side_effect=_fake_call):
            call_command(_Demo(), season=2026, stdout=StringIO(), stderr=StringIO())
        (r,) = self._records()
        self.assertEqual(r["title"], "DEMO")
        self.assertEqual(r["rc"], 1)
        self.assertEqual(r["options"]["season"], 2026)
        self.assertNotIn("stdout", r["options"])
        one, two, three = r["steps"]
        self.assertEqual((one["name"], one["ok"], one["rc"], one["note"]), ("Step one", True, 0, None))
        self.assertIsInstance(one["seconds"], float)
        self.assertEqual((two["ok"], two["rc"], two["note"]), (False, 1, "boom"))
        self.assertIsInstance(two["seconds"], float)
        self.assertEqual((three["ok"], three["rc"], three["seconds"], three["note"]),
                         (True, 0, None, "Skipped (--skip-ingest)"))
        self.assertLessEqual(r["started"], r["finished"])

    def test_fatal_step_writes_the_run_once(self):
        with mock.patch(BASE_CALL, side_effect=_fake_call), self.assertRaises(SystemExit):
            call_command(_Demo(), fatal=True, stdout=StringIO(), stderr=StringIO())
        (r,) = self._records()
        self.assertEqual(r["rc"], 1)
        self.assertEqual([s["name"] for s in r["steps"]], ["Step one", "Step two"])

    def test_update_daily_records_subprocess_and_pipeline_exit_codes(self):
        def ncaa(name, **kw):
            if name == "update_ncaa_players":
                raise SystemExit(1)   # what a league pipeline ends with when a step failed
        with mock.patch("ncaa.management.commands.update_daily.call_command", side_effect=ncaa), \
             mock.patch("ncaa.management.commands.update_daily.subprocess.run",
                        side_effect=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 3)), \
             self.assertRaises(SystemExit):
            call_command("update_daily", "--today", "2026-11-10", stdout=StringIO(), stderr=StringIO())
        daily = [r for r in self._records() if r["command"] == "update_daily"][-1]
        steps = {s["name"]: s for s in daily["steps"]}
        self.assertEqual(daily["rc"], 1)
        self.assertEqual(steps["NBA pipeline"]["rc"], 3)
        self.assertIn("exited with status 3", steps["NBA pipeline"]["note"])
        failed_ncaa = [s for s in daily["steps"] if not s["ok"] and s["name"] != "NBA pipeline"]
        self.assertEqual([s["rc"] for s in failed_ncaa], [1])
        self.assertIsInstance(steps["NBA pipeline"]["seconds"], float)
        self.assertIsInstance(failed_ncaa[0]["seconds"], float)


class LockFieldTests(TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        env = mock.patch.dict(os.environ, {"PIPELINE_LOG_DIR": self.dir,
                                           "PROD_LOCK_DIR": os.path.join(self.dir, "locks", "prod")})
        env.start()
        self.addCleanup(env.stop)
        for k in ("PIPELINE_LOCK_HOLDER", "PIPELINE_LOCK_WAIT_SECONDS"):
            os.environ.pop(k, None)

    def _lock(self):
        with mock.patch(BASE_CALL):
            call_command(_Demo(), stdout=StringIO(), stderr=StringIO())
        with open(os.path.join(self.dir, FILENAME)) as f:
            rec = json.loads(f.read().splitlines()[-1])
        return rec["lock_holder"], rec["lock_wait_seconds"]

    def test_nightly_environment(self):
        os.environ.update({"PIPELINE_LOCK_HOLDER": "nightly", "PIPELINE_LOCK_WAIT_SECONDS": "1234.56"})
        prod_lock.acquire("nightly", "update_daily")
        self.assertEqual(self._lock(), ("nightly", 1234.6))

    def test_lock_file_when_run_under_prod_lock_sh(self):
        prod_lock.acquire("spencer/session-A", "docker compose exec -T backend python manage.py update_ncaa_all")
        self.assertEqual(self._lock(), ("spencer/session-A", 0.0))

    def test_no_lock(self):
        self.assertEqual(self._lock(), (None, None))
        os.environ.pop("PROD_LOCK_DIR")
        self.assertEqual(self._lock(), (None, None))


class NoLogDirTests(SimpleTestCase):
    def test_unset_writes_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PIPELINE_LOG_DIR", None)
            self.assertIsNone(append_run({"x": 1}))

    def test_unwritable_dir_reports_and_continues(self):
        with mock.patch.dict(os.environ, {"PIPELINE_LOG_DIR": "/proc/macfax-not-writable"}), \
             mock.patch("sys.stderr", new_callable=StringIO) as err:
            self.assertIsNone(append_run({"x": 1}))
        self.assertIn("could not write", err.getvalue())
