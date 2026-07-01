from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nba", "0019_add_player_dob"),
    ]

    operations = [
        migrations.AddField(
            model_name="teamoutseasonmove",
            name="round_number",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="teamoutseasonmove",
            name="overall_pick",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
