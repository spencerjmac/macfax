from django.db import migrations, models


def lower_k_floor(apps, schema_editor):
    PipelineConfig = apps.get_model("core", "PipelineConfig")
    PipelineConfig.objects.filter(pk=1).update(adj_ratings_shrinkage_floor=150)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0057_rename_core_scenar_team_id_from_sea_idx_core_scenar_team_id_8181dc_idx"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pipelineconfig",
            name="adj_ratings_shrinkage_floor",
            field=models.IntegerField(
                default=150,
                help_text="Minimum shrinkage constant (possessions) regardless of games played",
            ),
        ),
        migrations.RunPython(lower_k_floor, migrations.RunPython.noop),
    ]
