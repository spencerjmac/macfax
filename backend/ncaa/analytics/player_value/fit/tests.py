"""
Tests for the Phase 3 Roster Fit Model.

Covers:
  - normalize() / blend_core_oncourt() / tag_archetypes()
  - Offensive fit: creation, shooting, ball security, finishing, pressure,
    off rebounding, role balance
  - Defensive fit: rim protection, def rebounding, disruption, foul discipline,
    perimeter defense, size coverage, mobility, role balance
  - Structural penalties: cap, registry (no double-counting)
  - Overall scoring: minutes weighting, determinism, empty roster edge case
  - score_roster_fit() integration: expected orderings, diagnostics completeness
  - SeasonRefs integration with _build_season_refs()

All tests are stateless — no DB access required.
"""

from __future__ import annotations

from unittest import TestCase

from ncaa.analytics.player_value.fit.archetypes import (
    PlayerFitInput,
    SeasonRefs,
    DEFAULT_REFS,
    normalize,
    blend_core_oncourt,
    tag_archetypes,
)
from ncaa.analytics.player_value.fit.constants import (
    SCORE_MID, SCORE_MIN, SCORE_MAX,
    Z_TO_SCORE_SCALE, WINSOR_SIGMA,
    TOP_ROTATION_THRESHOLD,
    MAX_STRUCTURAL_PENALTY_OFF, MAX_STRUCTURAL_PENALTY_DEF,
    SPACER_FG3A_THRESHOLD, PRIMARY_CREATOR_AST_THRESHOLD,
    SECONDARY_CREATOR_AST_THRESHOLD, RIM_PROTECTOR_BLK_THRESHOLD,
    DISRUPTOR_STL_THRESHOLD, FOUL_PRONE_THRESHOLD,
    WEAK_DEFENDER_DBPR_MAX, BALL_STOPPER_TOV_THRESHOLD,
    BALL_STOPPER_AST_MAX, NON_SHOOTING_BIG_FG3A_MAX,
    OFF_REBOUNDER_THRESHOLD, PRESSURE_DRIVER_FTA_THRESHOLD,
)
from ncaa.analytics.player_value.fit.offense import (
    score_offensive_fit,
    OffensiveFitResult,
)
from ncaa.analytics.player_value.fit.defense import (
    score_defensive_fit,
    DefensiveFitResult,
)
from ncaa.analytics.player_value.fit.engine import (
    score_roster_fit,
    RosterFitResult,
)
from ncaa.analytics.player_value.fit.service import _build_season_refs


# ── Helper factories ──────────────────────────────────────────────────────────

def _make_player(
    player_id: int = 1,
    minutes_share: float = 0.25,
    role_bucket: str = "Wing",
    ast_pg: float = 1.46,
    tov_pg: float = 1.16,
    blk_pg: float = 0.35,
    stl_pg: float = 0.70,
    pf_pg: float = 1.84,
    fg3a_pg: float = 2.44,
    fta_pg: float = 2.16,
    oreb_pg: float = 0.96,
    dreb_pg: float = 2.39,
    efg_pct: float = 0.50,
    ts_pct: float = 0.53,
    ast_to: float = 1.26,
    projected_obpr: float = 0.20,
    projected_dbpr: float = 0.10,
    off_efg_impact: float = 0.24,
    def_efg_impact: float = 0.19,
    off_tov_impact: float = 0.16,
    def_tov_impact: float = 0.06,
    off_orb_impact: float = 0.12,
    def_reb_impact: float = 0.14,
    off_ftr_impact: float = 0.10,
    def_ftr_impact: float = 0.13,
    on_court_adj_o: float = 111.8,
    on_court_adj_d: float = 110.8,
    on_court_off_poss: float = 500.0,
    on_court_def_poss: float = 500.0,
    rotation_rank: int = 5,
    gp: int = 30,
) -> PlayerFitInput:
    """Factory producing a D1-average player for tests."""
    return PlayerFitInput(
        player_id=player_id,
        player_name=f"Player{player_id}",
        minutes_share_p2=minutes_share,
        rotation_rank=rotation_rank,
        role_bucket=role_bucket,
        projected_obpr=projected_obpr,
        projected_dbpr=projected_dbpr,
        gp=gp,
        fg3a_pg=fg3a_pg,
        ast_pg=ast_pg,
        tov_pg=tov_pg,
        blk_pg=blk_pg,
        stl_pg=stl_pg,
        pf_pg=pf_pg,
        oreb_pg=oreb_pg,
        dreb_pg=dreb_pg,
        fta_pg=fta_pg,
        efg_pct=efg_pct,
        ts_pct=ts_pct,
        ast_to=ast_to,
        off_efg_impact=off_efg_impact,
        def_efg_impact=def_efg_impact,
        off_tov_impact=off_tov_impact,
        def_tov_impact=def_tov_impact,
        off_orb_impact=off_orb_impact,
        def_reb_impact=def_reb_impact,
        off_ftr_impact=off_ftr_impact,
        def_ftr_impact=def_ftr_impact,
        on_court_adj_o=on_court_adj_o,
        on_court_adj_d=on_court_adj_d,
        on_court_off_poss=on_court_off_poss,
        on_court_def_poss=on_court_def_poss,
    )


