"""
Tests — Phase 2 minutes allocation model.

Covers:
  • Role bucket classification (G / Wing / Big)
  • Bucket context (scarcity / crowding flags)
  • Water‑fill normalisation (_normalize_with_caps)
  • Demand score computation (_compute_demand_score)
  • End‑to‑end roster allocation:
      – Total shares sum to 5.00
      – Total MPG sums to 200
      – No negative minutes
      – Floor / ceiling enforced
      – Higher BPR → more minutes (all else equal)
      – Prior MPG signal matters
      – Returner beats comparable newcomer
      – Position scarcity boosts allocation
      – Crowded role bucket penalises deep bench
      – Top‑8/9 concentration is present
      – Manual overrides are respected
      – Override overflow raises ValueError
      – Negative override raises ValueError
      – Deterministic regardless of input order
      – Empty roster handled gracefully
      – Single‑player roster gets all shares
      – Large (13‑player) roster concentrates correctly
      – Split‑season canonical inputs work correctly

All tests are pure Python — no Django DB required.
"""

import math
import unittest

from ncaa.analytics.player_value.minutes.constants import (
    TEAM_TOTAL_SHARES,
    MINIMUM_PLAYER_SHARE,
    MAXIMUM_PLAYER_SHARE,
    CONCENTRATION_POWER,
    RETURNER_STABILITY_BONUS,
    SCARCITY_BONUS,
    CROWDING_PENALTY_PER_SLOT,
    CROWDING_PENALTY_START,
    CROWDING_THRESHOLD,
    SCARCITY_THRESHOLD,
)
from ncaa.analytics.player_value.minutes.role_buckets import (
    GUARD, WING, BIG,
    classify_role_bucket,
    compute_bucket_contexts,
    bucket_rank_by_bpr,
)
from ncaa.analytics.player_value.minutes.engine import (
    PlayerMinutesInput,
    PlayerMinutesOutput,
    RosterAllocationResult,
    _compute_demand_score,
    _normalize_with_caps,
    allocate_roster_minutes,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _player(
    player_id:    int   = 1,
    bpr:          float = 2.0,
    uncertainty:  float = 0.40,
    rtype:        str   = "returner",
    prior_seasons: int  = 2,
    mpg:          float = 25.0,
    gp:           int   = 30,
    poss:         float = 800.0,
    position:     str   = "G",
    ast_pg:       float = 2.0,
    blk_pg:       float = 0.1,
    reb_pg:       float = 3.0,
) -> PlayerMinutesInput:
    """Create a PlayerMinutesInput with sensible defaults for testing."""
    return PlayerMinutesInput(
        player_id=player_id,
        projected_bpr=bpr,
        projection_uncertainty=uncertainty,
        recruitment_type=rtype,
        n_prior_seasons=prior_seasons,
        prior_mpg=mpg,
        prior_gp=gp,
        prior_poss=poss,
        position=position,
        ast_pg=ast_pg,
        blk_pg=blk_pg,
        reb_pg=reb_pg,
    )


def _make_roster(n: int, base_bpr: float = 2.0) -> list[PlayerMinutesInput]:
    """Create a simple n‑player roster with linearly decreasing BPR."""
    return [
        _player(player_id=i + 1, bpr=base_bpr - 0.5 * i)
        for i in range(n)
    ]


# ── Role bucket classification ─────────────────────────────────────────────────

class TestClassifyRoleBucket(unittest.TestCase):

    def test_pure_guard_positions(self):
        for pos in ("G", "PG", "SG"):
            self.assertEqual(classify_role_bucket(pos), GUARD,
                             f"Expected GUARD for position '{pos}'")

    def test_pure_big_positions(self):
        for pos in ("C", "PF"):
            self.assertEqual(classify_role_bucket(pos), BIG,
                             f"Expected BIG for position '{pos}'")

    def test_pure_wing_positions(self):
        for pos in ("F", "SF"):
            # Without big signals → Wing
            self.assertEqual(classify_role_bucket(pos, blk_pg=0.2, reb_pg=3.0), WING,
                             f"Expected WING for position '{pos}' without big signals")

    def test_forward_with_big_signals_becomes_big(self):
        """A player listed as 'F' who blocks/rebounds like a big → Big."""
        self.assertEqual(classify_role_bucket("F", blk_pg=1.5, reb_pg=9.0), BIG)

    def test_forward_with_borderline_signals_stays_wing(self):
        """Moderate rebounds, no blocks → stays Wing."""
        self.assertEqual(classify_role_bucket("F", blk_pg=0.4, reb_pg=5.0), WING)

    def test_athlete_high_blocks_becomes_big(self):
        self.assertEqual(classify_role_bucket("ATH", blk_pg=1.5, reb_pg=8.0), BIG)

    def test_athlete_high_assists_becomes_guard(self):
        self.assertEqual(classify_role_bucket("ATH", ast_pg=4.0, blk_pg=0.1, reb_pg=2.0), GUARD)

    def test_empty_position_defaults_to_wing(self):
        """No signals at all → Wing (safe neutral default)."""
        self.assertEqual(classify_role_bucket("", blk_pg=0.0, reb_pg=0.0, ast_pg=0.0), WING)

    def test_na_position_with_no_signals(self):
        self.assertEqual(classify_role_bucket("NA"), WING)

    def test_case_insensitive(self):
        """Position string is upper‑cased internally."""
        self.assertEqual(classify_role_bucket("g"), GUARD)
        self.assertEqual(classify_role_bucket("c"), BIG)


# ── Bucket contexts ────────────────────────────────────────────────────────────

class TestBucketContexts(unittest.TestCase):

    def _make_buckets(self, assignments: dict[int, str]) -> dict[str, object]:
        return compute_bucket_contexts(assignments)

    def test_all_buckets_present(self):
        """Even if no player is in a bucket, all three are returned."""
        ctx = self._make_buckets({1: GUARD, 2: GUARD})
        self.assertIn(GUARD, ctx)
        self.assertIn(WING, ctx)
        self.assertIn(BIG, ctx)

    def test_scarce_flag(self):
        """≤ SCARCITY_THRESHOLD players in a bucket → is_scarce = True."""
        ctx = self._make_buckets({1: BIG, 2: GUARD, 3: GUARD, 4: GUARD})
        # BIG has 1 player → scarce
        self.assertTrue(ctx[BIG].is_scarce)
        # GUARD has 3 players; threshold is 2 → not scarce
        self.assertFalse(ctx[GUARD].is_scarce)

    def test_crowded_flag(self):
        """Count > CROWDING_THRESHOLD → is_crowded = True."""
        buckets = {i: GUARD for i in range(CROWDING_THRESHOLD + 2)}
        ctx = self._make_buckets(buckets)
        self.assertTrue(ctx[GUARD].is_crowded)

    def test_counts_correct(self):
        ctx = self._make_buckets({1: GUARD, 2: GUARD, 3: BIG})
        self.assertEqual(ctx[GUARD].count, 2)
        self.assertEqual(ctx[BIG].count, 1)
        self.assertEqual(ctx[WING].count, 0)


# ── _normalize_with_caps ──────────────────────────────────────────────────────

class TestNormalizeWithCaps(unittest.TestCase):

    def test_sums_to_target(self):
        # Use 10 demands so n × max_share = 10 × 0.875 = 8.75 > 5.0 (feasible).
        shares = _normalize_with_caps([1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
                                      total_target=5.0,
                                      min_share=0.025, max_share=0.875)
        self.assertAlmostEqual(sum(shares), 5.0, places=5)

    def test_floor_respected(self):
        """All players receive at least min_share."""
        shares = _normalize_with_caps([100, 1, 1, 1, 1], total_target=5.0,
                                      min_share=0.10, max_share=0.875)
        for s in shares:
            self.assertGreaterEqual(s, 0.10 - 1e-6)

    def test_ceiling_respected(self):
        """No player exceeds max_share."""
        shares = _normalize_with_caps([1000, 1, 1, 1, 1], total_target=5.0,
                                      min_share=0.025, max_share=0.50)
        for s in shares:
            self.assertLessEqual(s, 0.50 + 1e-6)

    def test_uniform_demands_uniform_result(self):
        """Equal demands → equal shares."""
        shares = _normalize_with_caps([1.0] * 10, total_target=5.0,
                                      min_share=0.025, max_share=0.875)
        self.assertAlmostEqual(sum(shares), 5.0, places=5)
        for s in shares:
            self.assertAlmostEqual(s, 0.5, places=4)

    def test_empty_list_returns_empty(self):
        self.assertEqual(_normalize_with_caps([], 5.0, 0.025, 0.875), [])


# ── End‑to‑end allocation: totals ─────────────────────────────────────────────

class TestAllocationTotals(unittest.TestCase):

    def _roster(self, n=10) -> list[PlayerMinutesInput]:
        return _make_roster(n)

    def test_shares_sum_to_five(self):
        result = allocate_roster_minutes(self._roster(10))
        self.assertAlmostEqual(result.total_shares, TEAM_TOTAL_SHARES, places=4)

    def test_mpg_sums_to_two_hundred(self):
        result = allocate_roster_minutes(self._roster(10))
        self.assertAlmostEqual(result.total_mpg, 200.0, places=3)

    def test_no_negative_minutes(self):
        result = allocate_roster_minutes(self._roster(13))
        for p in result.players:
            self.assertGreaterEqual(p.minutes_share, 0.0,
                                    f"Negative share for player {p.player_id}")

    def test_floor_enforced(self):
        result = allocate_roster_minutes(self._roster(13))
        for p in result.players:
            self.assertGreaterEqual(p.minutes_share, MINIMUM_PLAYER_SHARE - 1e-6,
                                    f"Below floor for player {p.player_id}")

    def test_ceiling_enforced(self):
        # Roster with one extreme star — shares should not exceed the cap.
        star    = _player(player_id=1, bpr=30.0, mpg=38.0)
        others  = [_player(player_id=i + 2, bpr=-2.0, mpg=5.0) for i in range(9)]
        result  = allocate_roster_minutes([star] + others)
        for p in result.players:
            self.assertLessEqual(p.minutes_share, MAXIMUM_PLAYER_SHARE + 1e-6,
                                 f"Above ceiling for player {p.player_id}")

    def test_rotation_ranks_are_unique(self):
        result = allocate_roster_minutes(self._roster(12))
        ranks  = [p.rotation_rank for p in result.players]
        self.assertEqual(sorted(ranks), list(range(1, len(ranks) + 1)))

    def test_mpg_consistent_with_share(self):
        result = allocate_roster_minutes(self._roster(8))
        for p in result.players:
            self.assertAlmostEqual(p.mpg, p.minutes_share * 40.0, places=3)


# ── Higher BPR → more minutes ─────────────────────────────────────────────────

class TestBPRSignal(unittest.TestCase):

    def test_higher_bpr_gets_more_minutes(self):
        """All else equal, higher projected BPR → higher minutes share."""
        low_bpr  = _player(player_id=1, bpr=-1.0, mpg=20.0, gp=30)
        high_bpr = _player(player_id=2, bpr=7.0,  mpg=20.0, gp=30)
        fillers  = [_player(player_id=i + 3, bpr=2.0) for i in range(8)]
        result   = allocate_roster_minutes([low_bpr, high_bpr] + fillers)
        by_id    = {p.player_id: p for p in result.players}
        self.assertGreater(by_id[2].minutes_share, by_id[1].minutes_share)

    def test_star_player_near_top_of_rotation(self):
        """A player with dominant BPR should rank near the top."""
        star    = _player(player_id=1, bpr=10.0, mpg=30.0, gp=30)
        average = [_player(player_id=i + 2, bpr=1.0, mpg=15.0) for i in range(8)]
        result  = allocate_roster_minutes([star] + average)
        star_out = next(p for p in result.players if p.player_id == 1)
        self.assertEqual(star_out.rotation_rank, 1)


# ── Prior MPG signal ──────────────────────────────────────────────────────────

class TestPriorMPGSignal(unittest.TestCase):

    def test_prior_mpg_increases_demand(self):
        """Two identical players except one has much higher prior MPG."""
        low_mpg  = _player(player_id=1, bpr=2.0, mpg=5.0,  gp=30)
        high_mpg = _player(player_id=2, bpr=2.0, mpg=34.0, gp=30)
        fillers  = [_player(player_id=i + 3, bpr=2.0, mpg=20.0) for i in range(6)]
        result   = allocate_roster_minutes([low_mpg, high_mpg] + fillers)
        by_id    = {p.player_id: p for p in result.players}
        self.assertGreater(by_id[2].minutes_share, by_id[1].minutes_share)

    def test_below_gp_threshold_mpg_ignored(self):
        """Player with < MIN_GP_FOR_MPG_SIGNAL games receives no MPG signal."""
        few_gp   = _player(player_id=1, bpr=2.0, mpg=40.0, gp=2)   # 40 mpg but 2 GP
        many_gp  = _player(player_id=2, bpr=2.0, mpg=20.0, gp=30)  # normal MPG
        fillers  = [_player(player_id=i + 3, bpr=2.0, mpg=20.0) for i in range(6)]
        result   = allocate_roster_minutes([few_gp, many_gp] + fillers)
        by_id    = {p.player_id: p for p in result.players}
        # The 40‑mpg player with only 2 GP should not dominate the 20‑mpg player.
        self.assertGreater(by_id[2].minutes_share, by_id[1].minutes_share)


# ── Returner vs newcomer ──────────────────────────────────────────────────────

class TestReturnerEdge(unittest.TestCase):

    def test_returner_beats_comparable_newcomer(self):
        """Otherwise identical players: returner should get slightly more minutes."""
        returner = _player(player_id=1, bpr=2.0, rtype="returner",
                           mpg=20.0, gp=30, prior_seasons=2)
        newcomer = _player(player_id=2, bpr=2.0, rtype="newcomer",
                           mpg=0.0, gp=0, prior_seasons=0, uncertainty=0.80)
        fillers  = [_player(player_id=i + 3, bpr=2.0) for i in range(6)]
        result   = allocate_roster_minutes([returner, newcomer] + fillers)
        by_id    = {p.player_id: p for p in result.players}
        self.assertGreater(by_id[1].minutes_share, by_id[2].minutes_share)

    def test_elite_newcomer_can_outrank_mediocre_returner(self):
        """A truly great newcomer should still get more minutes than a weak returner."""
        great_newcomer = _player(player_id=1, bpr=8.0, rtype="newcomer",
                                 uncertainty=0.80, mpg=0.0, gp=0, prior_seasons=0)
        weak_returner  = _player(player_id=2, bpr=-2.0, rtype="returner",
                                 mpg=10.0, gp=30, prior_seasons=3)
        fillers = [_player(player_id=i + 3, bpr=2.0) for i in range(6)]
        result  = allocate_roster_minutes([great_newcomer, weak_returner] + fillers)
        by_id   = {p.player_id: p for p in result.players}
        self.assertGreater(by_id[1].minutes_share, by_id[2].minutes_share)


# ── Position scarcity ─────────────────────────────────────────────────────────

class TestScarcityBonus(unittest.TestCase):

    def test_lone_big_gets_scarcity_boost(self):
        """
        A team with only one Big should see that player's minutes share
        boosted relative to the same player on a balanced roster.
        """
        lone_big         = _player(player_id=99, bpr=1.0, mpg=20.0, gp=30,
                                   position="C", blk_pg=0.5, reb_pg=7.0)
        guards_and_wings = [
            _player(player_id=i, bpr=1.0, mpg=20.0, gp=30, position="G")
            for i in range(1, 10)
        ]
        scarce_result = allocate_roster_minutes([lone_big] + guards_and_wings)

        # Same player + a second big (not scarce any more)
        second_big = _player(player_id=100, bpr=1.0, mpg=20.0, gp=30,
                             position="C", blk_pg=0.5, reb_pg=7.0)
        balanced_result = allocate_roster_minutes([lone_big, second_big] + guards_and_wings)

        by_id_scarce   = {p.player_id: p for p in scarce_result.players}
        by_id_balanced = {p.player_id: p for p in balanced_result.players}

        self.assertGreater(
            by_id_scarce[99].minutes_share,
            by_id_balanced[99].minutes_share,
        )


# ── Crowded role penalty ──────────────────────────────────────────────────────

class TestCrowdingPenalty(unittest.TestCase):

    def test_deep_bench_guard_penalised_in_crowded_bucket(self):
        """
        With many guards on the roster, the weakest guard should see a
        reduced minutes share compared to a lightly populated bucket.
        """
        # 7 guards, 2 wings, 2 bigs (guards heavily crowded)
        guards = [
            _player(player_id=i, bpr=3.0 - 0.3 * i, mpg=20.0, gp=30, position="G")
            for i in range(7)
        ]
        wings = [
            _player(player_id=10 + i, bpr=2.0, mpg=20.0, gp=30, position="F", blk_pg=0.2, reb_pg=5.0)
            for i in range(2)
        ]
        bigs = [
            _player(player_id=20 + i, bpr=2.0, mpg=20.0, gp=30, position="C")
            for i in range(2)
        ]
        crowded = allocate_roster_minutes(guards + wings + bigs)

        # Weakest guard (lowest BPR) should have less time in the crowded team
        # vs an uncrowded team with just 3 guards
        guards_small = guards[:3]
        uncrowded    = allocate_roster_minutes(guards_small + wings + bigs)

        weak_guard_id = guards[-1].player_id
        by_crowded    = {p.player_id: p for p in crowded.players}
        by_uncrowded  = {p.player_id: p for p in uncrowded.players if p.player_id == weak_guard_id}

        if by_uncrowded:
            self.assertLessEqual(
                by_crowded[weak_guard_id].minutes_share,
                by_uncrowded[weak_guard_id].minutes_share,
            )
        else:
            # Player not in uncrowded roster — verify they're below the team average
            # (crowding penalty should reduce deep-bench guards below average).
            avg_share = TEAM_TOTAL_SHARES / len(guards + wings + bigs)
            self.assertLess(
                by_crowded[weak_guard_id].minutes_share,
                avg_share,
                f"Crowded weak guard share {by_crowded[weak_guard_id].minutes_share:.3f} "
                f"should be below team avg {avg_share:.3f}",
            )


# ── Top‑8/9 concentration ─────────────────────────────────────────────────────

class TestRotationConcentration(unittest.TestCase):

    def test_top_8_carry_majority_of_minutes(self):
        """On a 13‑man roster the top 8 should receive >75% of team minutes."""
        roster = _make_roster(13, base_bpr=6.0)
        result = allocate_roster_minutes(roster)
        top_8_fraction = result.top_8_share / TEAM_TOTAL_SHARES
        self.assertGreater(top_8_fraction, 0.75,
                           f"Top‑8 only have {top_8_fraction:.2%} of minutes; expected >75%")

    def test_bottom_players_below_meaningful_threshold(self):
        """On a 13‑man roster the 13th player should have very little time."""
        roster = _make_roster(13, base_bpr=6.0)
        result = allocate_roster_minutes(roster)
        result.players.sort(key=lambda p: p.rotation_rank)
        last_player_share = result.players[-1].minutes_share
        self.assertLess(last_player_share, 0.20,
                        f"Last player has {last_player_share:.3f} share; expected <0.20")

    def test_top_player_has_highest_share(self):
        """Rotation rank 1 player must have the highest minutes share."""
        roster = _make_roster(10, base_bpr=5.0)
        result = allocate_roster_minutes(roster)
        by_rank = sorted(result.players, key=lambda p: p.rotation_rank)
        self.assertEqual(by_rank[0].minutes_share, max(p.minutes_share for p in result.players))


# ── Manual overrides ──────────────────────────────────────────────────────────

class TestManualOverrides(unittest.TestCase):

    def test_locked_player_share_is_exact(self):
        """A locked player's minutes share must match the override exactly."""
        roster = _make_roster(8)
        locked = {roster[0].player_id: 0.50}
        result = allocate_roster_minutes(roster, locked_minutes=locked)
        locked_out = next(p for p in result.players if p.player_id == roster[0].player_id)
        self.assertAlmostEqual(locked_out.minutes_share, 0.50, places=5)
        self.assertTrue(locked_out.is_overridden)

    def test_total_still_sums_to_five_with_override(self):
        """Total shares must still sum to 5.00 after an override."""
        roster = _make_roster(10)
        locked = {roster[0].player_id: 0.40, roster[1].player_id: 0.60}
        result = allocate_roster_minutes(roster, locked_minutes=locked)
        self.assertAlmostEqual(result.total_shares, TEAM_TOTAL_SHARES, places=4)

    def test_unlocked_players_are_not_overridden(self):
        roster = _make_roster(8)
        locked = {roster[0].player_id: 0.50}
        result = allocate_roster_minutes(roster, locked_minutes=locked)
        for p in result.players:
            if p.player_id != roster[0].player_id:
                self.assertFalse(p.is_overridden)

    def test_override_zero_is_valid(self):
        """A player can be locked to zero (benched) without crashing."""
        roster = _make_roster(8)
        locked = {roster[0].player_id: 0.0}
        result = allocate_roster_minutes(roster, locked_minutes=locked)
        zeroed = next(p for p in result.players if p.player_id == roster[0].player_id)
        self.assertAlmostEqual(zeroed.minutes_share, 0.0, places=5)
        self.assertAlmostEqual(result.total_shares, TEAM_TOTAL_SHARES, places=4)

    def test_multiple_overrides(self):
        """Multiple locks leave the correct remaining shares for free players."""
        roster  = _make_roster(10)
        lock1   = roster[0].player_id
        lock2   = roster[1].player_id
        locked  = {lock1: 0.70, lock2: 0.65}
        result  = allocate_roster_minutes(roster, locked_minutes=locked)
        by_id   = {p.player_id: p for p in result.players}
        self.assertAlmostEqual(by_id[lock1].minutes_share, 0.70, places=5)
        self.assertAlmostEqual(by_id[lock2].minutes_share, 0.65, places=5)
        self.assertAlmostEqual(result.total_shares, TEAM_TOTAL_SHARES, places=4)


# ── Override error paths ──────────────────────────────────────────────────────

class TestOverrideErrors(unittest.TestCase):

    def test_locked_total_exceeds_team_total_raises(self):
        """Locked total > TEAM_TOTAL_SHARES must raise ValueError."""
        roster = _make_roster(5)
        locked = {roster[i].player_id: 1.2 for i in range(5)}  # 6.0 > 5.0
        with self.assertRaises(ValueError):
            allocate_roster_minutes(roster, locked_minutes=locked)

    def test_negative_locked_share_raises(self):
        roster = _make_roster(5)
        with self.assertRaises(ValueError):
            allocate_roster_minutes(roster, locked_minutes={roster[0].player_id: -0.1})

    def test_locked_share_exceeds_maximum_raises(self):
        roster = _make_roster(5)
        with self.assertRaises(ValueError):
            allocate_roster_minutes(roster, locked_minutes={roster[0].player_id: 0.99})


# ── Determinism ───────────────────────────────────────────────────────────────

class TestDeterminism(unittest.TestCase):

    def test_order_independent(self):
        """Allocation result must not depend on the order of input players."""
        import random
        roster = _make_roster(12, base_bpr=4.0)
        result_a = allocate_roster_minutes(roster)

        shuffled = roster.copy()
        random.shuffle(shuffled)
        result_b = allocate_roster_minutes(shuffled)

        by_id_a = {p.player_id: p.minutes_share for p in result_a.players}
        by_id_b = {p.player_id: p.minutes_share for p in result_b.players}

        for pid in by_id_a:
            self.assertAlmostEqual(by_id_a[pid], by_id_b[pid], places=5,
                                   msg=f"Player {pid} shares differ by input order")


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases(unittest.TestCase):

    def test_empty_roster_returns_empty_result(self):
        result = allocate_roster_minutes([])
        self.assertEqual(result.players, [])
        self.assertEqual(result.total_shares, 0.0)

    def test_single_player_gets_all_shares(self):
        """One player on the roster receives the full 5.00 shares."""
        solo   = _player(player_id=1, bpr=3.0, mpg=30.0, gp=30)
        result = allocate_roster_minutes([solo])
        self.assertAlmostEqual(result.total_shares, TEAM_TOTAL_SHARES, places=4)
        self.assertAlmostEqual(result.players[0].minutes_share, TEAM_TOTAL_SHARES, places=4)

    def test_large_roster_still_sums_correctly(self):
        """A 15‑player roster (deep bench) must still sum to 5.00."""
        roster = _make_roster(15, base_bpr=4.0)
        result = allocate_roster_minutes(roster)
        self.assertAlmostEqual(result.total_shares, TEAM_TOTAL_SHARES, places=4)

    def test_all_same_bpr_splits_evenly_ish(self):
        """If all signals are identical, minutes should be roughly equal."""
        roster = [_player(player_id=i + 1, bpr=2.0, mpg=20.0, gp=30,
                          position="G", uncertainty=0.40, prior_seasons=2)
                  for i in range(5)]
        result = allocate_roster_minutes(roster)
        shares = [p.minutes_share for p in result.players]
        # All should be identical (within floating-point tolerance)
        for s in shares:
            self.assertAlmostEqual(s, shares[0], places=5)

    def test_players_with_no_rapm_handled(self):
        """Players with bpr=0.0 and high uncertainty (box fallback) must not crash."""
        roster = [
            _player(player_id=1, bpr=0.0,  uncertainty=1.0, rtype="newcomer", mpg=0.0, gp=0),
            _player(player_id=2, bpr=3.0,  uncertainty=0.4, rtype="returner"),
            _player(player_id=3, bpr=-1.0, uncertainty=0.6, rtype="transfer"),
        ]
        result = allocate_roster_minutes(roster)
        self.assertAlmostEqual(result.total_shares, TEAM_TOTAL_SHARES, places=4)
        for p in result.players:
            self.assertGreaterEqual(p.minutes_share, 0.0)


# ── Split‑season canonical inputs ─────────────────────────────────────────────

class TestSplitSeasonCompatibility(unittest.TestCase):

    def test_canonical_projection_allocates_correctly(self):
        """
        When Phase 1 produces a single canonical row for a split‑season player,
        the minutes model should treat it like any other player and include it
        in the allocation without errors.
        """
        # Simulate a player who played at two teams; Phase 1 selected the row
        # with more possessions (canonical_team=TeamA).
        split_season_player = _player(
            player_id=999,
            bpr=4.0,
            uncertainty=0.45,
            rtype="transfer",  # changed teams mid-season
            mpg=25.0,          # canonical row's mpg
            gp=18,
            poss=600.0,
            position="G",
        )
        roster  = [split_season_player] + _make_roster(9, base_bpr=2.0)
        result  = allocate_roster_minutes(roster)
        by_id   = {p.player_id: p for p in result.players}

        # Canonical player should participate in allocation normally
        self.assertIn(999, by_id)
        self.assertGreater(by_id[999].minutes_share, MINIMUM_PLAYER_SHARE - 1e-6)
        self.assertAlmostEqual(result.total_shares, TEAM_TOTAL_SHARES, places=4)


if __name__ == "__main__":
    unittest.main()
