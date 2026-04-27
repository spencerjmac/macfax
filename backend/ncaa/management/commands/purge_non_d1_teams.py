"""
Management command: purge_non_d1_teams

Deletes only non-D1 Team records that are NOT involved in any Game (as home or away).
Teams that appear as opponents in D1 vs non-D1 games are kept so that:
  - Game and TeamGameStats records stay valid (record and game log include those games).
  - D1 team W-L record continues to count all games.

For each non-D1 team that is never referenced in any Game, we delete:
  - TeamSeasonRatings, TeamSeasonMetrics, TeamExternalId for that team
  - The Team record

No Games or TeamGameStats are ever deleted by this command.

Safe to run after fix_team_duplicates. Use --dry-run to see what would be removed.

Usage:
    python manage.py purge_non_d1_teams
    python manage.py purge_non_d1_teams --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q


class Command(BaseCommand):
    help = "Delete non-D1 teams that are not used in any game (keeps D1 vs non-D1 games)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        from ncaa.models import (
            Team,
            TeamSeasonRatings,
            TeamSeasonMetrics,
            TeamExternalId,
        )

        # Non-D1 teams that appear in at least one game (home or away) — KEEP these
        non_d1_in_games = Team.objects.filter(is_d1=False).filter(
            Q(home_games__isnull=False) | Q(away_games__isnull=False)
        ).distinct()

        # Non-D1 teams that are not in any game — safe to delete
        all_non_d1 = Team.objects.filter(is_d1=False)
        orphan_non_d1 = all_non_d1.exclude(
            id__in=non_d1_in_games.values_list("id", flat=True)
        )
        team_count = orphan_non_d1.count()
        kept_count = all_non_d1.count() - team_count

        if team_count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "No orphan non-D1 teams (all non-D1 teams are used in games). Nothing to do."
                )
            )
            if all_non_d1.exists():
                self.stdout.write(
                    f"  {all_non_d1.count()} non-D1 team(s) kept (appear as opponents in games)."
                )
            return

        ratings_count = TeamSeasonRatings.objects.filter(team__in=orphan_non_d1).count()
        metrics_count = TeamSeasonMetrics.objects.filter(team__in=orphan_non_d1).count()
        ext_id_count = TeamExternalId.objects.filter(team__in=orphan_non_d1).count()

        self.stdout.write(f"\nOrphan non-D1 teams to delete:   {team_count}")
        self.stdout.write(f"Non-D1 teams kept (in games):     {kept_count}")
        self.stdout.write(f"TeamSeasonRatings to delete:     {ratings_count}")
        self.stdout.write(f"TeamSeasonMetrics to delete:     {metrics_count}")
        self.stdout.write(f"TeamExternalId records to delete:{ext_id_count}")
        self.stdout.write("  (No games or TeamGameStats are deleted.)\n")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("Dry run — no changes made. Re-run without --dry-run to apply.")
            )
            return

        confirm = input("Proceed with deletion? [y/N] ").strip().lower()
        if confirm != "y":
            self.stdout.write("Aborted.")
            return

        with transaction.atomic():
            r, _ = TeamSeasonRatings.objects.filter(team__in=orphan_non_d1).delete()
            m, _ = TeamSeasonMetrics.objects.filter(team__in=orphan_non_d1).delete()
            e, _ = TeamExternalId.objects.filter(team__in=orphan_non_d1).delete()
            self.stdout.write(f"  Deleted {r} ratings, {m} metrics, {e} external IDs")

            deleted_teams, _ = orphan_non_d1.delete()
            self.stdout.write(f"  Deleted {deleted_teams} orphan non-D1 team records")

        self.stdout.write(self.style.SUCCESS("\nDone."))