def _avg_roster(n: int = 10) -> list[PlayerFitInput]:
    """Return n average players with equal minutes shares summing to 5.0."""
    share = 5.0 / n  # minutes_share_p2 = mpg/40; 10 equal players → 0.5 each
    return [_make_player(player_id=i, minutes_share=share) for i in range(n)]


# ──────────────────────────────────────────────────────────────────────────────
# 1.  normalize() tests
# ──────────────────────────────────────────────────────────────────────────────

class TestNormalize(TestCase):
    """normalize(value, ref_mean, ref_std) → [SCORE_MIN, SCORE_MAX]"""

    def test_at_mean_returns_50(self):
        self.assertAlmostEqual(normalize(5.0, 5.0, 1.0), SCORE_MID)

    def test_one_sigma_above_mean(self):
        self.assertAlmostEqual(normalize(6.0, 5.0, 1.0), SCORE_MID + Z_TO_SCORE_SCALE)

    def test_one_sigma_below_mean(self):
        self.assertAlmostEqual(normalize(4.0, 5.0, 1.0), SCORE_MID - Z_TO_SCORE_SCALE)

    def test_invert_reverses_direction(self):
        above = normalize(6.0, 5.0, 1.0, invert=False)
        below = normalize(6.0, 5.0, 1.0, invert=True)
        self.assertAlmostEqual(above + below, 2 * SCORE_MID)

    def test_winsorizing_clamps_extreme_values(self):
        # 10σ above mean should be clamped to WINSOR_SIGMA × Z_TO_SCORE_SCALE
        score = normalize(100.0, 5.0, 1.0)
        expected_max = SCORE_MID + WINSOR_SIGMA * Z_TO_SCORE_SCALE
        self.assertAlmostEqual(score, expected_max)

    def test_output_always_in_bounds(self):
        for v in [-100, -1, 0, 5, 50, 1000]:
            s = normalize(float(v), 5.0, 1.0)
            self.assertGreaterEqual(s, SCORE_MIN)
            self.assertLessEqual(s, SCORE_MAX)

    def test_invert_output_in_bounds(self):
        s = normalize(0.0, 5.0, 1.0, invert=True)
        self.assertGreaterEqual(s, SCORE_MIN)
        self.assertLessEqual(s, SCORE_MAX)


# ──────────────────────────────────────────────────────────────────────────────
# 2.  blend_core_oncourt() tests
# ──────────────────────────────────────────────────────────────────────────────

class TestBlendCoreOncourt(TestCase):

    def test_none_oncourt_returns_core_unchanged(self):
        result = blend_core_oncourt(60.0, on_court_value=None,
                                    on_court_poss=None,
                                    ref_mean=110.0, ref_std=9.0)
        self.assertAlmostEqual(result, 60.0)

    def test_zero_poss_gives_zero_reliability(self):
        result = blend_core_oncourt(60.0, on_court_value=120.0,
                                    on_court_poss=0.0,
                                    ref_mean=110.0, ref_std=9.0)
        self.assertAlmostEqual(result, 60.0)

    def test_positive_oncourt_nudges_up(self):
        # on_court_adj_o well above average with 500 poss → positive nudge
        result = blend_core_oncourt(50.0, on_court_value=130.0,
                                    on_court_poss=500.0,
                                    ref_mean=111.8, ref_std=9.0,
                                    max_modifier=6.0)
        self.assertGreater(result, 50.0)

    def test_negative_oncourt_nudges_down(self):
        result = blend_core_oncourt(50.0, on_court_value=95.0,
                                    on_court_poss=500.0,
                                    ref_mean=111.8, ref_std=9.0,
                                    max_modifier=6.0)
        self.assertLess(result, 50.0)

    def test_nudge_does_not_exceed_max_modifier(self):
        # Extremely good on-court — nudge should not exceed max_modifier
        result = blend_core_oncourt(50.0, on_court_value=200.0,
                                    on_court_poss=10000.0,
                                    ref_mean=111.8, ref_std=9.0,
                                    max_modifier=6.0)
        self.assertLessEqual(result, 50.0 + 6.0 + 1e-6)

    def test_result_stays_in_bounds(self):
        result = blend_core_oncourt(95.0, on_court_value=200.0,
                                    on_court_poss=10000.0,
                                    ref_mean=111.8, ref_std=9.0,
                                    max_modifier=6.0)
        self.assertGreaterEqual(result, SCORE_MIN)
        self.assertLessEqual(result, SCORE_MAX)


