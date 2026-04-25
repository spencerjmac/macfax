"""
Phase 4: Contextual Fit — comprehensive test suite.

Tests cover:
  1. Player pace score computation (unit, edge cases)
  2. Roster pace profile (minutes weighting, empty roster)
  3. Team pace normalization (units consistency — same 0-100 scale)
  4. Pace compatibility scoring (perfect match, mismatch, neutral/no data)
  5. Offensive scheme tag inference (all 5 tags)
  6. Defensive scheme tag inference (all 3 tags)
  7. Scheme compatibility scoring (off & def, neutral cases)
  8. Contextual engine: end-to-end score_contextual_fit()
  9. Cap enforcement: modifiers never exceed hard limits
 10. Missing data invariants: alignment=50, modifier=0 when no style data
 11. halfcourt_control scheme correctness

All tests are pure-Python and stateless (no DB required).
"""
from __future__ import annotations

from unittest import TestCase

from ncaa.analytics.player_value.fit.archetypes import PlayerFitInput, tag_archetypes
from ncaa.analytics.player_value.fit.context.constants import (
    MAX_PACE_MODIFIER_OFF,
    MAX_PACE_MODIFIER_DEF,
    MAX_SCHEME_MODIFIER_OFF,
    MAX_SCHEME_MODIFIER_DEF,
    MAX_CONTEXTUAL_TOTAL,
    NEUTRAL_ALIGNMENT_SCORE,
    NEUTRAL_MODIFIER,
    SCORE_MID,
)
from ncaa.analytics.player_value.fit.context.pace import (
    player_pace_score,
    roster_pace_profile,
    normalize_team_pace,
    score_pace_compatibility,
)
from ncaa.analytics.player_value.fit.context.scheme import (
    infer_off_scheme_tags,
    infer_def_scheme_tags,
    score_off_scheme_compatibility,
    score_def_scheme_compatibility,
)
from ncaa.analytics.player_value.fit.context.engine import (
    score_contextual_fit,
    ContextualFitResult,
)


# ── Test fixtures ─────────────────────────────────────────────────────────────

def _player(
    player_id: int = 1,
    minutes_share: float = 0.5,
    role_bucket: str = "Wing",
    fg3a: float = 2.44,    # D1 average
    ast: float = 1.46,
    stl: float = 0.70,
    fta: float = 2.16,
    oreb: float = 0.96,
    tov: float = 1.16,
    blk: float = 0.35,
    pf: float = 1.84,
    dreb: float = 2.39,
    efg_pct: float = 0.50,
    projected_dbpr: float = 0.0,
    archetypes: set = None,
) -> PlayerFitInput:
    """Build a PlayerFitInput with sensible defaults."""
    p = PlayerFitInput(
        player_id=player_id,
        player_name=f"Player{player_id}",
        minutes_share_p2=minutes_share,
        role_bucket=role_bucket,
        fg3a_pg=fg3a,
        ast_pg=ast,
        stl_pg=stl,
        fta_pg=fta,
        oreb_pg=oreb,
        tov_pg=tov,
        blk_pg=blk,
        pf_pg=pf,
        dreb_pg=dreb,
        efg_pct=efg_pct,
        projected_dbpr=projected_dbpr,
    )
    if archetypes is not None:
        p.archetypes = archetypes
    else:
        p.archetypes = tag_archetypes(p)
    return p


def _five_average_players() -> list[PlayerFitInput]:
    return [_player(player_id=i, minutes_share=0.5) for i in range(1, 6)]


# ── 1. Player pace score ──────────────────────────────────────────────────────

class TestPlayerPaceScore(TestCase):

    def test_average_player_scores_near_50(self):
        """A player at D1 average stats should score close to 50."""
        p = _player()
        score = player_pace_score(p)
        self.assertGreaterEqual(score, 45, f"Average player pace score = {score}")
        self.assertLessEqual(score, 55, f"Average player pace score = {score}")

    def test_fast_player_above_50(self):
        """High fg3a + high ast → above average pace tendency."""
        p = _player(fg3a=6.0, ast=5.0, stl=2.0, fta=1.0, oreb=0.2)
        score = player_pace_score(p)
        self.assertGreater(score, 55, f"Fast player pace score = {score}")

    def test_slow_player_below_50(self):
        """High fta + high oreb → below average pace tendency."""
        p = _player(fg3a=0.3, ast=0.5, stl=0.1, fta=6.0, oreb=3.5)
        score = player_pace_score(p)
        self.assertLess(score, 45, f"Slow player pace score = {score}")

    def test_score_bounded_0_100(self):
        """Pace score must always be within [0, 100]."""
        for fg3a in [0.0, 15.0]:
            for fta in [0.0, 12.0]:
                p = _player(fg3a=fg3a, fta=fta)
                score = player_pace_score(p)
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 100)

    def test_tov_not_in_pace_formula(self):
        """tov_pg is excluded from pace formula — changing it must not affect score."""
        p1 = _player(tov=0.0)
        p2 = _player(tov=5.0)
        s1 = player_pace_score(p1)
        s2 = player_pace_score(p2)
        self.assertAlmostEqual(s1, s2, places=2,
            msg=f"tov_pg should not affect pace score: s1={s1}, s2={s2}")


