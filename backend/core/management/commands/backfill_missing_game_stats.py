"""
Find games that have no or incomplete TeamGameStats and re-fetch boxscores to fill them.

Use after a run where the NCAA API returned 502 for many boxscores; this only hits
the API for games that are missing stats.

Usage:
    python manage.py backfill_missing_game_stats --season 2026
    python manage.py backfill_missing_game_stats --season 2026 --dry-run
    python manage.py backfill_missing_game_stats --season 2026 --limit 50
"""

import time
from django.core.management.base import BaseCommand
from django.db.models import Count

from core.models import Game, Season
from core.utils.ncaa_api import NCAAAPIClient, NCAAAPIError


class Command(BaseCommand):
    help = "Find games missing team stats and backfill from NCAA boxscore API"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            required=True,
            help="Season year (e.g. 2026)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only list games missing stats; do not call the API",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            metavar="N",
            help="Max number of games to backfill (0 = no limit)",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            metavar="SECS",
            help="Seconds between API requests (default 1.0)",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        dry_run = options["dry_run"]
        limit = options["limit"]
        delay = options["delay"]

        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Season {season_year} not found."))
            return

        # Games that have fewer than 2 team_stats (final games should have 2)
        # Only NCAA-sourced games; source_game_id is the NCAA game ID
        missing = (
            Game.objects.filter(
                season_year=season_year, status="final", source="ncaa"
            )
            .annotate(nstats=Count("team_stats"))
            .filter(nstats__lt=2)
            .order_by("game_date", "source_game_id")
            .select_related("home_team", "away_team")
        )
        total_missing = missing.count()
        if limit:
            missing = missing[:limit]

        self.stdout.write(
            f"\nSeason {season.display_name}: {total_missing} game(s) missing team stats"
        )
        if limit and total_missing > limit:
            self.stdout.write(f"Processing first {limit} (use --limit 0 for all).\n")
        else:
            self.stdout.write("")

        if total_missing == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to backfill."))
            return

        if dry_run:
            for g in missing:
                self.stdout.write(
                    f"  {g.source_game_id}  {g.game_date}  "
                    f"{g.away_team.name} @ {g.home_team.name}  (stats: {g.nstats})"
                )
            self.stdout.write(
                self.style.WARNING("\nRun without --dry-run to backfill these games.")
            )
            return

        api_client = NCAAAPIClient()
        from core.management.commands.ingest_gamelogs import Command as IngestCommand

        ingest_cmd = IngestCommand()
        ingest_cmd.stdout = self.stdout
        ingest_cmd.stderr = self.stderr
        updated = 0
        failed = 0
        skipped = 0

        for g in missing:
            try:
                boxscore = api_client.get_game_details(g.source_game_id)
            except NCAAAPIError as e:
                self.stdout.write(
                    self.style.WARNING(f"  Skip {g.source_game_id}: {e}")
                )
                skipped += 1
                if delay:
                    time.sleep(delay)
                continue

            home_stats = boxscore.get("home", {}).get("stats", {})
            away_stats = boxscore.get("away", {}).get("stats", {})
            if not home_stats and not away_stats:
                self.stdout.write(
                    self.style.WARNING(f"  Skip {g.source_game_id}: no stats in response")
                )
                skipped += 1
                if delay:
                    time.sleep(delay)
                continue

            try:
                n = ingest_cmd._extract_team_stats(g, boxscore)
                if n:
                    ingest_cmd._extract_scoring_events(g, boxscore)
                    updated += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  OK {g.source_game_id}  {g.away_team.name} @ {g.home_team.name}  (+{n} stats)"
                        )
                    )
                else:
                    skipped += 1
            except Exception as e:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(f"  FAIL {g.source_game_id}: {e}")
                )

            if delay:
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Updated: {updated}  Skipped: {skipped}  Failed: {failed}"
            )
        )
