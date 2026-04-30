from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0052_add_classification_reason"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScenarioSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("projected_season_year", models.IntegerField()),
                ("name", models.CharField(blank=True, default="", max_length=120, help_text="User-defined scenario name.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("scenario_input", models.JSONField(help_text="Serialized ScenarioRosterRequest as submitted by the client.")),
                ("scenario_result", models.JSONField(help_text="Serialized ScenarioResult as returned by compute_scenario().")),
                ("projected_adj_em", models.FloatField(blank=True, null=True)),
                ("projected_national_rank", models.IntegerField(blank=True, null=True)),
                ("n_manual_players", models.IntegerField(default=0)),
                ("from_season", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scenario_snapshots", to="core.season")),
                ("team", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scenario_snapshots", to="core.team")),
            ],
            options={
                "ordering": ["-updated_at"],
                "indexes": [models.Index(fields=["team", "from_season"], name="core_scenar_team_id_from_sea_idx")],
            },
        ),
    ]
