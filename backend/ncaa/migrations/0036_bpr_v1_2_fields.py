"""
Migration 0036 — BPR v1.2 fields.

Adds to PlayerSeasonStats:
  Baseline RAPM targets (raw, before prior-informed fit):
    baseline_obpr — used as clean training target for Box BPR across seasons.
    baseline_dbpr — eliminates recursive prior-target contamination.

  Source provenance tracking:
    obpr_source — "rapm" | "box_bpr" | null
    dbpr_source — "rapm" | "box_bpr" | null
    bpr_source  — "rapm" | "box_bpr" | "mixed" | "partial" | null

These changes support BPR v1.2 which ensures the teacher-student chain is:
    baseline RAPM → Box BPR prior → final prior-informed RAPM
rather than:
    final BPR → Box BPR prior → next final BPR  (v1.1 contamination)
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0035_bpr_fields"),
    ]

    operations = [
        # ── Baseline RAPM targets ──────────────────────────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="baseline_obpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Baseline RAPM OBPR (before prior-informed fit; clean target for Box BPR training)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="baseline_dbpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Baseline RAPM DBPR (before prior-informed fit; clean target for Box BPR training)",
            ),
        ),
        # ── BPR source provenance ──────────────────────────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="obpr_source",
            field=models.CharField(
                max_length=20, null=True, blank=True,
                help_text="Source of OBPR value: 'rapm', 'box_bpr', or null",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="dbpr_source",
            field=models.CharField(
                max_length=20, null=True, blank=True,
                help_text="Source of DBPR value: 'rapm', 'box_bpr', or null",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="bpr_source",
            field=models.CharField(
                max_length=20, null=True, blank=True,
                help_text="Source of total BPR: 'rapm', 'box_bpr', 'mixed', 'partial', or null",
            ),
        ),
    ]
