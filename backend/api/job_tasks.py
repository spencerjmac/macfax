"""
Task functions for update_all and data ingestion.

run_update_all_subprocess — runs update_all as a real subprocess, streams output
    line-by-line to DataProcessingJob.logs. Called from a background thread started
    by the /api/jobs/run/ endpoint.

Legacy _run_command_job functions — run management commands synchronously via
    call_command() and store all output at the end. Used by the old /start_update_all/
    endpoints.
"""

import logging
import os
import subprocess
import sys
import time
from io import StringIO

from django.conf import settings
from django.core.management import call_command
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

    # Use -u so the child Python runs unbuffered; otherwise stdout is fully buffered
    # when piped (no TTY) and output appears in big chunks instead of in real time.
    cmd = [
        sys.executable,
        "-u",
        str(settings.BASE_DIR / "manage.py"),
        "update_all",
        "--season",
        str(season_year),
        "--iterations",
        str(iterations),
        "--sor-trials",
        str(sor_trials),
    ]
    if skip_ingest:
        cmd.append("--skip-ingest")
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


def _run_command_job(job_id, command_name, cmd_args):
    """Run a management command and update DataProcessingJob."""
    job = DataProcessingJob.objects.get(id=job_id)
    job.status = "running"
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    stdout = StringIO()
    stderr = StringIO()

    cmd_args = {**cmd_args, "stdout": stdout, "stderr": stderr}
    call_command(command_name, **cmd_args)

    output = stdout.getvalue()
    errors = stderr.getvalue()

    job.logs = output
    if errors:
        job.error_message = errors
        job.status = "failed"
    else:
        job.status = "success"

    job.completed_at = timezone.now()
    duration = (job.completed_at - job.started_at).total_seconds()
    job.duration_seconds = int(duration)
    job.progress_percent = 100
    job.save()

    return {
        "status": job.status,
        "job_id": job.job_id,
        "duration": job.duration_seconds,
    }


def run_update_all(
    job_id, season_year, skip_ingest=False, iterations=25, sor_trials=10000
):
    """Run the complete update_all pipeline."""
    try:
        return _run_command_job(
            job_id,
            "update_all",
            {
                "season": season_year,
                "skip_ingest": skip_ingest,
                "iterations": iterations,
                "sor_trials": sor_trials,
            },
        )

    except Exception as e:
        logger.exception(f"Error in run_update_all: {e}")
        try:
            job = DataProcessingJob.objects.get(id=job_id)
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at"])
        except Exception:
            pass
        raise


def run_ingest_gamelogs(
    job_id, season_year, source="ncaa", refresh=False, start_date=None, end_date=None
):
    """Run the ingest_gamelogs management command."""
    try:
        cmd_args = {
            "season": season_year,
            "source": source,
        }

        if refresh:
            cmd_args["refresh"] = True
        if start_date:
            cmd_args["start"] = start_date
        if end_date:
            cmd_args["end"] = end_date

        return _run_command_job(job_id, "ingest_gamelogs", cmd_args)

    except Exception as e:
        logger.exception(f"Error in run_ingest_gamelogs: {e}")
        try:
            job = DataProcessingJob.objects.get(id=job_id)
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at"])
        except Exception:
            pass
        raise


def run_compute_team_metrics(job_id, season_year):
    try:
        return _run_command_job(job_id, "compute_team_metrics", {"season": season_year})
    except Exception as e:
        logger.exception(f"Error in run_compute_team_metrics: {e}")
        try:
            job = DataProcessingJob.objects.get(id=job_id)
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at"])
        except Exception:
            pass
        raise


def run_compute_adjusted_ratings(job_id, season_year, iterations=25):
    try:
        return _run_command_job(
            job_id,
            "compute_adjusted_ratings",
            {"season": season_year, "iterations": iterations},
        )
    except Exception as e:
        logger.exception(f"Error in run_compute_adjusted_ratings: {e}")
        try:
            job = DataProcessingJob.objects.get(id=job_id)
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at"])
        except Exception:
            pass
        raise


def run_compute_four_factor_index(job_id, season_year):
    try:
        return _run_command_job(
            job_id, "compute_four_factor_index", {"season": season_year}
        )
    except Exception as e:
        logger.exception(f"Error in run_compute_four_factor_index: {e}")
        try:
            job = DataProcessingJob.objects.get(id=job_id)
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at"])
        except Exception:
            pass
        raise


def run_fetch_net_rankings(job_id, season_year):
    try:
        return _run_command_job(job_id, "fetch_net_rankings", {"season": season_year})
    except Exception as e:
        logger.exception(f"Error in run_fetch_net_rankings: {e}")
        try:
            job = DataProcessingJob.objects.get(id=job_id)
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at"])
        except Exception:
            pass
        raise


def run_compute_sor(job_id, season_year, trials=10000):
    try:
        return _run_command_job(
            job_id,
            "compute_sor",
            {"season": season_year, "trials": trials},
        )
    except Exception as e:
        logger.exception(f"Error in run_compute_sor: {e}")
        try:
            job = DataProcessingJob.objects.get(id=job_id)
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at"])
        except Exception:
            pass
        raise


def run_compute_game_value(job_id, season_year):
    try:
        return _run_command_job(job_id, "compute_game_value", {"season": season_year})
    except Exception as e:
        logger.exception(f"Error in run_compute_game_value: {e}")
        try:
            job = DataProcessingJob.objects.get(id=job_id)
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at"])
        except Exception:
            pass
        raise


def run_compute_sos(job_id, season_year):
    try:
        return _run_command_job(job_id, "compute_sos", {"season": season_year})
    except Exception as e:
        logger.exception(f"Error in run_compute_sos: {e}")
        try:
            job = DataProcessingJob.objects.get(id=job_id)
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at"])
        except Exception:
            pass
        raise