# ──────────────────────────────────────────────────────────────────────────────
# 3.  tag_archetypes() tests
# ──────────────────────────────────────────────────────────────────────────────

class TestTagArchetypes(TestCase):

    def test_spacer_tag(self):
        p = _make_player(fg3a_pg=SPACER_FG3A_THRESHOLD + 0.1)
        tags = tag_archetypes(p)
        self.assertIn("spacer", tags)

    def test_not_spacer_below_threshold(self):
        p = _make_player(fg3a_pg=SPACER_FG3A_THRESHOLD - 0.1)
        tags = tag_archetypes(p)
        self.assertNotIn("spacer", tags)

    def test_primary_creator_tag(self):
        p = _make_player(ast_pg=PRIMARY_CREATOR_AST_THRESHOLD + 0.5)
        tags = tag_archetypes(p)
        self.assertIn("primary_creator", tags)

    def test_secondary_creator_tag(self):
        p = _make_player(ast_pg=SECONDARY_CREATOR_AST_THRESHOLD + 0.1)
        tags = tag_archetypes(p)
        self.assertIn("secondary_creator", tags)

    def test_ball_stopper_requires_both_conditions(self):
        # high tov + low ast → ball stopper
        p = _make_player(tov_pg=BALL_STOPPER_TOV_THRESHOLD + 0.1,
                         ast_pg=BALL_STOPPER_AST_MAX - 0.1)
        self.assertIn("ball_stopper", tag_archetypes(p))
        # high tov but also high ast → NOT ball stopper
        p2 = _make_player(tov_pg=BALL_STOPPER_TOV_THRESHOLD + 0.1,
                          ast_pg=BALL_STOPPER_AST_MAX + 1.0)
        self.assertNotIn("ball_stopper", tag_archetypes(p2))

    def test_non_shooting_big(self):
        p = _make_player(role_bucket="Big", fg3a_pg=NON_SHOOTING_BIG_FG3A_MAX - 0.1)
        self.assertIn("non_shooting_big", tag_archetypes(p))

    def test_rim_protector_tag(self):
        p = _make_player(blk_pg=RIM_PROTECTOR_BLK_THRESHOLD + 0.1)
        self.assertIn("rim_protector", tag_archetypes(p))

    def test_disruptor_tag(self):
        p = _make_player(stl_pg=DISRUPTOR_STL_THRESHOLD + 0.1)
        self.assertIn("disruptor", tag_archetypes(p))

    def test_foul_prone_tag(self):
        p = _make_player(pf_pg=FOUL_PRONE_THRESHOLD + 0.1)
        self.assertIn("foul_prone", tag_archetypes(p))

    def test_weak_defender_tag(self):
        p = _make_player(projected_dbpr=WEAK_DEFENDER_DBPR_MAX - 0.5)
        self.assertIn("weak_defender", tag_archetypes(p))

    def test_average_player_has_no_extreme_tags(self):
        p = _make_player()
        tags = tag_archetypes(p)
        for extreme in ("spacer", "primary_creator", "rim_protector",
                        "ball_stopper", "weak_defender", "foul_prone"):
            self.assertNotIn(extreme, tags)


# ──────────────────────────────────────────────────────────────────────────────
# 4.  Offensive fit scoring
# ──────────────────────────────────────────────────────────────────────────────

class TestOffensiveFitAverage(TestCase):
    """An all-average roster should score close to 50 on all offensive dims."""

    def setUp(self):
        self.result: OffensiveFitResult = score_offensive_fit(_avg_roster(10))

    def test_all_subcomponents_near_50(self):
        # role_balance and shooting may dip below 40 for a pure-Wing average roster
        # (no Bigs triggers size_coverage penalty; no spacers hurts shooting).
        # We verify the subcomponents that don't depend on roster composition.
        for field in (
            "creation_fit", "ball_security_fit",
            "finishing_fit", "pressure_fit", "off_rebounding_fit",
        ):
            val = getattr(self.result, field)
            self.assertGreater(val, 30, f"{field} too low: {val}")
            self.assertLess(val, 70, f"{field} too high: {val}")

    def test_offensive_fit_score_near_50(self):
        self.assertGreater(self.result.offensive_fit_score, 30)
        self.assertLess(self.result.offensive_fit_score, 70)


