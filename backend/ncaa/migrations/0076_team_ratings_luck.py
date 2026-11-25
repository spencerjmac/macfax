# Split 2026-11-24 from the combined 0075_team_ratings_luck_schedule (never shipped)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0075_team_ratings_schedule'),
    ]

    operations = [
        migrations.AddField(
            model_name='teamseasonratings',
            name='luck',
            field=models.FloatField(blank=True, help_text="(wins - expected wins) / games; expected = sum of forecast_game win probabilities from this row's own ratings, HCA and sigma", null=True),
        ),
    ]
