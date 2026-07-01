from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nba", "0020_teamoutseasonmove_draft_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="teamoutseasonmove",
            name="mps_score",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
