"""
Data Processing Job Management Views
API endpoints for triggering, monitoring, and managing update_all and other data processing jobs
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.core.management import call_command
from django.utils import timezone
from io import StringIO
import django_rq
import uuid
import logging

from core.models import DataProcessingJob, Season
from .serializers import DataProcessingJobSerializer

logger = logging.getLogger(__name__)


class DataProcessingJobViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for monitoring data processing jobs

    Endpoints:
    - GET /api/jobs/ - List all jobs
    - GET /api/jobs/{id}/ - Get job details
    - GET /api/jobs/{id}/logs/ - Get job logs
    - POST /api/jobs/start-update-all/ - Start update_all job
    - POST /api/jobs/start-ingest/ - Start ingest_gamelogs job
    """

    queryset = DataProcessingJob.objects.all().order_by("-started_at")
    serializer_class = DataProcessingJobSerializer
    permission_classes = [IsAdminUser]
    pagination_class = None  # No pagination for job history
    filterset_fields = ["job_type", "status", "season"]
    search_fields = ["job_id", "error_message"]
    ordering_fields = ["started_at", "completed_at", "status"]

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def start_update_all(self, request):
        """
        Start a full update_all job

        Request body:
        {
            "season": 2026,
            "skip_ingest": false,
            "iterations": 25,
            "sor_trials": 10000
        }
        """
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

            # Get or create season
            try:
                season = Season.objects.get(year=season_year)
            except Season.DoesNotExist:
                return Response(
                    {"error": f"Season {season_year} not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create job record
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

            # Queue the job
            try:
                queue = django_rq.get_queue("default")
                rq_job = queue.enqueue(
                    "api.job_tasks.run_update_all",
                    kwargs={
                        "job_id": job.id,
                        "season_year": season_year,
                        "skip_ingest": skip_ingest,
                        "iterations": iterations,
                        "sor_trials": sor_trials,
                    },
                    result_ttl=14400,  # 4 hours
                )

                job.status = "running"
                job.save(update_fields=["status"])

                return Response(
                    DataProcessingJobSerializer(job).data,
                    status=status.HTTP_201_CREATED,
                )
            except Exception as e:
                job.status = "failed"
                job.error_message = f"Failed to queue job: {str(e)}"
                job.save(update_fields=["status", "error_message"])
                logger.exception(f"Failed to queue update_all job {job_id}")

                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as e:
            logger.exception("Error starting update_all job")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def start_ingest(self, request):
        """
        Start a game log ingestion job

        Request body:
        {
            "season": 2026,
            "source": "ncaa",
            "refresh": false,
            "start_date": "2025-11-01",
            "end_date": "2026-03-02"
        }
        """
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

            # Get or create season
            try:
                season = Season.objects.get(year=season_year)
            except Season.DoesNotExist:
                return Response(
                    {"error": f"Season {season_year} not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create job record
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

            # Queue the job
            try:
                queue = django_rq.get_queue("default")
                rq_job = queue.enqueue(
                    "api.job_tasks.run_ingest_gamelogs",
                    kwargs={
                        "job_id": job.id,
                        "season_year": season_year,
                        "source": source,
                        "refresh": refresh,
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                    result_ttl=7200,  # 2 hours
                )

                job.status = "running"
                job.save(update_fields=["status"])

                return Response(
                    DataProcessingJobSerializer(job).data,
                    status=status.HTTP_201_CREATED,
                )
            except Exception as e:
                job.status = "failed"
                job.error_message = f"Failed to queue job: {str(e)}"
                job.save(update_fields=["status", "error_message"])
                logger.exception(f"Failed to queue ingest job {job_id}")

                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as e:
            logger.exception("Error starting ingest job")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def start_subjob(self, request):
        """
        Start a specific update_all sub-job

        Request body:
        {
            "job_type": "compute_team_metrics",
            "season": 2026,
            "parameters": {"iterations": 25, "sor_trials": 10000}
        }
        """
        try:
            job_type = request.data.get("job_type")
            season_year = request.data.get("season")
            parameters = request.data.get("parameters", {})

            if not job_type or not season_year:
                return Response(
                    {"error": "job_type and season are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            allowed_job_types = {
                "compute_team_metrics": "api.job_tasks.run_compute_team_metrics",
                "compute_adjusted_ratings": "api.job_tasks.run_compute_adjusted_ratings",
                "compute_four_factor_index": "api.job_tasks.run_compute_four_factor_index",
                "fetch_net_rankings": "api.job_tasks.run_fetch_net_rankings",
                "compute_sor": "api.job_tasks.run_compute_sor",
                "compute_game_value": "api.job_tasks.run_compute_game_value",
                "compute_sos": "api.job_tasks.run_compute_sos",
            }

            if job_type not in allowed_job_types:
                return Response(
                    {"error": f"Unsupported job_type: {job_type}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get season
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

            try:
                queue = django_rq.get_queue("default")
                task_path = allowed_job_types[job_type]

                enqueue_kwargs = {
                    "job_id": job.id,
                    "season_year": season_year,
                }

                if job_type == "compute_adjusted_ratings":
                    enqueue_kwargs["iterations"] = parameters.get("iterations", 25)
                if job_type == "compute_sor":
                    enqueue_kwargs["trials"] = parameters.get("sor_trials", 10000)

                queue.enqueue(task_path, kwargs=enqueue_kwargs, result_ttl=14400)

                job.status = "running"
                job.save(update_fields=["status"])

                return Response(
                    DataProcessingJobSerializer(job).data,
                    status=status.HTTP_201_CREATED,
                )
            except Exception as e:
                job.status = "failed"
                job.error_message = f"Failed to queue job: {str(e)}"
                job.save(update_fields=["status", "error_message"])
                logger.exception(f"Failed to queue subjob {job_id}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as e:
            logger.exception("Error starting subjob")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["get"], permission_classes=[IsAdminUser])
    def logs(self, request, pk=None):
        """Get job logs"""
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
    def status(self, request, pk=None):
        """Get current job status"""
        job = self.get_object()

        # Try to refresh from RQ if still running
        if job.status == "running":
            try:
                rq_job = django_rq.get_queue("default").fetch_job(
                    f"dj_job_{job.job_id}"
                )
                if rq_job:
                    if rq_job.is_finished:
                        job.status = "success"
                        job.completed_at = timezone.now()
                        job.save(update_fields=["status", "completed_at"])
                    elif rq_job.is_failed:
                        job.status = "failed"
                        job.error_message = str(rq_job.exc_info)
                        job.completed_at = timezone.now()
                        job.save(
                            update_fields=["status", "error_message", "completed_at"]
                        )
            except Exception as e:
                logger.warning(f"Could not fetch RQ job status: {e}")

        return Response(DataProcessingJobSerializer(job).data)
