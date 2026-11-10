"""
Phase 3 task 3.1: nba_compute_box_bpr --lebron-blend-w sets LEBRON's weight in
the training-target blend (default 0.7, unchanged), and --dump-json PATH writes
{nba_id: [box_obpr, box_dbpr]} to PATH and skips all database writes.

Real test database; model fitting and NBA-wide inputs are stood in for.
"""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from nba.management.commands.nba_compute_box_bpr import LEBRON_BLEND_W
from nba.models import NBAPlayer, NBAPlayerSeasonStats, NBASeason

MOD = "nba.management.commands.nba_compute_box_bpr"


class BoxBlendAndDumpTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.season = NBASeason.objects.create(year=2026, display_name="2025-26")
        # 31 players with RAPM targets (box BPR needs >= 30); RAPM O 1.0 / D 0.5.
        cls.players = [NBAPlayer.objects.create(player_id=1000 + n, name=f"Player {n}") for n in range(31)]
        for p in cls.players:
            NBAPlayerSeasonStats.objects.create(
                player=p, season=cls.season, team=None, season_type="regular", gp=60, mpg=25.0,
                baseline_obpr=1.0, baseline_dbpr=0.5,
                box_obpr=9.0, box_dbpr=9.0, box_bpr=18.0, nba_archetype="scorer")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

        # LEBRON O 3.0 / D -1.5 for every player; predictions differ per player.
        lebron = {p.pk: (3.0, -1.5) for p in self.players}
        self.preds = {p.pk: {"box_obpr": 0.1 * i, "box_dbpr": -0.05 * i, "archetype": "connector"}
                      for i, p in enumerate(self.players)}
        artifacts = {"off_cv_alpha": 5.0, "def_cv_alpha": 10.0, "n_train_off": 31, "n_train_def": 31,
                     "n_mpir_excluded": 0}
        self.train = mock.MagicMock(return_value=artifacts)
        for target, value in {
            "compute_opp_quality_map": mock.MagicMock(return_value={}),
            "compute_team_adj_em_map": mock.MagicMock(return_value={}),
            "build_career_stats_map": mock.MagicMock(return_value={}),
            "_load_lebron_targets": mock.MagicMock(return_value=lebron),
            "train_nba_box_bpr": self.train,
            "predict_nba_box_bpr": mock.MagicMock(return_value=self.preds),
        }.items():
            patcher = mock.patch(f"{MOD}.{target}", value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name in ("_print_top_players", "_print_fix_summary"):
            patcher = mock.patch(f"{MOD}.Command.{name}")
            patcher.start()
            self.addCleanup(patcher.stop)

    def _targets(self, *args):
        call_command("nba_compute_box_bpr", "--season", "2026", "--dry-run", *args, stdout=StringIO())
        kw = self.train.call_args.kwargs
        pk = self.players[0].pk
        return kw["target_obpr"][pk], kw["target_dbpr"][pk]

    def test_default_blend_is_unchanged(self):
        self.assertEqual(LEBRON_BLEND_W, 0.7)
        o, d = self._targets()
        self.assertAlmostEqual(o, 0.3 * 1.0 + 0.7 * 3.0)
        self.assertAlmostEqual(d, 0.3 * 0.5 + 0.7 * -1.5)

    def test_blend_weight_flag(self):
        o, d = self._targets("--lebron-blend-w", "0")
        self.assertEqual((o, d), (1.0, 0.5))                       # pure RAPM
        o, d = self._targets("--lebron-blend-w", "0.25")
        self.assertAlmostEqual(o, 0.75 * 1.0 + 0.25 * 3.0)
        self.assertAlmostEqual(d, 0.75 * 0.5 + 0.25 * -1.5)

    def test_dump_json_writes_nba_ids_and_skips_db_writes(self):
        path = self.dir / "sub" / "box.json"
        call_command("nba_compute_box_bpr", "--season", "2026", "--dump-json", str(path), stdout=StringIO())

        dumped = json.loads(path.read_text())
        self.assertEqual(set(dumped), {str(p.player_id) for p in self.players})   # NBA.com ids, not pks
        for i, p in enumerate(self.players):
            self.assertEqual(dumped[str(p.player_id)], [0.1 * i, -0.05 * i])
        # No writes: every row keeps its old values.
        self.assertEqual(NBAPlayerSeasonStats.objects.filter(box_bpr=18.0, nba_archetype="scorer").count(), 31)

    def test_without_dump_json_the_run_still_writes(self):
        call_command("nba_compute_box_bpr", "--season", "2026", stdout=StringIO())
        row = NBAPlayerSeasonStats.objects.get(player=self.players[2])
        self.assertEqual((row.box_obpr, row.box_dbpr, row.nba_archetype), (0.2, -0.1, "connector"))
