# Generated migration for DataProcessingJob model
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_add_sos_rank"),
    ]

    operations = [
        migrations.CreateModel(
            name="DataProcessingJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "job_id",
                    models.CharField(
                        help_text="Unique job identifier (from RQ)",
                        max_length=50,
                        unique=True,
                    ),
                ),
                (
                    "job_type",
                    models.CharField(
                        choices=[
                            ("update_all", "Full Data Update"),
                            ("ingest_gamelogs", "Ingest Game Logs"),
                            ("compute_metrics", "Compute Metrics"),
                        ],
                        help_text="Type of data processing job",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="pending",
                        help_text="Current job status",
                        max_length=20,
                    ),
                ),
                (
                    "progress_percent",
                    models.IntegerField(
                        default=0, help_text="Completion percentage (0-100)"
                    ),
                ),
                (
                    "parameters",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Additional job parameters as JSON",
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(
                        auto_now_add=True, help_text="When job started"
                    ),
                ),
                (
                    "completed_at",
                    models.DateTimeField(
                        blank=True, null=True, help_text="When job completed"
                    ),
                ),
                (
                    "duration_seconds",
                    models.IntegerField(
                        blank=True,
                        help_text="Total execution time in seconds",
                        null=True,
                    ),
                ),
                (
                    "logs",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Job execution logs (stdout + stderr)",
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True, default="", help_text="Error message if job failed"
                    ),
                ),
                (
                    "created_by",
                    models.CharField(
                        default="system",
                        help_text="User or system that triggered job",
                        max_length=100,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "season",
                    models.ForeignKey(
                        blank=True,
                        help_text="Season for this job (if applicable)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="core.season",
                    ),
                ),
            ],
            options={
                "verbose_name": "Data Processing Job",
                "verbose_name_plural": "Data Processing Jobs",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="dataprocessingjob",
            index=models.Index(fields=["job_id"], name="core_datapr_job_id_idx"),
        ),
        migrations.AddIndex(
            model_name="dataprocessingjob",
            index=models.Index(fields=["status"], name="core_datapr_status_idx"),
        ),
        migrations.AddIndex(
            model_name="dataprocessingjob",
            index=models.Index(
                fields=["season", "-started_at"], name="core_datapr_season_idx"
            ),
        ),
    ]
