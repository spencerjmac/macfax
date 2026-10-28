"""Set the current NCAA and NBA seasons together, preserving historical rows.

Run after deploying a new season, then ingest current-season data. Year is the
ENDING year: --season 2027 means 2026–27. No historical statistics are erased.

    python manage.py activate_basketball_seasons --season 2027 --dry-run
    python manage.py activate_basketball_seasons --season 2027
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ncaa.models import Season
from nba.models import NBASeason


class Command(BaseCommand):
    help = "Activate the ending-year NCAA and NBA season in both databases"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True, help="Ending year (2027 = 2026–27)")
        parser.add_argument("--dry-run", action="store_true", help="Report actions only")

    def handle(self, *args, **options):
        year = options["season"]
        if year < 2000 or year > 2100:
            raise CommandError("Provide a valid season ending year (e.g. 2027).")

        label = f"{year - 1}-{str(year)[-2:]}"
        if options["dry_run"]:
            self.stdout.write(f"Would activate {label} (year={year}) for NCAA and NBA.")
            return

        with transaction.atomic():
            for model in (Season, NBASeason):
                season, _ = model.objects.get_or_create(
                    year=year,
                    defaults={"display_name": label, "is_current": False},
                )
                # Existing rows might have been seeded earlier without being current.
                if season.display_name != label or not season.is_current:
                    season.display_name = label
                    season.is_current = True
                    season.save(update_fields=["display_name", "is_current"])
                self.stdout.write(f"{model.__name__}: {label} is current")

        self.stdout.write(self.style.SUCCESS("Current seasons set; now ingest and compute the season data."))
