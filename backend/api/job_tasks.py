"""
Task functions for update_all and data ingestion.

run_update_all_subprocess — runs update_all as a real subprocess, streams output
    line-by-line to DataProcessingJob.logs. Called from a background thread started
    by the /api/jobs/run/ endpoint.
"""

import logging
import os
import subprocess
import sys
import time

from django.conf import settings
from django.db import close_old_connections
from django.db.models import TextField, Value
from django.db.models.functions import Coalesce, Concat
from django.utils import timezone

from ncaa.models import DataProcessingJob

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Subprocess-based runner (used by the streaming /run/ endpoint)
# ------------------------------------------------------------------


def run_update_all_subprocess(job_db_id: int) -> None:
    """
    Run `manage.py update_all` as a child process and stream stdout/stderr
    to DataProcessingJob.logs line-by-line via atomic DB appends.

    Designed to be called in a daemon thread. Handles:
      - DB connection management for the new thread
      - PID storage in job.parameters['_pid'] for cancellation
      - Checking job.status == 'cancelled' between flushes
      - Marking job success/failed/cancelled on completion
    """
    # Always reset DB connections at thread start
    close_old_connections()

    try:
        job = DataProcessingJob.objects.get(id=job_db_id)
    except DataProcessingJob.DoesNotExist:
        logger.error(f"run_update_all_subprocess: job {job_db_id} not found")
        return

    params = job.parameters or {}
    season_year = job.season.year
    skip_ingest = params.get("skip_ingest", False)
    days = params.get("days")
    iterations = params.get("iterations", 25)
    sor_trials = params.get("sor_trials", 10000)

    # Map job_type → management command name
    CMD_MAP = {
        "update_ncaa_teams":   "update_ncaa_teams",
        "update_ncaa_players": "update_ncaa_players",
        "update_nba_teams":    "update_nba_teams",
        "update_nba_players":  "update_nba_players",
        "update_nba_all":      "update_nba_all",
    }
    cmd_name = CMD_MAP.get(job.job_type, "update_ncaa_all")

    # Commands that support --skip-ingest
    SUPPORTS_SKIP_INGEST = {
        "update_ncaa_teams", "update_ncaa_players",
        "update_nba_teams",  "update_nba_players",
        "update_nba_all",    "update_ncaa_all",
    }
    # Commands that support NCAA-specific --iterations / --sor-trials / --days
    SUPPORTS_NCAA_OPTS = {"update_ncaa_all", "update_ncaa_teams"}

    # Use -u so the child Python runs unbuffered
    cmd = [
        sys.executable,
        "-u",
        str(settings.BASE_DIR / "manage.py"),
        cmd_name,
        "--season",
        str(season_year),
    ]

    if skip_ingest and cmd_name in SUPPORTS_SKIP_INGEST:
        cmd.append("--skip-ingest")

    if cmd_name in SUPPORTS_NCAA_OPTS:
        cmd.extend([
            "--iterations",
            str(iterations),
            "--sor-trials",
            str(sor_trials),
        ])
        if days:
            cmd.extend(["--days", str(days)])

    # Mark running
    job.status = "running"
    job.started_at = timezone.now()
    job.logs = ""
    job.save(update_fields=["status", "started_at", "logs"])

    proc = None
    try:
        # PYTHONUNBUFFERED=1 so child's stdout is unbuffered (real-time when piped).
        proc_env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # line-buffered on our side when reading from the pipe
            cwd=str(settings.BASE_DIR),
            env=proc_env,
        )

        # Store PID for cancellation via the cancel endpoint
        params["_pid"] = proc.pid
        job.parameters = params
        job.save(update_fields=["parameters"])

        # Read output line by line, flushing to DB periodically
        buffer: list[str] = []
        last_flush = time.monotonic()
        FLUSH_LINES = 5
        FLUSH_INTERVAL = 0.3  # seconds

        def flush_buffer():
            nonlocal buffer, last_flush
            if not buffer:
                return
            batch = "".join(buffer)
            buffer = []
            last_flush = time.monotonic()
            close_old_connections()
            DataProcessingJob.objects.filter(id=job_db_id).update(
                logs=Concat(
                    Coalesce("logs", Value("")),
                    Value(batch),
                    output_field=TextField(),
                )
            )

        for line in proc.stdout:
            buffer.append(line)
            elapsed = time.monotonic() - last_flush
            if len(buffer) >= FLUSH_LINES or elapsed >= FLUSH_INTERVAL:
                flush_buffer()
                # Check for cancellation signal from the cancel endpoint
                close_old_connections()
                if DataProcessingJob.objects.filter(
                    id=job_db_id, status="cancelled"
                ).exists():
                    proc.terminate()
                    break

        flush_buffer()
        proc.wait()

        # Set final status (unless the cancel endpoint already set it)
        close_old_connections()
        job.refresh_from_db(fields=["status", "started_at"])
        if job.status not in ("cancelled",):
            job.status = "success" if proc.returncode == 0 else "failed"
        job.completed_at = timezone.now()
        if job.started_at:
            job.duration_seconds = int(
                (job.completed_at - job.started_at).total_seconds()
            )
        job.progress_percent = 100
        job.save(
            update_fields=[
                "status",
                "completed_at",
                "duration_seconds",
                "progress_percent",
            ]
        )

    except Exception as exc:
        logger.exception(
            f"run_update_all_subprocess: unhandled error for job {job_db_id}"
        )
        try:
            close_old_connections()
            job.refresh_from_db(fields=["status"])
            if job.status not in ("cancelled", "success"):
                job.status = "failed"
                job.error_message = str(exc)
                job.completed_at = timezone.now()
                job.save(update_fields=["status", "error_message", "completed_at"])
        except Exception:
            pass
        if proc and proc.poll() is None:
            proc.terminate()
