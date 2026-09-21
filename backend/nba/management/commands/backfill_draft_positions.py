"""
backfill_draft_positions — populate NBAPlayer.draft_overall_pick / draft_year from
NBA.com DraftHistory (one all-history call). Prerequisite for the pick-conditional
young-development BPR curve (draft position is not otherwise on player records).

Match key: DraftHistory PERSON_ID == NBAPlayer.player_id (the NBA.com canonical id).
Undrafted / unmatched players are left NULL (the curve treats NULL as no pick bonus).

Usage:
  python manage.py backfill_draft_positions              # apply
  python manage.py backfill_draft_positions --dry-run    # report coverage only
"""

from django.core.management.base import BaseCommand, CommandError

from nba.models import NBAPlayer


class Command(BaseCommand):
    help = "Backfill NBAPlayer draft pick/year from NBA.com DraftHistory."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Report coverage without writing.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        try:
            from nba_api.stats.endpoints import drafthistory
        except ImportError:
            raise CommandError("nba_api not installed.")

        self.stdout.write("Fetching NBA.com DraftHistory (all years)…")
        try:
            df = drafthistory.DraftHistory(league_id="00", timeout=45).get_data_frames()[0]
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"DraftHistory call failed: {exc}")

        # PERSON_ID -> (overall_pick, draft_season_year)
        pick = {}
        for _, r in df.iterrows():
            try:
                pick[int(r["PERSON_ID"])] = (int(r["OVERALL_PICK"]), int(r["SEASON"]))
            except (ValueError, TypeError):
                continue
        self.stdout.write(f"  {len(pick)} drafted players in DraftHistory.")

        players = list(NBAPlayer.objects.all().only("id", "player_id",
                                                    "draft_overall_pick", "draft_year"))
        matched, updated = 0, 0
        for p in players:
            pk = pick.get(p.player_id)
            if pk is None:
                continue
            matched += 1
            overall, year = pk
            if p.draft_overall_pick != overall or p.draft_year != year:
                updated += 1
                if not dry_run:
                    p.draft_overall_pick = overall
                    p.draft_year = year
                    p.save(update_fields=["draft_overall_pick", "draft_year"])

        self.stdout.write(
            f"{'WOULD update' if dry_run else 'Updated'} {updated} players "
            f"({matched}/{len(players)} matched a draft pick; "
            f"{len(players) - matched} undrafted/unmatched left NULL)."
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — re-run without --dry-run to write."))
