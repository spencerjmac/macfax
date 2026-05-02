"""
Scenario API serializers — request validation and response formatting.
"""

from __future__ import annotations

from rest_framework import serializers


# ── Request serializers ───────────────────────────────────────────────────────

class ManualPlayerSpecSerializer(serializers.Serializer):
    display_name     = serializers.CharField(max_length=200)
    position         = serializers.CharField(max_length=5)
    recruitment_type = serializers.ChoiceField(choices=["returner", "transfer", "newcomer"])

    projected_obpr    = serializers.FloatField(required=False, allow_null=True)
    projected_dbpr    = serializers.FloatField(required=False, allow_null=True)

    national_rank     = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    stars             = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=5)
    composite_score   = serializers.FloatField(required=False, allow_null=True)

    placeholder_key   = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=64)

    conf_group    = serializers.ChoiceField(
        choices=["power", "high_mid", "mid_major", "national"],
        required=False, default="power",
    )
    quality_tier  = serializers.ChoiceField(
        choices=["elite", "all_conference", "starter", "rotation", "bench"],
        required=False, default="starter",
    )
    intended_mpg  = serializers.FloatField(required=False, allow_null=True, min_value=0.0, max_value=40.0)
    is_juco       = serializers.BooleanField(required=False, default=False)
    slot_id       = serializers.CharField(required=False, allow_blank=True, default="")


class ScenarioSlotSerializer(serializers.Serializer):
    slot_type     = serializers.ChoiceField(choices=["db_player", "manual_player"])
    projection_id = serializers.IntegerField(required=False, allow_null=True)
    manual_spec   = ManualPlayerSpecSerializer(required=False, allow_null=True)

    def validate(self, data):
        if data["slot_type"] == "db_player" and not data.get("projection_id"):
            raise serializers.ValidationError(
                "projection_id is required for slot_type='db_player'."
            )
        if data["slot_type"] == "manual_player" and not data.get("manual_spec"):
            raise serializers.ValidationError(
                "manual_spec is required for slot_type='manual_player'."
            )
        return data


class ScenarioRosterRequestSerializer(serializers.Serializer):
    team_id               = serializers.IntegerField()
    season_year           = serializers.IntegerField()
    slots                 = ScenarioSlotSerializer(many=True, min_length=1, max_length=20)
    compare_to_baseline   = serializers.BooleanField(required=False, default=False)


# ── Response serializers ──────────────────────────────────────────────────────

class ScenarioPlayerResultSerializer(serializers.Serializer):
    player_id            = serializers.IntegerField()
    display_name         = serializers.CharField()
    slot_id              = serializers.CharField()
    is_manual            = serializers.BooleanField()
    source_tier          = serializers.CharField()
    display_label        = serializers.CharField()
    role_bucket          = serializers.CharField()
    rotation_rank        = serializers.IntegerField()
    minutes_share        = serializers.FloatField()
    mpg                  = serializers.FloatField()
    is_overridden        = serializers.BooleanField()
    projected_obpr       = serializers.FloatField()
    projected_dbpr       = serializers.FloatField()
    projected_bpr        = serializers.FloatField()
    projection_uncertainty = serializers.FloatField()
    recruitment_type     = serializers.CharField()
    resolution_method    = serializers.CharField()
    national_rank        = serializers.IntegerField(allow_null=True)
    stars                = serializers.IntegerField(allow_null=True)
    is_juco              = serializers.BooleanField()
    archetypes           = serializers.ListField(child=serializers.CharField())
    competition_warning  = serializers.CharField(allow_null=True, allow_blank=True, required=False)


class ScenarioResultSerializer(serializers.Serializer):
    team_id              = serializers.IntegerField()
    season_year          = serializers.IntegerField()
    projected_season_year = serializers.IntegerField()
    players              = ScenarioPlayerResultSerializer(many=True)

    projected_adj_o      = serializers.FloatField()
    projected_adj_d      = serializers.FloatField()
    projected_adj_em     = serializers.FloatField()
    projected_adj_em_low = serializers.FloatField()
    projected_adj_em_high = serializers.FloatField()
    projected_national_rank   = serializers.IntegerField(allow_null=True)
    national_rank_range_low   = serializers.IntegerField(allow_null=True)
    national_rank_range_high  = serializers.IntegerField(allow_null=True)
    rank_display              = serializers.CharField()
    projected_offense_rank    = serializers.IntegerField(allow_null=True)
    offense_rank_range_low    = serializers.IntegerField(allow_null=True)
    offense_rank_range_high   = serializers.IntegerField(allow_null=True)
    off_rank_display          = serializers.CharField()
    projected_defense_rank    = serializers.IntegerField(allow_null=True)
    defense_rank_range_low    = serializers.IntegerField(allow_null=True)
    defense_rank_range_high   = serializers.IntegerField(allow_null=True)
    def_rank_display          = serializers.CharField()
    team_projection_uncertainty = serializers.FloatField()
    continuity_score     = serializers.FloatField()
    transfer_dependence_score = serializers.FloatField()

    offensive_fit_score  = serializers.FloatField()
    defensive_fit_score  = serializers.FloatField()
    overall_fit_score    = serializers.FloatField()
    off_subcomponents    = serializers.DictField()
    def_subcomponents    = serializers.DictField()
    top_off_strengths    = serializers.ListField(child=serializers.CharField())
    top_off_weaknesses   = serializers.ListField(child=serializers.CharField())
    top_def_strengths    = serializers.ListField(child=serializers.CharField())
    top_def_weaknesses   = serializers.ListField(child=serializers.CharField())
    structural_penalties = serializers.DictField()

    n_manual_players     = serializers.IntegerField()
    n_db_players         = serializers.IntegerField()
    has_mpg_overrides    = serializers.BooleanField()
    computed_at          = serializers.CharField()

    is_first_year_coach  = serializers.BooleanField(required=False, default=False)
    baseline_adj_em      = serializers.FloatField(allow_null=True, required=False)
    adj_em_delta         = serializers.FloatField(allow_null=True, required=False)


# ── Snapshot serializers ──────────────────────────────────────────────────────

class ScenarioSaveSerializer(serializers.Serializer):
    name              = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    scenario_request  = serializers.DictField()
    scenario_result   = serializers.DictField()


class ScenarioSnapshotListSerializer(serializers.Serializer):
    id                    = serializers.IntegerField()
    name                  = serializers.CharField()
    team_id               = serializers.IntegerField(source="team_id")
    from_season_year      = serializers.IntegerField(source="from_season.year")
    projected_season_year = serializers.IntegerField()
    projected_adj_em      = serializers.FloatField(allow_null=True)
    projected_national_rank = serializers.IntegerField(allow_null=True)
    n_manual_players      = serializers.IntegerField()
    created_at            = serializers.DateTimeField()
    updated_at            = serializers.DateTimeField()


class ScenarioSnapshotDetailSerializer(serializers.Serializer):
    id                    = serializers.IntegerField()
    name                  = serializers.CharField()
    team_id               = serializers.IntegerField(source="team_id")
    from_season_year      = serializers.IntegerField(source="from_season.year")
    projected_season_year = serializers.IntegerField()
    projected_adj_em      = serializers.FloatField(allow_null=True)
    projected_national_rank = serializers.IntegerField(allow_null=True)
    n_manual_players      = serializers.IntegerField()
    scenario_input        = serializers.DictField()
    scenario_result       = serializers.DictField()
    created_at            = serializers.DateTimeField()
    updated_at            = serializers.DateTimeField()
