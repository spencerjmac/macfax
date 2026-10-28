"""
Seed the Conference table and assign each TeamSeasonMetrics to a conference.

Conferences are created from a static D1 list. Each team's conference is looked up
using the season-aware NCAA slug-to-conference mapping.
Run this after you have TeamSeasonMetrics (e.g. after compute_team_metrics).

Usage:
    python manage.py seed_conferences --season 2026
    python manage.py seed_conferences --season 2026 --dry-run
    python manage.py seed_conferences --season 2027
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from ncaa.models import Conference, Season, TeamSeasonMetrics
from ncaa.conf_utils import get_season_conference


# D1 conferences (code, full name) for 2025-26.
# Old codes remain in the DB for historical seasons.
CONFERENCES = [
    ("ACC", "Atlantic Coast Conference"),
    ("AE", "America East"),
    ("Amer", "American Athletic Conference"),
    ("A10", "Atlantic 10"),
    ("ASun", "ASUN Conference"),
    ("B10", "Big Ten"),
    ("B12", "Big 12"),
    ("BE", "Big East"),
    ("BSky", "Big Sky"),
    ("BSth", "Big South"),
    ("BW", "Big West"),
    ("CAA", "Colonial Athletic Association"),
    ("CUSA", "Conference USA"),
    ("Horz", "Horizon League"),
    ("Ivy", "Ivy League"),
    ("MAAC", "Metro Atlantic Athletic Conference"),
    ("MAC", "Mid-American Conference"),
    ("MEAC", "Mid-Eastern Athletic Conference"),
    ("MVC", "Missouri Valley Conference"),
    ("MWC", "Mountain West Conference"),
    ("NEC", "Northeast Conference"),
    ("OVC", "Ohio Valley Conference"),
    ("Pat", "Patriot League"),
    ("SB", "Sun Belt"),
    ("SC", "Southern Conference"),
    ("SEC", "Southeastern Conference"),
    ("Slnd", "Southland Conference"),
    ("Sum", "Summit League"),
    ("SWAC", "Southwestern Athletic Conference"),
    ("WAC", "Western Athletic Conference"),
    ("WCC", "West Coast Conference"),
]

# New 2026-27 leagues and renamed leagues. Do not rename MAAC or WAC globally,
# because older season records must retain their historical conference.
CONFERENCES_2027 = [
    ("P12", "Pac-12 Conference"),
    ("UAC", "United Athletic Conference"),
    ("Metro", "Metro Conference"),
]


class Command(BaseCommand):
    help = "Seed Conference table and set TeamSeasonMetrics.conference from slug mapping"

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
            help="Only report what would be done",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        dry_run = options["dry_run"]

        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Season {season_year} not found."))
            return

        active_conferences = (
            [c for c in CONFERENCES if c[0] not in {"WAC", "MAAC"}] + CONFERENCES_2027
            if season_year >= 2027 else CONFERENCES
        )

        if dry_run:
            self.stdout.write(f"[DRY RUN] Would seed {len(active_conferences)} conferences")
            metrics_count = TeamSeasonMetrics.objects.filter(season=season).count()
            self.stdout.write(
                f"[DRY RUN] Would assign conference for {metrics_count} TeamSeasonMetrics"
            )
            return

        with transaction.atomic():
            # 1. Seed Conference table
            created_conf = 0
            for code, name in active_conferences:
                _, created = Conference.objects.get_or_create(
                    code=code, defaults={"name": name}
                )
                if created:
                    created_conf += 1
            self.stdout.write(
                self.style.SUCCESS(f"Conferences: {created_conf} created, {Conference.objects.count()} total")
            )

            # 2. Assign conference to each TeamSeasonMetrics for this season
            metrics_qs = TeamSeasonMetrics.objects.filter(season=season).select_related(
                "team", "conference"
            )
            updated = 0
            for metrics in metrics_qs:
                code = get_season_conference(metrics.team.slug, season_year)
                if code == "Unknown":
                    # Preserve a source-provided affiliation rather than guess.
                    if metrics.conference_id:
                        continue
                    self.stderr.write(
                        f"Unmapped conference: {metrics.team.slug} ({season_year}); skipped"
                    )
                    continue
                try:
                    conf = Conference.objects.get(code=code)
                except Conference.DoesNotExist:
                    conf, _ = Conference.objects.get_or_create(
                        code=code, defaults={"name": code}
                    )
                if metrics.conference_id != conf.id:
                    metrics.conference = conf
                    metrics.save(update_fields=["conference"])
                    updated += 1

            self.stdout.write(
                self.style.SUCCESS(f"TeamSeasonMetrics: {updated} updated with conference")
            )

        self.stdout.write(self.style.SUCCESS("Done."))
