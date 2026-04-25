from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add Phase 2 minutes‑allocation fields to PlayerSeasonProjection.

    New fields (all nullable — populated by compute_player_minutes after
    Phase 1 projections exist):
      role_bucket       — "G" / "Wing" / "Big" position grouping
      minutes_share_p2  — roster‑context projected minutes share (mpg / 40)
      mpg_p2            — projected MPG (minutes_share_p2 × 40)
      rotation_rank     — 1 = most projected minutes on this team
      minutes_overridden — True when manually pinned via sandbox override
    """

    dependencies = [
        ("core", "0040_projection_unique_player_season"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerseasonprojection",
            name="role_bucket",
            field=models.CharField(
                max_length=10,
                null=True,
                blank=True,
                choices=[("G", "Guard"), ("Wing", "Wing"), ("Big", "Big")],
                help_text=(
                    "Role bucket: G=Guard, Wing=Wing/Forward, Big=Center/PF.  "
                    "Derived from Player.position with box‑score fallback."
                ),
            ),
        ),
        migrations.AddField(
            model_name="playerseasonprojection",
            name="minutes_share_p2",
            field=models.FloatField(
                null=True,
                blank=True,
                help_text=(
                    "Phase 2 projected minutes share (mpg/40); sums to 5.00 "
                    "per team.  Replaces Phase 1 baseline for roster work."
                ),
            ),
        ),
        migrations.AddField(
            model_name="playerseasonprojection",
            name="mpg_p2",
            field=models.FloatField(
                null=True,
                blank=True,
                help_text="Phase 2 projected MPG = minutes_share_p2 × 40.",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonprojection",
            name="rotation_rank",
            field=models.IntegerField(
                null=True,
                blank=True,
                help_text="Rotation rank within team (1 = most projected minutes).",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonprojection",
            name="minutes_overridden",
            field=models.BooleanField(
                default=False,
                help_text="True if minutes share was manually pinned via sandbox override.",
            ),
        ),
    ]