# ── 2. Roster pace profile ────────────────────────────────────────────────────

class TestRosterPaceProfile(TestCase):

    def test_all_average_players_near_50(self):
        players = _five_average_players()
        profile = roster_pace_profile(players)
        self.assertGreaterEqual(profile, 45)
        self.assertLessEqual(profile, 55)

    def test_empty_roster_returns_50(self):
        self.assertEqual(roster_pace_profile([]), SCORE_MID)

    def test_zero_minutes_players_excluded(self):
        """Players with 0 minutes share should not affect the profile."""
        p1 = _player(player_id=1, minutes_share=1.0, fg3a=8.0, ast=6.0)
        p2 = _player(player_id=2, minutes_share=0.0, fg3a=0.0, ast=0.0, fta=10.0)
        profile_with_zero = roster_pace_profile([p1, p2])
        profile_without   = roster_pace_profile([p1])
        self.assertAlmostEqual(profile_with_zero, profile_without, places=2)

    def test_minutes_weighting(self):
        """High-pace player with more minutes pulls profile score up."""
        fast_many = _player(player_id=1, minutes_share=0.8, fg3a=7.0, ast=5.0)
        slow_few  = _player(player_id=2, minutes_share=0.2, fg3a=0.2, fta=6.0)
        fast_few  = _player(player_id=3, minutes_share=0.2, fg3a=7.0, ast=5.0)
        slow_many = _player(player_id=4, minutes_share=0.8, fg3a=0.2, fta=6.0)

        profile_fast = roster_pace_profile([fast_many, slow_few])
        profile_slow = roster_pace_profile([fast_few, slow_many])
        self.assertGreater(profile_fast, profile_slow)


# ── 3. Team pace normalization ────────────────────────────────────────────────

class TestNormalizeTeamPace(TestCase):

    def test_d1_average_tempo_near_50(self):
        score = normalize_team_pace(69.24)
        self.assertAlmostEqual(score, 50.0, delta=1.0)

    def test_fast_tempo_above_50(self):
        score = normalize_team_pace(75.0)
        self.assertGreater(score, 70)

    def test_slow_tempo_below_50(self):
        score = normalize_team_pace(64.0)
        self.assertLess(score, 30)

    def test_bounded_0_100(self):
        for tempo in [50.0, 90.0]:
            score = normalize_team_pace(tempo)
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)

    def test_same_scale_as_player_score(self):
        """Both team and player scores center near 50 for D1 average inputs."""
        team_score   = normalize_team_pace(69.24)
        player_score = player_pace_score(_player())
        self.assertAlmostEqual(team_score,   50.0, delta=5.0)
        self.assertAlmostEqual(player_score, 50.0, delta=5.0)


# ── 4. Pace compatibility ─────────────────────────────────────────────────────

class TestPaceCompatibility(TestCase):

    def test_no_team_data_returns_neutral(self):
        align, mod = score_pace_compatibility(50.0, None)
        self.assertEqual(align, NEUTRAL_ALIGNMENT_SCORE)
        self.assertEqual(mod,   NEUTRAL_MODIFIER)

    def test_perfect_match_gives_max_alignment(self):
        align, mod = score_pace_compatibility(65.0, 65.0)
        self.assertEqual(align, 100.0)
        self.assertGreater(mod, 0)

    def test_maximum_mismatch_gives_zero_alignment(self):
        align, mod = score_pace_compatibility(0.0, 100.0)
        self.assertEqual(align, 0.0)
        self.assertLess(mod, 0)

    def test_pace_modifier_capped(self):
        _, mod = score_pace_compatibility(100.0, 100.0)
        self.assertLessEqual(abs(mod), MAX_PACE_MODIFIER_OFF)

    def test_distance_50_gives_neutral_modifier(self):
        """Mismatch distance=50 → alignment=50 → modifier=0."""
        align, mod = score_pace_compatibility(0.0, 50.0)
        self.assertAlmostEqual(align, 50.0, places=1)
        self.assertAlmostEqual(mod,   0.0,  places=2)

    def test_near_perfect_match_gives_high_alignment(self):
        """A 2-point difference on 0-100 scale is near-perfect alignment → high score."""
        align, mod = score_pace_compatibility(52.0, 50.0)
        self.assertGreater(align, 90)
        self.assertGreater(mod, 0)  # small positive bonus for good fit
        self.assertLessEqual(mod, MAX_PACE_MODIFIER_OFF)


