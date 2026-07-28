"""
export_offseason_moves — dump a season's TeamOutseasonMove rows to a
re-importable CSV. The reverse of import_offseason_moves.

This is the backup you take BEFORE a destructive purge_offseason_moves +
rebuild. The roster-diff sync can only reconstruct signed/lost rows and never
trades, and moves_2026.csv is near-empty, so hand-curated moves (trades, FA)
exist only in the DB — export them first or the purge loses them for good.

Output header is a SUPERSET of the import schema:
  team_slug, player_name, move_type, salary, contract_years, notes, impact_rating
are read back by import_offseason_moves; the trailing provenance columns
  source, transaction_date, season, round_number, overall_pick, mps_score
are ignored on re-import but kept so a human can see/edit them.

Caveats (backup, not a perfect round-trip):
- salary / contract_years are not stored discretely on the model (import folds
  them into `detail`), so they export blank; `detail` round-trips via `notes`.
- re-import stamps source="manual" (import's default), so restored rows lose
  their sync/draft provenance — that's fine for a safety net; re-run the
  sync/draft writers afterward if you want provenance back.

Usage:
  python manage.py export_offseason_moves --target-season 2027
  python manage.py export_offseason_moves --target-season 2027 --out tools/moves_backup.csv
  python manage.py export_offseason_moves --target-season 2027 --source manual
"""

import csv
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from nba.models import NBASeason, TeamOutseasonMove


# Columns import_offseason_moves reads (order matters for human readability).
IMPORT_COLUMNS = [
    "team_slug", "player_name", "move_type",
    "salary", "contract_years", "notes", "impact_rating",
]
# Extra provenance columns — ignored on re-import, kept for the human editor.
PROVENANCE_COLUMNS = [
    "source", "transaction_date", "season",
    "round_number", "overall_pick", "mps_score",
]


class Command(BaseCommand):
    help = "Export a season's TeamOutseasonMove rows to a re-importable CSV backup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--target-season", dest="target_season", type=int, required=True,
            metavar="YEAR",
            help="Ending year of the projected season whose moves to export, e.g. 2027.",
        )
        parser.add_argument(
            "--out", dest="out", default=None, metavar="PATH",
            help="Output CSV path. Default: tools/moves_backup_<season>_<timestamp>.csv",
        )
        parser.add_argument(
            "--source", dest="source", default=None,
            choices=[c[0] for c in TeamOutseasonMove.SOURCE_CHOICES],
            help="Only export rows with this provenance. Default: all sources.",
        )

    def handle(self, *args, **options):
        target_season: int = options["target_season"]
        source: str | None = options.get("source")
        out: str | None = options.get("out")

        if not NBASeason.objects.filter(year=target_season).exists():
            raise CommandError(f"NBASeason with year={target_season} not found.")

        qs = (
            TeamOutseasonMove.objects
            .filter(season__year=target_season)
            .select_related("team", "season")
            .order_by("team__team_slug", "move_type", "player_name")
        )
        if source is not None:
            qs = qs.filter(source=source)

        total = qs.count()
        scope = f"season {target_season}" + (f", source='{source}'" if source else "")
        if total == 0:
            self.stdout.write(f"No moves for {scope}. Nothing to export.")
            return

        if out is None:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            out = f"tools/moves_backup_{target_season}_{ts}.csv"
        out_path = Path(out)
        if out_path.exists():
            raise CommandError(
                f"Refusing to overwrite existing file: {out_path} (choose another --out)."
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with out_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=IMPORT_COLUMNS + PROVENANCE_COLUMNS)
            writer.writeheader()
            for m in qs:
                writer.writerow({
                    "team_slug": m.team.team_slug,
                    "player_name": m.player_name,
                    "move_type": m.move_type,
                    "salary": "",
                    "contract_years": "",
                    "notes": m.detail,
                    "impact_rating": m.impact_rating,
                    "source": m.source,
                    "transaction_date": (
                        m.transaction_date.isoformat() if m.transaction_date else ""
                    ),
                    "season": m.season.year if m.season_id else "",
                    "round_number": "" if m.round_number is None else m.round_number,
                    "overall_pick": "" if m.overall_pick is None else m.overall_pick,
                    "mps_score": "" if m.mps_score is None else m.mps_score,
                })

        self.stdout.write(self.style.SUCCESS(
            f"Exported {total} moves ({scope}) → {out_path}"
        ))
