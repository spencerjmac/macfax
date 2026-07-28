"""
export_offseason_moves — re-importable backup taken before a destructive purge.

Invariants pinned here:
- Header is a superset of the import schema (so import_offseason_moves can read
  it back), and every target-season move lands as a row.
- --source narrows the export to one provenance class.
- Refuses to overwrite an existing file (a backup must never clobber a backup).
- Round-trip: export -> purge -> import recreates the moves (existence + type +
  team; provenance resets to manual by design, not asserted).
"""

import csv
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from nba.management.commands.export_offseason_moves import (
    IMPORT_COLUMNS,
    PROVENANCE_COLUMNS,
)
from nba.models import NBASeason, TeamOutseasonMove, TeamSeasonOutlook


class ExportOffseasonMovesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # is_current=2026 so import_offseason_moves derives target season 2027.
        cls.s2026 = NBASeason.objects.create(
            year=2026, display_name="2025-26", is_current=True
        )
        cls.s2027 = NBASeason.objects.create(year=2027, display_name="2026-27")

        cls.out = TeamSeasonOutlook.objects.create(
            team_name="Miami Heat", team_abbr="MIA", team_slug="miami-heat",
            season=cls.s2027, conference="East",
        )
        # A hand-curated trade the roster diff could never reconstruct — the
        # exact thing the backup exists to protect.
        TeamOutseasonMove.objects.create(
            team=cls.out, season=cls.s2027, move_type="traded_in",
            player_name="Giannis Antetokounmpo", detail="From Milwaukee",
            impact_rating="high", source="manual",
        )
        TeamOutseasonMove.objects.create(
            team=cls.out, season=cls.s2027, move_type="signed",
            player_name="Role Player", detail="MLE", impact_rating="medium",
            source="sync",
        )

    def _tmp(self, name="backup.csv"):
        return Path(self.tmpdir) / name

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmpdir = self._td.name
        self.addCleanup(self._td.cleanup)

    def test_header_is_import_superset_and_all_rows_written(self):
        out = self._tmp()
        call_command("export_offseason_moves", target_season=2027, out=str(out))
        with out.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        header = rows[0].keys() if rows else []
        for col in IMPORT_COLUMNS + PROVENANCE_COLUMNS:
            self.assertIn(col, header)
        # import_offseason_moves requires these three specifically.
        for col in ("team_slug", "player_name", "move_type"):
            self.assertIn(col, header)
        self.assertEqual(len(rows), 2)
        names = {r["player_name"] for r in rows}
        self.assertEqual(names, {"Giannis Antetokounmpo", "Role Player"})
        giannis = next(r for r in rows if r["player_name"].startswith("Giannis"))
        self.assertEqual(giannis["team_slug"], "miami-heat")
        self.assertEqual(giannis["move_type"], "traded_in")
        self.assertEqual(giannis["source"], "manual")

    def test_source_filter(self):
        out = self._tmp("manual_only.csv")
        call_command(
            "export_offseason_moves", target_season=2027, source="manual", out=str(out)
        )
        with out.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual([r["player_name"] for r in rows], ["Giannis Antetokounmpo"])

    def test_refuses_to_overwrite(self):
        out = self._tmp("exists.csv")
        out.write_text("do not clobber", encoding="utf-8")
        with self.assertRaises(CommandError):
            call_command("export_offseason_moves", target_season=2027, out=str(out))
        self.assertEqual(out.read_text(encoding="utf-8"), "do not clobber")

    def test_roundtrip_export_purge_import(self):
        out = self._tmp("roundtrip.csv")
        call_command("export_offseason_moves", target_season=2027, out=str(out))

        call_command("purge_offseason_moves", target_season=2027, yes=True)
        self.assertEqual(
            TeamOutseasonMove.objects.filter(season=self.s2027).count(), 0
        )

        call_command("import_offseason_moves", csv_path=str(out))
        restored = TeamOutseasonMove.objects.filter(season=self.s2027)
        self.assertEqual(restored.count(), 2)
        by_name = {m.player_name: m for m in restored}
        self.assertEqual(by_name["Giannis Antetokounmpo"].move_type, "traded_in")
        self.assertEqual(by_name["Giannis Antetokounmpo"].team_id, self.out.id)
