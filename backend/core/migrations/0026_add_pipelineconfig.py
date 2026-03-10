from django.db import migrations, models


def seed_pipeline_config(apps, schema_editor):
    """Create the singleton PipelineConfig row with all defaults."""
    PipelineConfig = apps.get_model("core", "PipelineConfig")
    PipelineConfig.objects.get_or_create(pk=1)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_delete_dataingestionrun"),
    ]

    operations = [
        migrations.CreateModel(
            name="PipelineConfig",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                # Adjusted Ratings
                (
                    "adj_ratings_iterations",
                    models.IntegerField(
                        default=25,
                        help_text="Max solver iterations before declaring convergence (compute_adjusted_ratings --iterations)",
                    ),
                ),
                (
                    "adj_ratings_convergence",
                    models.FloatField(
                        default=0.001,
                        help_text="Max AdjEM change between iterations to declare convergence",
                    ),
                ),
                (
                    "adj_ratings_shrinkage_floor",
                    models.IntegerField(
                        default=170,
                        help_text="Minimum shrinkage constant (possessions) regardless of games played",
                    ),
                ),
                (
                    "adj_ratings_shrinkage_ceiling",
                    models.IntegerField(
                        default=300,
                        help_text="Starting/maximum shrinkage constant (possessions)",
                    ),
                ),
                (
                    "adj_ratings_shrinkage_decay",
                    models.FloatField(
                        default=6.25,
                        help_text="Shrinkage k drops by this amount per average game played",
                    ),
                ),
                # Adjusted Four Factors
                (
                    "adj_ff_iterations",
                    models.IntegerField(
                        default=3,
                        help_text="Adjustment iterations for compute_adjusted_four_factors",
                    ),
                ),
                # Four Factor Index
                (
                    "ffi_weight_efg",
                    models.FloatField(
                        default=0.4069,
                        help_text="eFG% margin weight in the FFI composite score",
                    ),
                ),
                (
                    "ffi_weight_tov",
                    models.FloatField(
                        default=0.4069,
                        help_text="Turnover edge weight in the FFI composite score",
                    ),
                ),
                (
                    "ffi_weight_reb",
                    models.FloatField(
                        default=0.1432,
                        help_text="Rebounding edge weight in the FFI composite score",
                    ),
                ),
                (
                    "ffi_weight_ftr",
                    models.FloatField(
                        default=0.0428,
                        help_text="FTR margin weight in the FFI composite score",
                    ),
                ),
                (
                    "ffi_scale_midpoint",
                    models.IntegerField(
                        default=50,
                        help_text="FFI output scale midpoint (score = midpoint + multiplier * z)",
                    ),
                ),
                (
                    "ffi_scale_multiplier",
                    models.IntegerField(
                        default=20,
                        help_text="FFI z-score scale multiplier",
                    ),
                ),
                # Strength of Record
                (
                    "sor_trials",
                    models.IntegerField(
                        default=10000,
                        help_text="Monte Carlo win-simulation trials (compute_sor --trials)",
                    ),
                ),
                (
                    "sor_baseline_rank_min",
                    models.IntegerField(
                        default=20,
                        help_text="Primary SOR baseline: use teams ranked this or better",
                    ),
                ),
                (
                    "sor_baseline_rank_max",
                    models.IntegerField(
                        default=30,
                        help_text="Primary SOR baseline: use teams ranked this or worse",
                    ),
                ),
                (
                    "sor_fallback_rank_min",
                    models.IntegerField(
                        default=15,
                        help_text="Fallback SOR baseline (when primary range is underpopulated): rank floor",
                    ),
                ),
                (
                    "sor_fallback_rank_max",
                    models.IntegerField(
                        default=35,
                        help_text="Fallback SOR baseline (when primary range is underpopulated): rank ceiling",
                    ),
                ),
                # WAB / Game Value
                (
                    "wab_bubble_rank",
                    models.IntegerField(
                        default=45,
                        help_text="AdjEM rank of the 'bubble team' used as the WAB and game-value baseline",
                    ),
                ),
                # Strength of Schedule
                (
                    "sos_baseline_adjem",
                    models.FloatField(
                        default=0.0,
                        help_text="AdjEM of the 'average D1 team' anchor for the SOS logistic model",
                    ),
                ),
                (
                    "sos_logistic_sigma",
                    models.FloatField(
                        default=10.0,
                        help_text="Logistic spread/scale parameter for the SOS win-probability model",
                    ),
                ),
                (
                    "sos_home_advantage",
                    models.FloatField(
                        default=1.5,
                        help_text="Points added to the home team's margin in SOS win-probability calculations",
                    ),
                ),
                (
                    "sos_away_penalty",
                    models.FloatField(
                        default=1.5,
                        help_text="Points subtracted from the away team's margin in SOS win-probability calculations",
                    ),
                ),
                # Shared Fallbacks
                (
                    "fallback_hca",
                    models.FloatField(
                        default=1.85,
                        help_text="HCA (points) used when NationalAverages.hca_points has not been computed yet",
                    ),
                ),
                (
                    "fallback_sigma",
                    models.FloatField(
                        default=11.08,
                        help_text="Prediction sigma used when NationalAverages.prediction_sigma has not been computed yet",
                    ),
                ),
                (
                    "fallback_avg_ortg",
                    models.FloatField(
                        default=108.0,
                        help_text="National average offensive rating used when NationalAverages has not been computed yet",
                    ),
                ),
            ],
            options={
                "verbose_name": "Pipeline Configuration",
                "verbose_name_plural": "Pipeline Configuration",
            },
        ),
        migrations.RunPython(seed_pipeline_config, migrations.RunPython.noop),
    ]
