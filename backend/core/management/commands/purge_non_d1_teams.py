"""
Management command: purge_non_d1_teams

Deletes all Team records where is_d1=False, along with all associated data:
  - Games where the non-D1 team is home or away (cascades to TeamGameStats)
  - Any orphaned TeamGameStats rows where the non-D1 team is the opponent
  - TeamSeasonRatings, TeamSeasonMetrics, TeamExternalId for non-D1 teams

This is safe to run after fix_team_duplicates, which will have already moved
real game data from informal-name teams (e.g. "UConn") to canonical D1 teams
(e.g. "Connecticut") and marked the informal-name records as non-D1.

Usage:
    python manage.py purge_non_d1_teams
    python manage.py purge_non_d1_teams --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Delete all non-D1 Team records and their associated data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without making changes",
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

        non_d1 = Team.objects.filter(is_d1=False)
        team_count = non_d1.count()

        if team_count == 0:
            self.stdout.write(self.style.SUCCESS("No non-D1 teams found. Nothing to do."))
            return

        # Count related data that will be removed
        games_involved = Game.objects.filter(
            home_team__is_d1=False
        ) | Game.objects.filter(away_team__is_d1=False)
        games_involved = games_involved.distinct()
        game_count = games_involved.count()

        # Game stats cascade-deleted with games; count orphans (opponent ref only)
        orphan_stats = TeamGameStats.objects.filter(
            opponent__is_d1=False
        ).exclude(game__in=games_involved)
        orphan_stat_count = orphan_stats.count()

        ratings_count = TeamSeasonRatings.objects.filter(team__is_d1=False).count()
        metrics_count = TeamSeasonMetrics.objects.filter(team__is_d1=False).count()
        ext_id_count = TeamExternalId.objects.filter(team__is_d1=False).count()

        self.stdout.write(f"\nNon-D1 teams to delete:          {team_count}")
        self.stdout.write(f"Games to delete (+ their stats): {game_count}")
        self.stdout.write(f"Orphaned opponent-only stats:    {orphan_stat_count}")
        self.stdout.write(f"TeamSeasonRatings to delete:     {ratings_count}")
        self.stdout.write(f"TeamSeasonMetrics to delete:     {metrics_count}")
        self.stdout.write(f"TeamExternalId records to delete:{ext_id_count}\n")

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
            # 1. Delete games involving non-D1 teams (cascades to TeamGameStats)
            deleted_games, _ = games_involved.delete()
            self.stdout.write(f"  Deleted {deleted_games} game-related records (games + stats)")

            # 2. Delete any remaining orphaned stats where non-D1 is only the opponent
            deleted_orphans, _ = TeamGameStats.objects.filter(opponent__is_d1=False).delete()
            if deleted_orphans:
                self.stdout.write(f"  Deleted {deleted_orphans} orphaned opponent-only stats")

            # 3. Delete computed data for non-D1 teams
            r, _ = TeamSeasonRatings.objects.filter(team__is_d1=False).delete()
            m, _ = TeamSeasonMetrics.objects.filter(team__is_d1=False).delete()
            e, _ = TeamExternalId.objects.filter(team__is_d1=False).delete()
            self.stdout.write(f"  Deleted {r} ratings, {m} metrics, {e} external IDs")

            # 4. Delete non-D1 teams
            deleted_teams, _ = non_d1.delete()
            self.stdout.write(f"  Deleted {deleted_teams} non-D1 team records")

        self.stdout.write(self.style.SUCCESS("\nDone."))
