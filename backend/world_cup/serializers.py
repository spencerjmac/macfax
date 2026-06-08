from rest_framework import serializers
from .models import WorldCupTeam


class WorldCupTeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorldCupTeam
        fields = [
            "elo_rank",
            "name",
            "flag_emoji",
            "confederation",
            "group",
            "is_host",
            "elo_rating",
            "fifa_rank",
            "fifa_points",
            "elo_vs_fifa",
            "updated_at",
        ]
