# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_add_sor_net_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='teamgamestats',
            name='game_value',
            field=models.FloatField(blank=True, help_text='Game Value: Result (1=W, 0=L) - P(bubble team wins). Higher = better resume win', null=True),
        ),
    ]
