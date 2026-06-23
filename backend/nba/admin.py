"""
NBA admin registration — macfax NBA app
"""

from django.contrib import admin
from .models import (
    NBASeason,
    NBATeam,
    NBAGame,
    NBATeamGameStats,
    NBAPlayer,
    NBAPlayerGameStats,
    NBATeamSeasonRatings,
    TeamSeasonOutlook,
    TeamOutseasonMove,
    ProjectedStarter,
)


@admin.register(NBASeason)
class NBASeasonAdmin(admin.ModelAdmin):
    list_display = ["display_name", "year", "is_current"]
    list_editable = ["is_current"]


@admin.register(NBATeam)
class NBATeamAdmin(admin.ModelAdmin):
    list_display = ["name", "abbreviation", "conference", "division", "nba_team_id"]
    search_fields = ["name", "abbreviation", "slug"]
    list_filter = ["conference", "division"]


@admin.register(NBAGame)
class NBAGameAdmin(admin.ModelAdmin):
    list_display = [
        "game_id", "date", "away_team", "home_team",
        "away_score", "home_score", "season_type", "competition",
        "counts_toward_regular_season", "box_score_synced",
    ]
    list_filter = ["season_type", "competition", "season", "counts_toward_regular_season"]
    search_fields = ["game_id"]
    date_hierarchy = "date"


@admin.register(NBATeamGameStats)
class NBATeamGameStatsAdmin(admin.ModelAdmin):
    list_display = ["game", "team", "is_home", "pts", "opp_pts", "poss", "raw_ortg", "raw_drtg"]
    list_filter = ["is_home"]


@admin.register(NBAPlayer)
class NBAPlayerAdmin(admin.ModelAdmin):
    list_display = ["name", "player_id", "is_active", "current_team"]
    search_fields = ["name"]
    list_filter = ["is_active", "current_team"]


@admin.register(NBAPlayerGameStats)
class NBAPlayerGameStatsAdmin(admin.ModelAdmin):
    list_display = ["player", "game", "team", "seconds_played", "pts", "reb", "ast"]


@admin.register(NBATeamSeasonRatings)
class NBATeamSeasonRatingsAdmin(admin.ModelAdmin):
    list_display = [
        "team", "season", "games", "adj_off", "adj_def", "adj_net", "pace", "ffi",
        "rank_adj_net",
    ]
    list_filter = ["season"]
    search_fields = ["team__name"]


# ── Season Outlook admin ──────────────────────────────────────────────────────

class TeamOutseasonMoveInline(admin.TabularInline):
    model = TeamOutseasonMove
    extra = 1
    fields = ["move_type", "player_name", "detail", "impact_rating"]


class ProjectedStarterInline(admin.TabularInline):
    model = ProjectedStarter
    extra = 0
    fields = ["position_order", "position", "player_name", "bpr_rating", "role_note", "key_question"]


@admin.register(TeamSeasonOutlook)
class TeamSeasonOutlookAdmin(admin.ModelAdmin):
    list_display = [
        "team_name", "conference", "wins", "losses",
        "adj_net_rating", "ffi", "outlook_tier", "updated_at",
    ]
    list_filter = ["conference", "outlook_tier"]
    list_editable = ["outlook_tier"]
    search_fields = ["team_name", "team_abbr"]
    inlines = [TeamOutseasonMoveInline, ProjectedStarterInline]
    fieldsets = [
        ("Identity", {
            "fields": [
                "team_name", "team_abbr", "team_slug",
                "conference", "primary_color", "secondary_color",
            ],
        }),
        ("2025-26 Results", {
            "fields": [
                "wins", "losses",
                "adj_offensive_rating", "adj_defensive_rating", "adj_net_rating",
                "ffi", "pace",
                "efg_pct", "opp_efg_pct",
                "tov_pct", "opp_tov_pct",
                "oreb_pct", "opp_oreb_pct",
                "fta_rate", "opp_fta_rate",
            ],
        }),
        ("2026-27 Outlook", {
            "fields": [
                "projected_wins", "projected_losses",
                "projected_adj_net", "outlook_tier",
            ],
        }),
        ("Editorial", {
            "fields": [
                "season_headline", "macfax_take",
                "development_spotlight_player", "development_spotlight_text",
                "season_defining_variable",
            ],
        }),
    ]
