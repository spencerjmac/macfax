"""
Ensure Team table has a row for every canonical name in ncaa_team_name_mappings.yml.
Run this before game ingestion so NCAA short names (e.g. "Central Mich.") can resolve
to a Team (e.g. "Central Michigan").

Usage:
    python manage.py ensure_ncaa_teams
    python manage.py ensure_ncaa_teams --dry-run
"""

import yaml
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from core.models import Team


class Command(BaseCommand):
    help = "Create missing Team rows for every canonical name in ncaa_team_name_mappings.yml"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be created",
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

        canonical_names = sorted(set(mappings.values()))
        self.stdout.write(f"Found {len(canonical_names)} unique canonical names in {yaml_path.name}\n")

        created = 0
        existing = 0
        errors = 0

        for name in canonical_names:
            if not name or not name.strip():
                continue
            try:
                name_clean = name.strip()
                if dry_run:
                    if Team.objects.filter(name=name_clean).exists():
                        existing += 1
                    else:
                        self.stdout.write(f"  Would create: {name_clean}")
                        created += 1
                    continue
                slug = slugify(name_clean) or "team"
                suffix = 0
                while True:
                    try:
                        team, was_created = Team.objects.get_or_create(
                            name=name_clean,
                            defaults={"is_d1": True, "slug": slug},
                        )
                        break
                    except Exception as slug_error:
                        if "slug" in str(slug_error).lower() or "unique" in str(slug_error).lower():
                            suffix += 1
                            slug = f"{slugify(name_clean) or 'team'}-{suffix}"
                        else:
                            raise
                if was_created:
                    self.stdout.write(self.style.SUCCESS(f"  Created: {team.name}"))
                    created += 1
                else:
                    existing += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  Error for '{name}': {e}"))
                errors += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Existing: {existing} | Created: {created} | Errors: {errors}"
            )
        )
        if dry_run and created:
            self.stdout.write(self.style.WARNING("Run without --dry-run to create teams."))
