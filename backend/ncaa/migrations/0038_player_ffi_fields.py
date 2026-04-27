from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0037_player_on_court_adj_ratings"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerseasonstats",
            name="off_efg_impact",
            field=models.FloatField(blank=True, null=True, help_text="Offensive eFG% impact vs average (pp, positive-good)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="def_efg_impact",
            field=models.FloatField(blank=True, null=True, help_text="Defensive eFG% impact: reduction in opp eFG vs average (pp, positive-good)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="off_tov_impact",
            field=models.FloatField(blank=True, null=True, help_text="Offensive TOV impact: reduction in team TOV% vs average (pp, positive-good)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="def_tov_impact",
            field=models.FloatField(blank=True, null=True, help_text="Defensive TOV generation: increase in forced opp TOV% vs average (pp, positive-good)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="off_orb_impact",
            field=models.FloatField(blank=True, null=True, help_text="Offensive ORB% impact vs average (pp, positive-good)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="def_reb_impact",
            field=models.FloatField(blank=True, null=True, help_text="Defensive rebounding impact: reduction in opp ORB% vs average (pp, positive-good)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="off_ftr_impact",
            field=models.FloatField(blank=True, null=True, help_text="Offensive FTR impact vs average (pp, positive-good)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="def_ftr_impact",
            field=models.FloatField(blank=True, null=True, help_text="Defensive FTR prevention: reduction in opp FTR vs average (pp, positive-good)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="efg_impact_margin",
            field=models.FloatField(blank=True, null=True, help_text="Combined eFG impact margin (off + def)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="tov_impact_margin",
            field=models.FloatField(blank=True, null=True, help_text="Combined TOV impact margin (off + def)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="reb_impact_margin",
            field=models.FloatField(blank=True, null=True, help_text="Combined rebounding impact margin (off ORB + def REB)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="ftr_impact_margin",
            field=models.FloatField(blank=True, null=True, help_text="Combined FTR impact margin (off + def)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="four_factor_impact_index",
            field=models.FloatField(blank=True, null=True, help_text="Four Factor Impact Index (0-100): RAPM-based, player-specific, not team-context-driven"),
        ),
    ]
