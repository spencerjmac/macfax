"""
Foundational models: Season, Conference, NationalAverages, DataProcessingJob, PipelineConfig
"""

from django.db import models


class Season(models.Model):
    """Represents a basketball season (e.g., 2025-26)"""

    year = models.IntegerField(
        unique=True, help_text="Ending year (2026 for 2025-26 season)"
    )
    display_name = models.CharField(max_length=20, help_text="Human-readable name")
    is_current = models.BooleanField(
        default=False, help_text="Is this the active season?"
    )
    selection_sunday_date = models.DateField(
        null=True, blank=True, help_text="Date of Selection Sunday for this season"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year"]

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        # Auto-set is_current to False for all others if this is current
        if self.is_current:
            Season.objects.filter(is_current=True).update(is_current=False)
        super().save(*args, **kwargs)


class Conference(models.Model):
    """NCAA conferences"""

    code = models.CharField(max_length=10, unique=True, db_index=True)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class NationalAverages(models.Model):
    """
    National averages for a season (possession-weighted)
    Used for adjusted ratings and adjusted four factors
    """

    season = models.OneToOneField(
        Season, on_delete=models.CASCADE, related_name="national_averages"
    )

    # Basic efficiency
    avg_ortg = models.FloatField(help_text="National average offensive rating")
    avg_pace = models.FloatField(help_text="National average pace")

    # Four Factors averages
    avg_efg = models.FloatField(help_text="National average eFG%")
    avg_tov = models.FloatField(help_text="National average TOV%")
    avg_orb = models.FloatField(help_text="National average ORB%")
    avg_ftr = models.FloatField(help_text="National average FTR")

    # Total possessions (for weighting)
    total_possessions = models.FloatField(
        help_text="Total possessions across all games"
    )
    total_games = models.IntegerField(help_text="Total games in dataset")

    # Matchup prediction parameters
    hca_points = models.FloatField(
        null=True,
        blank=True,
        help_text="Home court advantage in points (estimated from game logs)",
    )
    prediction_sigma = models.FloatField(
        null=True,
        blank=True,
        help_text="Standard deviation of prediction errors (for win probability)",
    )

    # Four factor regression coefficients
    coef_efg = models.FloatField(
        null=True,
        blank=True,
        help_text="Regression coefficient for eFG% edge (points per % edge)",
    )
    coef_tov = models.FloatField(
        null=True,
        blank=True,
        help_text="Regression coefficient for TOV% edge (points per % edge)",
    )
    coef_orb = models.FloatField(
        null=True,
        blank=True,
        help_text="Regression coefficient for ORB% edge (points per % edge)",
    )
    coef_ftr = models.FloatField(
        null=True,
        blank=True,
        help_text="Regression coefficient for FTR edge (points per % edge)",
    )
    coef_intercept = models.FloatField(
        null=True, blank=True, help_text="Regression intercept (baseline margin)"
    )
    coef_r_squared = models.FloatField(
        null=True, blank=True, help_text="R-squared of four factor regression model"
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "National Averages"
        verbose_name_plural = "National Averages"

    def __str__(self):
        return f"{self.season.display_name} National Averages: ORtg={self.avg_ortg:.1f}"


class DataProcessingJob(models.Model):
    """Track background data processing jobs (update_all, ingest_gamelogs, etc.)"""

    JOB_TYPE_CHOICES = [
        ("update_all", "Full Data Update"),
        ("update_ncaa_teams", "NCAA Update Teams"),
        ("update_ncaa_players", "NCAA Update Players"),
        ("update_nba_teams", "NBA Update Teams"),
        ("update_nba_players", "NBA Update Players"),
        ("ingest_gamelogs", "Ingest Game Logs"),
        ("compute_team_metrics", "Compute Team Metrics"),
        ("compute_adjusted_ratings", "Compute Adjusted Ratings"),
        ("compute_four_factor_index", "Compute Four Factor Index"),
        ("fetch_net_rankings", "Fetch NCAA NET Rankings"),
        ("compute_sor", "Compute Strength of Record"),
        ("compute_game_value", "Compute Game Value"),
        ("compute_sos", "Compute Strength of Schedule"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    # Job identification
    job_id = models.CharField(
        max_length=50, unique=True, help_text="Unique job identifier"
    )
    job_type = models.CharField(
        max_length=30, choices=JOB_TYPE_CHOICES, help_text="Type of data processing job"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        help_text="Current job status",
    )
    progress_percent = models.IntegerField(
        default=0, help_text="Completion percentage (0-100)"
    )

    # Job parameters
    season = models.ForeignKey(
        Season,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Season for this job (if applicable)",
    )
    parameters = models.JSONField(
        default=dict, blank=True, help_text="Additional job parameters as JSON"
    )

    # Execution info
    started_at = models.DateTimeField(auto_now_add=True, help_text="When job started")
    completed_at = models.DateTimeField(
        null=True, blank=True, help_text="When job completed"
    )
    duration_seconds = models.IntegerField(
        null=True, blank=True, help_text="Total execution time in seconds"
    )

    # Logs and output
    logs = models.TextField(
        blank=True, default="", help_text="Job execution logs (stdout + stderr)"
    )
    error_message = models.TextField(
        blank=True, default="", help_text="Error message if job failed"
    )

    # Metadata
    created_by = models.CharField(
        max_length=100, default="system", help_text="User or system that triggered job"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Data Processing Job"
        verbose_name_plural = "Data Processing Jobs"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["job_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["season", "-started_at"]),
        ]

    def __str__(self):
        return f"{self.get_job_type_display()} - {self.job_id} ({self.get_status_display()})"

    @property
    def is_running(self):
        """Check if job is currently running"""
        return self.status == "running"

    @property
    def is_complete(self):
        """Check if job is complete (success or failed)"""
        return self.status in ("success", "failed")

    def append_log(self, text):
        """Append text to job logs"""
        if self.logs:
            self.logs += "\n" + text
        else:
            self.logs = text
        self.save(update_fields=["logs"])

    def set_progress(self, percent):
        """Update progress percentage"""
        self.progress_percent = min(100, max(0, percent))
        self.save(update_fields=["progress_percent"])


class PipelineConfig(models.Model):
    """
    Singleton model storing all tunable analytics parameters for the compute pipeline.

    Only one row (pk=1) should ever exist. Use PipelineConfig.get_config() to
    retrieve it (creates with defaults on first access).

    Parameters are grouped into 6 logical sections matching the compute commands
    that consume them.
    """

    # ── Adjusted Ratings ──────────────────────────────────────────────────────
    adj_ratings_iterations = models.IntegerField(
        default=75,
        help_text="Max solver iterations before declaring convergence (compute_adjusted_ratings --iterations)",
    )
    adj_ratings_convergence = models.FloatField(
        default=0.001,
        help_text="Max AdjEM change between iterations to declare convergence",
    )
    adj_ratings_shrinkage_floor = models.IntegerField(
        default=150,
        help_text="Minimum shrinkage constant (possessions) regardless of games played",
    )
    adj_ratings_shrinkage_ceiling = models.IntegerField(
        default=300,
        help_text="Starting/maximum shrinkage constant (possessions)",
    )
    adj_ratings_shrinkage_decay = models.FloatField(
        default=6.25,
        help_text="Shrinkage k drops by this amount per average game played",
    )

    # ── Adjusted Four Factors ─────────────────────────────────────────────────
    adj_ff_iterations = models.IntegerField(
        default=75,
        help_text="Max solver iterations before declaring convergence (compute_adjusted_four_factors --iterations)",
    )
    adj_ff_convergence = models.FloatField(
        default=0.01,
        help_text="Max change (percentage points) in any adjusted four factor stat between iterations to declare convergence",
    )
    adj_ff_shrinkage_floor = models.IntegerField(
        default=150,
        help_text="Minimum shrinkage constant (possessions) regardless of games played",
    )
    adj_ff_shrinkage_ceiling = models.IntegerField(
        default=300,
        help_text="Starting/maximum shrinkage constant (possessions)",
    )
    adj_ff_shrinkage_decay = models.FloatField(
        default=6.25,
        help_text="Shrinkage k drops by this amount per average game played",
    )

    # ── Four Factor Index ─────────────────────────────────────────────────────
    ffi_weight_efg = models.FloatField(
        default=0.47,
        help_text="eFG% margin weight in the FFI composite score",
    )
    ffi_weight_tov = models.FloatField(
        default=0.24,
        help_text="Turnover edge weight in the FFI composite score",
    )
    ffi_weight_reb = models.FloatField(
        default=0.21,
        help_text="Rebounding edge weight in the FFI composite score",
    )
    ffi_weight_ftr = models.FloatField(
        default=0.08,
        help_text="FTR margin weight in the FFI composite score",
    )
    ffi_scale_midpoint = models.IntegerField(
        default=50,
        help_text="FFI output scale midpoint (score = midpoint + multiplier * z)",
    )
    ffi_scale_multiplier = models.IntegerField(
        default=20,
        help_text="FFI z-score scale multiplier",
    )

    # ── Strength of Record ────────────────────────────────────────────────────
    sor_trials = models.IntegerField(
        default=10000,
        help_text="Monte Carlo win-simulation trials (compute_sor --trials)",
    )
    sor_baseline_rank_min = models.IntegerField(
        default=20,
        help_text="Primary SOR baseline: use teams ranked this or better",
    )
    sor_baseline_rank_max = models.IntegerField(
        default=30,
        help_text="Primary SOR baseline: use teams ranked this or worse",
    )
    sor_fallback_rank_min = models.IntegerField(
        default=15,
        help_text="Fallback SOR baseline (when primary range is underpopulated): rank floor",
    )
    sor_fallback_rank_max = models.IntegerField(
        default=35,
        help_text="Fallback SOR baseline (when primary range is underpopulated): rank ceiling",
    )

    # ── WAB / Game Value ──────────────────────────────────────────────────────
    wab_bubble_rank = models.IntegerField(
        default=45,
        help_text="AdjEM rank of the 'bubble team' used as the WAB and game-value baseline",
    )

    # ── Strength of Schedule ──────────────────────────────────────────────────
    sos_baseline_adjem = models.FloatField(
        default=0.0,
        help_text="AdjEM of the 'average D1 team' anchor for the SOS logistic model",
    )
    sos_logistic_sigma = models.FloatField(
        default=10.0,
        help_text="Logistic spread/scale parameter for the SOS win-probability model",
    )
    sos_home_advantage = models.FloatField(
        default=1.5,
        help_text="Points added to the home team's margin in SOS win-probability calculations",
    )
    sos_away_penalty = models.FloatField(
        default=1.5,
        help_text="Points subtracted from the away team's margin in SOS win-probability calculations",
    )

    # ── Shared Fallbacks ──────────────────────────────────────────────────────
    fallback_hca = models.FloatField(
        default=1.85,
        help_text="HCA (points) used when NationalAverages.hca_points has not been computed yet",
    )
    fallback_sigma = models.FloatField(
        default=11.08,
        help_text="Prediction sigma used when NationalAverages.prediction_sigma has not been computed yet",
    )
    fallback_avg_ortg = models.FloatField(
        default=108.0,
        help_text="National average offensive rating used when NationalAverages has not been computed yet",
    )

    class Meta:
        verbose_name = "Pipeline Configuration"
        verbose_name_plural = "Pipeline Configuration"

    def __str__(self):
        return "Pipeline Configuration"

    @classmethod
    def get_config(cls):
        """Return the singleton config row, creating it with defaults if absent."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
