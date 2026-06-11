from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connections
from ncaa.models import Season


class Command(BaseCommand):
    help = "Backfill pre-tournament snapshots for all historical seasons"

    def add_arguments(self, parser):
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            metavar="N",
            help="Number of seasons to process in parallel (default: 1, sequential)",
        )

    def handle(self, *args, **options):
        workers = options["workers"]
        seasons = Season.objects.filter(year__gte=2019, year__lte=2026).exclude(year=2020).order_by('year')

        if workers <= 1:
            for season in seasons:
                self._run_season(season)
            return

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._run_season, season): season for season in seasons}
            for future in as_completed(futures):
                future.result()

    def _run_season(self, season):
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Generating Pre-Tournament snapshot for {season.year}")
        self.stdout.write(f"{'='*60}\n")

        try:
            # Step 1: Compute metrics
            call_command("compute_team_metrics", season=season.year, pre_tournament=True)

            # Step 2: Compute adjusted ratings
            call_command("compute_adjusted_ratings", season=season.year, pre_tournament=True)

            # Step 3: Compute adjusted four factors
            call_command("compute_adjusted_four_factors", season=season.year, pre_tournament=True)

            # Step 4: Compute four factor index
            call_command("compute_four_factor_index", season=season.year, pre_tournament=True)

            # Step 5: Compute SOS
            call_command("compute_sos", season=season.year, pre_tournament=True)

            # Step 6: Compute WAB
            call_command("compute_wab", season=season.year, pre_tournament=True)

            self.stdout.write(self.style.SUCCESS(f"✓ Completed {season.year} Pre-Tournament Backfill\n"))
        finally:
            connections.close_all()
