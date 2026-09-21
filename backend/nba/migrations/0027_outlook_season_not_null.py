"""
Finalize the season FK as NOT NULL on both outlook models.

Depends on 0026 having backfilled every row, so the ALTER … SET NOT NULL cannot
fail on live data. A forward guard counts NULL-season rows first and raises if
any remain — this makes the migration refuse to run out of order (e.g. if 0026
was faked) rather than let a nullable FK quietly defeat the (team_slug, season)
uniqueness with a NULL-season shadow league.

Once this lands, every unscoped writer that forgets to set season fails with an
IntegrityError instead of silently duplicating — the desired forcing function
for the sync/seed commands that still assume one-row-per-slug.
"""

import django.db.models.deletion
from django.db import migrations, models


def guard_no_null_seasons(apps, schema_editor):
    TeamSeasonOutlook = apps.get_model("nba", "TeamSeasonOutlook")
    TeamOutseasonMove = apps.get_model("nba", "TeamOutseasonMove")
    n_outlook = TeamSeasonOutlook.objects.filter(season__isnull=True).count()
    n_move = TeamOutseasonMove.objects.filter(season__isnull=True).count()
    if n_outlook or n_move:
        raise RuntimeError(
            f"Refusing NOT NULL: {n_outlook} outlook + {n_move} move rows still "
            "have season IS NULL. Run migration 0026 (backfill) first."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("nba", "0026_backfill_outlook_season"),
    ]

    operations = [
        migrations.RunPython(guard_no_null_seasons, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="teamseasonoutlook",
            name="season",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="team_outlooks",
                to="nba.nbaseason",
                help_text="Projected (target) season this outlook row versions.",
            ),
        ),
        migrations.AlterField(
            model_name="teamoutseasonmove",
            name="season",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="outseason_moves",
                to="nba.nbaseason",
                help_text=(
                    "Target season this move affects (the projected season, e.g. "
                    "2027 for the 2026-27 outlook) — not the calendar offseason "
                    "window; order in-season transactions by transaction_date."
                ),
            ),
        ),
    ]
