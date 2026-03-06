"""
Data Processing Job Management Views
API endpoints for triggering and monitoring update_all and other data processing jobs.

New streaming endpoints:
  POST /api/jobs/run/          — start update_all in background, returns job_id immediately
  GET  /api/jobs/{id}/stream/  — SSE stream of live output (polls DB every 500ms)
  POST /api/jobs/{id}/cancel/  — send SIGTERM to the subprocess and mark cancelled

Legacy synchronous endpoints (kept for backward compat):
  POST /api/jobs/start_update_all/
  POST /api/jobs/start_ingest/
  POST /api/jobs/start_subjob/
"""

import json
import logging
import os
import signal
import threading
import time
import uuid

from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response


class ServerSentEventRenderer(BaseRenderer):
    """
    Passthrough renderer for text/event-stream responses.
    Required so DRF's content negotiation accepts EventSource requests
    (which send Accept: text/event-stream) before the action runs.
    The actual response is a StreamingHttpResponse, not rendered here.
    """
    media_type = "text/event-stream"
    format = "event-stream"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data

from core.models import DataProcessingJob, Season

from . import job_tasks
from .serializers import DataProcessingJobSerializer

logger = logging.getLogger(__name__)


class DataProcessingJobViewSet(viewsets.ModelViewSet):
    """ViewSet for data processing jobs."""

    queryset = DataProcessingJob.objects.all().order_by("-started_at")
    serializer_class = DataProcessingJobSerializer
    permission_classes = [IsAdminUser]
    pagination_class = None
    filterset_fields = ["job_type", "status", "season"]
    search_fields = ["job_id", "error_message"]
    ordering_fields = ["started_at", "completed_at", "status"]
    http_method_names = ["get", "delete", "post", "head", "options"]

    # ------------------------------------------------------------------
    # Streaming endpoints (new)
    # ------------------------------------------------------------------

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def run(self, request):
        """
        Start update_all in a background thread and return the job_id immediately.
        Blocks a second run if one is already in progress (HTTP 409).

        Request body:
            season      int   required
            skip_ingest bool  default false
            days        int   optional — ingest only last N days
            iterations  int   default 25
            sor_trials  int   default 10000
        """
        # Block concurrent runs
        running = DataProcessingJob.objects.filter(status="running").first()
        if running:
            return Response(
                {
                    "error": "A job is already running",
                    "job_id": running.job_id,
                    "id": running.id,
                },
                status=status.HTTP_409_CONFLICT,
            )

        season_year = request.data.get("season")
        if not season_year:
            return Response(
                {"error": "season is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            season = Season.objects.get(year=int(season_year))
        except Season.DoesNotExist:
            return Response(
                {"error": f"Season {season_year} not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        skip_ingest = bool(request.data.get("skip_ingest", False))
        days = request.data.get("days")
        iterations = int(request.data.get("iterations", 25))
        sor_trials = int(request.data.get("sor_trials", 10000))

        job_id = f"update_all_{season_year}_{uuid.uuid4().hex[:8]}"
        job = DataProcessingJob.objects.create(
            job_id=job_id,
            job_type="update_all",
            status="pending",
            season=season,
            parameters={
                "skip_ingest": skip_ingest,
                "days": days,
                "iterations": iterations,
                "sor_trials": sor_trials,
            },
            created_by=request.user.username,
        )

        t = threading.Thread(
            target=job_tasks.run_update_all_subprocess,
            args=(job.id,),
            daemon=True,
            name=f"job-{job_id}",
        )
        t.start()

        return Response({"job_id": job_id, "id": job.id}, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["get"],
        permission_classes=[IsAdminUser],
        renderer_classes=[ServerSentEventRenderer],
    )
    def stream(self, request, pk=None):
        """
        SSE endpoint that streams job output in real-time.
        Polls the DataProcessingJob.logs field every 500ms and yields new lines.
        Supports resume via Last-Event-ID (browser reconnect) or ?since=N (line index).
        Sends id: <line_index> with each log event so reconnects only receive new lines.
        """
        job = self.get_object()
        job_db_id = job.id

        # Resume from line index (browser sends Last-Event-ID; or client can pass ?since=N)
        last_event_id = request.META.get("HTTP_LAST_EVENT_ID", "").strip()
        since_param = request.GET.get("since", "").strip()
        try:
            initial_line = int(since_param) if since_param else (int(last_event_id) + 1 if last_event_id else 0)
        except ValueError:
            initial_line = 0
        initial_line = max(0, initial_line)

        def event_stream():
            from django.db import close_old_connections

            last_sent_line = initial_line
            last_keepalive = time.monotonic()
            keepalive_interval = 15.0
            consecutive_errors = 0
            max_errors_before_yield = 3

            while True:
                try:
                    close_old_connections()
                    current = DataProcessingJob.objects.get(id=job_db_id)
                    consecutive_errors = 0
                except DataProcessingJob.DoesNotExist:
                    break
                except Exception as e:
                    consecutive_errors += 1
                    logger.warning("stream poll error for job %s: %s", job_db_id, e)
                    if consecutive_errors >= max_errors_before_yield:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Stream stalled; reconnect to resume.'})}\n\n"
                        consecutive_errors = 0
                    time.sleep(1)
                    continue

                logs = current.logs or ""
                lines = logs.splitlines()
                if last_sent_line < len(lines):
                    for i in range(last_sent_line, len(lines)):
                        # id enables browser to send Last-Event-ID on reconnect so we resume from here
                        yield f"id: {i}\ndata: {json.dumps({'type': 'log', 'line': lines[i]})}\n\n"
                    last_sent_line = len(lines)

                if current.status in ("success", "failed", "cancelled"):
                    yield f"id: end\ndata: {json.dumps({'type': 'done', 'status': current.status})}\n\n"
                    break

                now = time.monotonic()
                if now - last_keepalive >= keepalive_interval:
                    yield ": keepalive\n\n"
                    last_keepalive = now

                time.sleep(0.5)

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache, no-store"
        response["X-Accel-Buffering"] = "no"
        return response

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def cancel(self, request, pk=None):
        """
        Cancel a running job. Sends SIGTERM to the subprocess and marks it cancelled.
        """
        job = self.get_object()
        if job.status != "running":
            return Response(
                {"error": f"Job is not running (status: {job.status})"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pid = (job.parameters or {}).get("_pid")
        if pid:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError) as e:
                logger.warning(f"Failed to send SIGTERM to pid {pid}: {e}")

        job.status = "cancelled"
        job.completed_at = timezone.now()
        if job.started_at:
            job.duration_seconds = int(
                (job.completed_at - job.started_at).total_seconds()
            )
        job.save(update_fields=["status", "completed_at", "duration_seconds"])

        return Response(DataProcessingJobSerializer(job).data)

    # ------------------------------------------------------------------
    # Bulk management endpoints
    # ------------------------------------------------------------------

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def fix_stuck(self, request):
        """
        Mark all jobs currently stuck as 'running' to 'failed'.
        Use this after a server restart or crash where processes were killed
        but the DB still shows them as running.
        """
        stuck = DataProcessingJob.objects.filter(status__in=["running", "pending"])
        count = stuck.count()
        stuck.update(
            status="failed",
            completed_at=timezone.now(),
            error_message="Marked failed by admin (process was no longer running).",
        )
        logger.info(f"fix_stuck: marked {count} jobs as failed by {request.user.username}")
        return Response({"fixed": count})

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def clear_history(self, request):
        """
        Delete all completed jobs (success, failed, cancelled).
        Running/pending jobs are not touched.
        """
        deleted_qs = DataProcessingJob.objects.filter(
            status__in=["success", "failed", "cancelled"]
        )
        count = deleted_qs.count()
        deleted_qs.delete()
        logger.info(f"clear_history: deleted {count} jobs by {request.user.username}")
        return Response({"deleted": count})

    # ------------------------------------------------------------------
    # Read endpoints
    # ------------------------------------------------------------------

    @action(detail=True, methods=["get"], permission_classes=[IsAdminUser])
    def logs(self, request, pk=None):
        """Get full job logs (snapshot)."""
        job = self.get_object()
        return Response(
            {
                "job_id": job.job_id,
                "logs": job.logs,
                "error_message": job.error_message,
                "updated_at": job.updated_at,
            }
        )

    @action(detail=True, methods=["get"], permission_classes=[IsAdminUser])
    def job_status(self, request, pk=None):
        """Get current job status."""
        job = self.get_object()
        return Response(DataProcessingJobSerializer(job).data)

    # ------------------------------------------------------------------
    # Legacy synchronous endpoints (kept for backward compat)
    # ------------------------------------------------------------------

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def start_update_all(self, request):
        """Legacy: run update_all synchronously in the request. Use /run/ instead."""
        try:
            season_year = request.data.get("season")
            skip_ingest = request.data.get("skip_ingest", False)
            iterations = request.data.get("iterations", 25)
            sor_trials = request.data.get("sor_trials", 10000)

            if not season_year:
                return Response(
                    {"error": "season parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                season = Season.objects.get(year=season_year)
            except Season.DoesNotExist:
                return Response(
                    {"error": f"Season {season_year} not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            job_id = f"update_all_{season_year}_{uuid.uuid4().hex[:8]}"
            job = DataProcessingJob.objects.create(
                job_id=job_id,
                job_type="update_all",
                status="pending",
                season=season,
                parameters={
                    "skip_ingest": skip_ingest,
                    "iterations": iterations,
                    "sor_trials": sor_trials,
                },
                created_by=request.user.username or "api",
            )

            job.status = "running"
            job.save(update_fields=["status"])

            try:
                job_tasks.run_update_all(
                    job.id,
                    season_year,
                    skip_ingest=skip_ingest,
                    iterations=iterations,
                    sor_trials=sor_trials,
                )
            except Exception:
                job.refresh_from_db()
                logger.exception(f"update_all job {job_id} failed")

            return Response(
                DataProcessingJobSerializer(DataProcessingJob.objects.get(pk=job.pk)).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception:
            logger.exception("Error starting update_all job")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def start_ingest(self, request):
        """Legacy: run ingest_gamelogs synchronously."""
        try:
            season_year = request.data.get("season")
            source = request.data.get("source", "ncaa")
            refresh = request.data.get("refresh", False)
            start_date = request.data.get("start_date")
            end_date = request.data.get("end_date")

            if not season_year:
                return Response(
                    {"error": "season parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                season = Season.objects.get(year=season_year)
            except Season.DoesNotExist:
                return Response(
                    {"error": f"Season {season_year} not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            job_id = f"ingest_gamelogs_{season_year}_{uuid.uuid4().hex[:8]}"
            job = DataProcessingJob.objects.create(
                job_id=job_id,
                job_type="ingest_gamelogs",
                status="pending",
                season=season,
                parameters={
                    "source": source,
                    "refresh": refresh,
                    "start_date": start_date,
                    "end_date": end_date,
                },
                created_by=request.user.username or "api",
            )

            job.status = "running"
            job.save(update_fields=["status"])

            try:
                job_tasks.run_ingest_gamelogs(
                    job.id,
                    season_year,
                    source=source,
                    refresh=refresh,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                job.refresh_from_db()
                logger.exception(f"ingest_gamelogs job {job_id} failed")

            return Response(
                DataProcessingJobSerializer(DataProcessingJob.objects.get(pk=job.pk)).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception:
            logger.exception("Error starting ingest job")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def start_subjob(self, request):
        """Legacy: run a single pipeline step synchronously."""
        try:
            job_type = request.data.get("job_type")
            season_year = request.data.get("season")
            parameters = request.data.get("parameters", {})

            if not job_type or not season_year:
                return Response(
                    {"error": "job_type and season are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            task_fns = {
                "compute_team_metrics": job_tasks.run_compute_team_metrics,
                "compute_adjusted_ratings": lambda jid, sy: job_tasks.run_compute_adjusted_ratings(
                    jid, sy, iterations=parameters.get("iterations", 25)
                ),
                "compute_four_factor_index": job_tasks.run_compute_four_factor_index,
                "fetch_net_rankings": job_tasks.run_fetch_net_rankings,
                "compute_sor": lambda jid, sy: job_tasks.run_compute_sor(
                    jid, sy, trials=parameters.get("sor_trials", 10000)
                ),
                "compute_game_value": job_tasks.run_compute_game_value,
                "compute_sos": job_tasks.run_compute_sos,
            }

            if job_type not in task_fns:
                return Response(
                    {"error": f"Unsupported job_type: {job_type}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                season = Season.objects.get(year=season_year)
            except Season.DoesNotExist:
                return Response(
                    {"error": f"Season {season_year} not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            job_id = f"{job_type}_{season_year}_{uuid.uuid4().hex[:8]}"
            job = DataProcessingJob.objects.create(
                job_id=job_id,
                job_type=job_type,
                status="pending",
                season=season,
                parameters=parameters,
                created_by=request.user.username or "api",
            )

            job.status = "running"
            job.save(update_fields=["status"])

            try:
                task_fns[job_type](job.id, season_year)
            except Exception:
                job.refresh_from_db()
                logger.exception(f"Subjob {job_id} failed")

            return Response(
                DataProcessingJobSerializer(DataProcessingJob.objects.get(pk=job.pk)).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception:
            logger.exception("Error starting subjob")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
