"""
purge_offseason_moves — delete TeamOutseasonMove rows for one target season.

One-time cleanup tool for the legacy-contamination problem: migration 0026
stamped every pre-existing move with the current target season and left
source="manual", transaction_date=NULL, so last-season / in-season rows that
bled into the offseason ledger under the old date-less schema are now
indistinguishable from real ones. A source filter can't separate legacy-manual
from genuinely-manual, so the clean path is: purge the whole season, then
regenerate all three move classes from their sources —

  purge_offseason_moves --target-season 2027 --yes
    → nba_sync_offseason_rosters --source-season 2026 --target-season 2027  (source="sync")
    → nba_sync_draft_picks --year 2026                                       (source="draft")
    → import_offseason_moves  (reads tools/moves_2026.csv)                   (source="manual")
    → compute_nba_team_outlooks

Guarded: prints a per-source / per-move_type breakdown and requires --yes to
actually delete (bare invocation is a dry run). --source narrows to one
provenance class for surgical re-runs.

Usage:
  python manage.py purge_offseason_moves --target-season 2027            # dry run
  python manage.py purge_offseason_moves --target-season 2027 --yes      # delete
  python manage.py purge_offseason_moves --target-season 2027 --source sync --yes
"""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from nba.models import NBASeason, TeamOutseasonMove


class Command(BaseCommand):
    help = "Delete TeamOutseasonMove rows for a target season (guarded; --yes to apply)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--target-season", dest="target_season", type=int, required=True,
            metavar="YEAR",
            help="Ending year of the projected season whose moves to purge, e.g. 2027.",
        )
        parser.add_argument(
            "--source", dest="source", default=None,
            choices=[c[0] for c in TeamOutseasonMove.SOURCE_CHOICES],
            help="Only purge rows with this provenance. Default: all sources.",
        )
        parser.add_argument(
            "--yes", action="store_true",
            help="Actually delete. Without it, this command only reports (dry run).",
        )

    def handle(self, *args, **options):
        target_season: int = options["target_season"]
        source: str | None = options.get("source")
        confirmed: bool = options["yes"]

        if not NBASeason.objects.filter(year=target_season).exists():
            raise CommandError(f"NBASeason with year={target_season} not found.")

        # season FK on the move is the target (projected) season — filter on it
        # directly rather than via the team's outlook, so a move whose team was
        # re-seasoned can't slip the net.
        qs = TeamOutseasonMove.objects.filter(season__year=target_season)
        if source is not None:
            qs = qs.filter(source=source)

        total = qs.count()
        scope = f"season {target_season}" + (f", source='{source}'" if source else "")

        if total == 0:
            self.stdout.write(f"No TeamOutseasonMove rows for {scope}. Nothing to do.")
            return

        by_source = Counter(qs.values_list("source", flat=True))
        by_type = Counter(qs.values_list("move_type", flat=True))
        self.stdout.write(f"{total} move rows match {scope}:")
        self.stdout.write("  by source:    " + ", ".join(
            f"{s or '∅'}={n}" for s, n in sorted(by_source.items())))
        self.stdout.write("  by move_type: " + ", ".join(
            f"{t}={n}" for t, n in sorted(by_type.items())))

        if not confirmed:
            self.stdout.write(self.style.WARNING(
                f"\nDRY RUN — {total} rows would be deleted. Re-run with --yes to apply."
            ))
            return

        qs.delete()
        self.stdout.write(self.style.SUCCESS(
            f"\nDeleted {total} move rows for {scope}. "
            f"Re-run the sync/draft/import writers to regenerate."
        ))
