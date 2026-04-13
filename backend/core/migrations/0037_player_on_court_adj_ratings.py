"""
Migration 0037 — Possession-based adjusted on-court player ratings.

Adds to PlayerSeasonStats:
  on_court_off_poss  — offensive possessions on court (FGA + 0.44·FTA + TOV − OREB)
  on_court_def_poss  — defensive possessions on court (opp version of above)
  on_court_raw_oe    — raw on-court offensive efficiency (pts/100 off poss)
  on_court_raw_de    — raw on-court defensive efficiency (opp pts/100 def poss)
  on_court_adj_o     — adjusted on-court offensive efficiency (opponent/site-adjusted + shrunk)
  on_court_adj_d     — adjusted on-court defensive efficiency (opponent/site-adjusted + shrunk)
  on_court_adj_em    — adjusted on-court net efficiency (adj_o − adj_d)

These are distinct from the legacy on_court_ortg/drtg (per-40 pts-based) and from
adj_team_off_eff_on/adj_team_def_eff_on (populated in the same compute pass).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_bpr_v1_2_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_off_poss",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Offensive possessions on court (FGA + 0.44·FTA + TOV − OREB)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_def_poss",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Defensive possessions on court (opp FGA + 0.44·FTA + TOV − OREB)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_raw_oe",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Raw on-court offensive efficiency (pts/100 off poss)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_raw_de",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Raw on-court defensive efficiency (opp pts/100 def poss)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_adj_o",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Adjusted on-court offensive efficiency (opponent-/site-adjusted, shrunk toward nat avg)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_adj_d",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Adjusted on-court defensive efficiency (opponent-/site-adjusted, shrunk toward nat avg)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_adj_em",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Adjusted on-court net efficiency (on_court_adj_o − on_court_adj_d)",
            ),
        ),
    ]
