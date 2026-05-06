"""
Validation API views.

GET /api/validation/summary/?season=YEAR
GET /api/validation/weekly/?season=YEAR
GET /api/validation/recent-games/?season=YEAR&limit=N
"""

from datetime import timedelta

from django.db.models import Avg, Count, Q
from rest_framework.response import Response
from rest_framework.views import APIView

from validation.models import GameValidationResult, ValidationSummary, MATCHUP_SNAPSHOT_VERSION


def _latest_season_year():
    from ncaa.models import Season
    s = Season.objects.filter(is_current=True).first()
    if s:
        return s.year
    s = Season.objects.order_by('-year').first()
    return s.year if s else None


class ValidationSummaryView(APIView):
    def get(self, request):
        season_year = request.query_params.get('season')
        if season_year:
            season_year = int(season_year)
        else:
            season_year = _latest_season_year()

        summaries = ValidationSummary.objects.filter(
            season_year=season_year,
            model_version=MATCHUP_SNAPSHOT_VERSION,
        ).order_by('period_type')

        data = [
            {
                'period_type': s.period_type,
                'period_start': s.period_start.isoformat() if s.period_start else None,
                'period_end': s.period_end.isoformat() if s.period_end else None,
                'games_evaluated': s.games_evaluated,
                'winner_accuracy': round(s.winner_accuracy, 4),
                'spread_mae': round(s.spread_mae, 3),
                'score_mae': round(s.score_mae, 3),
                'total_mae': round(s.total_mae, 3),
                'average_margin_bias': round(s.average_margin_bias, 3),
                'brier_score': round(s.brier_score, 4),
                'log_loss': round(s.log_loss, 4) if s.log_loss is not None else None,
                'upset_predictions': s.upset_predictions,
                'upset_hits': s.upset_hits,
                'upset_precision': round(s.upset_precision, 4) if s.upset_precision is not None else None,
                'updated_at': s.updated_at.isoformat(),
            }
            for s in summaries
        ]

        return Response({'season': season_year, 'model_version': MATCHUP_SNAPSHOT_VERSION, 'summaries': data})


class ValidationWeeklyView(APIView):
    def get(self, request):
        season_year = request.query_params.get('season')
        if season_year:
            season_year = int(season_year)
        else:
            season_year = _latest_season_year()

        results = (
            GameValidationResult.objects
            .filter(season_year=season_year)
            .select_related('game')
            .order_by('game__game_date')
        )

        # Group by ISO week start (Monday)
        from collections import defaultdict
        weeks: dict = defaultdict(lambda: {'games': 0, 'correct': 0, 'margin_abs_errors': [], 'score_abs_errors': []})

        for r in results:
            game_date = r.game.game_date
            # Monday of that week
            monday = game_date - timedelta(days=game_date.weekday())
            key = monday.isoformat()
            w = weeks[key]
            w['games'] += 1
            if r.winner_correct:
                w['correct'] += 1
            w['margin_abs_errors'].append(r.margin_abs_error)
            w['score_abs_errors'].append(r.avg_score_abs_error)

        week_data = []
        for week_start in sorted(weeks.keys()):
            w = weeks[week_start]
            n = w['games']
            week_data.append({
                'week_start': week_start,
                'games': n,
                'winner_accuracy': round(w['correct'] / n, 4) if n else 0.0,
                'spread_mae': round(sum(w['margin_abs_errors']) / n, 3) if n else 0.0,
                'score_mae': round(sum(w['score_abs_errors']) / n, 3) if n else 0.0,
            })

        return Response({'season': season_year, 'weeks': week_data})


class ValidationRecentGamesView(APIView):
    def get(self, request):
        season_year = request.query_params.get('season')
        limit = request.query_params.get('limit', 50)

        if season_year:
            season_year = int(season_year)
        else:
            season_year = _latest_season_year()

        try:
            limit = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            limit = 50

        results = (
            GameValidationResult.objects
            .filter(season_year=season_year)
            .select_related(
                'game',
                'game__home_team',
                'game__away_team',
                'prediction_snapshot',
            )
            .order_by('-game__game_date', '-game__id')
            [:limit]
        )

        games = [
            {
                'game_date': r.game.game_date.isoformat(),
                'home_team': r.game.home_team.name,
                'away_team': r.game.away_team.name,
                'actual_home_score': r.actual_home_score,
                'actual_away_score': r.actual_away_score,
                'projected_home_score': round(r.prediction_snapshot.projected_home_score, 1),
                'projected_away_score': round(r.prediction_snapshot.projected_away_score, 1),
                'projected_home_margin': round(r.prediction_snapshot.projected_home_margin, 1),
                'actual_home_margin': r.actual_home_margin,
                'margin_error': round(r.margin_error, 1),
                'home_win_probability': round(r.prediction_snapshot.home_win_probability, 3),
                'winner_correct': r.winner_correct,
                'brier_score': round(r.brier_score, 4),
            }
            for r in results
        ]

        return Response({'season': season_year, 'games': games})
