"""
Prod write lock, container side (ncaa/prod_lock.py) and the nightly's use of it (run_scheduler).

- acquire takes the lock (world-writable, so fab's macfax user can release a stale one), refuses a
  second holder; only the token releases; clear_if_holder clears only that holder's lock;
- acquire_waiting waits while held and gives up after the wait, returning the holder;
- the nightly runs update_daily holding the lock as "nightly" and releases it after;
- while another session holds it the nightly waits, then skips and logs rc 75 with the reason;
- at startup a lock left by "nightly" is cleared, anyone else's is kept;
- without PROD_LOCK_DIR the nightly runs without a lock.
"""
import json
import os
import stat
import subprocess
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from ncaa import prod_lock
from ncaa.management.commands.run_scheduler import SKIP_RC, Command

SUB = "ncaa.management.commands.run_scheduler.subprocess.run"


class LockTests(SimpleTestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "locks" / "prod"

    def test_acquire_refuse_release_by_token_only(self):
        token = prod_lock.acquire("nightly", "update_daily", self.path)
        self.assertTrue(token)
        info = prod_lock.read_info(self.path)
        self.assertEqual((info["holder"], info["command"], info["token"]), ("nightly", "update_daily", token))
        self.assertIn("started", info)
        self.assertIsNone(prod_lock.acquire("session-A", "fab deploy", self.path))
        self.assertFalse(prod_lock.release("not-it", self.path))
        self.assertIsNotNone(prod_lock.read_info(self.path))
        self.assertTrue(prod_lock.release(token, self.path))
        self.assertIsNone(prod_lock.read_info(self.path))

    def test_lock_is_world_writable_for_fab(self):
        prod_lock.acquire("nightly", "update_daily", self.path)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o777)
        self.assertEqual(stat.S_IMODE((self.path / "info").stat().st_mode), 0o666)

    def test_clear_if_holder_only_clears_that_holder(self):
        prod_lock.acquire("session-A", "backfill", self.path)
        self.assertIsNone(prod_lock.clear_if_holder("nightly", self.path))
        self.assertEqual(prod_lock.read_info(self.path)["holder"], "session-A")

    def test_acquire_waiting_gives_up_or_gets_it(self):
        other = prod_lock.acquire("session-A", "backfill", self.path)
        clock = iter(range(0, 10_000, 60))
        token, holder, waited = prod_lock.acquire_waiting("nightly", "update_daily", 3600, path=self.path,
                                                          sleep=lambda s: None, clock=lambda: next(clock))
        self.assertIsNone(token)
        self.assertEqual(holder["holder"], "session-A")
        self.assertGreaterEqual(waited, 3600)

        polls = []
        def sleep(s):  # the other session finishes during the second wait
            polls.append(s)
            if len(polls) == 2:
                prod_lock.release(other, self.path)
        token, holder, _ = prod_lock.acquire_waiting("nightly", "update_daily", 3600, path=self.path, sleep=sleep)
        self.assertTrue(token)
        self.assertIsNone(holder)
        self.assertEqual(prod_lock.read_info(self.path)["holder"], "nightly")


class NightlyLockTests(SimpleTestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp())
        self.lock = base / "locks" / "prod"
        self.logdir = base / "log"
        env = mock.patch.dict(os.environ, {"PROD_LOCK_DIR": str(self.lock), "PIPELINE_LOG_DIR": str(self.logdir),
                                           "NIGHTLY_LOCK_WAIT_MIN": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.cmd = Command(stdout=StringIO(), stderr=StringIO())

    def test_runs_holding_the_lock_and_releases(self):
        seen = []
        def run(cmd, **kw):
            seen.append(prod_lock.read_info()["holder"])
            return subprocess.CompletedProcess(cmd, 0)
        with mock.patch(SUB, side_effect=run) as sub:
            self.cmd._run_update()
        sub.assert_called_once()
        self.assertEqual(seen, ["nightly"])
        self.assertIsNone(prod_lock.read_info())

    def test_released_even_when_the_run_crashes(self):
        with mock.patch(SUB, side_effect=OSError("cannot start")), self.assertRaises(OSError):
            self.cmd._run_update()
        self.assertIsNone(prod_lock.read_info())

    def test_skips_and_logs_while_another_session_holds_it(self):
        prod_lock.acquire("spencer/session-A", "fab deploy")
        with mock.patch(SUB) as sub:
            self.cmd._run_update()
        sub.assert_not_called()
        self.assertEqual(prod_lock.read_info()["holder"], "spencer/session-A")   # untouched
        (rec,) = [json.loads(line) for line in (self.logdir / "pipeline_runs.jsonl").read_text().splitlines()]
        self.assertEqual((rec["command"], rec["rc"], rec["skipped"], rec["steps"]), ("update_daily", SKIP_RC, True, []))
        self.assertIn("prod lock held by spencer/session-A (fab deploy", rec["reason"])
        self.assertIn("SKIPPED update_daily", self.cmd.stdout.getvalue())

    def test_startup_clears_only_a_stale_nightly_lock(self):
        prod_lock.acquire("nightly", "update_daily")
        self.cmd._clear_stale_lock()
        self.assertIsNone(prod_lock.read_info())
        prod_lock.acquire("spencer/session-A", "backfill")
        self.cmd._clear_stale_lock()
        self.assertEqual(prod_lock.read_info()["holder"], "spencer/session-A")

    def test_no_lock_dir_runs_without_locking(self):
        os.environ.pop("PROD_LOCK_DIR")
        with mock.patch(SUB, return_value=subprocess.CompletedProcess([], 0)) as sub:
            self.cmd._run_update()
        sub.assert_called_once()
        self.assertFalse(self.lock.exists())
