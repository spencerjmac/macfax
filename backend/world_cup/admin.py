from django.contrib import admin
from .models import WorldCupTeam


@admin.register(WorldCupTeam)
class WorldCupTeamAdmin(admin.ModelAdmin):
    list_display = ("elo_rank", "name", "confederation", "group", "elo_rating", "fifa_rank", "elo_vs_fifa")
    list_filter = ("confederation", "group", "is_host")
    ordering = ("elo_rank",)
