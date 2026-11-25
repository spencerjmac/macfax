# Split 2026-11-24 from the combined 0075_team_ratings_luck_schedule (never shipped)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0074_team_metrics_box_games'),
    ]

    operations = [
        migrations.AddField(
            model_name='teamseasonratings',
            name='nc_sos_rank',
            field=models.IntegerField(blank=True, help_text='SOS rank over non-conference D1 games only (compute_sos; 1 = hardest)', null=True),
        ),
        migrations.AddField(
            model_name='teamseasonratings',
            name='nc_sos_win_pct',
            field=models.FloatField(blank=True, help_text='Expected win% of an average D1 team against the non-conference D1 schedule', null=True),
        ),
        migrations.AddField(
            model_name='teamseasonratings',
            name='opp_adj_d',
            field=models.FloatField(blank=True, help_text='Mean AdjD of D1 opponents', null=True),
        ),
        migrations.AddField(
            model_name='teamseasonratings',
            name='opp_adj_em',
            field=models.FloatField(blank=True, help_text="Mean AdjEM of D1 opponents (this row's ratings set)", null=True),
        ),
        migrations.AddField(
            model_name='teamseasonratings',
            name='opp_adj_o',
            field=models.FloatField(blank=True, help_text='Mean AdjO of D1 opponents', null=True),
        ),
    ]
