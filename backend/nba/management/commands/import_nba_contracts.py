"""
import_nba_contracts — import player salary data from a CSV file.

CSV format (header row required):
    player_name, team_abbr, salary, years_remaining, contract_type,
    player_option, team_option, is_guaranteed

  player_name:     Player full name (matched to NBAPlayer.name, case-insensitive)
  team_abbr:       e.g. OKC, BOS, LAL
  salary:          Annual guaranteed salary in dollars (e.g. 45000000)
  years_remaining: Contract years remaining AFTER this season (0 = expiring)
  contract_type:   max | mid | mini | veteran | two_way | rookie | vet_min | other
  player_option:   true/false (default false)
  team_option:     true/false (default false)
  is_guaranteed:   true/false (default true)

Usage:
    python manage.py import_nba_contracts --file contracts_2026-27.csv --season 2027
    python manage.py import_nba_contracts --file contracts_2026-27.csv --season 2027 --dry-run
"""

import csv
import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nba.models import NBASeason, NBATeam, NBAPlayer, NBAPlayerContract

logger = logging.getLogger(__name__)

VALID_CONTRACT_TYPES = {c[0] for c in NBAPlayerContract.CONTRACT_TYPE_CHOICES}


def _parse_bool(val: str, default: bool = False) -> bool:
    return val.strip().lower() in ("true", "1", "yes") if val.strip() else default


def _fuzzy_player(name: str):
    """Match player by exact name first, then icontains fallback."""
    player = NBAPlayer.objects.filter(name__iexact=name).first()
    if player is None:
        player = NBAPlayer.objects.filter(name__icontains=name).first()
    return player


class Command(BaseCommand):
    help = "Import NBA player contract data from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", type=str, required=True,
            help="Path to the contracts CSV file.",
        )
        parser.add_argument(
            "--season", type=int, required=True,
            help="Target season year (e.g. 2027 for 2026-27 season).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Parse and validate without writing to DB.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["file"])
        if not csv_path.exists():
            raise CommandError(f"File not found: {csv_path}")

        season_year = options["season"]
        dry_run = options["dry_run"]

        try:
            season = NBASeason.objects.get(year=season_year)
        except NBASeason.DoesNotExist:
            raise CommandError(
                f"Season {season_year} not found in DB. Run compute_nba_team_outlooks first "
                "to create the target season row."
            )

        rows = []
        errors = []

        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for i, row in enumerate(reader, start=2):  # 1-indexed, row 1 = header
                player_name = row.get("player_name", "").strip()
                team_abbr   = row.get("team_abbr", "").strip().upper()

                try:
                    salary = int(str(row.get("salary", "0")).replace(",", "").strip())
                except (ValueError, TypeError):
                    errors.append(f"Row {i}: invalid salary '{row.get('salary')}'")
                    continue

                try:
                    years_remaining = int(row.get("years_remaining", "0").strip())
                except ValueError:
                    years_remaining = 0

                contract_type = row.get("contract_type", "other").strip().lower()
                if contract_type not in VALID_CONTRACT_TYPES:
                    contract_type = "other"

                player = _fuzzy_player(player_name)
                if player is None:
                    errors.append(f"Row {i}: player not found: '{player_name}'")
                    continue

                team = NBATeam.objects.filter(abbreviation=team_abbr).first()
                if team is None:
                    errors.append(f"Row {i}: team not found: '{team_abbr}'")
                    continue

                rows.append({
                    "player": player,
                    "team": team,
                    "salary": salary,
                    "years_remaining": years_remaining,
                    "contract_type": contract_type,
                    "player_option": _parse_bool(row.get("player_option", "")),
                    "team_option": _parse_bool(row.get("team_option", "")),
                    "is_guaranteed": _parse_bool(row.get("is_guaranteed", ""), default=True),
                    "player_name_raw": player_name,
                })

        if errors:
            self.stderr.write(f"\n{len(errors)} validation errors:")
            for err in errors:
                self.stderr.write(f"  {err}")
            if not rows:
                raise CommandError("No valid rows to import.")

        self.stdout.write(f"{len(rows)} valid rows, {len(errors)} errors.")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no DB writes."))
            return

        created = updated = 0
        with transaction.atomic():
            for r in rows:
                _, was_created = NBAPlayerContract.objects.update_or_create(
                    player=r["player"],
                    team=r["team"],
                    season=season,
                    defaults={
                        "salary": r["salary"],
                        "years_remaining": r["years_remaining"],
                        "contract_type": r["contract_type"],
                        "player_option": r["player_option"],
                        "team_option": r["team_option"],
                        "is_guaranteed": r["is_guaranteed"],
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {created} created, {updated} updated for season {season.display_name}."
            )
        )
