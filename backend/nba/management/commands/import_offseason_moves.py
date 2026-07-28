"""
import_offseason_moves — bulk-create TeamOutseasonMove rows from CSV.

CSV columns (header required):
  team_slug, player_name, move_type, salary, contract_years, notes,
  impact_rating, transaction_date

  move_type one of: signed lost traded_in traded_out waived drafted extended
  salary, contract_years, notes, impact_rating, transaction_date are optional —
  leave blank or omit the column. transaction_date is ISO YYYY-MM-DD (use the
  real trade/signing date on hand-entered rows). Extra columns written by
  export_offseason_moves (source, season, …) are ignored.

Usage:
  python manage.py import_offseason_moves --file tools/moves_2026.csv
  python manage.py import_offseason_moves --file tools/moves_2026.csv --dry-run
  python manage.py import_offseason_moves --file tools/moves_2026.csv \\
      --prospects-json web/src/data/prospects_2026.json

The command is idempotent: uses get_or_create on (team, player_name, move_type).
Running twice with the same input is safe.
"""

import csv
import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from nba.models import NBASeason, TeamOutseasonMove, TeamSeasonOutlook


VALID_MOVE_TYPES = {c[0] for c in TeamOutseasonMove.MOVE_TYPE_CHOICES}
VALID_IMPACT = {"high", "medium", "low"}


