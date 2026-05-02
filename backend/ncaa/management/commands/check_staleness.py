"""
Management command: check_staleness

Checks for stale pipeline phases across all teams for a season.

A phase is stale when its data was computed BEFORE an upstream phase
re-ran (e.g., Phase 1 re-ran but Phase 3 was not subsequently updated).

Usage:
    python manage.py check_staleness --season 2026
    python manage.py check_staleness --season 2026 --team-id 123
    python manage.py check_staleness --season 2026 --errors-only
"""

from django.core.management.base import BaseCommand
from django.db.models import Max

from ncaa.models import PlayerSeasonProjection, TeamRosterFit, TeamSeasonProjection
from ncaa.analytics.staleness import check_team_staleness_bulk, StalenessWarning


class Command(BaseCommand):
    help = "Check for stale pipeline phases across teams for a given season."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True, metavar="YEAR")
        parser.add_argument("--team-id", type=int, default=None, metavar="ID",
                            help="Check only this team.")
        parser.add_argument("--errors-only", action="store_true",
                            help="Show only error-severity warnings (stale > 24h).")

    def handle(self, *args, **options):
        season_year = options["season"]
        team_id_filter = options["team_id"]
        errors_only = options["errors_only"]

        self.stdout.write(f"\nStaleness check — season {season_year}")

        # ── 3 bulk queries (not one per team) ────────────────────────────────
        psp_qs = PlayerSeasonProjection.objects.filter(from_season__year=season_year)
        if team_id_filter:
            psp_qs = psp_qs.filter(team_id=team_id_filter)
        psp_map: dict[int, object] = {
            row["team_id"]: row["latest"]
            for row in psp_qs.values("team_id").annotate(latest=Max("computed_at"))
        }

        trf_qs = TeamRosterFit.objects.filter(from_season__year=season_year)
        if team_id_filter:
            trf_qs = trf_qs.filter(team_id=team_id_filter)
        trf_map: dict[int, object] = {
            row["team_id"]: row["computed_at"]
            for row in trf_qs.values("team_id", "computed_at")
        }

        tsp_qs = TeamSeasonProjection.objects.filter(from_season__year=season_year)
        if team_id_filter:
            tsp_qs = tsp_qs.filter(team_id=team_id_filter)
        tsp_map: dict[int, object] = {
            row["team_id"]: row["computed_at"]
            for row in tsp_qs.values("team_id", "computed_at")
        }

        # Union of all team IDs
        all_team_ids = set(psp_map) | set(trf_map) | set(tsp_map)

        teams_data = [
            {
                "team_id": tid,
                "psp_computed_at": psp_map.get(tid),
                "trf_computed_at": trf_map.get(tid),
                "tsp_computed_at": tsp_map.get(tid),
            }
            for tid in all_team_ids
        ]

        result = check_team_staleness_bulk(season_year, teams_data)

        # Flatten + filter
        all_warnings: list[StalenessWarning] = []
        for warnings in result.values():
            for w in warnings:
                if errors_only and w.severity != "error":
                    continue
                all_warnings.append(w)

        # Sort by delta descending (most stale first)
        all_warnings.sort(key=lambda w: w.delta_seconds, reverse=True)

        if not all_warnings:
            self.stdout.write(self.style.SUCCESS("\nNo staleness warnings found.\n"))
            return

        # Print table
        header = f"  {'Team ID':<10}  {'Sev':<8}  {'Upstream':<10}  {'Downstream':<12}  {'Delta':>10}  Message"
        self.stdout.write("\n" + "=" * 90)
        self.stdout.write(header)
        self.stdout.write("  " + "-" * 86)

        for w in all_warnings:
            delta_str = f"{w.delta_seconds / 3600:.1f}h" if w.delta_seconds >= 3600 else f"{w.delta_seconds / 60:.0f}m"
            row = (
                f"  {w.team_id:<10}  {w.severity:<8}  {w.upstream_phase:<10}  "
                f"{w.downstream_phase:<12}  {delta_str:>10}  {w.message[:50]}"
            )
            if w.severity == "error":
                self.stdout.write(self.style.ERROR(row))
            else:
                self.stdout.write(self.style.WARNING(row))

        self.stdout.write("=" * 90)
        self.stdout.write(f"\nTotal: {len(all_warnings)} warning(s) across {len(result)} team(s).\n")
