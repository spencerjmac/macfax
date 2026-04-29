from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0051_add_recruiting_prior_used"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerseasonprojection",
            name="classification_reason",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "How recruitment_type was determined: "
                    "no_prior_season | same_team_prior | grad_transfer_return | different_team_prior"
                ),
                max_length=60,
            ),
        ),
    ]
