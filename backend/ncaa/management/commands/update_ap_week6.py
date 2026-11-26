"""
Management command: update_ap_week6
Daily-pipeline step: keep a season's AP Poll Week 6 ranks on its rating rows.

Locked season (any rating row has ap_poll_week6): no fetch. Copy the stored rank onto
that season's rating rows that lack it (e.g. the Selection Sunday snapshot, which
compute_adjusted_ratings creates without it), and log "AP Week 6 locked (N ranked)".

Unlocked season: fetch Sports-Reference's poll page (backfill_ap_polls' parser).
  - No Week 6 column yet: warn and exit 0.
  - Week 6 present: match every school first; write only if 25-26 teams matched
    (26 = a tie at 25), to every rating row of the season (live and snapshot), and
    log unmatched names. A wrong first write would lock the season, so nothing is
    written when the count is off.

Usage:
    python manage.py update_ap_week6 --season 2027
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ncaa.management.commands.backfill_ap_polls import fetch_poll_page, parse_week6, resolve_sr_team
from ncaa.models import Season, TeamSeasonRatings
from ncaa.utils.team_mapping import TeamMapper

MIN_MATCHED, MAX_MATCHED = 25, 26


class Command(BaseCommand):
    help = "Set AP Poll Week 6 ranks on a season's rating rows (locks once written)"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True, help="Season year (e.g. 2027)")

    def handle(self, *args, **options):
        year = options["season"]
        season = Season.objects.filter(year=year).first()
        if season is None:
            raise CommandError(f"Season {year} not found")
        rows = TeamSeasonRatings.all_objects.filter(season=season)

        stored = list(rows.filter(ap_poll_week6__isnull=False).values_list("team_id", "ap_poll_week6"))
        if stored:
            self._copy_locked(year, rows, stored)
            return

        try:
            week6 = parse_week6(fetch_poll_page(year))
        except Exception as e:  # network or page layout; the pipeline logs the step as failed
            raise CommandError(f"AP Week 6 fetch/parse failed for {year}: {e}") from e
        if week6 is None:
            self.stdout.write(self.style.WARNING(f"AP Week 6 not out yet for {year} (no Week 6 column)"))
            return

        mapper = TeamMapper(source="ncaa")
        matched, unmatched, names = {}, [], {}
        team_ids_with_rows = set(rows.values_list("team_id", flat=True))
        for rank, school in week6:
            team, sr_name = resolve_sr_team(school, mapper)
            if team is None or team.id not in team_ids_with_rows:
                why = "no team match" if team is None else f"{team.name} has no {year} rating row"
                unmatched.append(f"#{rank} {sr_name} ({why})")
                continue
            matched[team.id] = rank
            names[team.id] = team.name

        for line in unmatched:
            self.stdout.write(self.style.WARNING(f"  AP Week 6 unmatched: {line}"))
        if not MIN_MATCHED <= len(matched) <= MAX_MATCHED:
            raise CommandError(
                f"AP Week 6 {year}: matched {len(matched)} teams (expected {MIN_MATCHED}-{MAX_MATCHED}); nothing written"
            )

        with transaction.atomic():
            written = sum(rows.filter(team_id=tid).update(ap_poll_week6=rank) for tid, rank in matched.items())
        # The first write locks the season, so record exactly what was written
        for tid, rank in sorted(matched.items(), key=lambda kv: (kv[1], names[kv[0]])):
            self.stdout.write(f"  AP Week 6 {year}: #{rank:2d} {names[tid]}")
        self.stdout.write(self.style.SUCCESS(
            f"AP Week 6 written for {year}: {len(matched)} ranked, {written} rating rows"
            + (f", {len(unmatched)} unmatched" if unmatched else "")
        ))

    def _copy_locked(self, year, rows, stored):
        ranks = {}
        for team_id, rank in stored:
            if ranks.setdefault(team_id, rank) != rank:
                self.stdout.write(self.style.WARNING(
                    f"  AP Week 6 {year}: team {team_id} has ranks {ranks[team_id]} and {rank}; keeping {ranks[team_id]}"
                ))
        with transaction.atomic():
            filled = sum(
                rows.filter(team_id=tid, ap_poll_week6__isnull=True).update(ap_poll_week6=rank)
                for tid, rank in ranks.items()
            )
        self.stdout.write(
            f"AP Week 6 locked ({len(ranks)} ranked)" + (f"; filled {filled} rating rows" if filled else "")
        )
