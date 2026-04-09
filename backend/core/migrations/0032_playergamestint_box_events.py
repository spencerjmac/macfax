from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0031_player_season_stats_derived_fields"),
    ]

    operations = [
        # ── Team box events while this player was on court ────────────────────
        migrations.AddField(
            model_name="playergamestint",
            name="team_fgm",
            field=models.SmallIntegerField(default=0, help_text="Team FG made while on"),
        ),
        migrations.AddField(
            model_name="playergamestint",
            name="team_fga",
            field=models.SmallIntegerField(default=0, help_text="Team FG attempted while on"),
        ),
        migrations.AddField(
            model_name="playergamestint",
            name="team_fg3m",
            field=models.SmallIntegerField(default=0, help_text="Team 3P made while on"),
        ),
        migrations.AddField(
            model_name="playergamestint",
            name="team_fta",
            field=models.SmallIntegerField(default=0, help_text="Team FT attempted while on"),
        ),
        migrations.AddField(
            model_name="playergamestint",
            name="team_tov",
            field=models.SmallIntegerField(default=0, help_text="Team turnovers while on"),
        ),
        migrations.AddField(
            model_name="playergamestint",
            name="team_oreb",
            field=models.SmallIntegerField(default=0, help_text="Team offensive rebounds while on"),
        ),
        migrations.AddField(
            model_name="playergamestint",
            name="team_dreb",
            field=models.SmallIntegerField(default=0, help_text="Team defensive rebounds while on"),
        ),
        # ── Opponent box events while this player was on court ────────────────
        migrations.AddField(
            model_name="playergamestint",
            name="opp_fgm",
            field=models.SmallIntegerField(default=0, help_text="Opp FG made while on"),
        ),
        migrations.AddField(
            model_name="playergamestint",
            name="opp_fga",
            field=models.SmallIntegerField(default=0, help_text="Opp FG attempted while on"),
        ),
        migrations.AddField(
            model_name="playergamestint",
            name="opp_fg3m",
            field=models.SmallIntegerField(default=0, help_text="Opp 3P made while on"),
        ),
        migrations.AddField(
            model_name="playergamestint",
            name="opp_fta",
            field=models.SmallIntegerField(default=0, help_text="Opp FT attempted while on"),
        ),
        migrations.AddField(
            model_name="playergamestint",
            name="opp_tov",
            field=models.SmallIntegerField(default=0, help_text="Opp turnovers while on"),
        ),
        migrations.AddField(
            model_name="playergamestint",
            name="opp_oreb",
            field=models.SmallIntegerField(default=0, help_text="Opp offensive rebounds while on"),
        ),
        migrations.AddField(
            model_name="playergamestint",
            name="opp_dreb",
            field=models.SmallIntegerField(default=0, help_text="Opp defensive rebounds while on"),
        ),
    ]
