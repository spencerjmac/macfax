from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0050_add_update_pipeline_job_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerseasonprojection",
            name="recruiting_prior_used",
            field=models.BooleanField(
                default=False,
                help_text="True when a PlayerRecruitingProfile was used to set the newcomer BPR prior.",
            ),
        ),
    ]
