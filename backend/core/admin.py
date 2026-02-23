from django.contrib import admin
from .models import (
    Season, Conference, Team, TeamSeasonStats, DataIngestionRun,
    TeamExternalId, Game, TeamGameStats, ScoringEvent,
    TeamSeasonMetrics, TeamSeasonRatings
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


@admin.register(DataIngestionRun)
class DataIngestionRunAdmin(admin.ModelAdmin):
    list_display = ['season', 'status', 'teams_ingested', 'started_at', 'completed_at']
    list_filter = ['status', 'season']
    readonly_fields = ['started_at']


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
