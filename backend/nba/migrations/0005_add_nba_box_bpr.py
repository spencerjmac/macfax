from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nba', '0004_add_player_advanced_stats'),
    ]

    operations = [
        migrations.AddField(
            model_name='nbaplayerseasonstats',
            name='box_obpr',
            field=models.FloatField(blank=True, help_text='Box-score offensive BPR', null=True),
        ),
        migrations.AddField(
            model_name='nbaplayerseasonstats',
            name='box_dbpr',
            field=models.FloatField(blank=True, help_text='Box-score defensive BPR', null=True),
        ),
        migrations.AddField(
            model_name='nbaplayerseasonstats',
            name='box_bpr',
            field=models.FloatField(blank=True, help_text='Box-score total BPR', null=True),
        ),
        migrations.AddField(
            model_name='nbaplayerseasonstats',
            name='nba_archetype',
            field=models.CharField(
                blank=True,
                help_text='Role archetype (creator/scorer/stretch/three_and_d/interior/connector)',
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='nbaplayerseasonstats',
            name='bpr_last_updated',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
