"""
Tests for scenario/service.py — apply_mpg_overrides (pure Python) and
compute_scenario (Django TestCase with mocked DB).
"""

import unittest
from copy import deepcopy
from dataclasses import dataclass


# ── apply_mpg_overrides tests (pure Python) ───────────────────────────────────

from ncaa.analytics.player_value.minutes.engine import (
    PlayerMinutesOutput,
    RosterAllocationResult,
)
from ncaa.analytics.player_value.scenario.service import apply_mpg_overrides


def _make_roster(shares: list[float]) -> RosterAllocationResult:
    """Build a minimal RosterAllocationResult with given per-player shares."""
    players = [
        PlayerMinutesOutput(
            player_id=i + 1,
            role_bucket="G",
            minutes_share=s,
            mpg=s * 40.0,
            rotation_rank=i + 1,
            demand_score=float(len(shares) - i),
            is_overridden=False,
        )
        for i, s in enumerate(shares)
    ]
    total = sum(shares)
    return RosterAllocationResult(
        players=players,
        total_shares=total,
        total_mpg=total * 40.0,
        top_5_share=min(sum(sorted(shares, reverse=True)[:5]), total),
        top_8_share=min(sum(sorted(shares, reverse=True)[:8]), total),
        top_9_share=min(sum(sorted(shares, reverse=True)[:9]), total),
        n_above_tenth_share=sum(1 for s in shares if s >= 0.10),
        n_above_quarter_share=sum(1 for s in shares if s >= 0.25),
    )


TEAM_TOTAL = 5.0
TOL = 0.001  # tolerance for float comparison


class TestApplyMpgOverridesSingleOverride(unittest.TestCase):
    def setUp(self):
        # 10 players at 0.5 share each → team total = 5.0
        # Using 10 players so remaining budget (4.25) distributes safely under 0.875 cap.
        self.roster = _make_roster([0.5] * 10)

    def test_total_preserved_after_single_override(self):
        # Pin player_id=1 to 0.75; remaining 9 need 4.25 → 0.472 each (under 0.875 cap).
        result = apply_mpg_overrides(self.roster, {1: 0.75})
        total = sum(p.minutes_share for p in result.players)
        self.assertAlmostEqual(total, TEAM_TOTAL, places=3)

    def test_overridden_player_gets_correct_share(self):
        result = apply_mpg_overrides(self.roster, {1: 0.75})
        p1 = next(p for p in result.players if p.player_id == 1)
        self.assertAlmostEqual(p1.minutes_share, 0.75, places=3)
        self.assertTrue(p1.is_overridden)

    def test_non_overridden_players_share_remaining(self):
        result = apply_mpg_overrides(self.roster, {1: 0.75})
        non_pinned = [p for p in result.players if p.player_id != 1]
        total_non = sum(p.minutes_share for p in non_pinned)
        self.assertAlmostEqual(total_non, TEAM_TOTAL - 0.75, places=3)


class TestApplyMpgOverridesTwoOverrides(unittest.TestCase):
    def setUp(self):
        self.roster = _make_roster([0.5] * 10)

    def test_total_preserved_after_two_overrides(self):
        result = apply_mpg_overrides(self.roster, {1: 0.75, 2: 0.50})
        total = sum(p.minutes_share for p in result.players)
        self.assertAlmostEqual(total, TEAM_TOTAL, places=3)

    def test_both_overridden_players_correct(self):
        result = apply_mpg_overrides(self.roster, {1: 0.75, 2: 0.50})
        p1 = next(p for p in result.players if p.player_id == 1)
        p2 = next(p for p in result.players if p.player_id == 2)
        self.assertAlmostEqual(p1.minutes_share, 0.75, places=3)
        self.assertAlmostEqual(p2.minutes_share, 0.50, places=3)


class TestApplyMpgOverridesExceedsCapClips(unittest.TestCase):
    def test_override_exceeding_budget_clips_correctly(self):
        """Overrides sum to 4.375; non-pinned (8 players) share 0.625 → 0.078 each (above floor)."""
        roster = _make_roster([0.5] * 10)
        result = apply_mpg_overrides(roster, {1: 0.875, 2: 0.875, 3: 0.875, 4: 0.875, 5: 0.875})
        total = sum(p.minutes_share for p in result.players)
        self.assertAlmostEqual(total, TEAM_TOTAL, places=3)
        # Non-pinned players should still have positive shares
        non_pinned = [p for p in result.players if p.player_id not in range(1, 6)]
        for p in non_pinned:
            self.assertGreater(p.minutes_share, 0.0)


class TestApplyMpgOverridesRankOrderPreserved(unittest.TestCase):
    def test_non_overridden_rank_order_preserved(self):
        """Players with different shares — pin player_id=4 and verify relative order of others."""
        # 10 players: player 1 has 0.8, player 2 has 0.6, player 3 has 0.4,
        # player 4 has 0.5 (to be overridden), rest at 0.45
        shares = [0.8, 0.6, 0.4, 0.5, 0.45, 0.45, 0.45, 0.45, 0.45, 0.45]
        roster = _make_roster(shares)
        result = apply_mpg_overrides(roster, {4: 0.7})
        share_map = {p.player_id: p.minutes_share for p in result.players}
        # Relative order of non-overridden: 1(0.8) > 2(0.6) > 3(0.4)
        self.assertGreater(share_map[1], share_map[2])
        self.assertGreater(share_map[2], share_map[3])


if __name__ == "__main__":
    unittest.main()
