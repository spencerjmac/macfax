"""
Seed the Conference table and assign each TeamSeasonMetrics to its conference.

Conference rows come from the registry in ncaa/conferences.py. A team's conference
for a season comes from that season's data file (ncaa/data/conferences/<season>.csv)
when one applies, else from the frozen CONF_MAP (seasons <= 2026). Run after
compute_team_metrics -- update_ncaa_teams does this automatically.

Usage:
    python manage.py seed_conferences                 # season in play
    python manage.py seed_conferences --season 2027
    python manage.py seed_conferences --season 2027 --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from ncaa.conf_utils import get_team_conference
from ncaa.conferences import CONFERENCES, file_year_for, season_conference_map
from ncaa.models import Conference, Season, Team, TeamSeasonMetrics
from ncaa.seasons import resolve_season_year


class Command(BaseCommand):
    help = "Seed Conference table and set TeamSeasonMetrics.conference for a season"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            default=None,
            help="Season year (e.g. 2027 for 2026-27) (default: the season in play)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be done",
        )

    def handle(self, *args, **options):
        season_year = resolve_season_year(options["season"])
        dry_run = options["dry_run"]

        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Season {season_year} not found."))
            return

        file_year = file_year_for(season_year)
        source = f"{file_year}.csv" if file_year is not None else "frozen CONF_MAP"
        self.stdout.write(f"Season {season_year}: conference source = {source}")

        metrics_qs = TeamSeasonMetrics.objects.filter(season=season).select_related("team", "conference")

        if dry_run:
            self.stdout.write(f"[DRY RUN] Would ensure {len(CONFERENCES)} conferences")
            self.stdout.write(f"[DRY RUN] Would assign a conference to {metrics_qs.count()} TeamSeasonMetrics")
            self._report_coverage(season_year, metrics_qs)
            return

        with transaction.atomic():
            created = 0
            conf_by_code: dict[str, Conference] = {}
            for c in CONFERENCES:
                conf, was_created = Conference.objects.get_or_create(code=c.code, defaults={"name": c.name})
                conf_by_code[c.code] = conf
                created += was_created
            self.stdout.write(
                self.style.SUCCESS(f"Conferences: {created} created, {Conference.objects.count()} total")
            )

            updated = unchanged = 0
            unknown: list[str] = []
            for metrics in metrics_qs:
                code = get_team_conference(metrics.team.slug, season_year)
                conf = conf_by_code.get(code)
                if conf is None:
                    unknown.append(metrics.team.slug)
                    continue
                if metrics.conference_id == conf.id:
                    unchanged += 1
                else:
                    metrics.conference = conf
                    metrics.save(update_fields=["conference"])
                    updated += 1

            self.stdout.write(
                self.style.SUCCESS(f"TeamSeasonMetrics: {updated} updated, {unchanged} already correct")
            )
            if unknown:
                self.stdout.write(
                    self.style.WARNING(
                        f"{len(unknown)} team(s) not in any conference list, left unassigned: {sorted(unknown)}"
                    )
                )

        self._report_coverage(season_year, metrics_qs)
        self.stdout.write(self.style.SUCCESS("Done."))

    def _report_coverage(self, season_year: int, metrics_qs):
        """Flag mismatches between the season's data file and the teams in the DB."""
        by_slug = season_conference_map(season_year)
        if by_slug is None:
            return
        db_slugs = set(Team.objects.filter(is_d1=True).values_list("slug", flat=True))
        in_file_not_db = sorted(set(by_slug) - set(Team.objects.values_list("slug", flat=True)))
        d1_not_in_file = sorted(db_slugs - set(by_slug))
        if in_file_not_db:
            self.stdout.write(
                self.style.WARNING(
                    f"In the data file but no Team in the DB (run ensure_ncaa_teams / add to "
                    f"mappings/ncaa_team_name_mappings.yml): {in_file_not_db}"
                )
            )
        if d1_not_in_file:
            self.stdout.write(f"D1 teams in the DB not in the data file (no {season_year} conference): {d1_not_in_file}")
