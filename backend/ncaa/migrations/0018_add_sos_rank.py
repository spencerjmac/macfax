# Generated migration to add sos_rank and sos_win_pct fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_add_game_value_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='teamseasonratings',
            name='sos_rank',
            field=models.IntegerField(null=True, blank=True, help_text='Strength of Schedule rank (1 = hardest)'),
        ),
        migrations.AddField(
            model_name='teamseasonratings',
            name='sos_win_pct',
            field=models.FloatField(null=True, blank=True, help_text='Expected win% for an average D1 team vs this schedule'),
        ),
    ]
