"""
compute_nba_team_cap — sum player contract salaries per team and classify
cap status tier. Writes TeamSeasonOutlook.cap_total_salary + cap_status_tier.

2026-27 cap thresholds (update each offseason):
    Salary cap:   $165,000,000
    Tax line:     $201,000,000
    First apron:  $209,000,000
    Second apron: $222,000,000

Usage:
    python manage.py compute_nba_team_cap --season 2027
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from nba.models import NBASeason, NBATeam, NBAPlayerContract, TeamSeasonOutlook

logger = logging.getLogger(__name__)

# 2026-27 thresholds in dollars
CAP_LINE        = 165_000_000
TAX_LINE        = 201_000_000
FIRST_APRON     = 209_000_000
SECOND_APRON    = 222_000_000


def classify_cap(total: int) -> str:
    if total >= SECOND_APRON:
        return "second_apron"
    if total >= FIRST_APRON:
        return "first_apron"
    if total >= TAX_LINE:
        return "taxpayer"
    if total >= CAP_LINE:
        return "over_cap"
    return "under_cap"


CAP_CONSEQUENCES = {
    "under_cap": "Can sign any player; full cap room available.",
    "over_cap": "Can use full Non-Taxpayer MLE (~$15M); sign-and-trade in/out.",
    "taxpayer": "Taxpayer MLE (~$6M) only; paying luxury tax dollar-for-dollar.",
    "first_apron": "Lost BAE and Non-Taxpayer MLE; sign-and-trade restricted.",
    "second_apron": "Cannot aggregate salaries in trades; no buyout signings; repeat-offender pick risk.",
}


class Command(BaseCommand):
    help = "Compute team cap totals from NBAPlayerContract and update TeamSeasonOutlook."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True,
            help="Target season year (e.g. 2027 for 2026-27).",
        )
        parser.add_argument(
            "--team", type=str, default=None,
            help="Limit to one team abbreviation (e.g. OKC).",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        team_filter = options["team"]

        try:
            season = NBASeason.objects.get(year=season_year)
        except NBASeason.DoesNotExist:
            raise CommandError(f"Season {season_year} not in DB.")

        contract_qs = NBAPlayerContract.objects.filter(season=season, is_guaranteed=True)
        if team_filter:
            contract_qs = contract_qs.filter(team__abbreviation=team_filter.upper())

        # Sum salaries per team
        team_totals = (
            contract_qs
            .values("team_id", "team__abbreviation", "team__slug")
            .annotate(total=Sum("salary"))
        )

        updated = 0
        for row in team_totals:
            total = row["total"] or 0
            tier = classify_cap(total)

            # Match TeamSeasonOutlook by team slug (with abbr fallback)
            team_slug = row["team__slug"]
            team_abbr = row["team__abbreviation"]
            # Scope to the --season outlook row (team_slug no longer globally
            # unique); .first() would otherwise pick an arbitrary season.
            outlook = (
                TeamSeasonOutlook.objects.filter(team_slug=team_slug, season=season).first()
                or TeamSeasonOutlook.objects.filter(team_abbr=team_abbr, season=season).first()
            )
            if outlook is None:
                self.stderr.write(f"  No outlook for {team_abbr} — skipping")
                continue

            outlook.cap_total_salary = total
            outlook.cap_status_tier = tier
            outlook.save(update_fields=["cap_total_salary", "cap_status_tier"])

            total_m = total / 1_000_000
            self.stdout.write(
                f"  {team_abbr}: ${total_m:.1f}M → {tier}  ({CAP_CONSEQUENCES[tier][:55]})"
            )
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. {updated} teams updated for {season.display_name}.")
        )
