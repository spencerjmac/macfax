"""
backfill_player_dob — populate NBAPlayer.date_of_birth from NBA.com.

Calls commonplayerinfo once per player where date_of_birth is currently null.
Rate-limited to one call per --sleep seconds (default 0.6 s).

Usage:
  python manage.py backfill_player_dob
  python manage.py backfill_player_dob --all     # re-fetch even if already set
  python manage.py backfill_player_dob --limit 50  # process at most N players
  python manage.py backfill_player_dob --sleep 1.0
"""

import time
import logging
from datetime import date

from django.core.management.base import BaseCommand

from nba.models import NBAPlayer

logger = logging.getLogger(__name__)


def _parse_nba_date(raw: str | None) -> date | None:
    """Parse '1989-02-17T00:00:00' or '1989-02-17' to a date. Returns None on failure."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except (ValueError, TypeError):
        return None


class Command(BaseCommand):
    help = "Back-fill NBAPlayer.date_of_birth from NBA.com commonplayerinfo endpoint."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all", action="store_true",
            help="Re-fetch even for players that already have date_of_birth set.",
        )
        parser.add_argument(
            "--limit", type=int, default=None, metavar="N",
            help="Process at most N players (useful for incremental runs).",
        )
        parser.add_argument(
            "--sleep", type=float, default=0.6, metavar="SECS",
            help="Sleep between NBA.com calls (default 0.6 s).",
        )

    def handle(self, *args, **options):
        try:
            from nba_api.stats.endpoints import commonplayerinfo
        except ImportError:
            self.stderr.write("nba_api not installed. Run: pip install nba-api")
            return

        refetch_all: bool = options["all"]
        limit: int | None = options["limit"]
        sleep_secs: float = options["sleep"]

        qs = NBAPlayer.objects.all().order_by("id")
        if not refetch_all:
            qs = qs.filter(date_of_birth__isnull=True)

        if limit is not None:
            qs = qs[:limit]

        players = list(qs)
        total = len(players)
        self.stdout.write(f"Players to process: {total}  (sleep={sleep_secs}s between calls)")

        updated = skipped = failed = 0

        for i, player in enumerate(players, start=1):
            try:
                info = commonplayerinfo.CommonPlayerInfo(
                    player_id=player.player_id, timeout=30
                )
                df = info.common_player_info.get_data_frame()
                if df.empty:
                    self.stderr.write(f"  [{i}/{total}] {player.name} — empty response")
                    failed += 1
                    time.sleep(sleep_secs)
                    continue

                raw_dob = df.iloc[0].get("BIRTHDATE")
                parsed = _parse_nba_date(raw_dob)

                if parsed is None:
                    self.stderr.write(
                        f"  [{i}/{total}] {player.name} — unparseable BIRTHDATE: {raw_dob!r}"
                    )
                    skipped += 1
                else:
                    player.date_of_birth = parsed
                    player.save(update_fields=["date_of_birth"])
                    self.stdout.write(f"  [{i}/{total}] {player.name}  →  {parsed}")
                    updated += 1

            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"  [{i}/{total}] {player.name} — error: {exc}")
                failed += 1

            time.sleep(sleep_secs)

        self.stdout.write(
            f"\nDone.  Updated: {updated}  Skipped (no DOB): {skipped}  Failed: {failed}"
        )
