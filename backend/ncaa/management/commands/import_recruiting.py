"""
import_recruiting — Load recruiting profiles into PlayerRecruitingProfile.

Reads player recruiting data from a CSV file and upserts records into
PlayerRecruitingProfile.  Players are matched by ESPN athlete ID; if no ESPN
ID is given, an optional fuzzy name+year match is attempted.

Expected CSV columns (order flexible, header row required):

    espn_id        — ESPN athlete ID (strongly preferred; links directly to Player)
    player_name    — Display name (used for fuzzy match when espn_id absent)
    class_year     — Season year of first college season (integer, e.g. 2026)
    stars          — Star rating 1–5 (integer; empty for unrated)
    national_rank  — Overall national rank (integer; empty if unknown)
    composite_score— 247Sports composite score 0.0–1.0 (float; empty if unknown)
    position_rank  — Position group rank (integer; empty if unknown)
    source         — Data source label (default: "manual")
    notes          — Free-text notes (optional)

Fuzzy name matching:
    When `espn_id` is absent, the command tries to find a Player whose
    display_name matches `player_name` case-insensitively with optional
    prefix-match tolerance.  A match is only accepted when exactly one
    Player row matches.  Ambiguous or failed matches are logged and skipped.

Usage examples:

    # Load from a CSV file
    ./manage.py import_recruiting --file recruiting_2027.csv

    # Preview what would change without writing (dry run)
    ./manage.py import_recruiting --file recruiting_2027.csv --dry-run

    # Override the class_year column value for every row
    ./manage.py import_recruiting --file 247sports_2027.csv --class-year 2027

    # Print a CSV template to stdout
    ./manage.py import_recruiting --print-template
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


TEMPLATE_CSV = (
    "espn_id,player_name,class_year,stars,national_rank,"
    "composite_score,position_rank,source,notes\n"
    "4431237,Asa Newell,2025,5,4,0.9993,1,247sports,\n"
    "5108983,VJ Edgecombe,2025,5,5,0.9988,2,247sports,\n"
    "4431234,Dylan Harper,2025,5,1,0.9998,1,247sports,top-1 national\n"
    ",Some Player,2027,4,,0.9600,,manual,no ESPN id – matched by name\n"
)

# Columns we recognise; all optional except at least one identifier must be present
_INT_COLS   = {"stars", "national_rank", "position_rank", "class_year"}
_FLOAT_COLS = {"composite_score"}


class Command(BaseCommand):
    help = "Import player recruiting profiles from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", "-f",
            type=str,
            default=None,
            help="Path to the CSV file to import.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Parse and match rows but do not write to the database.",
        )
        parser.add_argument(
            "--class-year",
            type=int,
            default=None,
            help="Override class_year for every row (useful when the CSV lacks the column).",
        )
        parser.add_argument(
            "--source",
            type=str,
            default=None,
            help="Override source label for every row.",
        )
        parser.add_argument(
            "--print-template",
            action="store_true",
            default=False,
            help="Print a blank CSV template to stdout and exit.",
        )
        parser.add_argument(
            "--allow-unresolved",
            action="store_true",
            default=False,
            help=(
                "Phase 5: rows whose player cannot be resolved (e.g. future-class "
                "recruits not yet in the Player table) are stored as unresolved "
                "profiles (player=NULL) keyed on normalized name + class + source, "
                "with optional committed_team_slug / source_url CSV columns. "
                "Default off: unresolved rows are skipped as before."
            ),
        )

    # ── Main entry point ──────────────────────────────────────────────────────

    def handle(self, *args, **options):
        if options["print_template"]:
            self.stdout.write(TEMPLATE_CSV)
            return

        csv_path = options.get("file")
        if not csv_path:
            raise CommandError("--file is required (or --print-template for a template).")

        path = Path(csv_path)
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        dry_run   = options["dry_run"]
        class_year_override = options.get("class_year")
        source_override     = options.get("source")

        rows = self._parse_csv(path)
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nImport recruiting — {path.name}  ({len(rows)} rows)"
                + (" [DRY RUN]" if dry_run else "")
                + "\n"
            )
        )

        stats = {"matched": 0, "created": 0, "updated": 0, "skipped": 0}

        with transaction.atomic():
            for i, row in enumerate(rows, 1):
                result = self._process_row(
                    row, i,
                    class_year_override=class_year_override,
                    source_override=source_override,
                    dry_run=dry_run,
                    allow_unresolved=options.get("allow_unresolved", False),
                )
                if result:
                    stats[result] += 1
                else:
                    stats["skipped"] += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {stats['created']} created, {stats['updated']} updated, "
                f"{stats['skipped']} skipped, {stats['matched']} already up-to-date."
            )
            if not dry_run else
            self.style.WARNING(
                f"[DRY RUN] Would: {stats['created']} create, {stats['updated']} update, "
                f"{stats['skipped']} skip."
            )
        )

    # ── CSV parsing ───────────────────────────────────────────────────────────

    def _parse_csv(self, path: Path) -> list[dict]:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            rows = []
            for r in reader:
                # Strip whitespace from all values
                rows.append({k.strip(): v.strip() for k, v in r.items()})
        return rows

    # ── Per-row processing ────────────────────────────────────────────────────

    def _process_row(
        self,
        row: dict,
        row_num: int,
        class_year_override: int | None,
        source_override: str | None,
        dry_run: bool,
        allow_unresolved: bool = False,
    ) -> str | None:
        """
        Process one CSV row.  Returns 'created', 'updated', 'matched' (no change),
        or None (skipped — logged).
        """
        from ncaa.models import Player, PlayerRecruitingProfile

        # ── Resolve class_year ─────────────────────────────────────────────
        class_year = class_year_override
        if class_year is None:
            raw_cy = row.get("class_year", "").strip()
            if not raw_cy:
                self.stderr.write(
                    f"  Row {row_num}: no class_year — skipping."
                )
                return None
            try:
                class_year = int(raw_cy)
            except ValueError:
                self.stderr.write(
                    f"  Row {row_num}: invalid class_year '{raw_cy}' — skipping."
                )
                return None

        # ── Resolve Player ─────────────────────────────────────────────────
        player = self._resolve_player(row, row_num)
        if player is None:
            if allow_unresolved:
                return self._process_unresolved_row(
                    row, row_num, class_year,
                    source_override=source_override, dry_run=dry_run,
                )
            return None

        # ── Parse numeric fields ───────────────────────────────────────────
        stars           = _parse_int(row.get("stars"))
        national_rank   = _parse_int(row.get("national_rank"))
        position_rank   = _parse_int(row.get("position_rank"))
        composite_score = _parse_float(row.get("composite_score"))
        source          = source_override or row.get("source") or "manual"
        notes           = row.get("notes", "") or ""

        # Validate stars range
        if stars is not None and stars not in range(1, 6):
            self.stderr.write(
                f"  Row {row_num} [{player.display_name}]: "
                f"stars={stars} out of range 1-5 — skipping."
            )
            return None

        # ── Upsert ────────────────────────────────────────────────────────
        defaults = {
            "stars":           stars,
            "national_rank":   national_rank,
            "composite_score": composite_score,
            "position_rank":   position_rank,
            "source":          source,
            "notes":           notes,
        }

        existing_qs = PlayerRecruitingProfile.objects.filter(
            player=player, class_year=class_year
        )
        existing = existing_qs.first()

        if existing is None:
            if not dry_run:
                PlayerRecruitingProfile.objects.create(
                    player=player,
                    class_year=class_year,
                    **defaults,
                )
            stars_str = f"{stars}★" if stars else "unrated"
            self.stdout.write(
                f"  [{'DRY' if dry_run else 'NEW '}] {player.display_name} "
                f"({stars_str}, {class_year})"
            )
            return "created"

        # Check whether anything changed
        changed = any(
            getattr(existing, field) != val
            for field, val in defaults.items()
        )
        if not changed:
            return "matched"

        if not dry_run:
            for field, val in defaults.items():
                setattr(existing, field, val)
            existing.save()

        stars_str = f"{stars}★" if stars else "unrated"
        self.stdout.write(
            f"  [{'DRY' if dry_run else 'UPD'}] {player.display_name} "
            f"({stars_str}, {class_year})"
        )
        return "updated"

    # ── Unresolved (future-class) profiles ────────────────────────────────────

    def _process_unresolved_row(
        self, row, row_num, class_year, source_override, dry_run
    ) -> str | None:
        """
        Store a recruit not yet in the Player table (player=NULL), keyed on
        (normalized_name, class_year, source). Linked to a real Player later
        when they appear in game data.
        """
        from ncaa.models import PlayerRecruitingProfile, Team
        # Sport-agnostic string normalizer; lives in nba.utils historically —
        # candidate for promotion to a shared package (see Phase 5 report).
        from nba.utils.name_utils import normalize_name

        name = row.get("player_name", "").strip()
        if not name:
            self.stderr.write(f"  Row {row_num}: unresolved with no player_name — skipping.")
            return None

        committed_team = None
        team_slug = row.get("committed_team_slug", "").strip()
        if team_slug:
            committed_team = Team.objects.filter(slug=team_slug).first()
            if committed_team is None:
                self.stderr.write(
                    f"  Row {row_num} [{name}]: committed_team_slug "
                    f"'{team_slug}' not found — storing uncommitted."
                )

        stars = _parse_int(row.get("stars"))
        if stars is not None and stars not in range(1, 6):
            self.stderr.write(f"  Row {row_num} [{name}]: stars={stars} out of range — skipping.")
            return None

        defaults = {
            "recruit_name":    name,
            "stars":           stars,
            "national_rank":   _parse_int(row.get("national_rank")),
            "composite_score": _parse_float(row.get("composite_score")),
            "position_rank":   _parse_int(row.get("position_rank")),
            "committed_team":  committed_team,
            "source_url":      row.get("source_url", "") or "",
            "notes":           row.get("notes", "") or "",
        }
        source = source_override or row.get("source") or "manual"

        if dry_run:
            self.stdout.write(f"  [DRY-UNRES] {name} ({class_year}, {source})")
            return "created"
        _, was_created = PlayerRecruitingProfile.objects.update_or_create(
            player=None,
            normalized_name=normalize_name(name),
            class_year=class_year,
            source=source,
            defaults=defaults,
        )
        self.stdout.write(
            f"  [{'NEW-UNRES' if was_created else 'UPD-UNRES'}] {name} ({class_year}, {source})"
        )
        return "created" if was_created else "updated"

    # ── Player resolution ─────────────────────────────────────────────────────

    def _resolve_player(self, row: dict, row_num: int):
        """Return a Player instance or None (logs on failure)."""
        from ncaa.models import Player

        espn_id = row.get("espn_id", "").strip()
        name    = row.get("player_name", "").strip()

        # Preferred path: exact ESPN ID match
        if espn_id:
            try:
                return Player.objects.get(espn_athlete_id=espn_id)
            except Player.DoesNotExist:
                self.stderr.write(
                    f"  Row {row_num}: no Player with espn_id='{espn_id}'"
                    + (f" (name: {name!r})" if name else "")
                    + " — skipping."
                )
                return None

        # Fallback: case-insensitive display_name match
        if not name:
            self.stderr.write(
                f"  Row {row_num}: no espn_id and no player_name — skipping."
            )
            return None

        matches = list(
            Player.objects.filter(display_name__iexact=name)
        )
        if len(matches) == 1:
            return matches[0]
        if len(matches) == 0:
            # Try prefix-match as fallback
            matches = list(Player.objects.filter(display_name__istartswith=name.split()[0]))
            exact = [p for p in matches if p.display_name.lower() == name.lower()]
            if len(exact) == 1:
                return exact[0]
            self.stderr.write(
                f"  Row {row_num}: no Player found matching '{name}' — skipping."
            )
            return None

        # Multiple hits — ambiguous
        names_list = ", ".join(p.display_name for p in matches[:5])
        self.stderr.write(
            f"  Row {row_num}: ambiguous name '{name}' — "
            f"{len(matches)} matches ({names_list}) — skipping."
        )
        return None


# ── Utilities ─────────────────────────────────────────────────────────────────

def _parse_int(val: str | None) -> int | None:
    if not val or not val.strip():
        return None
    try:
        return int(val.strip())
    except (ValueError, TypeError):
        return None


def _parse_float(val: str | None) -> float | None:
    if not val or not val.strip():
        return None
    try:
        return float(val.strip())
    except (ValueError, TypeError):
        return None