class TestOffensiveCreation(TestCase):
    """High-assist roster should outscore low-assist roster on creation_fit."""

    def _creation_score(self, ast_pg: float) -> float:
        players = [
            _make_player(player_id=i, ast_pg=ast_pg,
                         minutes_share=5.0 / 10)
            for i in range(10)
        ]
        return score_offensive_fit(players).creation_fit

    def test_high_assist_beats_low_assist(self):
        high = self._creation_score(4.5)
        low = self._creation_score(0.3)
        self.assertGreater(high, low)

    def test_extreme_creator_scores_above_60(self):
        self.assertGreater(self._creation_score(6.0), 60)

    def test_low_creator_scores_below_40(self):
        self.assertLess(self._creation_score(0.2), 40)


class TestOffensiveShooting(TestCase):
    """Distribution-aware shooting fit tests."""

    def _shooting_roster(self, n_spacers: int, fg3a: float = 4.5) -> list[PlayerFitInput]:
        """Create a roster where n_spacers have high fg3a and the rest are avg."""
        players = []
        share = 5.0 / 10
        for i in range(10):
            a = fg3a if i < n_spacers else 1.0
            players.append(_make_player(
                player_id=i, fg3a_pg=a, minutes_share=share, rotation_rank=i + 1,
            ))
        return players

    def test_more_spacers_better_shooting_fit(self):
        one_spacer = score_offensive_fit(self._shooting_roster(1)).shooting_fit
        three_spacers = score_offensive_fit(self._shooting_roster(3)).shooting_fit
        self.assertGreater(three_spacers, one_spacer)

    def test_no_spacers_shoots_below_50(self):
        no_spacers = score_offensive_fit(self._shooting_roster(0)).shooting_fit
        self.assertLess(no_spacers, 50)

    def test_no_spacers_triggers_penalty(self):
        result = score_offensive_fit(self._shooting_roster(0))
        penalty_labels = [lbl for lbl, _ in result.structural_penalties]
        self.assertIn("few_spacers", penalty_labels)


class TestOffensiveBallSecurity(TestCase):

    def _tov_score(self, tov_pg: float) -> float:
        players = [
            _make_player(player_id=i, tov_pg=tov_pg,
                         minutes_share=5.0 / 10)
            for i in range(10)
        ]
        return score_offensive_fit(players).ball_security_fit

    def test_low_tov_beats_high_tov(self):
        self.assertGreater(self._tov_score(0.5), self._tov_score(3.0))

    def test_ball_stopper_triggers_penalty(self):
        players = []
        share = 5.0 / 10
        for i in range(10):
            # Put a ball-stopper in a top-5 slot (rotation_rank ≤ 5)
            tov = BALL_STOPPER_TOV_THRESHOLD + 0.2 if i == 0 else 1.0
            ast = BALL_STOPPER_AST_MAX - 0.1 if i == 0 else 2.0
            players.append(_make_player(
                player_id=i, tov_pg=tov, ast_pg=ast,
                minutes_share=share, rotation_rank=i + 1,
            ))
        result = score_offensive_fit(players)
        penalty_labels = [lbl for lbl, _ in result.structural_penalties]
        self.assertIn("ball_stopper_in_top5", penalty_labels)


class TestOffensiveRoleBalance(TestCase):

    def test_nsb_penalty_fires_with_two_nsbs_in_top8(self):
        players = []
        share = 5.0 / 10
        for i in range(10):
            # First two spots: non-shooting bigs in top-8
            is_nsb = i < 2
            players.append(_make_player(
                player_id=i,
                role_bucket="Big" if is_nsb else "Wing",
                fg3a_pg=0.5 if is_nsb else 3.0,
                minutes_share=share,
                rotation_rank=i + 1,
            ))
        result = score_offensive_fit(players)
        penalty_labels = [lbl for lbl, _ in result.structural_penalties]
        self.assertIn("many_non_shooting_bigs", penalty_labels)

    def test_no_creator_no_spacer_triggers_overlap_penalty(self):
        # All players: low ast and low fg3a
        players = [
            _make_player(player_id=i, ast_pg=0.5, fg3a_pg=0.5,
                         minutes_share=5.0 / 10, rotation_rank=i + 1)
            for i in range(10)
        ]
        result = score_offensive_fit(players)
        penalty_labels = [lbl for lbl, _ in result.structural_penalties]
        self.assertIn("no_creator_no_spacer_overlap", penalty_labels)


