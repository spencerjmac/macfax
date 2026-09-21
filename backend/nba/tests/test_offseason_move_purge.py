"""
purge_offseason_moves — guarded full-season purge for the legacy-contamination
cleanup (migration 0026 canonized date-less bleed rows under the target season).

Invariants pinned here:
- No --yes → dry run, nothing deleted (destructive command must be opt-in).
- --yes → deletes every move for the target season, leaves other seasons alone.
- --source narrows the purge to one provenance class (the same source-scoping
  the sync's --replace relies on to spare draft/manual rows).
- Unknown target season → CommandError, not a silent no-op.
"""

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from nba.models import NBASeason, TeamOutseasonMove, TeamSeasonOutlook


class PurgeOffseasonMovesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s2026 = NBASeason.objects.create(year=2026, display_name="2025-26")
        cls.s2027 = NBASeason.objects.create(year=2027, display_name="2026-27")

        cls.out2027 = TeamSeasonOutlook.objects.create(
            team_name="Boston Celtics", team_abbr="BOS", team_slug="celtics",
            season=cls.s2027, conference="East",
        )
        cls.out2026 = TeamSeasonOutlook.objects.create(
            team_name="Boston Celtics", team_abbr="BOS", team_slug="celtics",
            season=cls.s2026, conference="East",
        )

        # Target-season (2027) moves across all three provenance classes,
        # including the legacy "manual" bleed rows the cleanup exists to evict.
        for i in range(3):
            TeamOutseasonMove.objects.create(
                team=cls.out2027, season=cls.s2027, move_type="signed",
                player_name=f"Sync {i}", source="sync",
            )
        for i in range(2):
            TeamOutseasonMove.objects.create(
                team=cls.out2027, season=cls.s2027, move_type="drafted",
                player_name=f"Draft {i}", source="draft",
            )
        for i in range(4):  # the legacy 196-style rows: source defaulted to manual
            TeamOutseasonMove.objects.create(
                team=cls.out2027, season=cls.s2027, move_type="lost",
                player_name=f"Legacy {i}", source="manual",
            )
        # A different-season move that must survive every 2027 purge.
        TeamOutseasonMove.objects.create(
            team=cls.out2026, season=cls.s2026, move_type="signed",
            player_name="Prior Year", source="sync",
        )

    def test_dry_run_deletes_nothing(self):
        before = TeamOutseasonMove.objects.count()
        call_command("purge_offseason_moves", target_season=2027)  # no --yes
        self.assertEqual(TeamOutseasonMove.objects.count(), before)

    def test_yes_purges_whole_target_season_only(self):
        call_command("purge_offseason_moves", target_season=2027, yes=True)
        # All nine 2027 rows gone; the lone 2026 row untouched.
        self.assertEqual(
            TeamOutseasonMove.objects.filter(season=self.s2027).count(), 0
        )
        self.assertEqual(
            TeamOutseasonMove.objects.filter(season=self.s2026).count(), 1
        )

    def test_source_scoped_purge_spares_other_provenance(self):
        call_command(
            "purge_offseason_moves", target_season=2027, source="sync", yes=True
        )
        rows = TeamOutseasonMove.objects.filter(season=self.s2027)
        self.assertEqual(rows.filter(source="sync").count(), 0)
        self.assertEqual(rows.filter(source="draft").count(), 2)
        self.assertEqual(rows.filter(source="manual").count(), 4)

    def test_unknown_season_raises(self):
        with self.assertRaises(CommandError):
            call_command("purge_offseason_moves", target_season=2099, yes=True)
