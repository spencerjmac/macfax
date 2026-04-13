import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0038_player_ffi_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlayerSeasonProjection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="season_projections",
                        to="core.player",
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="player_projections",
                        to="core.team",
                        help_text="The team the player was on in from_season",
                    ),
                ),
                (
                    "from_season",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="player_projections",
                        to="core.season",
                        help_text="The season this projection is based on",
                    ),
                ),
                (
                    "projected_season_year",
                    models.IntegerField(
                        help_text="The season year being projected to (e.g. 2027 if from_season.year=2026)",
                    ),
                ),
                (
                    "recruitment_type",
                    models.CharField(
                        choices=[
                            ("returner", "Returner"),
                            ("transfer", "Transfer"),
                            ("newcomer", "Newcomer"),
                        ],
                        max_length=20,
                        help_text="How the player arrived at their current team (vs prior season)",
                    ),
                ),
                (
                    "projected_obpr",
                    models.FloatField(
                        blank=True,
                        null=True,
                        help_text="Projected offensive BPR for next season (pts/100 poss above D1 avg)",
                    ),
                ),
                (
                    "projected_dbpr",
                    models.FloatField(
                        blank=True,
                        null=True,
                        help_text="Projected defensive BPR for next season (pts/100 poss above D1 avg)",
                    ),
                ),
                (
                    "projected_bpr",
                    models.FloatField(
                        blank=True,
                        null=True,
                        help_text="projected_obpr + projected_dbpr",
                    ),
                ),
                (
                    "projected_minutes_share",
                    models.FloatField(
                        blank=True,
                        null=True,
                        help_text=(
                            "Estimated fraction of 40 minutes played per game (mpg/40) for next season. "
                            "Phase 1 baseline — will be refined in Phase 2."
                        ),
                    ),
                ),
                (
                    "projection_uncertainty",
                    models.FloatField(
                        blank=True,
                        null=True,
                        help_text=(
                            "Projection confidence score: 0 = low uncertainty (high confidence), "
                            "1 = high uncertainty. Influenced by recruitment type and sample size."
                        ),
                    ),
                ),
                (
                    "n_prior_seasons",
                    models.IntegerField(
                        default=0,
                        help_text="Number of prior college seasons in DB before from_season",
                    ),
                ),
                (
                    "prior_rapm_used",
                    models.BooleanField(
                        default=False,
                        help_text="Whether prior-season RAPM (obpr/dbpr) was available and incorporated",
                    ),
                ),
                (
                    "projection_version",
                    models.CharField(
                        default="1.0",
                        max_length=20,
                        help_text="Version tag of the projection model that generated this row",
                    ),
                ),
                (
                    "computed_at",
                    models.DateTimeField(auto_now=True),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="playerseasonprojection",
            constraint=models.UniqueConstraint(
                fields=["player", "from_season", "team"],
                name="unique_player_season_projection",
            ),
        ),
        migrations.AddIndex(
            model_name="playerseasonprojection",
            index=models.Index(
                fields=["from_season", "projected_season_year"],
                name="core_playerse_from_se_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="playerseasonprojection",
            index=models.Index(
                fields=["player", "from_season"],
                name="core_playerse_player_idx",
            ),
        ),
    ]
