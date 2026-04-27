from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_playergamestint_box_events"),
    ]

    operations = [
        # ── On-court Four Factors — Offense ───────────────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_efg_pct",
            field=models.FloatField(null=True, blank=True, help_text="Team eFG% while on court"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_tov_pct",
            field=models.FloatField(null=True, blank=True, help_text="Team TOV% while on court"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_orb_pct",
            field=models.FloatField(null=True, blank=True, help_text="Team ORB% while on court"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_ftr",
            field=models.FloatField(null=True, blank=True, help_text="Team FTR (FTA/FGA) while on court"),
        ),
        # ── On-court Four Factors — Defense (opponent) ────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_opp_efg_pct",
            field=models.FloatField(null=True, blank=True, help_text="Opp eFG% while on court"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_opp_tov_pct",
            field=models.FloatField(null=True, blank=True, help_text="Opp TOV% while on court (turnovers forced)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_drb_pct",
            field=models.FloatField(null=True, blank=True, help_text="Team DRB% while on court (opp ORB%)"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_opp_ftr",
            field=models.FloatField(null=True, blank=True, help_text="Opp FTR while on court"),
        ),
        # ── Margins ───────────────────────────────────────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_efg_margin",
            field=models.FloatField(null=True, blank=True, help_text="eFG% margin (team - opp) while on"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_tov_edge",
            field=models.FloatField(null=True, blank=True, help_text="TOV edge (opp_tov - team_tov) while on"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_reb_edge",
            field=models.FloatField(null=True, blank=True, help_text="Reb edge (orb_pct - opp_orb_pct) while on"),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_ftr_margin",
            field=models.FloatField(null=True, blank=True, help_text="FTR margin (team_ftr - opp_ftr) while on"),
        ),
        # ── Four Factor Index ─────────────────────────────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="on_court_ffi",
            field=models.FloatField(null=True, blank=True, help_text="Four Factor Index (0-100) for team while player is on court"),
        ),
    ]
