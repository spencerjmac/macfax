"""
Management command: import_logos
Scans backend/static/logos for team logo files and sets Team.logo_url in the database.
Uses a name->filename mapping so ESPN-style filenames (e.g. alabama_crimson_tide.png)
match Team names. Logos must already be in backend/static/logos.

Usage:
    python manage.py import_logos
    python manage.py import_logos --dry-run
    python manage.py import_logos --logos-dir /path/to/logos
    python manage.py import_logos --clear-missing
"""

import os
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import Team
from core.utils.team_logo_mapping import TEAM_NAME_TO_LOGO_STEM

# Extensions we consider as logo images (order = preference when multiple exist)
LOGO_EXTENSIONS = (".png", ".svg", ".webp", ".jpg", ".jpeg", ".gif")


class Command(BaseCommand):
    help = "Set Team.logo_url from logo files in backend/static/logos using name→filename mapping"

    def add_arguments(self, parser):
        parser.add_argument(
            "--logos-dir",
            type=str,
            default=None,
            help="Directory containing logo files (default: backend/static/logos)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be updated",
        )
        parser.add_argument(
            "--clear-missing",
            action="store_true",
            help="Set logo_url to NULL for teams with no matching file",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        clear_missing = options["clear_missing"]
        logos_dir_arg = options.get("logos_dir")

        base = Path(settings.BASE_DIR)
        if logos_dir_arg:
            logos_dir = Path(logos_dir_arg).resolve()
        elif os.getenv("LOGOS_DIR"):
            logos_dir = Path(os.environ["LOGOS_DIR"]).resolve()
        else:
            logos_dir = base / "static" / "logos"

        if not logos_dir.exists():
            self.stderr.write(
                self.style.ERROR(f"Logos directory does not exist: {logos_dir}")
            )
            return

        # Build map: logo stem (filename without extension) -> actual filename
        # So we can find alabama_crimson_tide.png from stem "alabama_crimson_tide"
        stem_to_filename = {}
        for f in logos_dir.iterdir():
            if f.is_file() and f.suffix.lower() in LOGO_EXTENSIONS:
                stem = f.stem
                if stem not in stem_to_filename:
                    stem_to_filename[stem] = f.name

        self.stdout.write(f"Found {len(stem_to_filename)} logo files in {logos_dir}\n")

        updated = 0
        cleared = 0
        no_mapping = 0
        no_file = 0

        for team in Team.objects.all():
            # Look up logo stem by team name (or first alias that has a mapping)
            logo_stem = TEAM_NAME_TO_LOGO_STEM.get(team.name)
            if logo_stem is None and team.aliases:
                for alias in team.aliases:
                    if isinstance(alias, str) and alias in TEAM_NAME_TO_LOGO_STEM:
                        logo_stem = TEAM_NAME_TO_LOGO_STEM[alias]
                        break

            if logo_stem is None:
                no_mapping += 1
                if clear_missing and team.logo_url:
                    if not dry_run:
                        team.logo_url = None
                        team.save(update_fields=["logo_url"])
                    cleared += 1
                    self.stdout.write(self.style.WARNING(f"  {team.name}: no mapping, cleared"))
                else:
                    self.stdout.write(self.style.WARNING(f"  {team.name}: no mapping"))
                continue

            filename = stem_to_filename.get(logo_stem)
            if filename is None and logo_stem:
                # Try ASCII-normalized stem (e.g. san_josé -> san_jose)
                ascii_stem = unicodedata.normalize("NFKD", logo_stem).encode("ascii", "ignore").decode()
                filename = stem_to_filename.get(ascii_stem)
            if filename is None:
                no_file += 1
                if clear_missing and team.logo_url:
                    if not dry_run:
                        team.logo_url = None
                        team.save(update_fields=["logo_url"])
                    cleared += 1
                self.stdout.write(self.style.WARNING(f"  {team.name}: expected {logo_stem}.png (not found)"))
                continue

            new_url = f"/static/logos/{filename}"
            if team.logo_url != new_url:
                if not dry_run:
                    team.logo_url = new_url
                    team.save(update_fields=["logo_url"])
                updated += 1
                self.stdout.write(f"  {team.name}: {new_url}")

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Updated: {updated}, Cleared: {cleared}, No mapping: {no_mapping}, File missing: {no_file}"
                + (" (dry run)" if dry_run else "")
            )
        )
