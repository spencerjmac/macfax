"""
NBA DRF Serializers — macfax NBA app
"""

from rest_framework import serializers
from .models import (
    NBASeason,
    NBATeam,
    NBAGame,
    NBATeamGameStats,
    NBAPlayer,
    NBAPlayerGameStats,
    NBAPlayerSeasonStats,
    NBATeamSeasonRatings,
    NBAModelCalibration,
)


class NBASeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = NBASeason
        fields = ["id", "year", "display_name", "is_current"]


class NBATeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = NBATeam
        fields = [
            "id", "nba_team_id", "slug", "name", "abbreviation",
            "city", "conference", "division", "logo_url",
        ]


class NBAGameSerializer(serializers.ModelSerializer):
    home_team_abbr = serializers.CharField(source="home_team.abbreviation", read_only=True)
    away_team_abbr = serializers.CharField(source="away_team.abbreviation", read_only=True)
    home_team_slug = serializers.CharField(source="home_team.slug", read_only=True)
    away_team_slug = serializers.CharField(source="away_team.slug", read_only=True)

    class Meta:
        model = NBAGame
        fields = [
            "id", "game_id", "date", "season_type", "competition",
            "counts_toward_regular_season", "status",
            "home_team", "home_team_abbr", "home_team_slug", "home_score",
            "away_team", "away_team_abbr", "away_team_slug", "away_score",
            "rest_days_home", "rest_days_away", "home_b2b", "away_b2b",
            "box_score_synced",
        ]


class NBATeamGameStatsSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.name", read_only=True)
    team_abbreviation = serializers.CharField(source="team.abbreviation", read_only=True)

    class Meta:
        model = NBATeamGameStats
        fields = [
            "id", "game", "team", "team_name", "team_abbreviation", "is_home",
            "pts", "opp_pts",
            "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "tov",
            "poss", "raw_ortg", "raw_drtg", "adj_ortg", "adj_drtg",
        ]


class NBAPlayerSerializer(serializers.ModelSerializer):
    current_team_name = serializers.CharField(
        source="current_team.name", read_only=True, allow_null=True
    )
    current_team_slug = serializers.CharField(
        source="current_team.slug", read_only=True, allow_null=True
    )

    class Meta:
        model = NBAPlayer
        fields = [
            "id", "player_id", "name", "is_active",
            "current_team", "current_team_name", "current_team_slug",
        ]


class NBAPlayerSeasonStatsSerializer(serializers.ModelSerializer):
    player_name = serializers.CharField(source="player.name", read_only=True)
    player_id = serializers.IntegerField(source="player.player_id", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True, allow_null=True)
    team_slug = serializers.CharField(source="team.slug", read_only=True, allow_null=True)
    season_display = serializers.CharField(source="season.display_name", read_only=True)

    class Meta:
        model = NBAPlayerSeasonStats
        fields = [
            "id", "player", "player_id", "player_name",
            "team", "team_name", "team_slug", "season", "season_display",
            # Traditional box score
            "gp", "mpg",
            "pts", "reb", "ast", "stl", "blk", "tov", "plus_minus",
            "fg_pct", "fg3_pct", "ft_pct", "fga_pg", "fg3a_pg",
            "oreb_pg", "dreb_pg", "fta_pg", "ftm_pg",
            # Advanced efficiency
            "efg_pct", "ts_pct", "usg_pct",
            "oreb_pct", "dreb_pct", "ast_pct", "tov_pct", "ast_to", "pie",
            # Raw on-court ratings
            "on_court_ortg", "on_court_drtg", "on_court_net", "on_court_poss",
            # Bayesian-stabilised on-court (NBA.com E_*)
            "on_court_adj_o", "on_court_adj_d", "on_court_adj_em",
            # MPIR
            "mpir", "o_mpir", "d_mpir",
            # Defense rates
            "stl_pct", "blk_pct",
            "updated_at",
        ]


class NBATeamSeasonRatingsSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.name", read_only=True)
    team_slug = serializers.CharField(source="team.slug", read_only=True)
    team_abbreviation = serializers.CharField(source="team.abbreviation", read_only=True)
    team_logo_url = serializers.CharField(
        source="team.logo_url", read_only=True, allow_null=True
    )
    team_conference = serializers.CharField(source="team.conference", read_only=True)
    season_display = serializers.CharField(source="season.display_name", read_only=True)

    class Meta:
        model = NBATeamSeasonRatings
        fields = [
            "id", "team", "team_name", "team_slug", "team_abbreviation",
            "team_logo_url", "team_conference", "season", "season_display",
            "games", "adj_off", "adj_def", "adj_net", "pace",
            "efg_pct", "opp_efg_pct", "tov_rate", "opp_tov_rate",
            "oreb_pct", "opp_oreb_pct", "fta_rate", "opp_fta_rate",
            "efg_margin", "tov_edge", "oreb_edge", "fta_margin",
            "ffi", "rank_adj_net", "rank_ffi", "updated_at",
        ]


class NBAModelCalibrationSerializer(serializers.ModelSerializer):
    season_display = serializers.CharField(source="season.display_name", read_only=True)
    season_year = serializers.IntegerField(source="season.year", read_only=True)

    class Meta:
        model = NBAModelCalibration
        fields = [
            "id", "season", "season_display", "season_year", "computed_at",
            # Analysis 1
            "games_predicted", "correct_predictions",
            "straight_up_accuracy", "brier_score", "log_loss",
            # Analysis 2+3
            "ols_games", "ols_r_squared",
            "empirical_hca", "configured_hca", "ols_model_scale",
            "empirical_home_b2b_penalty", "empirical_away_b2b_penalty",
            "configured_b2b_penalty",
            # Analysis 4
            "ffi_teams_used", "ffi_adj_net_r_squared",
            "ffi_proposed_weight_efg", "ffi_proposed_weight_tov",
            "ffi_proposed_weight_oreb", "ffi_proposed_weight_fta",
            "ffi_current_weight_efg", "ffi_current_weight_tov",
            "ffi_current_weight_oreb", "ffi_current_weight_fta",
        ]
