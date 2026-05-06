from django.contrib import admin

from .models import PredictionSnapshot, GameValidationResult, ValidationSummary


@admin.register(PredictionSnapshot)
class PredictionSnapshotAdmin(admin.ModelAdmin):
    list_display = ['game', 'season_year', 'model_version', 'is_locked', 'predicted_at', 'locked_at']
    list_filter = ['season_year', 'model_version', 'is_locked']
    readonly_fields = ['predicted_at', 'locked_at', 'created_at']
    search_fields = ['home_team__name', 'away_team__name']
    ordering = ['-predicted_at']


@admin.register(GameValidationResult)
class GameValidationResultAdmin(admin.ModelAdmin):
    list_display = ['game', 'season_year', 'winner_correct', 'margin_abs_error', 'brier_score', 'evaluated_at']
    list_filter = ['season_year', 'winner_correct']
    readonly_fields = ['evaluated_at']
    ordering = ['-evaluated_at']


@admin.register(ValidationSummary)
class ValidationSummaryAdmin(admin.ModelAdmin):
    list_display = ['season_year', 'period_type', 'games_evaluated', 'winner_accuracy', 'spread_mae', 'brier_score', 'updated_at']
    list_filter = ['season_year', 'period_type', 'model_version']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-season_year', 'period_type']