# ── 5. Offensive scheme tag inference ────────────────────────────────────────

class TestOffSchemeTagInference(TestCase):

    def test_no_tags_when_all_none(self):
        tags = infer_off_scheme_tags({})
        self.assertFalse(any(tags.values()))

    def test_spacing_driven_fires(self):
        tags = infer_off_scheme_tags({"adj_efg_pct": 55.0})
        self.assertTrue(tags["spacing_driven"])

    def test_spacing_driven_below_threshold(self):
        tags = infer_off_scheme_tags({"adj_efg_pct": 50.0})
        self.assertFalse(tags["spacing_driven"])

    def test_creator_driven_fires(self):
        tags = infer_off_scheme_tags({"adj_tov_pct": 14.0})
        self.assertTrue(tags["creator_driven"])

    def test_pressure_offense_fires(self):
        tags = infer_off_scheme_tags({"adj_ftr": 42.0})
        self.assertTrue(tags["pressure_offense"])

    def test_glass_emphasis_fires(self):
        tags = infer_off_scheme_tags({"adj_orb_pct": 36.0})
        self.assertTrue(tags["glass_emphasis"])

    def test_halfcourt_control_requires_both_conditions(self):
        # Only low tov — should not fire
        tags = infer_off_scheme_tags({"adj_tov_pct": 15.0, "adj_tempo": 70.0})
        self.assertFalse(tags["halfcourt_control"])

        # Only slow tempo — should not fire
        tags = infer_off_scheme_tags({"adj_tov_pct": 18.0, "adj_tempo": 67.0})
        self.assertFalse(tags["halfcourt_control"])

        # Both met — should fire
        tags = infer_off_scheme_tags({"adj_tov_pct": 15.0, "adj_tempo": 67.0})
        self.assertTrue(tags["halfcourt_control"])

    def test_multiple_tags_can_fire(self):
        tags = infer_off_scheme_tags({
            "adj_efg_pct": 56.0,
            "adj_tov_pct": 14.0,
            "adj_ftr": 42.0,
        })
        self.assertTrue(tags["spacing_driven"])
        self.assertTrue(tags["creator_driven"])
        self.assertTrue(tags["pressure_offense"])


# ── 6. Defensive scheme tag inference ────────────────────────────────────────

class TestDefSchemeTagInference(TestCase):

    def test_no_tags_when_all_none(self):
        tags = infer_def_scheme_tags({})
        self.assertFalse(any(tags.values()))

    def test_turnover_forcing_fires(self):
        tags = infer_def_scheme_tags({"adj_opp_tov_pct": 20.0})
        self.assertTrue(tags["turnover_forcing"])

    def test_rim_anchored_requires_both_conditions(self):
        # High drb, but not low opp_orb — should not fire
        tags = infer_def_scheme_tags({"adj_drb_pct": 78.0, "adj_opp_orb_pct": 32.0})
        self.assertFalse(tags["rim_anchored"])

        # Both conditions — should fire
        tags = infer_def_scheme_tags({"adj_drb_pct": 78.0, "adj_opp_orb_pct": 25.0})
        self.assertTrue(tags["rim_anchored"])

    def test_disciplined_rebounding_at_threshold(self):
        tags = infer_def_scheme_tags({"adj_drb_pct": 72.0})
        self.assertTrue(tags["disciplined_rebounding"])

        tags = infer_def_scheme_tags({"adj_drb_pct": 70.0})
        self.assertFalse(tags["disciplined_rebounding"])


# ── 7. Scheme compatibility scoring ──────────────────────────────────────────

