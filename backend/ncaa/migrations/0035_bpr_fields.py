"""
Migration 0035 — Bayesian Performance Rating (BPR) fields.

Adds to PlayerSeasonStats:
  Core BPR outputs:
    bpr, obpr, dbpr
  Box BPR (box-score model, no lineup data required):
    box_bpr, box_obpr, box_dbpr
  Preseason priors:
    preseason_obpr, preseason_dbpr
  Prior parameters used in Bayesian RAPM:
    prior_mean_obpr, prior_mean_dbpr, prior_sd_obpr, prior_sd_dbpr
  Possession counts (estimated from box events while on court):
    off_poss, def_poss
  Adjusted on-court team efficiencies (per 100 poss):
    adj_team_off_eff_on, adj_team_def_eff_on
  Model metadata:
    bpr_model_version, bpr_last_updated

Adds new model BPRModelArtifact for storing trained model weights and CV metrics.
"""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0034_playerseasonstats_mpir"),
    ]

    operations = [
        # ── Core BPR outputs ──────────────────────────────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="bpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Bayesian Performance Rating = OBPR + DBPR (pts per 100 poss above D1 avg)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="obpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Offensive BPR: offensive pts per 100 poss above D1 avg",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="dbpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Defensive BPR: defensive pts per 100 poss better than D1 avg (higher = better def)",
            ),
        ),
        # ── Box BPR ───────────────────────────────────────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="box_bpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Box BPR = box_obpr + box_dbpr (box-score model only, no lineup data)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="box_obpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Offensive Box BPR (box-score model prediction of offensive impact)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="box_dbpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Defensive Box BPR (box-score model prediction of defensive impact)",
            ),
        ),
        # ── Preseason priors ──────────────────────────────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="preseason_obpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Preseason estimated OBPR (from prior season + box BPR; 0 if no history)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="preseason_dbpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Preseason estimated DBPR",
            ),
        ),
        # ── Prior parameters used in Bayesian RAPM ────────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="prior_mean_obpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Prior mean for OBPR used in final Bayesian RAPM fit",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="prior_mean_dbpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Prior mean for DBPR used in final Bayesian RAPM fit",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="prior_sd_obpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Prior standard deviation for OBPR (controls how much on-court data can pull away from box prior)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="prior_sd_dbpr",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Prior standard deviation for DBPR",
            ),
        ),
        # ── Possession counts ─────────────────────────────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="off_poss",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Estimated offensive possessions while on court (FGA + 0.44*FTA + TOV - ORB)",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="def_poss",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Estimated defensive possessions while on court (opponent: FGA + 0.44*FTA + TOV - ORB)",
            ),
        ),
        # ── Adjusted on-court team efficiencies ───────────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="adj_team_off_eff_on",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Team adj offensive efficiency (pts/100 poss) while player is on court",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="adj_team_def_eff_on",
            field=models.FloatField(
                null=True, blank=True,
                help_text="Team adj defensive efficiency (pts/100 poss) while player is on court",
            ),
        ),
        # ── BPR model metadata ────────────────────────────────────────────────
        migrations.AddField(
            model_name="playerseasonstats",
            name="bpr_model_version",
            field=models.CharField(
                max_length=32, null=True, blank=True,
                help_text="BPR model version tag (e.g. '1.0-2026')",
            ),
        ),
        migrations.AddField(
            model_name="playerseasonstats",
            name="bpr_last_updated",
            field=models.DateTimeField(
                null=True, blank=True,
                help_text="Timestamp of last BPR computation for this player-season",
            ),
        ),
        # ── BPRModelArtifact: store trained model weights + CV results ─────────
        migrations.CreateModel(
            name="BPRModelArtifact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("season", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="bpr_artifacts",
                    to="core.season",
                    help_text="Season this model was trained on",
                )),
                ("model_type", models.CharField(
                    max_length=32,
                    help_text="One of: box_off | box_def | rapm_baseline | rapm_informed",
                )),
                ("version", models.CharField(max_length=32, help_text="Semantic version tag")),
                ("feature_names", models.JSONField(
                    default=list,
                    help_text="Ordered list of feature names for the coefficients",
                )),
                ("coefficients", models.JSONField(
                    default=list,
                    help_text="Trained model coefficients (list aligned to feature_names)",
                )),
                ("intercept", models.FloatField(
                    null=True, blank=True,
                    help_text="Model intercept (league average offset)",
                )),
                ("regularization_alpha", models.FloatField(
                    null=True, blank=True,
                    help_text="Ridge regularization strength (lambda) chosen by CV",
                )),
                ("cv_metrics", models.JSONField(
                    null=True, blank=True,
                    help_text="Cross-validation metrics: {rmse, r2, best_alpha, fold_scores}",
                )),
                ("assumptions", models.JSONField(
                    null=True, blank=True,
                    help_text="Documented deviations from public BPR article",
                )),
                ("n_observations", models.IntegerField(
                    null=True, blank=True,
                    help_text="Number of training observations used",
                )),
                ("n_players", models.IntegerField(
                    null=True, blank=True,
                    help_text="Number of unique players in training data",
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