class TestPenaltyCap(TestCase):
    """Total structural penalty must not exceed MAX_STRUCTURAL_PENALTY_OFF."""

    def test_offensive_penalty_cap(self):
        # Design a worst-case roster: no creator, no spacer, ball-stopper in top-5,
        # multiple NSBs — should trigger many penalties but cap applies.
        players = []
        share = 5.0 / 10
        for i in range(10):
            role = "Big" if i < 4 else "G"
            players.append(_make_player(
                player_id=i,
                role_bucket=role,
                fg3a_pg=0.3,          # no spacers
                ast_pg=0.2,           # no creators
                tov_pg=BALL_STOPPER_TOV_THRESHOLD + 0.5 if i == 0 else 1.0,
                minutes_share=share,
                rotation_rank=i + 1,
            ))
        result = score_offensive_fit(players)
        self.assertLessEqual(result.total_penalty, MAX_STRUCTURAL_PENALTY_OFF + 1e-6)

    def test_defensive_penalty_cap(self):
        players = [
            _make_player(player_id=i, role_bucket="G",
                         blk_pg=0.0, dreb_pg=0.5,
                         projected_dbpr=-2.0,
                         pf_pg=FOUL_PRONE_THRESHOLD + 0.5,
                         minutes_share=5.0 / 10, rotation_rank=i + 1)
            for i in range(10)
        ]
        result = score_defensive_fit(players)
        self.assertLessEqual(result.total_penalty, MAX_STRUCTURAL_PENALTY_DEF + 1e-6)


class TestPenaltyNoDuplication(TestCase):
    """Each penalty label should appear at most once per roster evaluation."""

    def test_offense_no_duplicate_labels(self):
        players = [
            _make_player(player_id=i, fg3a_pg=0.3, ast_pg=0.2,
                         minutes_share=5.0 / 10, rotation_rank=i + 1)
            for i in range(10)
        ]
        result = score_offensive_fit(players)
        labels = [lbl for lbl, _ in result.structural_penalties]
        self.assertEqual(len(labels), len(set(labels)),
                         f"Duplicate penalty labels: {labels}")

    def test_defense_no_duplicate_labels(self):
        players = [
            _make_player(player_id=i, role_bucket="G",
                         blk_pg=0.0, dreb_pg=0.5,
                         projected_dbpr=-2.0,
                         minutes_share=5.0 / 10, rotation_rank=i + 1)
            for i in range(10)
        ]
        result = score_defensive_fit(players)
        labels = [lbl for lbl, _ in result.structural_penalties]
        self.assertEqual(len(labels), len(set(labels)),
                         f"Duplicate penalty labels: {labels}")


# ──────────────────────────────────────────────────────────────────────────────
# 5.  Defensive fit scoring
# ──────────────────────────────────────────────────────────────────────────────

class TestDefensiveFitAverage(TestCase):

    def setUp(self):
        self.result: DefensiveFitResult = score_defensive_fit(_avg_roster(10))

    def test_all_subcomponents_near_50(self):
        # An all-Wing average roster triggers no_meaningful_big_minutes (size_coverage)
        # and no_rim_protector, pulling those scores down.  We verify the
        # subcomponents that are not structurally constrained.
        for field in (
            "disruption_fit", "foul_discipline_fit",
            "mobility_fit",
        ):
            val = getattr(self.result, field)
            self.assertGreater(val, 30, f"{field} too low: {val}")
            self.assertLess(val, 70, f"{field} too high: {val}")

    def test_defensive_fit_score_near_50(self):
        self.assertGreater(self.result.defensive_fit_score, 30)
        self.assertLess(self.result.defensive_fit_score, 70)


class TestRimProtection(TestCase):

    def _rim_score(self, blk_pg: float) -> float:
        players = [
            _make_player(player_id=i, blk_pg=blk_pg,
                         minutes_share=5.0 / 10)
            for i in range(10)
        ]
        return score_defensive_fit(players).rim_protection_fit

    def test_high_blocks_beats_no_blocks(self):
        self.assertGreater(self._rim_score(2.0), self._rim_score(0.0))

    def test_no_rim_protector_triggers_penalty(self):
        players = [
            _make_player(player_id=i, blk_pg=0.1,
                         minutes_share=5.0 / 10, rotation_rank=i + 1)
            for i in range(10)
        ]
        result = score_defensive_fit(players)
        labels = [lbl for lbl, _ in result.structural_penalties]
        self.assertIn("no_rim_protector", labels)

    def test_rim_protector_does_not_trigger_penalty(self):
        players = [
            _make_player(player_id=i,
                         blk_pg=RIM_PROTECTOR_BLK_THRESHOLD + 0.5,
                         minutes_share=5.0 / 10, rotation_rank=i + 1)
            for i in range(10)
        ]
        result = score_defensive_fit(players)
        labels = [lbl for lbl, _ in result.structural_penalties]
        self.assertNotIn("no_rim_protector", labels)


