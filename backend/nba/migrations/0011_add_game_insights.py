from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nba', '0010_add_ffi_raw_coefficients'),
    ]

    operations = [
        migrations.AddField(
            model_name='nbagame',
            name='game_insights',
            field=models.TextField(blank=True, null=True),
        ),
    ]
