from django.core.management.base import BaseCommand, CommandError

from world_cup.fifa_rankings import FifaRankingsError, refresh_teams_file_from_fifa


class Command(BaseCommand):
    help = "Fetch the latest FIFA men's world rankings and update world_cup/data/teams.json."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and compare rankings without writing teams.json.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="HTTP timeout in seconds for FIFA requests.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        timeout = options["timeout"]

        self.stdout.write("Fetching latest FIFA men's world rankings...")
        try:
            result = refresh_teams_file_from_fifa(dry_run=dry_run, timeout=timeout)
        except FifaRankingsError as exc:
            raise CommandError(str(exc)) from exc

        metadata = result.metadata
        self.stdout.write(
            f"  Source schedule: {metadata.schedule_id}"
            + (f" ({metadata.published_date})" if metadata.published_date else "")
        )
        if metadata.next_update_date:
            self.stdout.write(f"  FIFA next update: {metadata.next_update_date}")

        if result.changes:
            self.stdout.write(f"  Updated {len(result.changes)} teams:")
            for change in result.changes:
                old_rank = change.old_rank if change.old_rank is not None else "?"
                old_points = "?" if change.old_points is None else f"{change.old_points:.2f}"
                self.stdout.write(
                    "    "
                    f"{change.team_name}: rank {old_rank} -> {change.new_rank}, "
                    f"points {old_points} -> {change.new_points:.2f}"
                )
        else:
            self.stdout.write("  No FIFA rank or points changes found.")

        if dry_run:
            self.stdout.write(self.style.WARNING("  Dry run only; teams.json was not changed."))
        else:
            self.stdout.write(self.style.SUCCESS("  Updated world_cup/data/teams.json"))
