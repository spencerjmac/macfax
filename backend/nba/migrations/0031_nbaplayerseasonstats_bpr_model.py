from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nba', '0030_lineup_source_window_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='nbaplayerseasonstats',
            name='bpr_model',
            field=models.CharField(blank=True, help_text="Model that wrote obpr/dbpr/bpr: 'native-1' (nba_compute_native_bpr); null = earlier LEBRON-prior model", max_length=16, null=True),
        ),
    ]
