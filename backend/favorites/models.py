"""
Device-scoped "My Teams" list for the Expo app.

The app has no logins, so each install sends a random UUID (device_id).
team_slug is plain text on purpose (not a ForeignKey to ncaa.Team) so this
table never touches the stats tables; the view checks slugs against
ncaa.Team before saving.
"""

from django.db import models


class FavoriteTeam(models.Model):
    device_id = models.UUIDField(db_index=True)
    team_slug = models.SlugField(max_length=100)
    position = models.PositiveSmallIntegerField(help_text="0 = newest")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["device_id", "team_slug"],
                name="favorites_unique_device_team",
            ),
        ]

    def __str__(self):
        return f"{self.device_id} #{self.position}: {self.team_slug}"
