"""
Prod write lock, container side (ncaa/prod_lock.py) and the nightly's use of it (run_scheduler).

- acquire takes the lock (world-writable, so fab's macfax user can release a stale one), refuses a
  second holder; only the token releases; clear_if_holder clears only that holder's lock;
- acquire_waiting waits while held and gives up after the wait, returning the holder;
- the nightly runs update_daily holding the lock as "nightly" and releases it after;
- while another session holds it the nightly waits, then skips and logs rc 75 with the reason;
- at startup a lock left by "nightly" is cleared, anyone else's is kept;
- without PROD_LOCK_DIR the nightly runs without a lock;
- catch-up: at startup after today's slot, with no update_daily run (any outcome) logged since the
  slot, the nightly runs once; no run log means no catch-up.
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


class CatchUpTests(SimpleTestCase):
    """At startup, run the nightly once if today's slot passed and the run log has no run since it."""

    AT = __import__("datetime").time(10, 0)

    def setUp(self):
        self.logdir = Path(tempfile.mkdtemp())
        env = mock.patch.dict(os.environ, {"PIPELINE_LOG_DIR": str(self.logdir)})
        env.start()
        self.addCleanup(env.stop)
        self.cmd = Command(stdout=StringIO(), stderr=StringIO())

    def now(self, hh, mm=0, day=26):
        from datetime import datetime, timezone
        return datetime(2026, 11, day, hh, mm, tzinfo=timezone.utc)

    def log(self, **rec):
        with open(self.logdir / "pipeline_runs.jsonl", "a") as f:
            f.write(json.dumps({"command": "update_daily", "rc": 0, "steps": [], **rec}) + "\n")

    def test_no_run_log_means_no_catch_up(self):
        self.assertFalse(self.cmd._missed_today(self.now(16), self.AT))

    def test_missing_today_after_the_slot_catches_up(self):
        self.log(started="2026-11-25T10:00:03+00:00")            # yesterday's only
        self.assertTrue(self.cmd._missed_today(self.now(16), self.AT))

    def test_before_the_slot_waits(self):
        self.log(started="2026-11-25T10:00:03+00:00")
        self.assertFalse(self.cmd._missed_today(self.now(9, 59), self.AT))

    def test_completed_failed_or_skipped_today_counts(self):
        for rec in ({"rc": 0}, {"rc": 1}, {"rc": 75, "skipped": True}):
            with self.subTest(rec=rec):
                (self.logdir / "pipeline_runs.jsonl").unlink(missing_ok=True)
                self.log(started="2026-11-26T10:00:02+00:00", **rec)
                self.assertFalse(self.cmd._missed_today(self.now(16), self.AT))

    def test_other_commands_and_earlier_runs_do_not_count(self):
        self.log(command="update_ncaa_teams", started="2026-11-26T12:00:00+00:00")
        self.log(started="2026-11-26T09:00:00+00:00")             # a manual run before the slot
        with open(self.logdir / "pipeline_runs.jsonl", "a") as f:
            f.write('{"torn line\n')
        self.assertTrue(self.cmd._missed_today(self.now(16), self.AT))

    def test_handle_runs_the_catch_up_before_waiting(self):
        class Stop(Exception):
            pass
        calls = []
        with mock.patch.object(Command, "_missed_today", return_value=True), \
             mock.patch.object(Command, "_run_update", side_effect=lambda: calls.append("run")), \
             mock.patch("ncaa.management.commands.run_scheduler.time_module.sleep", side_effect=Stop), \
             self.assertRaises(Stop):
            self.cmd.handle(at="10:00", once=False, run_now=False)
        self.assertEqual(calls, ["run"])
        self.assertIn("catching up now", self.cmd.stdout.getvalue())

    def test_handle_does_not_catch_up_when_today_ran(self):
        class Stop(Exception):
            pass
        with mock.patch.object(Command, "_missed_today", return_value=False), \
             mock.patch.object(Command, "_run_update") as run, \
             mock.patch("ncaa.management.commands.run_scheduler.time_module.sleep", side_effect=Stop), \
             self.assertRaises(Stop):
            self.cmd.handle(at="10:00", once=False, run_now=False)
        run.assert_not_called()
