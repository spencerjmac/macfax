"""
Management command: snapshot_predictions

Saves locked pregame PredictionSnapshot rows for upcoming games.
Must be run BEFORE games tip off. Snapshots are immutable once locked.

Usage:
    python manage.py snapshot_predictions --season 2026
    python manage.py snapshot_predictions --season 2026 --days-ahead 3
    python manage.py snapshot_predictions --season 2026 --date 2026-01-15
    python manage.py snapshot_predictions --season 2026 --force
"""

import sys
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ncaa.models import Game, Season, NationalAverages, TeamSeasonRatings
from api.matchup_engine import forecast_game
from validation.models import PredictionSnapshot, MATCHUP_SNAPSHOT_VERSION


class Command(BaseCommand):
    help = "Save locked pregame PredictionSnapshots for upcoming games."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True, metavar="YEAR")
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Specific date to snapshot (YYYY-MM-DD). Default: today.",
        )
        parser.add_argument(
            "--days-ahead",
            type=int,
            default=1,
            help="Number of days ahead to include (default: 1 = today only).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing locked snapshots for the same game/model_version.",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        force = options["force"]
        days_ahead = options["days_ahead"]

        if options["date"]:
            try:
                start_date = date.fromisoformat(options["date"])
            except ValueError:
                raise CommandError(f"Invalid date format: {options['date']}. Use YYYY-MM-DD.")
        else:
            start_date = date.today()

        end_date = start_date + timedelta(days=days_ahead - 1)

        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(f"SNAPSHOT PREDICTIONS — season {season_year}")
        self.stdout.write(f"Date range: {start_date} to {end_date}")
        self.stdout.write(f"Model version: {MATCHUP_SNAPSHOT_VERSION}")
        self.stdout.write(f"Force overwrite: {force}")
        self.stdout.write(f"{'='*70}\n")

        # Fetch required data
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            raise CommandError(f"Season {season_year} not found.")

        try:
            nat_avg = NationalAverages.objects.get(season=season)
        except NationalAverages.DoesNotExist:
            raise CommandError(f"NationalAverages not computed for season {season_year}. Run compute_national_averages first.")

        hca = nat_avg.hca_points or 1.85
        sigma = nat_avg.prediction_sigma or 11.08
        avg_ortg = nat_avg.avg_ortg or 108.0

        # Find scheduled games in date range
        games = (
            Game.objects
            .filter(
                season_year=season_year,
                status='scheduled',
                game_date__gte=start_date,
                game_date__lte=end_date,
            )
            .select_related('home_team', 'away_team')
            .order_by('game_date', 'id')
        )

        total = games.count()
        self.stdout.write(f"Found {total} scheduled game(s) in range.\n")

        if total == 0:
            self.stdout.write(self.style.WARNING("No scheduled games found. Nothing to snapshot."))
            return

        # Pre-load all ratings for this season into a dict keyed by team_id
        ratings_qs = TeamSeasonRatings.objects.filter(season=season).select_related('team')
        ratings_map = {r.team_id: r for r in ratings_qs}

        saved = 0
        skipped = 0
        errors = 0

        for game in games:
            game_label = f"{game.away_team} @ {game.home_team} ({game.game_date})"

            # Skip if snapshot already locked (unless --force)
            existing = PredictionSnapshot.objects.filter(
                game=game,
                model_version=MATCHUP_SNAPSHOT_VERSION,
                is_locked=True,
            ).first()

            if existing and not force:
                self.stdout.write(f"  [SKIP] {game_label} — snapshot already locked")
                skipped += 1
                continue

            # Fetch ratings
            home_ratings = ratings_map.get(game.home_team_id)
            away_ratings = ratings_map.get(game.away_team_id)

            if not home_ratings or not away_ratings:
                missing = []
                if not home_ratings:
                    missing.append(str(game.home_team))
                if not away_ratings:
                    missing.append(str(game.away_team))
                self.stdout.write(
                    self.style.WARNING(f"  [WARN] {game_label} — missing ratings for: {', '.join(missing)}")
                )
                errors += 1
                continue

            # Compute forecast
            site = 'neutral' if game.neutral_site else 'home'
            try:
                forecast = forecast_game(
                    adj_o_a=home_ratings.adj_o,
                    adj_d_a=home_ratings.adj_d,
                    adj_em_a=home_ratings.adj_em,
                    tempo_a=home_ratings.adj_tempo,
                    adj_o_b=away_ratings.adj_o,
                    adj_d_b=away_ratings.adj_d,
                    adj_em_b=away_ratings.adj_em,
                    tempo_b=away_ratings.adj_tempo,
                    nat_avg_ortg=avg_ortg,
                    hca_points=hca,
                    sigma=sigma,
                    site=site,
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  [FAIL] {game_label} — forecast error: {e}"))
                errors += 1
                continue

            predicted_winner = game.home_team if forecast['prob_a'] > 0.5 else game.away_team
            now = timezone.now()

            if existing and force:
                existing.delete()

            PredictionSnapshot.objects.create(
                game=game,
                season_year=season_year,
                model_version=MATCHUP_SNAPSHOT_VERSION,
                snapshot_type='pregame',
                locked_at=now,
                home_team=game.home_team,
                away_team=game.away_team,
                projected_home_score=forecast['pts_a'],
                projected_away_score=forecast['pts_b'],
                projected_home_margin=forecast['margin'],
                projected_total=forecast['total'],
                home_win_probability=forecast['prob_a'],
                away_win_probability=forecast['prob_b'],
                predicted_winner=predicted_winner,
                home_adj_o=home_ratings.adj_o,
                home_adj_d=home_ratings.adj_d,
                away_adj_o=away_ratings.adj_o,
                away_adj_d=away_ratings.adj_d,
                nat_avg_ortg=avg_ortg,
                hca_points=hca,
                sigma_used=sigma,
                is_locked=True,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"  [OK] {game_label} — "
                    f"{forecast['pts_a']:.1f}-{forecast['pts_b']:.1f} "
                    f"(p_home={forecast['prob_a']:.2f})"
                )
            )
            saved += 1

        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(f"Saved: {saved}  Skipped: {skipped}  Errors: {errors}")
        self.stdout.write(f"{'='*70}\n")

        if errors > 0:
            sys.exit(1)
