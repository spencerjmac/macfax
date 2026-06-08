from django.core.management.base import BaseCommand
from django.core.management import call_command
from ncaa.models import Season

class Command(BaseCommand):
    help = "Backfill pre-tournament snapshots for all historical seasons"

    def handle(self, *args, **options):
        seasons = Season.objects.filter(year__gte=2019, year__lte=2026).exclude(year=2020).order_by('year')

        for season in seasons:
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"Generating Pre-Tournament snapshot for {season.year}")
            self.stdout.write(f"{'='*60}\n")
            
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
