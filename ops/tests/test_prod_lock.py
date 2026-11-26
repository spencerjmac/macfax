"""
Prod write lock (ops/prod-lock.sh and the fab wrapper in fabfile.py).

Run from the repo root with the interpreter fab uses:
    /usr/bin/python3 -m unittest discover -s ops/tests -v

- acquire takes the lock and records holder, command, start time and a token; a second acquire is
  refused (exit 3) and shows who holds it;
- only the token's owner releases it; break --yes removes a stale lock;
- run holds the lock for the command, passes stdin and the exit code through, and releases on exit;
  run refuses (and does not run the command) while another session holds the lock;
- of many simultaneous acquires exactly one wins;
- fab's _prod_lock takes and releases the lock around a task body, refuses while it is held, and
  releases when the body fails;
- the nightly's Python lock (backend/ncaa/prod_lock.py) and the bash script are the same lock: each
  sees and respects the other's holder, a token works in either, and a deploy refuses while the
  nightly holds it.
"""
import importlib.util
import os
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "ops", "prod-lock.sh")


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.lock = os.path.join(tempfile.mkdtemp(), "prod-lock")

    def sh(self, *args, stdin=None):
        return subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True, input=stdin,
                              env={**os.environ, "PROD_LOCK_DIR": self.lock})

    def test_acquire_records_holder_and_refuses_a_second_session(self):
        a = self.sh("acquire", "session-A", "fab", "deploy")
        self.assertEqual(a.returncode, 0)
        token = a.stdout.strip()
        status = self.sh("status").stdout
        self.assertIn("HELD", status)
        self.assertIn("holder=session-A", status)
        self.assertIn("command=fab deploy", status)
        self.assertIn("started=", status)
        self.assertIn(f"token={token}", status)

        b = self.sh("acquire", "session-B", "backfill")
        self.assertEqual(b.returncode, 3)
        self.assertIn("holder=session-A", b.stderr)
        self.assertIn("holder=session-A", self.sh("status").stdout)   # unchanged

    def test_only_the_owner_releases(self):
        token = self.sh("acquire", "A", "x").stdout.strip()
        wrong = self.sh("release", "not-the-token")
        self.assertEqual(wrong.returncode, 4)
        self.assertIn("HELD", self.sh("status").stdout)
        self.assertEqual(self.sh("release", token).returncode, 0)
        self.assertEqual(self.sh("status").stdout.strip(), "free")
        self.assertEqual(self.sh("release", token).returncode, 0)        # already free: no error

    def test_break_needs_yes(self):
        self.sh("acquire", "stale", "x")
        self.assertEqual(self.sh("break").returncode, 2)
        self.assertIn("HELD", self.sh("status").stdout)
        out = self.sh("break", "--yes")
        self.assertIn("holder=stale", out.stdout)
        self.assertEqual(self.sh("status").stdout.strip(), "free")

    def test_run_holds_the_lock_passes_stdin_and_exit_code_and_releases(self):
        inner = (f'PROD_LOCK_DIR={self.lock} bash {SCRIPT} status | head -1; '
                 'read line; echo "got:$line"; exit 7')
        r = self.sh("run", "session-A", "--", "bash", "-c", inner, stdin="hello\n")
        self.assertEqual(r.returncode, 7)
        self.assertIn("HELD", r.stdout)
        self.assertIn("got:hello", r.stdout)
        self.assertEqual(self.sh("status").stdout.strip(), "free")

    def test_run_refuses_while_held_and_does_not_run(self):
        self.sh("acquire", "session-A", "fab deploy")
        marker = os.path.join(os.path.dirname(self.lock), "ran")
        r = self.sh("run", "session-B", "--", "touch", marker)
        self.assertEqual(r.returncode, 3)
        self.assertFalse(os.path.exists(marker))
        self.assertIn("holder=session-A", self.sh("status").stdout)

    def test_simultaneous_acquires_one_winner(self):
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda i: self.sh("acquire", f"s{i}", "x").returncode, range(12)))
        self.assertEqual(results.count(0), 1)
        self.assertEqual(results.count(3), 11)


