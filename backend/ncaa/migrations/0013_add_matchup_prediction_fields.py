# Generated migration to add HCA and sigma fields to NationalAverages

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_teamseasonratings_d1_games_played_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='nationalaverages',
            name='hca_points',
            field=models.FloatField(
                null=True,
                blank=True,
                help_text='Home court advantage in points (estimated from game logs)'
            ),
        ),
        migrations.AddField(
            model_name='nationalaverages',
            name='prediction_sigma',
            field=models.FloatField(
                null=True,
                blank=True,
                help_text='Standard deviation of prediction errors (for win probability)'
            ),
        ),
    ]
