from django.contrib import admin
from django.utils import timezone
from .models import (
    Season, Conference, Team, TeamSeasonStats,
    TeamExternalId, Game, TeamGameStats, ScoringEvent,
    TeamSeasonMetrics, TeamSeasonRatings, DataProcessingJob, PipelineConfig
)


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ['year', 'display_name', 'is_current', 'created_at']
    list_filter = ['is_current']
    search_fields = ['display_name']


@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']
    search_fields = ['code', 'name']


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'logo_url']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(TeamSeasonStats)
class TeamSeasonStatsAdmin(admin.ModelAdmin):
    list_display = ['team', 'season', 'rank', 'record', 'adj_em', 'conference']
    list_filter = ['season', 'conference', 'has_kenpom', 'has_torvik']
    search_fields = ['team__name']
    readonly_fields = ['efg_margin', 'tov_edge', 'reb_edge', 'ftr_margin', 'last_updated', 'created_at']



# ==================== GAME LOG PIPELINE ADMINS ====================


@admin.register(TeamExternalId)
class TeamExternalIdAdmin(admin.ModelAdmin):
    list_display = ['team', 'source', 'external_id', 'external_name', 'confidence', 'is_manual_override']
    list_filter = ['source', 'is_manual_override']
    search_fields = ['team__name', 'external_name', 'external_id']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['game_date', 'away_team', 'home_team', 'away_score', 'home_score', 'status', 'neutral_site']
    list_filter = ['season_year', 'status', 'neutral_site', 'game_date']
    search_fields = ['home_team__name', 'away_team__name', 'source_game_id']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'game_date'


@admin.register(TeamGameStats)
class TeamGameStatsAdmin(admin.ModelAdmin):
    list_display = ['game', 'team', 'opponent', 'pts', 'fgm', 'fga', 'reb', 'ast', 'tov']
    list_filter = ['home_away', 'game__game_date']
    search_fields = ['team__name', 'opponent__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ScoringEvent)
class ScoringEventAdmin(admin.ModelAdmin):
    list_display = ['game', 'seq', 'period', 'clock', 'scoring_team', 'points', 'home_score', 'away_score']
    list_filter = ['period', 'points']
    search_fields = ['game__source_game_id', 'scoring_team__name']


@admin.register(TeamSeasonMetrics)
class TeamSeasonMetricsAdmin(admin.ModelAdmin):
    list_display = ['team', 'season', 'games', 'ppg', 'ortg', 'drtg', 'net_rtg', 'kill_shots_pg']
    list_filter = ['season']
    search_fields = ['team__name']
    readonly_fields = ['last_updated']


@admin.register(TeamSeasonRatings)
class TeamSeasonRatingsAdmin(admin.ModelAdmin):
    list_display = ['team', 'season', 'adj_o', 'adj_d', 'adj_em', 'rank_adj_em', 'games_played']
    list_filter = ['season']
    search_fields = ['team__name']
    readonly_fields = ['computed_at']


# ── DataProcessingJob admin actions ───────────────────────────────────────────

def mark_success(modeladmin, request, queryset):
    queryset.update(status="success", completed_at=timezone.now())
mark_success.short_description = "Mark selected jobs as success"

def mark_failed(modeladmin, request, queryset):
    queryset.update(status="failed", completed_at=timezone.now())
mark_failed.short_description = "Mark selected jobs as failed"

def mark_cancelled(modeladmin, request, queryset):
    queryset.update(status="cancelled", completed_at=timezone.now())
mark_cancelled.short_description = "Mark selected jobs as cancelled"

def fix_stuck_running(modeladmin, request, queryset):
    """Force-fail any jobs stuck in running/pending state."""
    count = queryset.filter(status__in=["running", "pending"]).update(
        status="failed",
        completed_at=timezone.now(),
        error_message="Marked failed by admin (process was no longer running).",
    )
    modeladmin.message_user(request, f"Fixed {count} stuck job(s).")
fix_stuck_running.short_description = "Fix stuck running/pending jobs → failed"

def clear_logs(modeladmin, request, queryset):
    queryset.update(logs="", error_message="")
clear_logs.short_description = "Clear logs for selected jobs"


@admin.register(DataProcessingJob)
class DataProcessingJobAdmin(admin.ModelAdmin):
    list_display = ['job_id', 'job_type', 'status', 'progress_percent', 'season', 'started_at', 'duration_seconds', 'created_by']
    list_filter = ['job_type', 'status', 'season']
    search_fields = ['job_id', 'error_message']
    readonly_fields = ['job_id', 'started_at', 'updated_at', 'logs']
    actions = [mark_success, mark_failed, mark_cancelled, fix_stuck_running, clear_logs]

    fieldsets = (
        ('Job Info', {
            'fields': ('job_id', 'job_type', 'status', 'season', 'created_by')
        }),
        ('Progress', {
            'fields': ('progress_percent', 'started_at', 'completed_at', 'duration_seconds')
        }),
        ('Parameters', {
            'fields': ('parameters',),
            'classes': ('collapse',)
        }),
        ('Logs & Errors', {
            'fields': ('logs', 'error_message'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # Allow deleting any job that isn't actively running
        if obj is None:
            return True
        return not obj.is_running


@admin.register(PipelineConfig)
class PipelineConfigAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Adjusted Ratings", {
            "fields": (
                "adj_ratings_iterations",
                "adj_ratings_convergence",
                "adj_ratings_shrinkage_floor",
                "adj_ratings_shrinkage_ceiling",
                "adj_ratings_shrinkage_decay",
            ),
        }),
        ("Adjusted Four Factors", {
            "fields": (
                "adj_ff_iterations",
                "adj_ff_convergence",
                "adj_ff_shrinkage_floor",
                "adj_ff_shrinkage_ceiling",
                "adj_ff_shrinkage_decay",
            ),
        }),
        ("Four Factor Index Weights", {
            "description": "Weights must sum to 1.0. Defaults are derived from regression training.",
            "fields": (
                "ffi_weight_efg",
                "ffi_weight_tov",
                "ffi_weight_reb",
                "ffi_weight_ftr",
                "ffi_scale_midpoint",
                "ffi_scale_multiplier",
            ),
        }),
        ("Strength of Record", {
            "fields": (
                "sor_trials",
                "sor_baseline_rank_min",
                "sor_baseline_rank_max",
                "sor_fallback_rank_min",
                "sor_fallback_rank_max",
            ),
        }),
        ("WAB / Game Value", {
            "fields": ("wab_bubble_rank",),
        }),
        ("Strength of Schedule", {
            "fields": (
                "sos_baseline_adjem",
                "sos_logistic_sigma",
                "sos_home_advantage",
                "sos_away_penalty",
            ),
        }),
        ("Shared Fallbacks", {
            "description": (
                "Used when the corresponding NationalAverages values have not been computed yet "
                "(e.g. on the very first pipeline run). Updated automatically after each run."
            ),
            "fields": (
                "fallback_hca",
                "fallback_sigma",
                "fallback_avg_ortg",
            ),
        }),
    )

    def has_add_permission(self, request):
        return not PipelineConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# Customize admin site branding
admin.site.site_header = "CBB Analytics Admin"
admin.site.site_title = "CBB Analytics"
admin.site.index_title = "Data Management & Analytics"
