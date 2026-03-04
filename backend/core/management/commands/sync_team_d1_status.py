"""
Set Team.is_d1 from the official D1 list in ncaa_team_name_mappings.yml.

The YAML lists ~365 canonical D1 team names (right-hand side of each mapping).
Any team in the DB whose name matches one of those is D1; all others are set to
non-D1 (e.g. D2, D3, NAIA, or opponents created during game ingest).

Usage:
    python manage.py sync_team_d1_status
    python manage.py sync_team_d1_status --dry-run
"""

import yaml
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Team


class Command(BaseCommand):
    help = "Set Team.is_d1 from ncaa_team_name_mappings.yml (D1 = names in file)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would change; do not update",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        base_dir = Path(settings.BASE_DIR)
        yaml_path = base_dir / "mappings" / "ncaa_team_name_mappings.yml"

        if not yaml_path.exists():
            self.stderr.write(self.style.ERROR(f"Not found: {yaml_path}"))
            return

        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f) or {}
        mappings = data.get("ncaa", {})
        if not mappings:
            self.stderr.write(self.style.ERROR("No 'ncaa' key in YAML"))
            return

        d1_canonical_names = set(m.strip() for m in mappings.values() if m and str(m).strip())
        self.stdout.write(
            f"Official D1 list: {len(d1_canonical_names)} names from {yaml_path.name}\n"
        )

        # Teams in DB: match by exact name
        all_teams = Team.objects.all().order_by("name")
        total = all_teams.count()

        to_d1 = []
        to_non_d1 = []
        for t in all_teams:
            if t.name.strip() in d1_canonical_names:
                if not t.is_d1:
                    to_d1.append(t)
            else:
                if t.is_d1:
                    to_non_d1.append(t)

        self.stdout.write(f"Teams in DB: {total}")
        self.stdout.write(f"  Would set is_d1=True:  {len(to_d1)}")
        self.stdout.write(f"  Would set is_d1=False: {len(to_non_d1)}")

        if dry_run:
            if to_d1:
                self.stdout.write(self.style.WARNING("\nWould mark as D1:"))
                for t in to_d1[:20]:
                    self.stdout.write(f"  {t.name}")
                if len(to_d1) > 20:
                    self.stdout.write(f"  ... and {len(to_d1) - 20} more")
            if to_non_d1:
                self.stdout.write(self.style.WARNING("\nWould mark as non-D1:"))
                for t in to_non_d1[:20]:
                    self.stdout.write(f"  {t.name}")
                if len(to_non_d1) > 20:
                    self.stdout.write(f"  ... and {len(to_non_d1) - 20} more")
            self.stdout.write(
                self.style.WARNING("\nRun without --dry-run to apply changes.")
            )
            return

        if not to_d1 and not to_non_d1:
            self.stdout.write(self.style.SUCCESS("No changes needed."))
            return

        with transaction.atomic():
            if to_d1:
                Team.objects.filter(pk__in=[t.pk for t in to_d1]).update(is_d1=True)
                self.stdout.write(self.style.SUCCESS(f"  Set is_d1=True for {len(to_d1)} team(s)."))
            if to_non_d1:
                Team.objects.filter(pk__in=[t.pk for t in to_non_d1]).update(is_d1=False)
                self.stdout.write(
                    self.style.SUCCESS(f"  Set is_d1=False for {len(to_non_d1)} team(s).")
                )

        d1_count = Team.objects.filter(is_d1=True).count()
        self.stdout.write(self.style.SUCCESS(f"\nDone. Teams now marked D1: {d1_count}"))
