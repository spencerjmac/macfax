"""
Pipeline run log: one JSON line per update_* run (steps, rc, timings), appended to
$PIPELINE_LOG_DIR/pipeline_runs.jsonl.

Why: the nightly's only record used to be the scheduler container's stdout, which is gone after the
container is recreated (a deploy). On prod PIPELINE_LOG_DIR is a named volume (docker-compose.yml), so
the log survives recreation. Unset (dev, tests by default): nothing is written.

Record: {"command", "title", "options", "started", "finished", "seconds", "rc", "host", "pid",
         "lock_holder", "lock_wait_seconds", "steps": [{"name", "ok", "rc", "seconds", "note"}]}

lock_holder / lock_wait_seconds: who held the prod write lock (ncaa/prod_lock.py) during the run and how
long the run waited for it. The nightly (run_scheduler) passes both to update_daily in the environment;
any other run under the lock (ops/prod-lock.sh run, which never waits) gets the holder from the lock file
and a wait of 0. No lock held: both null. A skipped nightly records the holder it waited behind.
Read it with `fab pipeline_log` or `tail .../pipeline_runs.jsonl`.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

from django.utils import timezone

from ncaa import prod_lock

ENV_DIR = "PIPELINE_LOG_DIR"
ENV_LOCK_HOLDER = "PIPELINE_LOCK_HOLDER"
ENV_LOCK_WAIT = "PIPELINE_LOCK_WAIT_SECONDS"
FILENAME = "pipeline_runs.jsonl"
# BaseCommand options that say nothing about the run
_DJANGO_OPTIONS = {"verbosity", "settings", "pythonpath", "traceback", "no_color", "force_color",
                   "skip_checks", "stdout", "stderr"}


def log_path() -> Path | None:
    d = os.environ.get(ENV_DIR)
    return Path(d) / FILENAME if d else None


def append_run(record: dict) -> Path | None:
    """Append one record; a logging failure is reported and never breaks the pipeline."""
    path = log_path()
    if path is None:
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, default=str, sort_keys=True) + "\n"
        with open(path, "a", encoding="utf-8") as f:   # one small append per run
            f.write(line)
        return path
    except OSError as e:
        print(f"[pipeline-log] could not write {path}: {e}", file=sys.stderr)
        return None


def read_runs() -> list[dict] | None:
    """All logged runs, oldest first; None when there is no log (unset dir, or nothing written yet)."""
    path = log_path()
    if path is None or not path.exists():
        return None
    runs = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                runs.append(json.loads(line))
            except ValueError:
                continue   # a torn line (killed mid-write) is skipped, not fatal
    except OSError:
        return None
    return runs


def lock_fields() -> dict:
    """{"lock_holder", "lock_wait_seconds"} for this run (see the module docstring)."""
    holder = os.environ.get(ENV_LOCK_HOLDER)
    if holder:
        try:
            wait = round(float(os.environ.get(ENV_LOCK_WAIT, "")), 1)
        except ValueError:
            wait = None
        return {"lock_holder": holder, "lock_wait_seconds": wait}
    try:
        info = prod_lock.read_info()
    except OSError:
        info = None
    if info and info.get("holder"):
        return {"lock_holder": info["holder"], "lock_wait_seconds": 0.0}
    return {"lock_holder": None, "lock_wait_seconds": None}


def _jsonable(v) -> bool:
    try:
        json.dumps(v)
        return True
    except (TypeError, ValueError):
        return False


class PipelineRunLogMixin:
    """
    For update_* commands: records when the run started, how long each step took, and writes the
    run once when the command prints its summary (also on the fatal-step exit path).

    Commands call `self._time_step(steps, t0[, rc])` right after appending a step they timed, and
    `self._persist_run(title, steps)` from their summary.
    """

    def execute(self, *args, **options):
        self._run_log_started = timezone.now()
        self._run_log_options = {k: v for k, v in options.items() if k not in _DJANGO_OPTIONS and _jsonable(v)}
        self._run_log_steps = {}
        self._run_log_written = False
        return super().execute(*args, **options)

    def _time_step(self, steps: list, t0: float, rc: int | None = None):
        """Timing (and an exit code, when known) for the step just appended to `steps`."""
        meta = {"seconds": round(time.monotonic() - t0, 1)}
        if rc is not None:
            meta["rc"] = rc
        self.__dict__.setdefault("_run_log_steps", {})[len(steps) - 1] = meta

    def _persist_run(self, title: str, steps: list):
        if getattr(self, "_run_log_written", False):
            return
        self._run_log_written = True
        meta = getattr(self, "_run_log_steps", {})
        rows = []
        for i, (name, ok, note) in enumerate(steps):
            m = meta.get(i, {})
            rows.append({"name": name, "ok": bool(ok), "rc": m.get("rc", 0 if ok else 1),
                         "seconds": m.get("seconds"),
                         "note": None if note in (None, "None") else str(note)})
        finished = timezone.now()
        started = getattr(self, "_run_log_started", finished)
        append_run({
            "command": self.__module__.rsplit(".", 1)[-1],
            "title": title,
            "options": getattr(self, "_run_log_options", {}),
            "started": started.isoformat(),
            "finished": finished.isoformat(),
            "seconds": round((finished - started).total_seconds(), 1),
            "rc": 0 if all(r["ok"] for r in rows) else 1,
            "host": socket.gethostname(),
            "pid": os.getpid(),
            **lock_fields(),
            "steps": rows,
        })
