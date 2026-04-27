from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Change PlayerSeasonProjection unique constraint from
    (player, from_season, team) to (player, from_season).

    Phase 1 produces one canonical projection row per player per from_season
    (not one per player-team pair).  The team field is retained to identify
    which team's court-time sample was used as the canonical signal source,
    but it is no longer part of the uniqueness key.
    """

    dependencies = [
        ("core", "0039_player_season_projection"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="playerseasonprojection",
            name="unique_player_season_projection",
        ),
        migrations.AddConstraint(
            model_name="playerseasonprojection",
            constraint=models.UniqueConstraint(
                fields=["player", "from_season"],
                name="unique_player_season_projection",
            ),
        ),
    ]
