from django.db import models

from ncaa.models import Game, Team


MATCHUP_SNAPSHOT_VERSION = "1.0"

PERIOD_TYPE_CHOICES = [
    ('season', 'Full Season'),
    ('last_7', 'Last 7 Days'),
    ('last_30', 'Last 30 Days'),
    ('all_time', 'All Time'),
]


class PredictionSnapshot(models.Model):
    """
    Locked pregame prediction for a single game.
    Created before tip-off; never modified after locking.
    """
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='prediction_snapshots')
    season_year = models.IntegerField(db_index=True)
    model_version = models.CharField(max_length=50, default=MATCHUP_SNAPSHOT_VERSION)
    snapshot_type = models.CharField(max_length=30, default='pregame')

    predicted_at = models.DateTimeField(auto_now_add=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='+')
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='+')

    # Prediction outputs
    projected_home_score = models.FloatField()
    projected_away_score = models.FloatField()
    projected_home_margin = models.FloatField()
    projected_total = models.FloatField()
    home_win_probability = models.FloatField()
    away_win_probability = models.FloatField()
    predicted_winner = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )

    # Rating context stored at snapshot time for auditability
    home_adj_o = models.FloatField(null=True, blank=True)
    home_adj_d = models.FloatField(null=True, blank=True)
    away_adj_o = models.FloatField(null=True, blank=True)
    away_adj_d = models.FloatField(null=True, blank=True)
    nat_avg_ortg = models.FloatField(null=True, blank=True)
    hca_points = models.FloatField(null=True, blank=True)
    sigma_used = models.FloatField(null=True, blank=True)

    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['game', 'model_version'],
                name='unique_snapshot_per_game_version',
            )
        ]
        indexes = [
            models.Index(fields=['season_year', 'is_locked']),
            models.Index(fields=['season_year', 'model_version']),
        ]

    def __str__(self):
        return f"Snapshot: {self.away_team} @ {self.home_team} ({self.game.game_date}) v{self.model_version}"


class GameValidationResult(models.Model):
    """
    Computed accuracy metrics for one completed game with a locked PredictionSnapshot.
    """
    prediction_snapshot = models.OneToOneField(
        PredictionSnapshot, on_delete=models.CASCADE, related_name='validation_result'
    )
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='validation_results')
    season_year = models.IntegerField(db_index=True)

    # Actuals
    actual_home_score = models.IntegerField()
    actual_away_score = models.IntegerField()
    actual_home_margin = models.IntegerField()
    actual_total = models.IntegerField()

    # Winner accuracy
    winner_correct = models.BooleanField()

    # Margin accuracy
    margin_error = models.FloatField()      # projected − actual (signed)
    margin_abs_error = models.FloatField()

    # Score accuracy
    home_score_error = models.FloatField()
    away_score_error = models.FloatField()
    home_score_abs_error = models.FloatField()
    away_score_abs_error = models.FloatField()
    avg_score_abs_error = models.FloatField()  # (home_abs + away_abs) / 2

    # Total accuracy
    total_error = models.FloatField()
    total_abs_error = models.FloatField()

    # Probability calibration
    brier_score = models.FloatField()       # (p_home − actual_outcome)^2
    log_loss = models.FloatField(null=True, blank=True)  # −log(p_correct)

    # Upset tracking
    predicted_upset = models.BooleanField(default=False)
    actual_upset = models.BooleanField(default=False)
    upset_correct = models.BooleanField(null=True, blank=True)

    evaluated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['season_year']),
            models.Index(fields=['season_year', 'winner_correct']),
        ]

    def __str__(self):
        tick = '✓' if self.winner_correct else '✗'
        return f"Result: {self.game} [{tick}] MAE={self.margin_abs_error:.1f}"


class ValidationSummary(models.Model):
    """
    Aggregated validation metrics for a season/period.
    Recomputed by compute_validation_summaries; upserted on (season_year, model_version, period_type).
    """
    season_year = models.IntegerField(db_index=True)
    model_version = models.CharField(max_length=50)
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    games_evaluated = models.IntegerField(default=0)
    winner_accuracy = models.FloatField(default=0.0)   # 0.0–1.0
    spread_mae = models.FloatField(default=0.0)
    score_mae = models.FloatField(default=0.0)
    total_mae = models.FloatField(default=0.0)
    average_margin_bias = models.FloatField(default=0.0)
    brier_score = models.FloatField(default=0.0)
    log_loss = models.FloatField(null=True, blank=True)

    upset_predictions = models.IntegerField(default=0)
    upset_hits = models.IntegerField(default=0)
    upset_precision = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['season_year', 'model_version', 'period_type'],
                name='unique_validation_summary',
            )
        ]

    def __str__(self):
        return f"Summary {self.season_year} {self.period_type}: {self.winner_accuracy:.1%} ({self.games_evaluated} games)"
