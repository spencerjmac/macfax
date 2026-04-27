from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0027_teamseasonratings_ap_poll_week6'),
    ]

    operations = [
        migrations.AddField(
            model_name='teamseasonratings',
            name='tournament_seed',
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text='NCAA Tournament seed (1-16, null if not in tournament)',
            ),
        ),
        migrations.AddField(
            model_name='teamseasonratings',
            name='tournament_region',
            field=models.CharField(
                blank=True,
                null=True,
                max_length=20,
                choices=[
                    ('South', 'South'),
                    ('East', 'East'),
                    ('West', 'West'),
                    ('Midwest', 'Midwest'),
                ],
                help_text='NCAA Tournament region (South/East/West/Midwest)',
            ),
        ),
    ]
