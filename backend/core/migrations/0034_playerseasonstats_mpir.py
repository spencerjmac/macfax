from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0033_playerseasonstats_oncourt_fourfactors"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerseasonstats",
            name="o_mpir",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Offensive MPIR: blend of on-court offensive impact and box-score offensive prior",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="d_mpir",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Defensive MPIR: blend of on-court defensive impact and box-score defensive prior",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="mpir",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Macfax Player Impact Rating = O-MPIR + D-MPIR",
            ),
        ),
    ]
