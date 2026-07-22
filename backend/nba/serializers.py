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
    TeamSeasonOutlook,
    TeamOutseasonMove,
    ProjectedStarter,
    NBAProjectedRosterSlot,
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
            "peak_bpr", "career_bpr",
        ]


class NBAPlayerSeasonStatsSerializer(serializers.ModelSerializer):
    player_name = serializers.CharField(source="player.name", read_only=True)
    player_id = serializers.IntegerField(source="player.player_id", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True, allow_null=True)
    team_slug = serializers.CharField(source="team.slug", read_only=True, allow_null=True)
    season_display = serializers.CharField(source="season.display_name", read_only=True)

    # RAPM aliases — expose baseline RAPM under display-friendly names
    rapm_o = serializers.FloatField(source="baseline_obpr", read_only=True, allow_null=True)
    rapm_d = serializers.FloatField(source="baseline_dbpr", read_only=True, allow_null=True)

    # Replacement-adjusted BPR — computed at serialization time, never stored
    # Replacement level = BPR -2.0 (freely available player, industry standard)
    # Displayed as 0 = replacement, positive = above replacement
    bpr_replacement_adjusted  = serializers.SerializerMethodField()
    obpr_replacement_adjusted = serializers.SerializerMethodField()
    dbpr_replacement_adjusted = serializers.SerializerMethodField()

    def get_bpr_replacement_adjusted(self, obj) -> float | None:
        return round(obj.bpr + 2.0, 3) if obj.bpr is not None else None

    def get_obpr_replacement_adjusted(self, obj) -> float | None:
        return round(obj.obpr + 1.0, 3) if obj.obpr is not None else None

    def get_dbpr_replacement_adjusted(self, obj) -> float | None:
        return round(obj.dbpr + 1.0, 3) if obj.dbpr is not None else None

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
            # Final BPR (prior-informed RAPM — displayed)
            "obpr", "dbpr", "bpr",
            # Replacement-adjusted BPR — 0 = replacement level, computed at serialization
            "bpr_replacement_adjusted", "obpr_replacement_adjusted", "dbpr_replacement_adjusted",
            # Wins above replacement — derived at compute time from BPR + playing time
            "wins_added",
            # Box BPR (intermediate — not displayed directly)
            "box_obpr", "box_dbpr", "box_bpr", "nba_archetype",
            # Baseline RAPM (raw, no prior) — also exposed as rapm_o/rapm_d aliases
            "baseline_obpr", "baseline_dbpr",
            "rapm_o", "rapm_d",
            "bpr_last_updated",
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


# ─────────────────────────────────────────────────────────────────────────────
# Season Outlook serializers
# ─────────────────────────────────────────────────────────────────────────────


class TeamOutseasonMoveSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamOutseasonMove
        fields = [
            "id", "move_type", "player_name", "detail", "impact_rating",
            "round_number", "overall_pick", "mps_score",
        ]


class ProjectedStarterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectedStarter
        fields = [
            "id", "position", "player_name", "position_order",
            "role_note", "bpr_rating", "key_question",
        ]


class NBAProjectedRosterSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = NBAProjectedRosterSlot
        fields = [
            "id", "player_name", "position", "archetype", "age",
            "acquisition_type", "confidence",
            "projected_obpr", "projected_dbpr", "projected_bpr",
            "projected_minutes_share", "projected_wins_added",
        ]


