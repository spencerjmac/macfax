"""
nba/management/commands/nba_sync_injury_report.py

Fetches the current NBA injury report from ESPN's public JSON API and
upserts NBAPlayerAvailability records for the specified game date.

Usage
-----
  # Sync for today (default)
  uv run python manage.py nba_sync_injury_report

  # Sync for a specific future game date
  uv run python manage.py nba_sync_injury_report --date 2026-06-10

Source
------
  https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries

  Returns JSON: {"injuries": [{"displayName": "Atlanta Hawks", "injuries": [...]}]}
  Each player entry: {"status": "Out", "date": "...", "shortComment": "...",
                      "athlete": {"displayName": "Jayson Tatum", "links": [...]}}
"""

from __future__ import annotations

import logging
import re
import urllib.request
from datetime import date, datetime, timezone
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

_log = logging.getLogger(__name__)

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
SOURCE = "espn"

# Map ESPN status strings → our model status choices (case-insensitive)
_STATUS_MAP = {
    "available":          "available",
    "probable":           "probable",
    "day-to-day":         "day_to_day",
    "day to day":         "day_to_day",
    "questionable":       "questionable",
    "game-time decision": "game_time_decision",
    "game time decision": "game_time_decision",
    "doubtful":           "doubtful",
    "out":                "out",
    "out for season":     "out_for_season",
    "out for the season": "out_for_season",
    "injured reserve":    "out_for_season",
    "suspended":          "out",
}


def _map_status(raw: str) -> str:
    """Normalise ESPN status string to our enum value."""
    key = raw.strip().lower()
    return _STATUS_MAP.get(key, "out")  # default OUT for unknown statuses


def _fetch_espn() -> list[dict]:
    """
    Fetch ESPN injury endpoint, return raw list of team-level dicts.
    Raises urllib.error.URLError / ValueError on failure.
    """
    req = urllib.request.Request(
        ESPN_URL,
        headers={"User-Agent": "macfax-cbb-analytics/2.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        import json
        data = json.loads(resp.read().decode("utf-8"))

    if data.get("status") != "success":
        raise ValueError(f"ESPN API returned non-success status: {data.get('status')}")

    return data.get("injuries", [])


def _parse_report_timestamp(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ESPN's ISO-8601 date string to an aware datetime, or None."""
    if not date_str:
        return None
    try:
        # ESPN uses e.g. "2026-05-02T21:43Z" — strip trailing Z and add UTC
        clean = date_str.rstrip("Z")
        dt = datetime.fromisoformat(clean)
        return dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


class Command(BaseCommand):
    help = "Sync NBA injury report from ESPN and upsert NBAPlayerAvailability records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Game date to apply injuries to (YYYY-MM-DD). Defaults to today.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would be upserted without writing to the database.",
        )
        parser.add_argument(
            "--season",
            type=int,
            default=None,
            help="Season year (e.g. 2026). Defaults to current season.",
        )

    def handle(self, *args, **options):
        from nba.models import NBAPlayer, NBAPlayerAvailability, NBASeason, NBATeam

        # --date
        date_str = options["date"]
        if date_str:
            try:
                game_date = date.fromisoformat(date_str)
            except ValueError:
                raise CommandError(f"Invalid date format '{date_str}'. Use YYYY-MM-DD.")
        else:
            game_date = date.today()

        # Season
        season_year = options["season"]
        if season_year:
            try:
                season = NBASeason.objects.get(year=season_year)
            except NBASeason.DoesNotExist:
                raise CommandError(f"Season {season_year} not found.")
        else:
            season = NBASeason.objects.filter(is_current=True).first()
            if season is None:
                season = NBASeason.objects.order_by("-year").first()
            if season is None:
                raise CommandError("No seasons found. Run nba data sync first.")

        dry_run = options["dry_run"]

        self.stdout.write(
            f"Syncing ESPN injury report for {game_date} (season {season.year})"
            + (" [DRY RUN]" if dry_run else "")
        )

        # Fetch
        try:
            espn_teams = _fetch_espn()
        except Exception as exc:
            raise CommandError(f"Failed to fetch ESPN injury report: {exc}") from exc

        self.stdout.write(f"  ESPN returned {len(espn_teams)} team entries.")

        # Build team lookup: full name → NBATeam
        team_map: dict[str, "NBATeam"] = {t.name: t for t in NBATeam.objects.all()}

        # Build player lookup: lower name → NBAPlayer
        player_map: dict[str, "NBAPlayer"] = {
            p.name.lower(): p for p in NBAPlayer.objects.filter(is_active=True)
        }

        created = 0
        updated = 0
        skipped_team = 0
        skipped_player = 0

        records_to_upsert = []

        for team_entry in espn_teams:
            team_name = team_entry.get("displayName", "")
            team = team_map.get(team_name)
            if team is None:
                _log.debug("ESPN team '%s' not found in DB — skipping", team_name)
                skipped_team += 1
                continue

            for inj in team_entry.get("injuries", []):
                athlete = inj.get("athlete", {})
                player_name = athlete.get("displayName", "")
                player = player_map.get(player_name.lower())

                if player is None:
                    _log.debug(
                        "ESPN player '%s' (%s) not found in DB — skipping",
                        player_name, team_name,
                    )
                    skipped_player += 1
                    continue

                status = _map_status(inj.get("status", "out"))
                injury_reason = inj.get("shortComment", "")[:200]
                notes = inj.get("longComment", "")
                report_ts = _parse_report_timestamp(inj.get("date"))

                records_to_upsert.append(
                    {
                        "player": player,
                        "team": team,
                        "season": season,
                        "game_date": game_date,
                        "status": status,
                        "injury_reason": injury_reason,
                        "notes": notes,
                        "source": SOURCE,
                        "report_timestamp": report_ts,
                    }
                )

        if dry_run:
            for r in records_to_upsert:
                self.stdout.write(
                    f"  [DRY] {r['team'].abbreviation} {r['player'].name} → {r['status']}"
                )
            self.stdout.write(
                f"\nWould upsert {len(records_to_upsert)} records. "
                f"Skipped: {skipped_team} unknown teams, {skipped_player} unknown players."
            )
            return

        with transaction.atomic():
            for r in records_to_upsert:
                obj, was_created = NBAPlayerAvailability.objects.update_or_create(
                    player=r["player"],
                    game_date=r["game_date"],
                    source=SOURCE,
                    defaults={
                        "team":             r["team"],
                        "season":           r["season"],
                        "status":           r["status"],
                        "injury_reason":    r["injury_reason"],
                        "notes":            r["notes"],
                        "report_timestamp": r["report_timestamp"],
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created: {created}  Updated: {updated}  "
                f"Skipped: {skipped_team} unknown teams, {skipped_player} unknown players."
            )
        )
