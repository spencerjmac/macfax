"""
Phase 4 P2: _resolve_player_by_name must never cross-assign one player's
BPR history to another via a loose substring match. Exact → normalized →
loud fail; ambiguity fails loud too.
"""

import logging

from django.test import TestCase

from nba.management.commands.compute_nba_team_outlooks import Command
from nba.models import NBAPlayer


class NameResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # near-collision cluster: substring + suffix + diacritic cases
        cls.jalen = NBAPlayer.objects.create(player_id=1001, name="Jalen Williams")
        cls.jaylin = NBAPlayer.objects.create(player_id=1002, name="Jaylin Williams")
        cls.gp2 = NBAPlayer.objects.create(player_id=1003, name="Gary Payton II")
        cls.luka = NBAPlayer.objects.create(player_id=1004, name="Luka Dončić")

    def setUp(self):
        self.cmd = Command()

    def test_exact_match_resolves(self):
        self.assertEqual(self.cmd._resolve_player_by_name("Jalen Williams"), self.jalen)
        self.assertEqual(self.cmd._resolve_player_by_name("Jaylin Williams"), self.jaylin)

    def test_no_substring_cross_assignment(self):
        # "Williams" is a substring of two names — the old icontains fallback
        # would have silently returned one of them. Must resolve to neither.
        self.assertIsNone(self.cmd._resolve_player_by_name("Williams"))

    def test_case_and_diacritic_insensitive(self):
        self.assertEqual(self.cmd._resolve_player_by_name("luka doncic"), self.luka)
        self.assertEqual(self.cmd._resolve_player_by_name("LUKA DONČIĆ"), self.luka)

    def test_suffix_stripping(self):
        # "Gary Payton" (no suffix) normalizes to the same as "Gary Payton II"
        self.assertEqual(self.cmd._resolve_player_by_name("Gary Payton"), self.gp2)

    def test_unknown_name_fails_loud_and_empty(self):
        with self.assertLogs("nba.management.commands.compute_nba_team_outlooks", level="WARNING") as cm:
            result = self.cmd._resolve_player_by_name("Nonexistent Person")
        self.assertIsNone(result)
        self.assertTrue(any("no NBAPlayer matched" in m for m in cm.output))

    def test_ambiguous_normalized_fails_loud(self):
        # "Gary Payton II" and "Gary Payton Jr." both normalize to "gary payton"
        # but neither equals the bare query exactly → tier-2 sees 2 candidates.
        NBAPlayer.objects.create(player_id=1005, name="Gary Payton Jr.")
        with self.assertLogs(
            "nba.management.commands.compute_nba_team_outlooks", level="WARNING"
        ) as cm:
            result = self.cmd._resolve_player_by_name("Gary Payton")
        self.assertIsNone(result)
        self.assertTrue(any("ambiguous" in m for m in cm.output))

    def test_lookup_bpr_returns_empty_on_no_match(self):
        self.assertEqual(self.cmd._lookup_player_bpr("Ghost McPhantom", None), {})
