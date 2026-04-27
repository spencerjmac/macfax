"""
Add derived per-game / efficiency fields to PlayerSeasonStats.

Fields added:
  ftm_pg, fta_pg           — free throw makes/attempts per game
  oreb_pg, dreb_pg         — offensive/defensive rebounds per game
  efg_pct                  — effective FG% = (fgm + 0.5*fg3m) / fga
  ts_pct                   — true shooting% = pts / (2*(fga + 0.44*fta))
  ast_to                   — assist-to-turnover ratio
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_phase_b_lineup_stints"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerseasonstats",
            name="ftm_pg",
            field=models.FloatField(default=0.0, help_text="FTM per game"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="fta_pg",
            field=models.FloatField(default=0.0, help_text="FTA per game"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="oreb_pg",
            field=models.FloatField(default=0.0, help_text="Offensive rebounds per game"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="dreb_pg",
            field=models.FloatField(default=0.0, help_text="Defensive rebounds per game"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="efg_pct",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Effective FG% = (FGM + 0.5*FG3M) / FGA",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="ts_pct",
            field=models.FloatField(
                null=True, blank=True,
                help_text="True Shooting% = PTS / (2*(FGA + 0.44*FTA))",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="ast_to",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Assist-to-turnover ratio",
            ),
        ),
    ]
