"""
Management command: fix_team_duplicates

Resolves the situation where ingest_gamelogs ran before ensure_ncaa_teams,
causing game data to be stored against informal team names (e.g. "UConn",
"App State") instead of the canonical names ("Connecticut", "Appalachian St.").

For every duplicate pair detected from ncaa_team_name_mappings.yml, this command:
  1. Moves all TeamGameStats, Game FKs, TeamSeasonRatings, TeamSeasonMetrics, and
     TeamExternalId records from the informal-name team to the canonical team.
  2. Adds the informal name as an alias on the canonical team.
  3. Marks the informal-name team as non-D1 so it no longer clutters lists.

This is safe to re-run: it is idempotent after the first pass.

Usage:
    python manage.py fix_team_duplicates
    python manage.py fix_team_duplicates --dry-run
"""

import yaml
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Merge duplicate informal-name teams into canonical teams from ncaa_team_name_mappings.yml"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be done without making any changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        from core.models import (
            Team,
            Game,
            TeamGameStats,
            TeamSeasonRatings,
            TeamSeasonMetrics,
            TeamExternalId,
        )

        # Load mappings
        yaml_path = Path(settings.BASE_DIR) / "mappings" / "ncaa_team_name_mappings.yml"
        if not yaml_path.exists():
            self.stderr.write(self.style.ERROR(f"Not found: {yaml_path}"))
            return

        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}
        mappings = data.get("ncaa", {})

        # Find all duplicate pairs: NCAA name exists as a Team AND canonical name also exists as a Team
        pairs = []
        for ncaa_name, canonical_name in mappings.items():
            if ncaa_name == canonical_name:
                continue
            try:
                ncaa_team = Team.objects.get(name=ncaa_name)
                canon_team = Team.objects.get(name=canonical_name)
                pairs.append((ncaa_name, ncaa_team, canonical_name, canon_team))
            except Team.DoesNotExist:
                pass

        self.stdout.write(f"Found {len(pairs)} duplicate team pairs to merge.\n")

        merged = 0
        skipped = 0

        for ncaa_name, ncaa_team, canonical_name, canon_team in pairs:
            game_stats = TeamGameStats.objects.filter(team=ncaa_team).count()
            canon_stats = TeamGameStats.objects.filter(team=canon_team).count()

            self.stdout.write(
                f"  {ncaa_name} (id={ncaa_team.id}, games={game_stats}) → "
                f"{canonical_name} (id={canon_team.id}, games={canon_stats})"
            )

            if dry_run:
                skipped += 1
                continue

            try:
                with transaction.atomic():
                    # --- TeamGameStats ---
                    TeamGameStats.objects.filter(team=ncaa_team).update(team=canon_team)
                    TeamGameStats.objects.filter(opponent=ncaa_team).update(opponent=canon_team)

                    # --- Game FKs ---
                    Game.objects.filter(home_team=ncaa_team).update(home_team=canon_team)
                    Game.objects.filter(away_team=ncaa_team).update(away_team=canon_team)

                    # --- TeamSeasonRatings (unique_together team+season) ---
                    # Delete canonical stubs first, then move ncaa team's records
                    ncaa_season_ids = TeamSeasonRatings.objects.filter(
                        team=ncaa_team
                    ).values_list("season_id", flat=True)
                    # Delete canonical records for any season where ncaa also has data
                    TeamSeasonRatings.objects.filter(
                        team=canon_team, season_id__in=ncaa_season_ids
                    ).delete()
                    TeamSeasonRatings.objects.filter(team=ncaa_team).update(team=canon_team)

                    # --- TeamSeasonMetrics (unique_together team+season) ---
                    ncaa_metric_seasons = TeamSeasonMetrics.objects.filter(
                        team=ncaa_team
                    ).values_list("season_id", flat=True)
                    TeamSeasonMetrics.objects.filter(
                        team=canon_team, season_id__in=ncaa_metric_seasons
                    ).delete()
                    TeamSeasonMetrics.objects.filter(team=ncaa_team).update(team=canon_team)

                    # --- TeamExternalId (unique_together team+source) ---
                    for ext_id in TeamExternalId.objects.filter(team=ncaa_team):
                        # Remove any existing canonical mapping for the same source
                        TeamExternalId.objects.filter(
                            team=canon_team, source=ext_id.source
                        ).delete()
                        ext_id.team = canon_team
                        ext_id.save()

                    # --- Aliases ---
                    aliases = list(canon_team.aliases or [])
                    if ncaa_name not in aliases:
                        aliases.append(ncaa_name)
                    canon_team.aliases = aliases
                    canon_team.is_d1 = True
                    canon_team.save()

                    # Mark the informal-name team as non-D1
                    ncaa_team.is_d1 = False
                    ncaa_team.save()

                merged += 1
                self.stdout.write(self.style.SUCCESS("    ✓ Merged"))

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"    ✗ Error: {e}"))
                skipped += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\nDry run complete. Would merge {len(pairs)} pairs.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nDone. Merged: {merged} | Errors/skipped: {skipped}")
            )