class TestDefensiveRebounding(TestCase):

    def test_high_dreb_beats_low_dreb(self):
        def _score(dreb):
            players = [
                _make_player(player_id=i, dreb_pg=dreb,
                             minutes_share=5.0 / 10)
                for i in range(10)
            ]
            return score_defensive_fit(players).def_rebounding_fit

        self.assertGreater(_score(4.0), _score(1.0))


class TestFoulDiscipline(TestCase):

    def test_low_fouls_beats_high_fouls(self):
        def _score(pf):
            players = [
                _make_player(player_id=i, pf_pg=pf,
                             minutes_share=5.0 / 10)
                for i in range(10)
            ]
            return score_defensive_fit(players).foul_discipline_fit

        self.assertGreater(_score(1.0), _score(3.5))

    def test_foul_stack_triggers_penalty(self):
        players = []
        share = 5.0 / 10
        for i in range(10):
            pf = FOUL_PRONE_THRESHOLD + 0.5 if i < 2 else 1.5
            players.append(_make_player(
                player_id=i, pf_pg=pf,
                minutes_share=share, rotation_rank=i + 1,
            ))
        result = score_defensive_fit(players)
        labels = [lbl for lbl, _ in result.structural_penalties]
        self.assertIn("foul_stack_in_top5", labels)


class TestSizeCoverage(TestCase):
    """Size coverage is a roster-level metric (not per-player)."""

    def test_big_heavy_roster_beats_all_guards(self):
        share = 5.0 / 10

        big_heavy = [
            _make_player(player_id=i, role_bucket="Big" if i < 4 else "Wing",
                         dreb_pg=3.5, blk_pg=1.0, minutes_share=share)
            for i in range(10)
        ]
        all_guards = [
            _make_player(player_id=i, role_bucket="G",
                         dreb_pg=1.0, blk_pg=0.1, minutes_share=share)
            for i in range(10)
        ]

        big_score = score_defensive_fit(big_heavy).size_coverage_fit
        guard_score = score_defensive_fit(all_guards).size_coverage_fit
        self.assertGreater(big_score, guard_score)

    def test_no_meaningful_big_minutes_penalty(self):
        players = [
            _make_player(player_id=i, role_bucket="G",
                         minutes_share=5.0 / 10, rotation_rank=i + 1)
            for i in range(10)
        ]
        result = score_defensive_fit(players)
        labels = [lbl for lbl, _ in result.structural_penalties]
        self.assertIn("no_meaningful_big_minutes", labels)


# ──────────────────────────────────────────────────────────────────────────────
# 6.  score_roster_fit() integration tests
# ──────────────────────────────────────────────────────────────────────────────

class TestScoreRosterFitEmpty(TestCase):
    """Empty player list should return safe default result."""

    def test_empty_roster_returns_defaults(self):
        result = score_roster_fit([])
        self.assertEqual(result.overall_fit_score, SCORE_MID)
        self.assertEqual(result.offensive_fit_score, SCORE_MID)
        self.assertEqual(result.defensive_fit_score, SCORE_MID)


class TestScoreRosterFitDeterminism(TestCase):
    """Same roster → same result on repeated calls."""

    def test_deterministic(self):
        players = _avg_roster(10)
        r1 = score_roster_fit(players)
        r2 = score_roster_fit(players)
        self.assertEqual(r1.overall_fit_score, r2.overall_fit_score)
        self.assertEqual(r1.offensive_fit_score, r2.offensive_fit_score)


class TestScoreRosterFitMetadata(TestCase):

    def test_team_id_and_season_year_propagated(self):
        result = score_roster_fit(_avg_roster(5), team_id=99, season_year=2027)
        self.assertEqual(result.team_id, 99)
        self.assertEqual(result.season_year, 2027)