class TestSchemeCompatibility(TestCase):

    def test_no_style_neutral_off(self):
        players = _five_average_players()
        align, mod = score_off_scheme_compatibility(players, None)
        self.assertEqual(align, NEUTRAL_ALIGNMENT_SCORE)
        self.assertEqual(mod,   NEUTRAL_MODIFIER)

    def test_no_style_neutral_def(self):
        players = _five_average_players()
        align, mod = score_def_scheme_compatibility(players, None)
        self.assertEqual(align, NEUTRAL_ALIGNMENT_SCORE)
        self.assertEqual(mod,   NEUTRAL_MODIFIER)

    def test_no_scheme_fires_neutral(self):
        """Average style values below all thresholds → neutral."""
        players = _five_average_players()
        style = {
            "adj_efg_pct": 51.0,   # below spacing threshold 54.0
            "adj_tov_pct": 17.0,   # above creator threshold 15.5
            "adj_ftr": 35.0,       # below pressure threshold 39.0
            "adj_orb_pct": 30.0,   # below glass threshold 34.0
        }
        align, mod = score_off_scheme_compatibility(players, style)
        self.assertEqual(align, NEUTRAL_ALIGNMENT_SCORE)
        self.assertEqual(mod,   NEUTRAL_MODIFIER)

    def test_spacing_team_with_spacers_gets_bonus(self):
        spacers = [
            _player(player_id=i, minutes_share=0.5, fg3a=5.5, efg_pct=0.56)
            for i in range(1, 6)
        ]
        _, mod = score_off_scheme_compatibility(spacers, {"adj_efg_pct": 56.0})
        self.assertGreater(mod, 0, f"Spacing team with spacers: mod={mod}")
        self.assertLessEqual(mod, MAX_SCHEME_MODIFIER_OFF)

    def test_spacing_team_without_spacers_gets_penalty(self):
        bigs = [
            _player(player_id=i, role_bucket="Big", fg3a=0.1, efg_pct=0.40,
                    minutes_share=0.5)
            for i in range(1, 6)
        ]
        _, mod = score_off_scheme_compatibility(bigs, {"adj_efg_pct": 56.0})
        self.assertLess(mod, 0, f"Spacing team without spacers: mod={mod}")

    def test_rim_anchored_team_with_rim_protectors(self):
        rim_p = [
            _player(player_id=i, role_bucket="Big", minutes_share=0.5,
                    archetypes={"rim_protector"})
            for i in range(1, 4)
        ]
        wings = [_player(player_id=i, minutes_share=0.5) for i in range(4, 6)]
        _, mod = score_def_scheme_compatibility(
            rim_p + wings, {"adj_drb_pct": 78.0, "adj_opp_orb_pct": 24.0}
        )
        self.assertGreater(mod, 0, f"Rim-anchored team with protectors: mod={mod}")

    def test_off_scheme_modifier_within_cap(self):
        players = _five_average_players()
        for adj_efg in [40.0, 50.0, 60.0]:
            _, mod = score_off_scheme_compatibility(players, {"adj_efg_pct": adj_efg})
            self.assertLessEqual(abs(mod), MAX_SCHEME_MODIFIER_OFF + 1e-9)

    def test_def_scheme_modifier_within_cap(self):
        players = _five_average_players()
        for opp_tov in [12.0, 17.0, 22.0]:
            _, mod = score_def_scheme_compatibility(
                players, {"adj_opp_tov_pct": opp_tov}
            )
            self.assertLessEqual(abs(mod), MAX_SCHEME_MODIFIER_DEF + 1e-9)


# ── 8. Contextual engine end-to-end ──────────────────────────────────────────

