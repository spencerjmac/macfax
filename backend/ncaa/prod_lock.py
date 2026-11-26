"""
Prod write lock, container side: the same lock as ops/prod-lock.sh (fab tasks and server-side write
scripts), so the nightly and a deploy never run at once.

The lock is a directory (mkdir is atomic) at $PROD_LOCK_DIR with an `info` file of key=value lines:
holder, command, started, host, token. Only the token's owner releases it. On prod the scheduler
mounts the host's /opt/macfax/.locks at /locks, so PROD_LOCK_DIR=/locks/prod there is the same lock
fab takes at /opt/macfax/.locks/prod. Unset PROD_LOCK_DIR (dev, tests by default): no locking.

The container runs as root and fab as the `macfax` user, so a lock taken here is left world-writable
(directory 0777, info 0666): fab can still release a stale one with `fab lock-break --yes`.

Pure Python (no Django), so ops/tests can load it next to the bash script.
"""
from __future__ import annotations

import os
import random
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ENV_DIR = "PROD_LOCK_DIR"


def lock_dir() -> Path | None:
    d = os.environ.get(ENV_DIR)
    return Path(d) if d else None


def read_info(path: Path | None = None) -> dict | None:
    """The holder's info (a dict) when the lock is held, else None."""
    path = path or lock_dir()
    if path is None or not path.is_dir():
        return None
    info = {}
    try:
        for line in (path / "info").read_text().splitlines():
            k, _, v = line.partition("=")
            if k:
                info[k] = v
    except OSError:
        pass  # just taken (info not written yet), or left by a crash
    return info


def acquire(holder: str, command: str, path: Path | None = None) -> str | None:
    """Take the lock: the token, or None when another holder has it."""
    path = path or lock_dir()
    if path is None:
        raise RuntimeError(f"{ENV_DIR} is not set")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.parent.stat().st_uid == 0:
            os.chmod(path.parent, 0o777)   # a root-created mount point: let fab (macfax) use it too
    except OSError:
        pass
    try:
        path.mkdir()
    except FileExistsError:
        return None
    os.chmod(path, 0o777)
    now = datetime.now(timezone.utc)
    token = f"{now:%Y%m%dT%H%M%SZ}-{os.getpid()}-{random.randrange(10**9)}"
    tmp = path / "info.tmp"
    tmp.write_text(f"holder={holder}\ncommand={command}\nstarted={now:%Y-%m-%dT%H:%M:%SZ}\n"
                   f"host={socket.gethostname()}\ntoken={token}\n")
    os.chmod(tmp, 0o666)
    tmp.replace(path / "info")
    return token


def release(token: str, path: Path | None = None) -> bool:
    """Release the lock if `token` holds it. True when released (or not held), False otherwise."""
    path = path or lock_dir()
    if path is None or not path.is_dir():
        return True
    if (read_info(path) or {}).get("token") != token:
        return False
    _remove(path)
    return True


def clear_if_holder(holder: str, path: Path | None = None) -> dict | None:
    """Remove the lock when `holder` holds it (a stale lock of ours); the removed info, else None."""
    path = path or lock_dir()
    info = read_info(path) if path else None
    if info is not None and info.get("holder") == holder:
        _remove(path)
        return info
    return None


def acquire_waiting(holder: str, command: str, wait_seconds: float, poll_seconds: float = 60,
                    path: Path | None = None, sleep: Callable[[float], None] = time.sleep,
                    clock: Callable[[], float] = time.monotonic) -> tuple[str | None, dict | None, float]:
    """
    Take the lock, waiting up to `wait_seconds` while someone else holds it.
    Returns (token or None, the last holder's info when it gave up, seconds waited).
    """
    start = clock()
    while True:
        token = acquire(holder, command, path)
        if token:
            return token, None, clock() - start
        waited = clock() - start
        if waited >= wait_seconds:
            return None, read_info(path), waited
        sleep(min(poll_seconds, max(0.0, wait_seconds - waited)))


def _remove(path: Path):
    for child in path.iterdir():
        child.unlink()
    path.rmdir()
