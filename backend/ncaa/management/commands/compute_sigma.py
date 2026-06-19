"""
Management command to compute prediction sigma (standard deviation of errors)

Uses actual game results vs forecast_game() predictions to calibrate the
win probability normal CDF. One residual per game (home-team perspective).

Requires: compute_national_averages, compute_adjusted_ratings, compute_hca
must all have run first for the target season.
"""
import statistics

from django.core.management.base import BaseCommand

from api.matchup_engine import forecast_game
from ncaa.models import Game, NationalAverages, Season, TeamSeasonRatings


class Command(BaseCommand):
    help = 'Compute prediction sigma from forecast_game residuals and store in NationalAverages'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            default=2026,
            help='Season year (default: 2026)'
        )

    def handle(self, *args, **options):
        from ncaa.models import PipelineConfig
        cfg = PipelineConfig.get_config()

        season_year = options['season']

        self.stdout.write(f'\n{"="*80}')
        self.stdout.write(f'COMPUTING PREDICTION SIGMA (Error Standard Deviation)')
        self.stdout.write(f'{"="*80}\n')

        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Season {season_year} not found!'))
            return

        self.stdout.write(f'Season: {season.display_name}')

        try:
            nat_avg = NationalAverages.objects.get(season=season)
        except NationalAverages.DoesNotExist:
            self.stdout.write(self.style.ERROR('National averages not computed yet! Run compute_national_averages first.'))
            return
        if nat_avg.avg_ortg is None:
            self.stdout.write(self.style.ERROR('National averages have null values! Run compute_national_averages first.'))
            return

        if nat_avg.hca_points is None:
            self.stdout.write(self.style.WARNING('HCA not computed yet. Run compute_hca first.'))
            self.stdout.write(self.style.WARNING(f'Using fallback HCA of {cfg.fallback_hca} points.'))
            hca = cfg.fallback_hca
        else:
            hca = nat_avg.hca_points
            self.stdout.write(f'Using HCA: {hca:.2f} points')

        # Preload team ratings — use .values() to avoid per-game ORM hits
        team_ratings = {
            r['team_id']: r
            for r in TeamSeasonRatings.objects.filter(
                season=season,
                team__is_d1=True,
                adj_o__isnull=False,
                adj_d__isnull=False,
                adj_em__isnull=False,
                adj_tempo__isnull=False,
            ).values('team_id', 'adj_o', 'adj_d', 'adj_em', 'adj_tempo')
        }
        self.stdout.write(f'Team ratings cached: {len(team_ratings)} teams')

        # Load completed D1 vs D1 games — one record per game (not TeamGameStats)
        games = list(
            Game.objects.filter(
                season_year=season_year,
                status='final',
                home_score__isnull=False,
                away_score__isnull=False,
                home_team__is_d1=True,
                away_team__is_d1=True,
            ).values('home_team_id', 'away_team_id', 'home_score', 'away_score', 'neutral_site')
        )
        self.stdout.write(f'Total D1 vs D1 games: {len(games)}')

        if not games:
            self.stdout.write(self.style.ERROR('No games found!'))
            return

        residuals = []
        n_skipped = 0

        for g in games:
            rh = team_ratings.get(g['home_team_id'])
            ra = team_ratings.get(g['away_team_id'])
            if not rh or not ra:
                n_skipped += 1
                continue

            site = 'neutral' if g['neutral_site'] else 'home'

            try:
                result = forecast_game(
                    adj_o_a=rh['adj_o'], adj_d_a=rh['adj_d'],
                    adj_em_a=rh['adj_em'], tempo_a=rh['adj_tempo'],
                    adj_o_b=ra['adj_o'], adj_d_b=ra['adj_d'],
                    adj_em_b=ra['adj_em'], tempo_b=ra['adj_tempo'],
                    nat_avg_ortg=nat_avg.avg_ortg,
                    hca_points=hca,
                    sigma=cfg.fallback_sigma,
                    site=site,
                )
            except Exception as e:
                n_skipped += 1
                continue

            actual_margin = g['home_score'] - g['away_score']
            residual = actual_margin - result['margin']
            residuals.append(residual)

        if not residuals:
            self.stdout.write(self.style.ERROR('No residuals computed (missing team ratings)!'))
            return

        sigma = statistics.stdev(residuals) if len(residuals) > 1 else cfg.fallback_sigma
        mean_error = statistics.mean(residuals)
        median_error = statistics.median(residuals)

        nat_avg.prediction_sigma = sigma
        nat_avg.save()

        self.stdout.write(f'\n{"-"*80}')
        self.stdout.write('RESIDUAL STATISTICS')
        self.stdout.write(f'{"-"*80}')
        self.stdout.write(f'  Games analyzed: {len(residuals)}  |  Skipped: {n_skipped}')
        self.stdout.write(f'  Mean error (bias): {mean_error:.2f} points')
        self.stdout.write(f'  Median error:      {median_error:.2f} points')
        self.stdout.write(self.style.SUCCESS(f'  Sigma (std dev):   {sigma:.2f} points'))

        self.stdout.write(f'\n{"-"*80}')
        self.stdout.write('PREDICTION INTERVALS (assuming normal distribution)')
        self.stdout.write(f'{"-"*80}')
        self.stdout.write(f'  68% of games within ±{sigma:.1f} points of prediction')
        self.stdout.write(f'  95% of games within ±{2*sigma:.1f} points of prediction')
        self.stdout.write(f'  99% of games within ±{3*sigma:.1f} points of prediction')

        self.stdout.write(f'\n{"="*80}')
        self.stdout.write(self.style.SUCCESS(f'✓ Sigma stored: {sigma:.2f} points'))
        self.stdout.write(f'{"="*80}\n')