class Command(BaseCommand):
    help = "Bulk-import offseason moves from CSV (and optionally from a prospects JSON)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", dest="csv_path", required=False, metavar="PATH",
            help="Path to the moves CSV file.",
        )
        parser.add_argument(
            "--prospects-json", dest="prospects_json", metavar="PATH",
            help="Path to prospects JSON (e.g. web/src/data/prospects_2026.json). "
                 "Creates 'drafted' move rows for each prospect that has a non-null team_slug.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print what would be created without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        csv_path: str | None = options.get("csv_path")
        prospects_path: str | None = options.get("prospects_json")

        if not csv_path and not prospects_path:
            raise CommandError("Provide at least --file or --prospects-json.")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no rows will be written.\n"))

        # Build team_slug → TeamSeasonOutlook lookup, scoped to the target
        # projected season (is_current + 1). Moves attach to that season's rows;
        # an unscoped .all() would collapse to an arbitrary season per slug.
        current = NBASeason.objects.filter(is_current=True).first()
        if current is None:
            raise CommandError("No current season flagged — cannot resolve target season.")
        target_year = current.year + 1
        outlook_by_slug: dict[str, TeamSeasonOutlook] = {
            o.team_slug: o
            for o in TeamSeasonOutlook.objects.filter(season__year=target_year)
        }

        created = skipped = warnings = 0

        # ── CSV source ────────────────────────────────────────────────────────
        if csv_path:
            path = Path(csv_path)
            if not path.exists():
                raise CommandError(f"CSV not found: {csv_path}")

            with path.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                required = {"team_slug", "player_name", "move_type"}
                missing = required - set(reader.fieldnames or [])
                if missing:
                    raise CommandError(f"CSV missing required columns: {missing}")

                for i, row in enumerate(reader, start=2):  # 2 = first data row
                    c, s, w = self._process_row(
                        row=row,
                        row_num=i,
                        outlook_by_slug=outlook_by_slug,
                        dry_run=dry_run,
                        source="CSV",
                    )
                    created += c; skipped += s; warnings += w

        # ── Prospects JSON source ─────────────────────────────────────────────
        if prospects_path:
            ppath = Path(prospects_path)
            if not ppath.exists():
                raise CommandError(f"Prospects JSON not found: {prospects_path}")

            with ppath.open(encoding="utf-8") as fh:
                data = json.load(fh)

            prospects = data.get("prospects", [])
            draft_rows = [p for p in prospects if p.get("team_slug")]

            self.stdout.write(
                f"Prospects JSON: {len(prospects)} total, {len(draft_rows)} with team_slug assigned."
            )

            for p in draft_rows:
                mps = p.get("mps") or p.get("mpsComposite")
                notes = f"MPS={mps:.1f}" if mps is not None else ""
                row = {
                    "team_slug": p["team_slug"],
                    "player_name": p["name"],
                    "move_type": "drafted",
                    "salary": str(p.get("salary", "")),
                    "contract_years": str(p.get("contract_years", "")),
                    "notes": notes,
                    "impact_rating": p.get("impact_rating", "medium"),
                    "_mps_score": mps,
                }
                c, s, w = self._process_row(
                    row=row,
                    row_num=None,
                    outlook_by_slug=outlook_by_slug,
                    dry_run=dry_run,
                    source="prospects JSON",
                )
                created += c; skipped += s; warnings += w

        # ── Summary ───────────────────────────────────────────────────────────
        action = "Would create" if dry_run else "Created"
        self.stdout.write(
            f"\n{action} {created} move rows.  "
            f"Skipped {skipped} (duplicates or lookup failures).  "
            f"Warnings: {warnings}."
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("Re-run without --dry-run to apply."))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _process_row(
        self,
        row: dict,
        row_num: int | None,
        outlook_by_slug: dict[str, TeamSeasonOutlook],
        dry_run: bool,
        source: str,
    ) -> tuple[int, int, int]:
        """Return (created, skipped, warnings) for one row."""
        loc = f"[{source} row {row_num}]" if row_num else f"[{source}]"

        team_slug = (row.get("team_slug") or "").strip().lower()
        player_name = (row.get("player_name") or "").strip()
        move_type = (row.get("move_type") or "").strip().lower()

        if not team_slug or not player_name or not move_type:
            self.stderr.write(f"  {loc} Skipping blank team_slug/player_name/move_type.")
            return 0, 1, 1

        if move_type not in VALID_MOVE_TYPES:
            self.stderr.write(
                f"  {loc} Unknown move_type '{move_type}' for {player_name}. "
                f"Valid: {sorted(VALID_MOVE_TYPES)}"
            )
            return 0, 1, 1

        outlook = outlook_by_slug.get(team_slug)
        if outlook is None:
            self.stderr.write(
                f"  {loc} No TeamSeasonOutlook for team_slug='{team_slug}' "
                f"(player: {player_name}). Skipping."
            )
            return 0, 1, 1

        # Optional fields
        raw_salary = (row.get("salary") or "").strip()
        raw_years = (row.get("contract_years") or "").strip()
        notes = (row.get("notes") or "").strip()
        impact = (row.get("impact_rating") or "medium").strip().lower()
        if impact not in VALID_IMPACT:
            impact = "medium"

        # Optional transaction_date (ISO YYYY-MM-DD). Lets a hand-entered trade
        # carry the real date, so when the date-filter feed eventually exists
        # these rows are already correct instead of NULL. Blank/omitted → NULL;
        # bad format → warn and leave NULL (never guess a date).
        raw_txn_date = (row.get("transaction_date") or "").strip()
        txn_date = None
        if raw_txn_date:
            try:
                txn_date = date.fromisoformat(raw_txn_date)
            except ValueError:
                self.stderr.write(
                    f"  {loc} Bad transaction_date '{raw_txn_date}' for {player_name} "
                    f"— expected YYYY-MM-DD, leaving blank."
                )

        # Build detail string from salary/years/notes
        detail_parts = []
        if raw_salary:
            try:
                salary_m = int(raw_salary) / 1_000_000
                detail_parts.append(f"${salary_m:.1f}M")
            except ValueError:
                detail_parts.append(raw_salary)
        if raw_years:
            try:
                detail_parts.append(f"{int(raw_years)}yr")
            except ValueError:
                detail_parts.append(raw_years)
        if notes:
            detail_parts.append(notes)
        detail = " · ".join(detail_parts)[:200]

        if dry_run:
            self.stdout.write(
                f"  WOULD CREATE  {team_slug:<28} {move_type:<12} {player_name}"
                + (f"  [{detail}]" if detail else "")
            )
            return 1, 0, 0

        mps_score = row.get("_mps_score")
        defaults = {"detail": detail, "impact_rating": impact}
        if mps_score is not None:
            defaults["mps_score"] = float(mps_score)
        if txn_date is not None:
            defaults["transaction_date"] = txn_date

        obj, was_created = TeamOutseasonMove.objects.get_or_create(
            team=outlook,
            season=outlook.season,
            player_name=player_name,
            move_type=move_type,
            defaults=defaults,
        )

        if was_created:
            self.stdout.write(
                f"  + {team_slug:<28} {move_type:<12} {player_name}"
                + (f"  [{detail}]" if detail else "")
            )
            return 1, 0, 0
        else:
            return 0, 1, 0
