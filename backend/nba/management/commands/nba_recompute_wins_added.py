"""
nba_recompute_wins_added — recompute stored Wins Added on native-1 seasons with the current divisor.

    wins_added = (bpr - R) x mpg x gp / 48 / WA_DIVISOR     (R = the season's stored replacement level)

Same formula nba_compute_native_bpr writes, without re-running the ratings: use it after WA_DIVISOR
changes (nba/rating_scale.py). Only regular-season rows the native model rated (bpr_model native-1)
change; each season's NBASeasonRatingScale.wins_divisor is set to the divisor used.

Usage:
    python manage.py nba_recompute_wins_added --all
    python manage.py nba_recompute_wins_added --season 2027 --season 2026
    python manage.py nba_recompute_wins_added --all --dry-run
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nba.models import NBAPlayerSeasonStats, NBASeasonRatingScale
from nba.rating_scale import NATIVE_MODEL, WA_DIVISOR


class Command(BaseCommand):
    help = "Recompute Wins Added on native-1 seasons with the current WA_DIVISOR."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, action="append", default=[], help="Season year (repeatable)")
        parser.add_argument("--all", action="store_true", help="Every season with a native-1 rating scale")
        parser.add_argument("--dry-run", action="store_true", help="Report the change, write nothing")

    def handle(self, *args, **opts):
        scales = NBASeasonRatingScale.objects.filter(bpr_model=NATIVE_MODEL).select_related("season")
        if not opts["all"]:
            if not opts["season"]:
                raise CommandError("pass --all or one or more --season YEAR")
            scales = scales.filter(season__year__in=opts["season"])
        scales = sorted(scales, key=lambda s: s.season.year)
        if not scales:
            raise CommandError("no native-1 seasons matched")
        self.stdout.write(f"divisor {WA_DIVISOR} ({'dry run' if opts['dry_run'] else 'writing'})")
        total = 0
        for scale in scales:
            rows = list(NBAPlayerSeasonStats.objects.filter(
                season=scale.season, season_type="regular", bpr_model=NATIVE_MODEL, bpr__isnull=False))
            old_sum = sum(r.wins_added or 0.0 for r in rows)
            for r in rows:
                r.wins_added = (r.bpr - scale.replacement) * (r.mpg or 0.0) * (r.gp or 0) / 48.0 / WA_DIVISOR
            new_sum = sum(r.wins_added for r in rows)
            top = max(rows, key=lambda r: r.wins_added, default=None)
            self.stdout.write(
                f"  {scale.season.year}: {len(rows)} rows, divisor {scale.wins_divisor} -> {WA_DIVISOR}, "
                f"league Σ wins_added {old_sum:.1f} -> {new_sum:.1f}"
                + (f", top {top.player_id}: {top.wins_added:.2f}" if top else ""))
            if not opts["dry_run"]:
                with transaction.atomic():
                    NBAPlayerSeasonStats.objects.bulk_update(rows, ["wins_added"], batch_size=1000)
                    scale.wins_divisor = WA_DIVISOR
                    scale.save(update_fields=["wins_divisor", "updated_at"])
            total += len(rows)
        self.stdout.write(self.style.SUCCESS(
            f"{'Would update' if opts['dry_run'] else 'Updated'} {total} rows over {len(scales)} seasons."))
