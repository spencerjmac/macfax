from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0053_add_scenario_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="teamseasonstats",
            name="is_first_year_coach",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "True when the head coach is in their first season with this program. "
                    "Set manually each season via python manage.py set_coach_flags --season YEAR. "
                    "Used to add uncertainty to team projections for high-variance coaching transitions."
                ),
            ),
        ),
    ]
