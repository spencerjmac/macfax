"""
Management command: compute_validation_results

Computes accuracy metrics for completed games that have locked PredictionSnapshots.
Saves one GameValidationResult per snapshot.

Usage:
    python manage.py compute_validation_results --season 2026
    python manage.py compute_validation_results --season 2026 --recompute
"""

import math
import sys

from django.core.management.base import BaseCommand
from django.db.models import F

from ncaa.models import Game
from validation.models import PredictionSnapshot, GameValidationResult, MATCHUP_SNAPSHOT_VERSION


class Command(BaseCommand):
    help = "Compute accuracy metrics for completed games with locked prediction snapshots."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True, metavar="YEAR")
        parser.add_argument(
            "--recompute",
            action="store_true",
            help="Recompute and overwrite existing GameValidationResult rows.",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        recompute = options["recompute"]

        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(f"COMPUTE VALIDATION RESULTS — season {season_year}")
        self.stdout.write(f"Recompute mode: {recompute}")
        self.stdout.write(f"{'='*70}\n")

        # Find completed games with locked snapshots
        qs = PredictionSnapshot.objects.filter(
            is_locked=True,
            season_year=season_year,
            game__status='final',
        ).select_related('game', 'home_team', 'away_team', 'predicted_winner', 'game__home_team', 'game__away_team')

        if not recompute:
            already_evaluated = GameValidationResult.objects.filter(
                season_year=season_year
            ).values_list('prediction_snapshot_id', flat=True)
            qs = qs.exclude(id__in=already_evaluated)

        total = qs.count()
        self.stdout.write(f"Found {total} snapshot(s) to evaluate.\n")

        if total == 0:
            self.stdout.write(self.style.WARNING("Nothing to compute."))
            return

        computed = 0
        errors = 0

        for snapshot in qs:
            game = snapshot.game

            if game.home_score is None or game.away_score is None:
                self.stdout.write(
                    self.style.WARNING(f"  [SKIP] {game} — missing final scores")
                )
                errors += 1
                continue

            try:
                if recompute:
                    GameValidationResult.objects.filter(prediction_snapshot=snapshot).delete()

                actual_home_margin = game.home_score - game.away_score
                actual_total = game.home_score + game.away_score

                margin_error = snapshot.projected_home_margin - actual_home_margin
                margin_abs_error = abs(margin_error)

                home_score_error = snapshot.projected_home_score - game.home_score
                away_score_error = snapshot.projected_away_score - game.away_score
                home_score_abs_error = abs(home_score_error)
                away_score_abs_error = abs(away_score_error)
                avg_score_abs_error = (home_score_abs_error + away_score_abs_error) / 2

                total_error = snapshot.projected_total - actual_total
                total_abs_error = abs(total_error)

                # Winner
                winner = game.winner
                winner_correct = (
                    snapshot.predicted_winner_id == winner.id
                    if winner is not None
                    else False
                )

                # Probability calibration
                actual_outcome = 1.0 if (winner == game.home_team) else 0.0
                brier = (snapshot.home_win_probability - actual_outcome) ** 2
                p_correct = (
                    snapshot.home_win_probability
                    if actual_outcome == 1.0
                    else snapshot.away_win_probability
                )
                log_loss_val = -math.log(max(p_correct, 1e-7))

                # Upset tracking: upset = lower adj_em (or predicted underdog) wins
                # Use predicted_winner as proxy for favorite; if actual winner differs, it's an upset
                predicted_favorite = snapshot.predicted_winner
                predicted_upset = predicted_favorite != game.home_team and predicted_favorite is not None
                actual_upset = (winner != game.home_team) if winner else False
                upset_correct = None
                if predicted_upset:
                    upset_correct = (predicted_favorite == winner) if winner else None

                GameValidationResult.objects.create(
                    prediction_snapshot=snapshot,
                    game=game,
                    season_year=season_year,
                    actual_home_score=game.home_score,
                    actual_away_score=game.away_score,
                    actual_home_margin=actual_home_margin,
                    actual_total=actual_total,
                    winner_correct=winner_correct,
                    margin_error=margin_error,
                    margin_abs_error=margin_abs_error,
                    home_score_error=home_score_error,
                    away_score_error=away_score_error,
                    home_score_abs_error=home_score_abs_error,
                    away_score_abs_error=away_score_abs_error,
                    avg_score_abs_error=avg_score_abs_error,
                    total_error=total_error,
                    total_abs_error=total_abs_error,
                    brier_score=brier,
                    log_loss=log_loss_val,
                    predicted_upset=predicted_upset,
                    actual_upset=actual_upset,
                    upset_correct=upset_correct,
                )

                tick = '✓' if winner_correct else '✗'
                self.stdout.write(
                    f"  [{tick}] {game} — "
                    f"margin err: {margin_error:+.1f}  brier: {brier:.3f}"
                )
                computed += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  [FAIL] {game}: {e}"))
                errors += 1

        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(f"Computed: {computed}  Errors: {errors}")
        self.stdout.write(f"{'='*70}\n")

        if errors > 0:
            sys.exit(1)