def _load_fabfile():
    spec = importlib.util.spec_from_file_location("fabfile_under_test", os.path.join(ROOT, "fabfile.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LocalConn:
    """Stands in for a fabric Connection: runs the command locally with bash."""

    def run(self, cmd, in_stream=None, hide=None, warn=False, **kw):
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                           input=in_stream.read() if in_stream else None)
        return SimpleNamespace(exited=r.returncode, stdout=r.stdout, stderr=r.stderr)


@unittest.skipUnless(importlib.util.find_spec("fabric"), "fabric is not installed for this interpreter")
class FabWrapperTests(unittest.TestCase):
    def setUp(self):
        self.fab = _load_fabfile()
        self.fab.LOCK_DIR = os.path.join(tempfile.mkdtemp(), "prod-lock")
        os.environ["PROD_LOCK_HOLDER"] = "test-session"
        self.addCleanup(os.environ.pop, "PROD_LOCK_HOLDER", None)
        self.conn = LocalConn()

    def status(self):
        return self.fab._lock_run(self.conn, "status").stdout

    def test_takes_and_releases_around_the_task(self):
        with self.fab._prod_lock(self.conn, "fab deploy"):
            s = self.status()
            self.assertIn("holder=test-session", s)
            self.assertIn("command=fab deploy", s)
        self.assertEqual(self.status().strip(), "free")

    def test_refuses_while_another_session_holds_it(self):
        subprocess.run(["bash", SCRIPT, "acquire", "other-session", "backfill"], capture_output=True,
                       env={**os.environ, "PROD_LOCK_DIR": self.fab.LOCK_DIR})
        ran = []
        with self.assertRaises(SystemExit) as ctx:
            with self.fab._prod_lock(self.conn, "fab deploy"):
                ran.append(True)
        self.assertEqual(ran, [])
        self.assertIn("lock is held", str(ctx.exception))
        self.assertIn("holder=other-session", self.status())

    def test_releases_when_the_task_fails(self):
        with self.assertRaises(RuntimeError):
            with self.fab._prod_lock(self.conn, "fab migrate"):
                raise RuntimeError("migration failed")
        self.assertEqual(self.status().strip(), "free")


def _load_py_lock():
    """backend/ncaa/prod_lock.py (pure Python), the nightly's side of the same lock."""
    spec = importlib.util.spec_from_file_location(
        "prod_lock_under_test", os.path.join(ROOT, "backend", "ncaa", "prod_lock.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NightlyInteropTests(unittest.TestCase):
    """The nightly (Python, in the scheduler) and fab / server scripts (bash) share one lock."""

    def setUp(self):
        self.py = _load_py_lock()
        self.lock = os.path.join(tempfile.mkdtemp(), "locks", "prod")

    def sh(self, *args):
        return subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True,
                              env={**os.environ, "PROD_LOCK_DIR": self.lock})

    def test_nightly_holds_it_and_bash_sees_and_respects_it(self):
        from pathlib import Path
        token = self.py.acquire("nightly", "update_daily", Path(self.lock))
        status = self.sh("status").stdout
        self.assertIn("holder=nightly", status)
        self.assertIn("command=update_daily", status)
        self.assertEqual(self.sh("acquire", "session-A", "fab deploy").returncode, 3)
        self.assertEqual(self.sh("release", "other").returncode, 4)
        self.assertEqual(self.sh("release", token).returncode, 0)   # same format: the token works in bash

    def test_bash_holder_blocks_the_nightly(self):
        from pathlib import Path
        self.sh("acquire", "session-A", "backfill")
        self.assertIsNone(self.py.acquire("nightly", "update_daily", Path(self.lock)))
        self.assertEqual(self.py.read_info(Path(self.lock))["holder"], "session-A")

    @unittest.skipUnless(importlib.util.find_spec("fabric"), "fabric is not installed for this interpreter")
    def test_deploy_refuses_while_the_nightly_runs(self):
        from pathlib import Path
        self.py.acquire("nightly", "update_daily", Path(self.lock))
        fab = _load_fabfile()
        fab.LOCK_DIR = self.lock
        ran = []
        with self.assertRaises(SystemExit):
            with fab._prod_lock(LocalConn(), "fab deploy"):
                ran.append(True)
        self.assertEqual(ran, [])
        self.assertIn("holder=nightly", self.sh("status").stdout)


if __name__ == "__main__":
    unittest.main()