class TestScoreRosterFitDiagnostics(TestCase):
    """Diagnostics fields should always be populated."""

    def setUp(self):
        self.result = score_roster_fit(_avg_roster(10))

    def test_strengths_and_weaknesses_non_empty(self):
        self.assertTrue(len(self.result.offensive_strengths) > 0)
        self.assertTrue(len(self.result.offensive_weaknesses) > 0)
        self.assertTrue(len(self.result.defensive_strengths) > 0)
        self.assertTrue(len(self.result.defensive_weaknesses) > 0)

    def test_fit_summary_has_required_keys(self):
        s = self.result.fit_summary
        for key in ("offensive_fit", "defensive_fit", "overall_fit",
                    "off_subcomponents", "def_subcomponents", "penalties"):
            self.assertIn(key, s)

    def test_fit_summary_off_subcomponents_has_all_7(self):
        subs = self.result.fit_summary["off_subcomponents"]
        self.assertEqual(len(subs), 7)

    def test_fit_summary_def_subcomponents_has_all_8(self):
        subs = self.result.fit_summary["def_subcomponents"]
        self.assertEqual(len(subs), 8)


class TestScoreRosterFitOverallFormula(TestCase):
    """overall = 0.50 × off + 0.50 × def (within floating-point tolerance)."""

    def test_overall_is_average_of_off_and_def(self):
        result = score_roster_fit(_avg_roster(10))
        expected = 0.50 * result.offensive_fit_score + 0.50 * result.defensive_fit_score
        self.assertAlmostEqual(result.overall_fit_score, expected, places=1)


class TestScoreRosterFitOrdering(TestCase):
    """Higher-quality rosters should produce higher fit scores."""

    def _elite_off_roster(self) -> list[PlayerFitInput]:
        share = 5.0 / 10
        return [
            _make_player(player_id=i,
                         ast_pg=5.0, fg3a_pg=5.0, tov_pg=0.5,
                         projected_obpr=2.5, off_efg_impact=1.5,
                         minutes_share=share, rotation_rank=i + 1)
            for i in range(10)
        ]

    def _poor_off_roster(self) -> list[PlayerFitInput]:
        share = 5.0 / 10
        return [
            _make_player(player_id=i,
                         ast_pg=0.3, fg3a_pg=0.2, tov_pg=4.0,
                         projected_obpr=-2.0, off_efg_impact=-1.5,
                         minutes_share=share, rotation_rank=i + 1)
            for i in range(10)
        ]

    def test_elite_off_beats_poor_off(self):
        elite = score_roster_fit(self._elite_off_roster())
        poor = score_roster_fit(self._poor_off_roster())
        self.assertGreater(elite.offensive_fit_score, poor.offensive_fit_score)

    def test_elite_def_roster_beats_poor_def(self):
        share = 5.0 / 10
        good_def = [
            _make_player(player_id=i, blk_pg=1.5, stl_pg=1.5,
                         dreb_pg=5.0, pf_pg=1.0,
                         projected_dbpr=2.0,
                         role_bucket="Big" if i < 4 else "Wing",
                         minutes_share=share, rotation_rank=i + 1)
            for i in range(10)
        ]
        poor_def = [
            _make_player(player_id=i, blk_pg=0.0, stl_pg=0.2,
                         dreb_pg=1.0, pf_pg=4.0,
                         projected_dbpr=-2.0,
                         role_bucket="G",
                         minutes_share=share, rotation_rank=i + 1)
            for i in range(10)
        ]
        good = score_roster_fit(good_def)
        poor = score_roster_fit(poor_def)
        self.assertGreater(good.defensive_fit_score, poor.defensive_fit_score)


class TestScoreRosterFitMinutesWeighting(TestCase):
    """A great player with tiny minutes should not dominate the score."""

    def test_star_player_with_tiny_minutes_limited_impact(self):
        share = 5.0 / 10
        # 9 average players + 1 elite player with essentially 0 minutes
        players = [_make_player(player_id=i, minutes_share=share)
                   for i in range(9)]
        players.append(_make_player(
            player_id=9,
            ast_pg=10.0, fg3a_pg=10.0, projected_obpr=5.0,
            minutes_share=0.001,  # nearly zero
        ))
        result_star = score_roster_fit(players)

        # Compare to a pure average roster
        result_avg = score_roster_fit(_avg_roster(10))

        # Star's contribution should be tiny — overall scores should be close
        diff = abs(result_star.offensive_fit_score - result_avg.offensive_fit_score)
        self.assertLess(diff, 10.0, f"Star with tiny minutes moved score by {diff:.2f}")


