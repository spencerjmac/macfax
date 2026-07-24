"""
Backfill the new season FK on TeamSeasonOutlook and TeamOutseasonMove.

The existing 30 outlook rows (and their 196 offseason moves) all describe the
current projected season — the target of compute_nba_team_outlooks, which is
is_current + 1. Resolve that NBASeason and stamp it so the new
(team_slug, season) uniqueness becomes meaningful (NULL seasons are distinct in
Postgres, so pre-backfill the constraint permits duplicate NULL-season slugs).

Idempotent and reversible: forward only touches rows where season IS NULL;
reverse clears the FK again. If no is_current season is flagged, both are no-ops.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    NBASeason = apps.get_model("nba", "NBASeason")
    TeamSeasonOutlook = apps.get_model("nba", "TeamSeasonOutlook")
    TeamOutseasonMove = apps.get_model("nba", "TeamOutseasonMove")

    current = NBASeason.objects.filter(is_current=True).first()
    if current is None:
        return  # no anchor — leave season NULL, compute_nba_team_outlooks will set it

    target = NBASeason.objects.filter(year=current.year + 1).first()
    if target is None:
        display = f"{current.year}-{str(current.year + 1)[2:]}"
        target = NBASeason.objects.create(year=current.year + 1, display_name=display)

    TeamSeasonOutlook.objects.filter(season__isnull=True).update(season=target)
    # Each move inherits its team's (now-backfilled) season.
    for outlook in TeamSeasonOutlook.objects.all():
        TeamOutseasonMove.objects.filter(
            team=outlook, season__isnull=True
        ).update(season=outlook.season)


def unbackfill(apps, schema_editor):
    TeamSeasonOutlook = apps.get_model("nba", "TeamSeasonOutlook")
    TeamOutseasonMove = apps.get_model("nba", "TeamOutseasonMove")
    TeamOutseasonMove.objects.update(season=None)
    TeamSeasonOutlook.objects.update(season=None)


class Migration(migrations.Migration):

    dependencies = [
        ("nba", "0025_teamoutseasonmove_season_teamoutseasonmove_source_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