class TestContextualEngine(TestCase):

    def test_neutral_result_with_no_team_style(self):
        players = _five_average_players()
        ctx = score_contextual_fit(
            players=players,
            phase3_off=55.0, phase3_def=48.0, phase3_overall=51.5,
            team_style=None,
        )
        self.assertFalse(ctx.has_team_style_data)
        self.assertEqual(ctx.pace_alignment_score, NEUTRAL_ALIGNMENT_SCORE)
        self.assertEqual(ctx.pace_modifier, NEUTRAL_MODIFIER)
        self.assertEqual(ctx.off_scheme_alignment_score, NEUTRAL_ALIGNMENT_SCORE)
        self.assertEqual(ctx.off_scheme_modifier, NEUTRAL_MODIFIER)
        self.assertEqual(ctx.def_scheme_alignment_score, NEUTRAL_ALIGNMENT_SCORE)
        self.assertEqual(ctx.def_scheme_modifier, NEUTRAL_MODIFIER)
        self.assertEqual(ctx.off_contextual_modifier, 0.0)
        self.assertEqual(ctx.def_contextual_modifier, 0.0)
        self.assertAlmostEqual(ctx.adjusted_off_fit, 55.0, places=2)
        self.assertAlmostEqual(ctx.adjusted_def_fit, 48.0, places=2)

    def test_has_style_data_flag_set(self):
        players = _five_average_players()
        ctx = score_contextual_fit(
            players=players,
            phase3_off=50.0, phase3_def=50.0, phase3_overall=50.0,
            team_style={"adj_tempo": 69.24, "adj_efg_pct": 51.0},
        )
        self.assertTrue(ctx.has_team_style_data)

    def test_pace_biased_toward_offense(self):
        """Off contextual reflects 100% pace; def contextual reflects 50%."""
        fast_players = [
            _player(player_id=i, minutes_share=0.5, fg3a=7.0, ast=5.0,
                    fta=0.5, oreb=0.1)
            for i in range(1, 6)
        ]
        ctx = score_contextual_fit(
            players=fast_players,
            phase3_off=50.0, phase3_def=50.0, phase3_overall=50.0,
            team_style={"adj_tempo": 64.0},   # mismatch: fast roster, slow team
        )
        if ctx.pace_modifier != 0:
            expected_off = ctx.pace_modifier        # 100%
            expected_def = ctx.pace_modifier * 0.5  # 50%
            self.assertAlmostEqual(
                ctx.off_contextual_modifier, expected_off, delta=0.5,
                msg="off_contextual should reflect full pace modifier"
            )
            self.assertAlmostEqual(
                ctx.def_contextual_modifier, expected_def, delta=0.5,
                msg="def_contextual should reflect half pace modifier"
            )

    def test_adjusted_scores_clipped_0_100(self):
        players = _five_average_players()
        # Very high phase3
        ctx = score_contextual_fit(
            players=players,
            phase3_off=99.0, phase3_def=99.0, phase3_overall=99.0,
            team_style={"adj_tempo": 69.24},
        )
        self.assertGreaterEqual(ctx.adjusted_off_fit, 0)
        self.assertLessEqual(ctx.adjusted_off_fit, 100)
        self.assertGreaterEqual(ctx.adjusted_def_fit, 0)
        self.assertLessEqual(ctx.adjusted_def_fit, 100)
        self.assertGreaterEqual(ctx.adjusted_overall_fit, 0)
        self.assertLessEqual(ctx.adjusted_overall_fit, 100)

    def test_empty_players_preserves_phase3(self):
        ctx = score_contextual_fit(
            players=[],
            phase3_off=55.0, phase3_def=48.0, phase3_overall=51.5,
            team_style={"adj_tempo": 70.0},
        )
        self.assertEqual(ctx.adjusted_off_fit, 55.0)
        self.assertEqual(ctx.adjusted_def_fit, 48.0)


# ── 9. Cap enforcement ────────────────────────────────────────────────────────

class TestCapEnforcement(TestCase):

    def test_contextual_modifier_within_total_cap(self):
        spacers = [
            _player(player_id=i, minutes_share=0.5, fg3a=7.0, efg_pct=0.60,
                    archetypes={"spacer", "primary_creator"})
            for i in range(1, 6)
        ]
        extreme_style = {
            "adj_tempo": 75.0,
            "adj_efg_pct": 60.0,
            "adj_tov_pct": 13.0,
            "adj_ftr": 45.0,
            "adj_orb_pct": 38.0,
            "adj_opp_tov_pct": 22.0,
            "adj_drb_pct": 80.0,
            "adj_opp_orb_pct": 22.0,
        }
        ctx = score_contextual_fit(
            players=spacers,
            phase3_off=50.0, phase3_def=50.0, phase3_overall=50.0,
            team_style=extreme_style,
        )
        self.assertLessEqual(abs(ctx.off_contextual_modifier), MAX_CONTEXTUAL_TOTAL + 1e-9)
        self.assertLessEqual(abs(ctx.def_contextual_modifier), MAX_CONTEXTUAL_TOTAL + 1e-9)

    def test_pace_modifier_capped_at_max(self):
        _, mod = score_pace_compatibility(100.0, 100.0)
        self.assertLessEqual(abs(mod), MAX_PACE_MODIFIER_OFF + 1e-9)

        _, mod2 = score_pace_compatibility(0.0, 100.0)
        self.assertLessEqual(abs(mod2), MAX_PACE_MODIFIER_OFF + 1e-9)

    def test_off_scheme_modifier_capped(self):
        spacers = [
            _player(player_id=i, minutes_share=0.5, fg3a=8.0, efg_pct=0.62,
                    archetypes={"spacer"})
            for i in range(1, 6)
        ]
        _, mod = score_off_scheme_compatibility(spacers, {"adj_efg_pct": 60.0})
        self.assertLessEqual(abs(mod), MAX_SCHEME_MODIFIER_OFF + 1e-9)

    def test_def_scheme_modifier_capped(self):
        rim_players = [
            _player(player_id=i, role_bucket="Big", minutes_share=0.5,
                    archetypes={"rim_protector"})
            for i in range(1, 6)
        ]
        _, mod = score_def_scheme_compatibility(
            rim_players, {"adj_drb_pct": 82.0, "adj_opp_orb_pct": 22.0}
        )
        self.assertLessEqual(abs(mod), MAX_SCHEME_MODIFIER_DEF + 1e-9)


