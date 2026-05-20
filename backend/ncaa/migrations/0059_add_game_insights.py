from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0058_lower_k_floor_to_150'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='game_insights',
            field=models.TextField(blank=True, null=True),
        ),
    ]
