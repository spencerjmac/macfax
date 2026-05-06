"""
Management command: compute_validation_summaries

Aggregates GameValidationResult rows into ValidationSummary rows for:
    - full season
    - last 7 days
    - last 30 days
    - all time

Usage:
    python manage.py compute_validation_summaries --season 2026
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Avg, Count, Sum, Q
from django.utils import timezone

from validation.models import GameValidationResult, ValidationSummary, MATCHUP_SNAPSHOT_VERSION


PERIOD_CONFIGS = [
    ('season', None),   # all games in the season
    ('last_7', 7),
    ('last_30', 30),
    ('all_time', None), # all evaluated games regardless of season
]


class Command(BaseCommand):
    help = "Aggregate validation results into summary rows (season, last_7, last_30, all_time)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True, metavar="YEAR")

    def handle(self, *args, **options):
        season_year = options["season"]
        today = date.today()

        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(f"COMPUTE VALIDATION SUMMARIES — season {season_year}")
        self.stdout.write(f"{'='*70}\n")

        for period_type, days in PERIOD_CONFIGS:
            self._compute_period(season_year, period_type, days, today)

        self.stdout.write(self.style.SUCCESS(f"\nSummaries updated for season {season_year}.\n"))

    def _compute_period(self, season_year, period_type, days, today):
        if period_type == 'all_time':
            qs = GameValidationResult.objects.all()
            period_start = None
            period_end = today
        elif period_type == 'season':
            qs = GameValidationResult.objects.filter(season_year=season_year)
            period_start = None
            period_end = today
        else:
            period_start = today - timedelta(days=days)
            period_end = today
            qs = GameValidationResult.objects.filter(
                season_year=season_year,
                game__game_date__gte=period_start,
                game__game_date__lte=period_end,
            )

        total = qs.count()

        if total == 0:
            self.stdout.write(f"  [{period_type}] No results yet — skipping.")
            return

        agg = qs.aggregate(
            correct_count=Count('id', filter=Q(winner_correct=True)),
            spread_mae=Avg('margin_abs_error'),
            score_mae=Avg('avg_score_abs_error'),
            total_mae=Avg('total_abs_error'),
            avg_margin_bias=Avg('margin_error'),
            avg_brier=Avg('brier_score'),
            avg_log_loss=Avg('log_loss'),
            upset_preds=Count('id', filter=Q(predicted_upset=True)),
            upset_hits=Count('id', filter=Q(predicted_upset=True, upset_correct=True)),
        )

        winner_accuracy = agg['correct_count'] / total if total > 0 else 0.0
        upset_preds = agg['upset_preds'] or 0
        upset_hits = agg['upset_hits'] or 0
        upset_precision = (upset_hits / upset_preds) if upset_preds > 0 else None

        summary, created = ValidationSummary.objects.update_or_create(
            season_year=season_year,
            model_version=MATCHUP_SNAPSHOT_VERSION,
            period_type=period_type,
            defaults={
                'period_start': period_start,
                'period_end': period_end,
                'games_evaluated': total,
                'winner_accuracy': winner_accuracy,
                'spread_mae': agg['spread_mae'] or 0.0,
                'score_mae': agg['score_mae'] or 0.0,
                'total_mae': agg['total_mae'] or 0.0,
                'average_margin_bias': agg['avg_margin_bias'] or 0.0,
                'brier_score': agg['avg_brier'] or 0.0,
                'log_loss': agg['avg_log_loss'],
                'upset_predictions': upset_preds,
                'upset_hits': upset_hits,
                'upset_precision': upset_precision,
            },
        )

        action = 'Created' if created else 'Updated'
        self.stdout.write(
            self.style.SUCCESS(
                f"  [{period_type}] {action}: {total} games, "
                f"winner_acc={winner_accuracy:.1%}, spread_mae={agg['spread_mae']:.2f}"
            )
        )
