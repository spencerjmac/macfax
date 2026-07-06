"""
Management command: nba_compute_projection_values

Computes and stores Projection Value (docs/bpr_audit/09) on
NBAPlayerSeasonStats: projection_value + version/source/alpha fields.

Run AFTER nba_compute_final_bpr for the season (consumes stored bpr).
Team outlooks (compute_nba_team_outlooks) read the stored field.

Usage:
  python manage.py nba_compute_projection_values --season 2026
  python manage.py nba_compute_projection_values --season 2026 --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from nba.analytics.projection_value import compute_projection_values


class Command(BaseCommand):
    help = "Compute + store NBA Projection Value (team-forecast input; NOT BPR)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true", default=False)

    def handle(self, *args, **opts):
        from nba.models import NBAPlayerSeasonStats

        season = opts["season"]
        values = compute_projection_values(season)
        if not values:
            self.stderr.write(f"No projection values computed for {season}.")
            return

        n_bpm = sum(1 for v in values.values() if v["source"] == "bpr+bpm")
        self.stdout.write(
            f"Season {season}: {len(values)} projection values "
            f"({n_bpm} bpr+bpm, {len(values) - n_bpm} bpr_only)")
        top = sorted(values.items(), key=lambda kv: -kv[1]["value"])[:5]
        for pid, v in top:
            self.stdout.write(f"  top: player {pid}  pv={v['value']:+.2f}  ({v['source']})")

        if opts["dry_run"]:
            self.stdout.write("[dry-run] no writes")
            return

        rows = list(NBAPlayerSeasonStats.objects.filter(
            season__year=season, season_type="regular",
        ).select_related("player"))
        to_update = []
        for r in rows:
            v = values.get(r.player.player_id)
            if v is None:
                continue
            r.projection_value = v["value"]
            r.projection_value_version = v["version"]
            r.projection_value_source = v["source"]
            r.projection_alpha = v["alpha"]
            to_update.append(r)
        with transaction.atomic():
            NBAPlayerSeasonStats.objects.bulk_update(
                to_update,
                ["projection_value", "projection_value_version",
                 "projection_value_source", "projection_alpha"],
                batch_size=500)
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(to_update)} rows."))