# ── 10. Missing data invariants ───────────────────────────────────────────────

class TestMissingDataInvariants(TestCase):

    def test_pace_none_team_strictly_neutral(self):
        """No national-average substitution — must return exactly (50, 0)."""
        align, mod = score_pace_compatibility(45.0, None)
        self.assertEqual(align, 50.0)
        self.assertEqual(mod,   0.0)

    def test_off_scheme_none_strictly_neutral(self):
        players = _five_average_players()
        align, mod = score_off_scheme_compatibility(players, None)
        self.assertEqual(align, 50.0)
        self.assertEqual(mod,   0.0)

    def test_def_scheme_none_strictly_neutral(self):
        players = _five_average_players()
        align, mod = score_def_scheme_compatibility(players, None)
        self.assertEqual(align, 50.0)
        self.assertEqual(mod,   0.0)

    def test_engine_no_style_preserves_phase3(self):
        players = _five_average_players()
        ctx = score_contextual_fit(
            players=players,
            phase3_off=57.3, phase3_def=44.1, phase3_overall=50.7,
            team_style=None,
        )
        self.assertAlmostEqual(ctx.adjusted_off_fit, 57.3, places=2)
        self.assertAlmostEqual(ctx.adjusted_def_fit, 44.1, places=2)

    def test_empty_style_dict_treated_as_no_data(self):
        """Empty dict is falsy → has_team_style_data=False."""
        players = _five_average_players()
        ctx = score_contextual_fit(
            players=players,
            phase3_off=50.0, phase3_def=50.0, phase3_overall=50.0,
            team_style={},
        )
        self.assertFalse(ctx.has_team_style_data)

    def test_none_adj_tempo_triggers_neutral_pace(self):
        players = _five_average_players()
        ctx = score_contextual_fit(
            players=players,
            phase3_off=50.0, phase3_def=50.0, phase3_overall=50.0,
            team_style={"adj_tempo": None, "adj_efg_pct": 56.0},
        )
        self.assertEqual(ctx.pace_alignment_score, NEUTRAL_ALIGNMENT_SCORE)
        self.assertEqual(ctx.pace_modifier, 0.0)


# ── 11. Halfcourt control scheme ─────────────────────────────────────────────

class TestHalfcourtControlScheme(TestCase):

    def test_disciplined_guards_fit_halfcourt_team(self):
        """Low-tov guards align well with halfcourt_control team."""
        disciplined_guards = [
            _player(player_id=i, role_bucket="G", tov=0.5, minutes_share=0.5)
            for i in range(1, 6)
        ]
        style = {"adj_tov_pct": 15.0, "adj_tempo": 67.0}
        align, _ = score_off_scheme_compatibility(disciplined_guards, style)
        self.assertGreaterEqual(align, NEUTRAL_ALIGNMENT_SCORE,
            f"Disciplined guards on halfcourt team: alignment={align}")

    def test_sloppy_roster_aligns_worse_than_disciplined(self):
        """High-tov roster aligns worse than low-tov roster for halfcourt team."""
        sloppy = [_player(player_id=i, tov=3.5, minutes_share=0.5) for i in range(1, 6)]
        disc   = [_player(player_id=i, tov=0.5, minutes_share=0.5) for i in range(1, 6)]
        style = {"adj_tov_pct": 15.0, "adj_tempo": 67.0}

        align_sloppy, _ = score_off_scheme_compatibility(sloppy, style)
        align_disc,   _ = score_off_scheme_compatibility(disc, style)
        self.assertGreaterEqual(align_disc, align_sloppy,
            "Disciplined roster should align at least as well as sloppy roster")

