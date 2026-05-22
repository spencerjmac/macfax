"""
Management command: nba_compute_career_bpr

Computes career-level BPR aggregates for each player and writes them to NBAPlayer:

  peak_bpr   — best single-season BPR across all qualifying seasons
  career_bpr — minutes-weighted average BPR across all qualifying seasons

Qualifying season: season_type="regular", bpr not null, total minutes >= MIN_MINUTES

Run after nba_compute_final_bpr to ensure BPR is current.

Usage:
  python manage.py nba_compute_career_bpr
  python manage.py nba_compute_career_bpr --dry-run
"""

import logging

from django.core.management.base import BaseCommand

from nba.models import NBAPlayer, NBAPlayerSeasonStats

logger = logging.getLogger(__name__)

MIN_MINUTES = 500   # qualifying threshold — filters injury/cameo seasons


class Command(BaseCommand):
    help = "Compute peak_bpr and career_bpr for each player from historical BPR data"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print results without writing")

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        if dry_run:
            self.stdout.write("[DRY RUN] No writes")

        # Load all qualifying season stats in one query
        # annotate minutes = mpg * gp client-side (avoids DB expression complexity)
        stats_qs = list(
            NBAPlayerSeasonStats.objects.filter(
                season_type="regular",
                bpr__isnull=False,
            ).select_related("player").only(
                "player__id", "player__name", "bpr", "mpg", "gp"
            )
        )

        # Group by player
        from collections import defaultdict
        player_seasons: dict[int, list] = defaultdict(list)
        for row in stats_qs:
            minutes = (row.mpg or 0.0) * (row.gp or 0)
            if minutes >= MIN_MINUTES:
                player_seasons[row.player_id].append((row.bpr, minutes))

        updated = skipped = 0
        sample_rows = []

        players = NBAPlayer.objects.filter(pk__in=player_seasons.keys())
        for player in players:
            seasons = player_seasons[player.pk]
            if not seasons:
                skipped += 1
                continue

            bpr_vals = [bpr for bpr, _ in seasons]
            min_vals = [m for _, m in seasons]

            peak_bpr = round(max(bpr_vals), 3)
            total_min = sum(min_vals)
            career_bpr = round(
                sum(b * m for b, m in zip(bpr_vals, min_vals)) / total_min, 3
            )

            if not dry_run:
                player.peak_bpr   = peak_bpr
                player.career_bpr = career_bpr
                player.save(update_fields=["peak_bpr", "career_bpr"])

            updated += 1
            if len(sample_rows) < 10:
                sample_rows.append((player.name, career_bpr, peak_bpr, len(seasons)))

        self.stdout.write(f"\n[nba_compute_career_bpr] MIN_MINUTES={MIN_MINUTES}")
        self.stdout.write(f"  Players with qualifying seasons: {updated}")
        self.stdout.write(f"  Players skipped (no qualifying seasons): {skipped}")

        self.stdout.write("\nSample (top 10 by career_bpr):")
        sample_rows.sort(key=lambda x: x[1], reverse=True)
        for name, cbpr, pbpr, n_seasons in sample_rows[:10]:
            self.stdout.write(
                f"  {name:<30} career={cbpr:+.3f}  peak={pbpr:+.3f}  seasons={n_seasons}"
            )

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"\n[OK] career_bpr / peak_bpr written: {updated} players updated"
            ))
