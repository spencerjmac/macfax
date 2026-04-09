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
