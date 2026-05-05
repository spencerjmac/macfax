from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0055_add_placeholder_fg3a_pg"),
    ]

    operations = [
        migrations.AddField(
            model_name="placeholderarchetype",
            name="conference",
            field=models.CharField(
                blank=True,
                default="",
                db_index=True,
                help_text=(
                    "Actual conference code (e.g. 'ACC', 'WCC') — "
                    "blank for conf_group-level archetypes"
                ),
                max_length=16,
            ),
        ),
    ]
