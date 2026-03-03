"""
Background job task functions for update_all and data ingestion
These functions are called by django-rq workers
"""

from django.core.management import call_command
from django.utils import timezone
from io import StringIO
import logging
from core.models import DataProcessingJob

logger = logging.getLogger(__name__)


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
    """
    Run the complete update_all pipeline
    Called by django-rq worker
    """
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
        except:
            pass
        raise


def run_ingest_gamelogs(
    job_id, season_year, source="ncaa", refresh=False, start_date=None, end_date=None
):
    """
    Run the ingest_gamelogs management command
    Called by django-rq worker
    """
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
        except:
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
        except:
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
        except:
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
        except:
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
        except:
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
        except:
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
        except:
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
        except:
            pass
        raise
