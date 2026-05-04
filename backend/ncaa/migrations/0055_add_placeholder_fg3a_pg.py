from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0054_add_is_first_year_coach"),
    ]

    operations = [
        migrations.AddField(
            model_name="placeholderarchetype",
            name="fg3a_pg",
            field=models.FloatField(
                blank=True,
                null=True,
                help_text="Median 3-point attempts per game",
            ),
        ),
    ]
