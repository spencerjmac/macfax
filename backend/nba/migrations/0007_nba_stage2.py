from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('nba', '0006_add_season_type_to_ratings_and_player_stats'),
    ]

    operations = [
        # ── NBAGame: PBP checkpoint fields ────────────────────────────────────
        migrations.AddField(
            model_name='nbagame',
            name='pbp_synced',
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddField(
            model_name='nbagame',
            name='pbp_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='nbagame',
            name='pbp_quality_flag',
            field=models.BooleanField(
                default=False, db_index=True,
                help_text='True when > 5% of stints fail 10-player validation — excluded from RAPM',
            ),
        ),

        # ── NBAPlayerSeasonStats: RAPM output fields ──────────────────────────
        migrations.AddField(
            model_name='nbaplayerseasonstats',
            name='baseline_obpr',
            field=models.FloatField(blank=True, help_text='Baseline RAPM offensive BPR', null=True),
        ),
        migrations.AddField(
            model_name='nbaplayerseasonstats',
            name='baseline_dbpr',
            field=models.FloatField(blank=True, help_text='Baseline RAPM defensive BPR', null=True),
        ),
        migrations.AddField(
            model_name='nbaplayerseasonstats',
            name='off_poss',
            field=models.FloatField(blank=True, help_text='Total offensive possessions (from PBP stints)', null=True),
        ),
        migrations.AddField(
            model_name='nbaplayerseasonstats',
            name='def_poss',
            field=models.FloatField(blank=True, help_text='Total defensive possessions (from PBP stints)', null=True),
        ),

        # ── NBAPlayerGameStint: new model ─────────────────────────────────────
        migrations.CreateModel(
            name='NBAPlayerGameStint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='game_stints', to='nba.nbaplayer')),
                ('game',   models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='player_stints', to='nba.nbagame')),
                ('team',   models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='player_stints', to='nba.nbateam')),
                ('stint_index',      models.IntegerField(help_text='0-based sequential per (player, game)')),
                ('period',           models.IntegerField(help_text='1-4 regulation, 5+ OT')),
                ('clock_start_secs', models.IntegerField(help_text='Seconds remaining in period at stint start')),
                ('clock_end_secs',   models.IntegerField(help_text='Seconds remaining in period at stint end')),
                ('secs_on',          models.IntegerField(default=0, help_text='Duration in seconds')),
                ('pts_scored',       models.IntegerField(default=0, help_text='Team pts scored while on court')),
                ('pts_allowed',      models.IntegerField(default=0, help_text='Opp pts scored while on court')),
                ('plus_minus',       models.IntegerField(default=0)),
                ('team_fgm',  models.SmallIntegerField(default=0)),
                ('team_fga',  models.SmallIntegerField(default=0)),
                ('team_fg3m', models.SmallIntegerField(default=0)),
                ('team_fta',  models.SmallIntegerField(default=0)),
                ('team_tov',  models.SmallIntegerField(default=0)),
                ('team_oreb', models.SmallIntegerField(default=0)),
                ('team_dreb', models.SmallIntegerField(default=0)),
                ('opp_fgm',   models.SmallIntegerField(default=0)),
                ('opp_fga',   models.SmallIntegerField(default=0)),
                ('opp_fg3m',  models.SmallIntegerField(default=0)),
                ('opp_fta',   models.SmallIntegerField(default=0)),
                ('opp_tov',   models.SmallIntegerField(default=0)),
                ('opp_oreb',  models.SmallIntegerField(default=0)),
                ('opp_dreb',  models.SmallIntegerField(default=0)),
            ],
            options={'ordering': ['game', 'stint_index']},
        ),
        migrations.AddConstraint(
            model_name='nbaplayergamestint',
            constraint=models.UniqueConstraint(
                fields=['player', 'game', 'stint_index'],
                name='unique_nba_player_game_stint',
            ),
        ),
        migrations.AddIndex(
            model_name='nbaplayergamestint',
            index=models.Index(fields=['game', 'stint_index'], name='nba_pgstint_game_idx'),
        ),
        migrations.AddIndex(
            model_name='nbaplayergamestint',
            index=models.Index(fields=['player', 'game'], name='nba_pgstint_player_idx'),
        ),
        migrations.AddIndex(
            model_name='nbaplayergamestint',
            index=models.Index(fields=['game', 'team'], name='nba_pgstint_team_idx'),
        ),

        # ── NBABPRModelArtifact: new model ────────────────────────────────────
        migrations.CreateModel(
            name='NBABPRModelArtifact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='bpr_artifact', to='nba.nbaseason')),
                ('model_version', models.CharField(default='1.0', max_length=32)),
                ('target_type',   models.CharField(default='mpir', help_text="Training target: 'mpir' (Stage 1 proxy) or 'rapm' (Stage 2+)", max_length=32)),
                ('off_pipeline',  models.BinaryField(help_text='Pickled sklearn Pipeline for offense')),
                ('def_pipeline',  models.BinaryField(help_text='Pickled sklearn Pipeline for defense')),
                ('off_cv_alpha',  models.FloatField(blank=True, null=True)),
                ('def_cv_alpha',  models.FloatField(blank=True, null=True)),
                ('off_r2',        models.FloatField(blank=True, null=True)),
                ('def_r2',        models.FloatField(blank=True, null=True)),
                ('n_train_off',   models.IntegerField(default=0)),
                ('n_train_def',   models.IntegerField(default=0)),
                ('off_features',  models.JSONField(default=list)),
                ('def_features',  models.JSONField(default=list)),
                ('prior_sd_off',  models.FloatField(blank=True, null=True, help_text='sqrt(1 - R²) × σ_target for offense')),
                ('prior_sd_def',  models.FloatField(blank=True, null=True)),
                ('computed_at',   models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-season__year']},
        ),
    ]
