from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0025_delete_dataingestionrun'),
    ]

    operations = [
        migrations.AddField(
            model_name='teamseasonratings',
            name='ap_poll_week6',
            field=models.IntegerField(
                blank=True,
                help_text='AP Poll Week 6 ranking (1-25, null if unranked)',
                null=True,
            ),
        ),
    ]
