"""
Task 5.4 step 0: nba_compute_final_bpr (the LEBRON-prior model) never overwrites
native BPR. It refuses to write a season holding any bpr_model='native-1' row,
before fitting and again at write time, and labels the rows it writes
bpr_model='lebron'. Its dry run still works on a native season. Real test database.
"""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from nba.management.commands import nba_compute_final_bpr as final
from nba.models import NBAPlayer, NBAPlayerSeasonStats, NBASeason


class NativeGuardTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.s2026 = NBASeason.objects.create(year=2026, display_name="2025-26")
        cls.s2025 = NBASeason.objects.create(year=2025, display_name="2024-25")
        cls.p1 = NBAPlayer.objects.create(player_id=101, name="One")
        cls.p2 = NBAPlayer.objects.create(player_id=102, name="Two")

    def _row(self, player, season, **kw):
        return NBAPlayerSeasonStats.objects.create(player=player, season=season, team=None,
                                                   season_type="regular", gp=60, mpg=30.0, **kw)

    def _cmd(self):
        cmd = final.Command()
        cmd.stdout, cmd.stderr = StringIO(), StringIO()
        return cmd

    def test_write_refused_on_a_native_season(self):
        native = self._row(self.p1, self.s2026, obpr=1.0, dbpr=0.5, bpr=1.5, bpr_model="native-1", wins_added=2.0)
        with self.assertRaisesRegex(CommandError, "native BPR rows"):
            call_command("nba_compute_final_bpr", "--season", "2026", stdout=StringIO())
        with self.assertRaisesRegex(CommandError, "native BPR rows"):
            self._cmd()._write_to_db({101: 9.0}, {101: 9.0}, 2026)
        native.refresh_from_db()
        self.assertEqual((native.obpr, native.bpr, native.bpr_model, native.wins_added), (1.0, 1.5, "native-1", 2.0))

    def test_sweep_refused_on_a_native_season_even_with_dry_run(self):
        self._row(self.p1, self.s2026, bpr_model="native-1")
        with self.assertRaisesRegex(CommandError, "native BPR rows"):
            call_command("nba_compute_final_bpr", "--season", "2026", "--sweep", "--dry-run", stdout=StringIO())

    def test_writes_are_labelled_lebron(self):
        r1 = self._row(self.p1, self.s2025)
        self._row(self.p2, self.s2026, bpr_model="native-1")       # another season's native row is no bar
        self._cmd()._write_to_db({101: 1.0}, {101: 0.5}, 2025)
        r1.refresh_from_db()
        self.assertEqual((r1.obpr, r1.dbpr, r1.bpr, r1.bpr_model), (1.0, 0.5, 1.5, "lebron"))

    def test_refuse_if_native_counts_only_that_season(self):
        self._row(self.p1, self.s2026, bpr_model="native-1")
        final.refuse_if_native(2025)                                 # nothing native in 2025
        with self.assertRaises(CommandError):
            final.refuse_if_native(2026)
