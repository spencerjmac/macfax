import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nba", "0017_add_nbaplayergamestats_oreb_dreb"),
    ]

    operations = [
        # ── New fields on TeamSeasonOutlook ──────────────────────────────────
        migrations.AddField(
            model_name="teamseasonoutlook",
            name="projected_adj_o",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="teamseasonoutlook",
            name="projected_adj_d",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="teamseasonoutlook",
            name="projected_floor_wins",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="teamseasonoutlook",
            name="projected_ceil_wins",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="teamseasonoutlook",
            name="continuity_score",
            field=models.FloatField(blank=True, null=True, help_text="0-100: returner minutes fraction × 100"),
        ),
        migrations.AddField(
            model_name="teamseasonoutlook",
            name="weighted_effective_age",
            field=models.FloatField(blank=True, null=True, help_text="BPR-weighted average age of projected rotation"),
        ),
        migrations.AddField(
            model_name="teamseasonoutlook",
            name="top2_bpr_concentration",
            field=models.FloatField(blank=True, null=True, help_text="0-1: fraction of projected wins added from top-2 players"),
        ),
        migrations.AddField(
            model_name="teamseasonoutlook",
            name="cap_total_salary",
            field=models.BigIntegerField(blank=True, null=True, help_text="Total guaranteed salary commitment in dollars"),
        ),
        migrations.AddField(
            model_name="teamseasonoutlook",
            name="cap_status_tier",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=20,
                choices=[
                    ("under_cap", "Under Cap"),
                    ("over_cap", "Over Cap"),
                    ("taxpayer", "Luxury Taxpayer"),
                    ("first_apron", "First Apron"),
                    ("second_apron", "Second Apron"),
                ],
            ),
        ),

        # ── NBAProjectedRosterSlot ────────────────────────────────────────────
        migrations.CreateModel(
            name="NBAProjectedRosterSlot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("player_name", models.CharField(max_length=150)),
                ("position", models.CharField(blank=True, max_length=10)),
                ("archetype", models.CharField(blank=True, max_length=32, null=True)),
                ("age", models.IntegerField(blank=True, null=True)),
                ("acquisition_type", models.CharField(
                    choices=[
                        ("returner", "Returner"),
                        ("signed", "Free Agent Signed"),
                        ("traded_in", "Acquired via Trade"),
                        ("drafted", "Drafted"),
                        ("extended", "Extension"),
                    ],
                    default="returner",
                    max_length=20,
                )),
                ("projected_obpr", models.FloatField(blank=True, null=True)),
                ("projected_dbpr", models.FloatField(blank=True, null=True)),
                ("projected_bpr", models.FloatField(blank=True, null=True)),
                ("projected_minutes_share", models.FloatField(
                    blank=True, null=True, help_text="Fraction of 200 team-minutes (0–1)"
                )),
                ("projected_wins_added", models.FloatField(blank=True, null=True)),
                ("confidence", models.CharField(
                    choices=[("high", "High"), ("medium", "Medium"), ("low", "Low")],
                    default="medium",
                    max_length=10,
                )),
                ("team", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="projected_roster_slots",
                    to="nba.teamseasonoutlook",
                )),
                ("season", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to="nba.nbaseason",
                )),
                ("player", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to="nba.nbaplayer",
                )),
                ("prior_stats", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to="nba.nbaplayerseasonstats",
                )),
            ],
            options={
                "ordering": ["-projected_minutes_share"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="nbaprojectedrosterslot",
            unique_together={("team", "season", "player_name")},
        ),

        # ── NBAPlayerContract ─────────────────────────────────────────────────
        migrations.CreateModel(
            name="NBAPlayerContract",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("salary", models.BigIntegerField(help_text="Annual salary in dollars")),
                ("years_remaining", models.IntegerField(default=0, help_text="Contract years remaining after this season")),
                ("contract_type", models.CharField(
                    choices=[
                        ("max", "Max Contract"),
                        ("mid", "Mid-Level Exception"),
                        ("mini", "Mini Mid-Level"),
                        ("veteran", "Veteran Exception"),
                        ("two_way", "Two-Way Contract"),
                        ("rookie", "Rookie Scale"),
                        ("vet_min", "Veteran Minimum"),
                        ("other", "Other"),
                    ],
                    default="other",
                    max_length=20,
                )),
                ("player_option", models.BooleanField(default=False)),
                ("team_option", models.BooleanField(default=False)),
                ("is_guaranteed", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("player", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="contracts",
                    to="nba.nbaplayer",
                )),
                ("team", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="contracts",
                    to="nba.nbateam",
                )),
                ("season", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="contracts",
                    to="nba.nbaseason",
                )),
            ],
            options={
                "ordering": ["-salary"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="nbaplayercontract",
            unique_together={("player", "team", "season")},
        ),
    ]