class TestScoreRosterFitMissingData(TestCase):
    """Players with None impact fields should degrade gracefully (no crash)."""

    def test_all_none_impact_fields(self):
        players = [
            PlayerFitInput(
                player_id=i,
                minutes_share_p2=5.0 / 10,
                rotation_rank=i + 1,
                role_bucket="Wing",
                fg3a_pg=2.0,
                ast_pg=1.5,
                tov_pg=1.2,
                blk_pg=0.3,
                stl_pg=0.6,
                pf_pg=2.0,
                oreb_pg=0.8,
                dreb_pg=2.0,
                fta_pg=2.0,
                # No projected_obpr, projected_dbpr, efg_pct, ts_pct, impacts
            )
            for i in range(10)
        ]
        result = score_roster_fit(players)
        # Should complete without error and produce valid scores
        self.assertGreaterEqual(result.overall_fit_score, SCORE_MIN)
        self.assertLessEqual(result.overall_fit_score, SCORE_MAX)


# ──────────────────────────────────────────────────────────────────────────────
# 7.  SeasonRefs computation
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildSeasonRefs(TestCase):

    def _make_stat_row(self, gp=25, off_poss=500.0, ast=2.0, tov=1.5,
                       blk=0.5, stl=0.8, pf=2.0, fg3a_pg=3.0,
                       fta_pg=2.5, oreb_pg=1.0, dreb_pg=3.0,
                       efg_pct=0.50, ts_pct=0.55, ast_to=1.5,
                       obpr=0.3, dbpr=0.1,
                       off_efg_impact=0.2, def_efg_impact=0.1,
                       off_tov_impact=0.1, def_tov_impact=0.0,
                       off_orb_impact=0.1, def_reb_impact=0.1,
                       off_ftr_impact=0.1, def_ftr_impact=0.1,
                       on_court_adj_o=112.0, on_court_adj_d=111.0) -> dict:
        return {
            "gp": gp, "off_poss": off_poss, "ast": ast, "tov": tov,
            "blk": blk, "stl": stl, "pf": pf, "fg3a_pg": fg3a_pg,
            "fta_pg": fta_pg, "oreb_pg": oreb_pg, "dreb_pg": dreb_pg,
            "efg_pct": efg_pct, "ts_pct": ts_pct, "ast_to": ast_to,
            "obpr": obpr, "dbpr": dbpr,
            "off_efg_impact": off_efg_impact, "def_efg_impact": def_efg_impact,
            "off_tov_impact": off_tov_impact, "def_tov_impact": def_tov_impact,
            "off_orb_impact": off_orb_impact, "def_reb_impact": def_reb_impact,
            "off_ftr_impact": off_ftr_impact, "def_ftr_impact": def_ftr_impact,
            "on_court_adj_o": on_court_adj_o, "on_court_adj_d": on_court_adj_d,
        }

    def test_below_min_players_returns_default_refs(self):
        # Only 5 rows → should fall back to DEFAULT_REFS
        stats = [self._make_stat_row() for _ in range(5)]
        refs = _build_season_refs(stats)
        self.assertIs(refs, DEFAULT_REFS,
                      "Expected DEFAULT_REFS with fewer than SEASON_REF_MIN_PLAYERS rows")

    def test_above_min_players_returns_custom_refs(self):
        from ncaa.analytics.player_value.fit.constants import SEASON_REF_MIN_PLAYERS
        stats = [self._make_stat_row(ast=float(i % 5) + 0.5)
                 for i in range(SEASON_REF_MIN_PLAYERS + 50)]
        refs = _build_season_refs(stats)
        self.assertIsInstance(refs, SeasonRefs)
        # Custom refs should have reasonable ast_pg mean
        mean_ast, std_ast = refs.ast_pg
        self.assertGreater(mean_ast, 0.0)
        self.assertGreater(std_ast, 0.0)

    def test_unqualified_rows_excluded(self):
        # 1000 rows but gp=5 (below threshold) → should use DEFAULT_REFS
        from ncaa.analytics.player_value.fit.constants import SEASON_REF_MIN_PLAYERS
        stats = [self._make_stat_row(gp=5, off_poss=100)
                 for _ in range(SEASON_REF_MIN_PLAYERS + 100)]
        refs = _build_season_refs(stats)
        self.assertIs(refs, DEFAULT_REFS)

    def test_refs_std_always_positive(self):
        from ncaa.analytics.player_value.fit.constants import SEASON_REF_MIN_PLAYERS
        # All rows identical → std could be 0 without the safeguard
        stats = [self._make_stat_row() for _ in range(SEASON_REF_MIN_PLAYERS + 50)]
        refs = _build_season_refs(stats)
        for attr in ("fg3a_pg", "ast_pg", "tov_pg", "blk_pg", "stl_pg"):
            _, std = getattr(refs, attr)
            self.assertGreater(std, 0.0, f"{attr} std ≤ 0")
