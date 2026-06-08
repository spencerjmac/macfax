from django.db import models


class WorldCupTeam(models.Model):
    # Identity
    name = models.CharField(max_length=100)
    dataset_name = models.CharField(max_length=100)
    confederation = models.CharField(max_length=20)
    group = models.CharField(max_length=2)
    is_host = models.BooleanField(default=False)
    flag_emoji = models.CharField(max_length=10, blank=True)

    # Rankings
    fifa_rank = models.IntegerField(default=0)
    fifa_points = models.FloatField(default=0.0)
    elo_rating = models.FloatField(default=1500.0)
    elo_rank = models.IntegerField(default=0)
    elo_vs_fifa = models.IntegerField(default=0)  # positive = Elo rates higher than FIFA

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["elo_rank"]

    def __str__(self):
        return self.name
