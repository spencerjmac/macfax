from django.contrib import admin

from .models import FavoriteTeam


@admin.register(FavoriteTeam)
class FavoriteTeamAdmin(admin.ModelAdmin):
    list_display = ("device_id", "team_slug", "position", "created_at")