class TeamSeasonOutlookListSerializer(serializers.ModelSerializer):
    league_rank = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = TeamSeasonOutlook
        fields = [
            "team_name", "team_abbr", "team_slug", "conference",
            "primary_color", "secondary_color", "logo_url",
            "wins", "losses",
            "adj_offensive_rating", "adj_defensive_rating", "adj_net_rating",
            "ffi", "outlook_tier",
            "projected_wins", "projected_losses", "projected_adj_net",
            "projected_adj_o", "projected_adj_d",
            "projected_floor_wins", "projected_ceil_wins",
            "continuity_score", "weighted_effective_age", "top2_bpr_concentration",
            "season_headline",
            "league_rank",
        ]

    def get_league_rank(self, obj) -> int:
        # Phase 7 item 9: rank map precomputed by the view (one pass) — the
        # model property issues a COUNT query per row (N+1 across 30 teams).
        ranks = self.context.get("rank_by_slug")
        if ranks is not None:
            return ranks.get(obj.team_slug, 0)
        return obj.league_rank

    def get_logo_url(self, obj) -> str | None:
        # Phase 7 item 9: logo map from the view (single query) — the old
        # per-row NBATeam lookup was the logo N+1.
        logos = self.context.get("logo_by_abbr")
        if logos is not None:
            return logos.get(obj.team_abbr)
        return (
            NBATeam.objects.filter(abbreviation=obj.team_abbr)
            .values_list("logo_url", flat=True)
            .first()
        )


class TeamSeasonOutlookDetailSerializer(serializers.ModelSerializer):
    offseason_moves = TeamOutseasonMoveSerializer(many=True, read_only=True)
    projected_starters = ProjectedStarterSerializer(many=True, read_only=True)
    projected_roster_slots = NBAProjectedRosterSlotSerializer(many=True, read_only=True)
    development_watch = serializers.SerializerMethodField()
    league_rank = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = TeamSeasonOutlook
        fields = [
            # Identity
            "team_name", "team_abbr", "team_slug", "conference",
            "primary_color", "secondary_color", "logo_url",
            # Prior season
            "wins", "losses",
            "adj_offensive_rating", "adj_defensive_rating", "adj_net_rating",
            "ffi", "pace",
            "efg_pct", "opp_efg_pct", "tov_pct", "opp_tov_pct",
            "oreb_pct", "opp_oreb_pct", "fta_rate", "opp_fta_rate",
            # Projections
            "projected_wins", "projected_losses", "projected_adj_net",
            "projected_adj_o", "projected_adj_d",
            "projected_floor_wins", "projected_ceil_wins",
            # Roster construction metrics
            "continuity_score", "weighted_effective_age", "top2_bpr_concentration",
            # Cap
            "cap_total_salary", "cap_status_tier",
            # Editorial
            "outlook_tier", "season_headline", "macfax_take",
            "development_spotlight_player", "development_spotlight_text",
            "season_defining_variable",
            # Relations
            "offseason_moves", "projected_starters", "projected_roster_slots",
            "development_watch", "league_rank",
        ]

    def get_development_watch(self, obj) -> list:
        from django.db.models import Q

        slots = list(
            obj.projected_roster_slots.filter(
                Q(age__lte=25) | Q(acquisition_type="drafted")
            ).order_by("-projected_minutes_share")
        )

        draft_moves = {
            m.player_name.lower(): m
            for m in obj.offseason_moves.filter(move_type="drafted")
        }

        drafted_entries: list = []
        under25_entries: list = []
        seen: set = set()

        for slot in slots:
            name_lower = slot.player_name.lower()
            if name_lower in seen:
                continue
            seen.add(name_lower)

            move = draft_moves.get(name_lower)
            entry = {
                "player_name": slot.player_name,
                "age": slot.age,
                "acquisition_type": slot.acquisition_type,
                "projected_bpr": slot.projected_bpr,
                "projected_minutes_share": slot.projected_minutes_share,
                "archetype": slot.archetype,
                "mps_score": move.mps_score if move else None,
                "round_number": move.round_number if move else None,
                "overall_pick": move.overall_pick if move else None,
            }

            if slot.acquisition_type == "drafted":
                drafted_entries.append(entry)
            else:
                under25_entries.append(entry)

        drafted_entries.sort(key=lambda e: e["overall_pick"] or 999)
        under25_entries.sort(key=lambda e: -(e["projected_bpr"] or -99))

        return drafted_entries + under25_entries

    def get_league_rank(self, obj) -> int:
        return obj.league_rank

    def get_logo_url(self, obj) -> str | None:
        return (
            NBATeam.objects.filter(abbreviation=obj.team_abbr)
            .values_list("logo_url", flat=True)
            .first()
        )
