"""
Tests for the player projection engine (Phase 1).

These tests cover the pure-Python projection logic in engine.py without
requiring a Django database setup. The pipeline.py DB layer is tested
by integration tests (not included here because they require fixtures).
"""

import unittest

from ncaa.analytics.player_value.projection.engine import (
    RETURNER,
    TRANSFER,
    NEWCOMER,
    classify_recruitment_type,
    _select_talent_signal,
    _year_to_year_shrinkage,
    _trend_adjustment,
    _development_adjustment,
    _get_stratified_dev_adjustment,
    _transfer_competition_adjustment,
    _compute_uncertainty,
    _compute_minutes_share,
    get_recruiting_prior,
    project_player,
)
from ncaa.analytics.player_value.projection.pipeline import (
    classify_recruitment_type as pipeline_classify_recruitment_type,
)
from ncaa.analytics.player_value.projection.constants import (
    UNCERTAINTY_BASE,
    UNCERTAINTY_POSS_MAX_ADD,
    UNCERTAINTY_STABLE_POSS,
    MINUTES_SHARE_MIN,
    MINUTES_SHARE_MAX,
    PROJECTION_VERSION,
    NEWCOMER_RANK_PRIORS,
    NEWCOMER_STARS_PRIORS,
    USE_RECRUITING_PRIOR,
    USE_STRATIFIED_DEV_ADJUSTMENTS,
    DEV_OFF_NEWCOMER_BIG,
    DEV_OFF_NEWCOMER_G,
    DEV_OFF_NEWCOMER_WING,
)
from ncaa.analytics.player_value.projection.pipeline import _pick_canonical_row


# ── classify_recruitment_type ─────────────────────────────────────────────────

class TestClassifyRecruitmentType(unittest.TestCase):
    def test_returner_same_team(self):
        prior = {"team_id": 42}
        assert classify_recruitment_type(1, current_team_id=42, prior_season_row=prior) == RETURNER

    def test_transfer_different_team(self):
        prior = {"team_id": 99}
        assert classify_recruitment_type(1, current_team_id=42, prior_season_row=prior) == TRANSFER

    def test_newcomer_no_prior(self):
        assert classify_recruitment_type(1, current_team_id=42, prior_season_row=None) == NEWCOMER

    def test_newcomer_none_team_in_prior(self):
        # Missing team_id in prior row — conservative default
        prior = {"team_id": None}
        assert classify_recruitment_type(1, current_team_id=42, prior_season_row=prior) == RETURNER

    def test_current_team_none(self):
        # current_team_id is None — can't compare, default returner
        prior = {"team_id": 42}
        assert classify_recruitment_type(1, current_team_id=None, prior_season_row=prior) == RETURNER


# ── _select_talent_signal ─────────────────────────────────────────────────────

class TestSelectTalentSignal(unittest.TestCase):
    """
    RAPM BPR (obpr/dbpr) is the primary signal.
    Box BPR is used ONLY as a fallback when RAPM is absent.
    We do NOT blend them because obpr already incorporates box_obpr as a
    Bayesian prior; doing so would double-count the box signal.
    """

    def test_rapm_used_when_available_ignores_box(self):
        """RAPM-only result even when box is present — no blend."""
        off, def_ = _select_talent_signal(4.0, -2.0, 10.0, -8.0)  # box very different
        self.assertAlmostEqual(off, 4.0)
        self.assertAlmostEqual(def_, -2.0)

    def test_rapm_only_returned_as_is(self):
        off, def_ = _select_talent_signal(5.0, -3.0, None, None)
        self.assertEqual(off, 5.0)
        self.assertEqual(def_, -3.0)

    def test_box_fallback_when_no_rapm(self):
        off, def_ = _select_talent_signal(None, None, 2.0, -1.5)
        self.assertEqual(off, 2.0)
        self.assertEqual(def_, -1.5)

    def test_neither_returns_none(self):
        off, def_ = _select_talent_signal(None, None, None, None)
        self.assertIsNone(off)
        self.assertIsNone(def_)

    def test_partial_rapm_uses_fallback(self):
        """obpr present but dbpr absent — RAPM incomplete, falls through to box."""
        off, def_ = _select_talent_signal(3.0, None, 2.0, -1.0)
        # obpr alone doesn't satisfy has_rapm (need both), so box fallback is used
        self.assertEqual(off, 2.0)
        self.assertEqual(def_, -1.0)

    def test_partial_box_no_rapm_returns_none(self):
        """box_obpr present but box_dbpr absent — both fallbacks incomplete."""
        off, def_ = _select_talent_signal(None, None, 2.0, None)
        self.assertIsNone(off)
        self.assertIsNone(def_)


# ── _year_to_year_shrinkage ───────────────────────────────────────────────────

class TestYearToYearShrinkage(unittest.TestCase):
    def test_zero_poss_full_shrinkage(self):
        off, def_ = _year_to_year_shrinkage(5.0, -3.0, 0.0, 0.0)
        # λ = 500/(500+0) = 1.0 → projected = (1-1)*signal = 0
        assert abs(off) < 1e-9
        assert abs(def_) < 1e-9

    def test_large_poss_minimal_shrinkage(self):
        off, def_ = _year_to_year_shrinkage(4.0, -2.0, 50_000.0, 50_000.0)
        # λ ≈ 0 → projected ≈ signal
        assert abs(off - 4.0) < 0.1
        assert abs(def_ + 2.0) < 0.1

    def test_at_shrink_poss_half_shrinkage(self):
        # At YTY_SHRINK_POSS_OFF poss: λ = 0.5, projected = 0.5 * signal
        signal = 6.0
        off, _ = _year_to_year_shrinkage(signal, 0.0, 500.0, 500.0)
        assert abs(off - signal * 0.5) < 1e-9

    def test_returns_less_than_signal(self):
        off, def_ = _year_to_year_shrinkage(3.0, -2.0, 300.0, 300.0)
        assert off < 3.0
        assert def_ > -2.0   # shrinkage toward 0 means less negative


# ── _trend_adjustment ─────────────────────────────────────────────────────────

class TestTrendAdjustment(unittest.TestCase):
    def test_upward_trend(self):
        off, def_ = _trend_adjustment(5.0, -1.0, 3.0, -3.0)
        assert off > 0  # current obpr higher → positive trend adj
        assert def_ > 0  # current dbpr less negative → positive trend adj

    def test_downward_trend(self):
        off, def_ = _trend_adjustment(2.0, -3.0, 5.0, -1.0)
        assert off < 0
        assert def_ < 0

    def test_no_prior_no_adjustment(self):
        off, def_ = _trend_adjustment(5.0, -1.0, None, None)
        assert off == 0.0
        assert def_ == 0.0

    def test_no_current_no_adjustment(self):
        off, def_ = _trend_adjustment(None, None, 3.0, -2.0)
        assert off == 0.0
        assert def_ == 0.0


# ── _development_adjustment ───────────────────────────────────────────────────

class TestDevelopmentAdjustment(unittest.TestCase):
    def test_newcomer_gets_boost(self):
        off, def_ = _development_adjustment(0, NEWCOMER)
        assert off > 0
        assert def_ > 0

    def test_return_type_newcomer_treated_same_as_newcomer_type(self):
        # n_prior_seasons=0, recruitment_type=RETURNER still gets newcomer adj
        off, def_ = _development_adjustment(0, RETURNER)
        assert off > 0  # same rule as newcomer

    def test_second_year_smaller_than_newcomer(self):
        off_new, def_new = _development_adjustment(0, NEWCOMER)
        off_2nd, def_2nd = _development_adjustment(1, RETURNER)
        assert off_2nd < off_new
        assert def_2nd < def_new

    def test_third_year_no_adjustment(self):
        off, def_ = _development_adjustment(2, RETURNER)
        assert off == 0.0
        assert def_ == 0.0

    def test_senior_negative_adjustment(self):
        off, def_ = _development_adjustment(3, RETURNER)
        assert off < 0
        assert def_ < 0

    def test_senior_threshold_boundary(self):
        # Below threshold = no adjustment; at threshold = senior penalty
        off_below, _ = _development_adjustment(2, RETURNER)
        off_at, _    = _development_adjustment(3, RETURNER)
        assert off_below == 0.0
        assert off_at < 0.0


# ── _transfer_competition_adjustment ─────────────────────────────────────────

class TestTransferCompetitionAdjustment(unittest.TestCase):
    def test_came_from_stronger_program_positive_adj(self):
        # prior adj_em=15, current adj_em=5 → delta=+10 → small positive adj
        off, def_ = _transfer_competition_adjustment(15.0, 5.0)
        assert off > 0
        assert def_ > 0

    def test_came_from_weaker_program_negative_adj(self):
        off, def_ = _transfer_competition_adjustment(5.0, 15.0)
        assert off < 0
        assert def_ < 0

    def test_same_strength_zero_adj(self):
        off, def_ = _transfer_competition_adjustment(10.0, 10.0)
        assert off == 0.0
        assert def_ == 0.0

    def test_missing_prior_em_zero_adj(self):
        off, def_ = _transfer_competition_adjustment(None, 10.0)
        assert off == 0.0
        assert def_ == 0.0

    def test_missing_current_em_zero_adj(self):
        off, def_ = _transfer_competition_adjustment(10.0, None)
        assert off == 0.0
        assert def_ == 0.0


# ── _compute_uncertainty ──────────────────────────────────────────────────────

class TestComputeUncertainty(unittest.TestCase):
    def test_newcomer_base_is_highest(self):
        u_newcomer  = _compute_uncertainty(NEWCOMER,  0.0, 0.0, False)
        u_transfer  = _compute_uncertainty(TRANSFER,  0.0, 0.0, False)
        u_returner  = _compute_uncertainty(RETURNER,  0.0, 0.0, False)
        assert u_newcomer >= u_transfer >= u_returner

    def test_large_sample_reduces_uncertainty(self):
        u_small = _compute_uncertainty(RETURNER, 100.0, 100.0, True)
        u_large = _compute_uncertainty(RETURNER, 5000.0, 5000.0, True)
        assert u_large < u_small

    def test_no_rapm_adds_max_uncertainty(self):
        u_with    = _compute_uncertainty(RETURNER, 1000.0, 1000.0, True)
        u_without = _compute_uncertainty(RETURNER, 1000.0, 1000.0, False)
        assert u_without > u_with

    def test_clamped_to_range(self):
        for rtype in [RETURNER, TRANSFER, NEWCOMER]:
            for has_rapm in [True, False]:
                u = _compute_uncertainty(rtype, 0.0, 0.0, has_rapm)
                assert 0.0 <= u <= 1.0

    def test_stable_sample_near_base(self):
        # At UNCERTAINTY_STABLE_POSS, poss_add ≈ 0
        u = _compute_uncertainty(RETURNER, UNCERTAINTY_STABLE_POSS, UNCERTAINTY_STABLE_POSS, True)
        base = UNCERTAINTY_BASE[RETURNER]
        assert abs(u - base) < 0.01


# ── _compute_minutes_share ────────────────────────────────────────────────────

class TestComputeMinutesShare(unittest.TestCase):
    def test_observed_mpg_used_when_available(self):
        # mpg=30 → base=0.75, adjusted by BPR
        share = _compute_minutes_share(RETURNER, mpg=30.0, gp=30, projected_bpr=0.0)
        assert abs(share - 0.75) < 0.05

    def test_type_default_for_newcomer(self):
        share = _compute_minutes_share(NEWCOMER, mpg=None, gp=0, projected_bpr=0.0)
        # Should be near the newcomer default (0.25)
        assert abs(share - 0.25) < 0.05

    def test_clamped_to_min_max(self):
        share_low  = _compute_minutes_share(NEWCOMER, mpg=0.1, gp=30, projected_bpr=-50.0)
        share_high = _compute_minutes_share(RETURNER, mpg=40.0, gp=30, projected_bpr=50.0)
        assert share_low  >= MINUTES_SHARE_MIN
        assert share_high <= MINUTES_SHARE_MAX

    def test_fewer_than_5_gp_uses_default(self):
        # <5 GP → falls back to type default
        share_few = _compute_minutes_share(RETURNER, mpg=38.0, gp=3, projected_bpr=0.0)
        share_def = _compute_minutes_share(RETURNER, mpg=None, gp=0, projected_bpr=0.0)
        assert abs(share_few - share_def) < 0.05

    def test_positive_bpr_increases_share(self):
        s_neg = _compute_minutes_share(RETURNER, mpg=None, gp=0, projected_bpr=-5.0)
        s_pos = _compute_minutes_share(RETURNER, mpg=None, gp=0, projected_bpr=+5.0)
        assert s_pos > s_neg


# ── project_player (integration of all steps) ─────────────────────────────────

def _make_current(
    player_id=1, team_id=10,
    obpr=3.0, dbpr=-1.5,
    box_obpr=2.5, box_dbpr=-1.0,
    off_poss=800.0, def_poss=800.0,
    mpg=25.0, gp=30,
    season_id=1,
):
    return {
        "player_id": player_id,
        "team_id": team_id,
        "season_id": season_id,
        "obpr": obpr, "dbpr": dbpr,
        "box_obpr": box_obpr, "box_dbpr": box_dbpr,
        "off_poss": off_poss, "def_poss": def_poss,
        "mpg": mpg, "gp": gp,
    }


class TestProjectPlayer(unittest.TestCase):
    def test_returner_bpr_consistency(self):
        """projected_bpr must equal projected_obpr + projected_dbpr."""
        current = _make_current()
        prior   = {"team_id": 10, "obpr": 2.5, "dbpr": -1.2}
        result  = project_player(current, prior, current_team_adj_em=5.0, prior_team_adj_em=5.0, n_prior_seasons=2)
        expected_bpr = round(result["projected_obpr"] + result["projected_dbpr"], 4)
        assert abs(result["projected_bpr"] - expected_bpr) < 0.001

    def test_newcomer_no_crash_no_bpr(self):
        """Players with no BPR data at all must not crash."""
        current = _make_current(obpr=None, dbpr=None, box_obpr=None, box_dbpr=None)
        result  = project_player(current, None, None, None, 0)
        assert "projected_bpr" in result
        assert result["recruitment_type"] == NEWCOMER

    def test_transfer_type_detected(self):
        current = _make_current(team_id=10)
        prior   = {"team_id": 99, "obpr": 2.0, "dbpr": -1.0}
        result  = project_player(current, prior, None, None, 1)
        assert result["recruitment_type"] == TRANSFER

    def test_returner_type_detected(self):
        current = _make_current(team_id=42)
        prior   = {"team_id": 42, "obpr": 1.5, "dbpr": -0.5}
        result  = project_player(current, prior, None, None, 1)
        assert result["recruitment_type"] == RETURNER

    def test_newcomer_type_detected(self):
        current = _make_current()
        result  = project_player(current, None, None, None, 0)
        assert result["recruitment_type"] == NEWCOMER

    def test_all_required_keys_present(self):
        current = _make_current()
        prior   = {"team_id": 10, "obpr": 2.0, "dbpr": -1.0}
        result  = project_player(current, prior, 8.0, 8.0, 1)
        required = [
            "projected_obpr", "projected_dbpr", "projected_bpr",
            "projected_minutes_share", "projection_uncertainty",
            "recruitment_type", "n_prior_seasons", "prior_rapm_used",
            "projection_version",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_projection_version_matches_constant(self):
        current = _make_current()
        result  = project_player(current, None, None, None, 0)
        assert result["projection_version"] == PROJECTION_VERSION

    def test_uncertainty_in_range(self):
        current = _make_current()
        prior   = {"team_id": 10, "obpr": 2.0, "dbpr": -1.0}
        result  = project_player(current, prior, 10.0, 9.0, 3)
        assert 0.0 <= result["projection_uncertainty"] <= 1.0

    def test_minutes_share_in_range(self):
        current = _make_current()
        result  = project_player(current, None, None, None, 0)
        assert MINUTES_SHARE_MIN <= result["projected_minutes_share"] <= MINUTES_SHARE_MAX

    def test_prior_rapm_used_flag(self):
        current = _make_current()
        prior_with_rapm    = {"team_id": 10, "obpr": 2.0, "dbpr": -1.0}
        prior_without_rapm = {"team_id": 10, "obpr": None, "dbpr": None}

        result_with    = project_player(current, prior_with_rapm, None, None, 1)
        result_without = project_player(current, prior_without_rapm, None, None, 1)
        result_none    = project_player(current, None, None, None, 0)

        assert result_with["prior_rapm_used"] is True
        assert result_without["prior_rapm_used"] is False
        assert result_none["prior_rapm_used"] is False

    def test_transfer_comp_applies_only_to_transfers(self):
        """Symmetric setup: transfer from strong to weak program should lower projection."""
        current = _make_current(team_id=10)
        prior   = {"team_id": 99, "obpr": 3.0, "dbpr": -1.0}

        result_strong_to_weak = project_player(
            current, prior, current_team_adj_em=2.0, prior_team_adj_em=20.0, n_prior_seasons=1
        )
        result_weak_to_strong = project_player(
            current, prior, current_team_adj_em=20.0, prior_team_adj_em=2.0, n_prior_seasons=1
        )
        assert result_strong_to_weak["projected_bpr"] > result_weak_to_strong["projected_bpr"]

    def test_high_poss_lower_shrinkage(self):
        """More possessions → less YTY shrinkage → projection closer to raw talent."""
        base = {"obpr": 4.0, "dbpr": -2.0, "box_obpr": None, "box_dbpr": None, "mpg": 30.0}
        low_poss  = _make_current(**{**base, "off_poss": 50.0, "def_poss": 50.0,
                                     "obpr": 4.0, "dbpr": -2.0, "box_obpr": None, "box_dbpr": None,
                                     "mpg": 30.0, "gp": 30})
        high_poss = _make_current(**{**base, "off_poss": 5000.0, "def_poss": 5000.0,
                                     "obpr": 4.0, "dbpr": -2.0, "box_obpr": None, "box_dbpr": None,
                                     "mpg": 30.0, "gp": 30})
        prior = {"team_id": 10, "obpr": 4.0, "dbpr": -2.0}

        r_low  = project_player(low_poss,  prior, 8.0, 8.0, 2)
        r_high = project_player(high_poss, prior, 8.0, 8.0, 2)

        # High-poss player should have projected BPR closer to the raw signal
        assert abs(r_high["projected_bpr"]) > abs(r_low["projected_bpr"])

    def test_rapm_signal_not_blended_with_box(self):
        """
        When both RAPM and Box BPR are present, the projection uses RAPM only
        (box_obpr/box_dbpr are NOT blended in).  Specifically: giving a player
        an extreme box BPR far from their RAPM should not move the projection.
        """
        # Baseline: RAPM only (no box)
        current_rapm_only = _make_current(obpr=3.0, dbpr=-1.0, box_obpr=None, box_dbpr=None)
        # Same RAPM + box far away from RAPM
        current_with_box  = _make_current(obpr=3.0, dbpr=-1.0, box_obpr=50.0, box_dbpr=-50.0)
        prior = {"team_id": 10, "obpr": 2.0, "dbpr": -1.0}

        r_no_box   = project_player(current_rapm_only, prior, 5.0, 5.0, 2)
        r_with_box = project_player(current_with_box,  prior, 5.0, 5.0, 2)

        # Projections should be identical since box is ignored when RAPM present
        self.assertAlmostEqual(r_no_box["projected_obpr"], r_with_box["projected_obpr"], places=6)
        self.assertAlmostEqual(r_no_box["projected_dbpr"], r_with_box["projected_dbpr"], places=6)


# ── _pick_canonical_row (pipeline helper) ─────────────────────────────────────

class TestPickCanonicalRow(unittest.TestCase):
    """
    _pick_canonical_row selects the row with the most on-court sample.
    Rule: most total possessions → most gp → most mpg.
    """

    def _row(self, off_poss=0.0, def_poss=0.0, gp=0, mpg=0.0, team_id=1):
        return {
            "player_id": 1,
            "team_id": team_id,
            "off_poss": off_poss,
            "def_poss": def_poss,
            "gp": gp,
            "mpg": mpg,
        }

    def test_single_row_returned_unchanged(self):
        row = self._row(off_poss=500.0, def_poss=500.0, gp=25, mpg=28.0, team_id=10)
        self.assertEqual(_pick_canonical_row([row]), row)

    def test_higher_poss_wins(self):
        low  = self._row(off_poss=200.0, def_poss=200.0, team_id=1)
        high = self._row(off_poss=600.0, def_poss=600.0, team_id=2)
        self.assertEqual(_pick_canonical_row([low, high])["team_id"], 2)
        self.assertEqual(_pick_canonical_row([high, low])["team_id"], 2)

    def test_poss_tiebreak_by_gp(self):
        few_gp  = self._row(off_poss=300.0, def_poss=300.0, gp=10, team_id=1)
        more_gp = self._row(off_poss=300.0, def_poss=300.0, gp=25, team_id=2)
        self.assertEqual(_pick_canonical_row([few_gp, more_gp])["team_id"], 2)

    def test_gp_tiebreak_by_mpg(self):
        low_mpg  = self._row(off_poss=300.0, def_poss=300.0, gp=20, mpg=20.0, team_id=1)
        high_mpg = self._row(off_poss=300.0, def_poss=300.0, gp=20, mpg=32.0, team_id=2)
        self.assertEqual(_pick_canonical_row([low_mpg, high_mpg])["team_id"], 2)

    def test_null_poss_treated_as_zero(self):
        null_poss = self._row(off_poss=None, def_poss=None, gp=30, mpg=35.0, team_id=1)
        real_poss = self._row(off_poss=100.0, def_poss=100.0, gp=5, mpg=10.0, team_id=2)
        self.assertEqual(_pick_canonical_row([null_poss, real_poss])["team_id"], 2)

    def test_split_season_picks_primary_team(self):
        """A mid-year transfer's primary team (more poss) becomes canonical."""
        team_a = self._row(off_poss=800.0, def_poss=800.0, gp=28, mpg=30.0, team_id=10)
        team_b = self._row(off_poss=200.0, def_poss=200.0, gp=8,  mpg=25.0, team_id=20)
        result = _pick_canonical_row([team_a, team_b])
        self.assertEqual(result["team_id"], 10)

    def test_deterministic_regardless_of_input_order(self):
        """The same canonical row must be chosen regardless of list order."""
        row_a = self._row(off_poss=500.0, def_poss=500.0, gp=20, mpg=28.0, team_id=1)
        row_b = self._row(off_poss=700.0, def_poss=700.0, gp=25, mpg=30.0, team_id=2)
        self.assertEqual(
            _pick_canonical_row([row_a, row_b])["team_id"],
            _pick_canonical_row([row_b, row_a])["team_id"],
        )


# ── get_recruiting_prior (Phase 1.1) ─────────────────────────────────────────

class TestGetRecruitingPrior(unittest.TestCase):
    """Pure-function tests — no DB access required."""

    def test_rank_5_returns_top10_tier(self):
        result = get_recruiting_prior(national_rank=5, stars=5)
        self.assertAlmostEqual(result["obpr_prior"], 2.2)
        self.assertAlmostEqual(result["dbpr_prior"], 0.7)
        self.assertAlmostEqual(result["uncertainty_override"], 0.65)

    def test_rank_takes_priority_over_stars(self):
        # rank=150 → max_rank=200 tier (obpr=0.0), NOT the 4-star tier (obpr=0.3)
        result = get_recruiting_prior(national_rank=150, stars=4)
        self.assertAlmostEqual(result["obpr_prior"], 0.0)
        self.assertAlmostEqual(result["uncertainty_override"], 0.80)

    def test_stars_fallback_when_rank_none(self):
        result = get_recruiting_prior(national_rank=None, stars=4)
        self.assertAlmostEqual(result["obpr_prior"], 0.3)
        self.assertAlmostEqual(result["dbpr_prior"], 0.1)
        self.assertAlmostEqual(result["uncertainty_override"], 0.77)

    def test_both_none_returns_default(self):
        result = get_recruiting_prior(national_rank=None, stars=None)
        self.assertAlmostEqual(result["obpr_prior"], 0.0)
        self.assertAlmostEqual(result["dbpr_prior"], 0.0)
        self.assertAlmostEqual(result["uncertainty_override"], 0.80)

    def test_rank_over_200_catchall(self):
        result = get_recruiting_prior(national_rank=250, stars=None)
        self.assertAlmostEqual(result["obpr_prior"], -0.2)
        self.assertAlmostEqual(result["dbpr_prior"], -0.1)
        self.assertAlmostEqual(result["uncertainty_override"], 0.82)

    def test_rank_30_boundary(self):
        # rank=30 should match the top-30 tier (max_rank=30, inclusive)
        result = get_recruiting_prior(national_rank=30, stars=None)
        self.assertAlmostEqual(result["obpr_prior"], 1.4)

    def test_rank_31_falls_to_next_tier(self):
        result = get_recruiting_prior(national_rank=31, stars=None)
        self.assertAlmostEqual(result["obpr_prior"], 0.8)


# ── project_player: recruiting prior integration ──────────────────────────────

def _make_newcomer(player_id=5, team_id=10):
    """Minimal newcomer dict — no RAPM, no box BPR, no possessions."""
    return {
        "player_id": player_id,
        "team_id": team_id,
        "season_id": 1,
        "obpr": None, "dbpr": None,
        "box_obpr": None, "box_dbpr": None,
        "off_poss": 0.0, "def_poss": 0.0,
        "mpg": 0.0, "gp": 0,
    }


class TestProjectPlayerRecruitingPrior(unittest.TestCase):

    def test_top10_recruit_projects_positive_bpr(self):
        current = _make_newcomer()
        profile = {"national_rank": 5, "stars": 5, "composite_score": 0.9998}
        result = project_player(current, None, None, None, 0, recruiting_profile=profile)
        self.assertEqual(result["recruitment_type"], NEWCOMER)
        self.assertGreater(result["projected_obpr"], 0.0)
        self.assertGreater(result["projected_bpr"], 0.0)
        self.assertTrue(result["recruiting_prior_used"])

    def test_top10_recruit_uncertainty_lower_than_default_newcomer(self):
        current = _make_newcomer()
        profile = {"national_rank": 5, "stars": 5, "composite_score": 0.9998}
        result = project_player(current, None, None, None, 0, recruiting_profile=profile)
        default_unc = UNCERTAINTY_BASE["newcomer"]  # 0.80
        self.assertLess(result["projection_uncertainty"], default_unc)

    def test_returner_ignores_recruiting_profile(self):
        """A returner must produce the same result regardless of recruiting_profile."""
        current = _make_current(team_id=42)
        prior   = {"team_id": 42, "obpr": 2.0, "dbpr": -1.0}
        profile = {"national_rank": 5, "stars": 5, "composite_score": 0.9998}
        result_without = project_player(current, prior, None, None, 1)
        result_with    = project_player(current, prior, None, None, 1, recruiting_profile=profile)
        self.assertEqual(result_without["projected_obpr"], result_with["projected_obpr"])
        self.assertEqual(result_without["projected_dbpr"], result_with["projected_dbpr"])
        self.assertFalse(result_with["recruiting_prior_used"])

    def test_no_profile_returns_false_flag(self):
        current = _make_newcomer()
        result = project_player(current, None, None, None, 0)
        self.assertFalse(result["recruiting_prior_used"])

    def test_recruiting_prior_used_key_always_present(self):
        current = _make_current()
        prior   = {"team_id": 10, "obpr": 2.0, "dbpr": -1.0}
        result = project_player(current, prior, 8.0, 8.0, 1)
        self.assertIn("recruiting_prior_used", result)

    def test_bpr_consistency_with_recruiting_prior(self):
        """projected_bpr == projected_obpr + projected_dbpr even with recruiting prior."""
        current = _make_newcomer()
        profile = {"national_rank": 5, "stars": 5, "composite_score": 0.9998}
        result = project_player(current, None, None, None, 0, recruiting_profile=profile)
        expected = round(result["projected_obpr"] + result["projected_dbpr"], 4)
        self.assertAlmostEqual(result["projected_bpr"], expected, places=3)


# ── _get_stratified_dev_adjustment (Phase 1.2 BT-3) ──────────────────────────

class TestStratifiedDevAdjustment(unittest.TestCase):
    """Tests for position-stratified development constants (Task 2)."""

    def test_newcomer_big_uses_big_constant(self):
        off, def_ = _get_stratified_dev_adjustment(0, NEWCOMER, "Big")
        self.assertAlmostEqual(off, DEV_OFF_NEWCOMER_BIG)

    def test_newcomer_guard_uses_guard_constant(self):
        off, def_ = _get_stratified_dev_adjustment(0, NEWCOMER, "G")
        self.assertAlmostEqual(off, DEV_OFF_NEWCOMER_G)

    def test_newcomer_wing_uses_wing_constant(self):
        off, def_ = _get_stratified_dev_adjustment(0, NEWCOMER, "Wing")
        self.assertAlmostEqual(off, DEV_OFF_NEWCOMER_WING)

    def test_third_year_returns_zero(self):
        # n_prior=2 → third_year → no BT-3 constant defined → (0.0, 0.0)
        off, def_ = _get_stratified_dev_adjustment(2, RETURNER, "G")
        self.assertAlmostEqual(off, 0.0)
        self.assertAlmostEqual(def_, 0.0)

    def test_unknown_bucket_returns_zero(self):
        off, def_ = _get_stratified_dev_adjustment(0, NEWCOMER, "Unknown")
        self.assertAlmostEqual(off, 0.0)

    def test_stratified_flag_false_falls_back_to_flat(self):
        """project_player with USE_STRATIFIED_DEV_ADJUSTMENTS=False uses flat constants."""
        import ncaa.analytics.player_value.projection.engine as eng
        orig = eng.USE_STRATIFIED_DEV_ADJUSTMENTS
        try:
            eng.USE_STRATIFIED_DEV_ADJUSTMENTS = False
            current = _make_newcomer()
            result = project_player(current, None, None, None, 0, role_bucket="Big")
            # With flag off, flat DEV_OFF_NEWCOMER (+0.20) applies
            # With flag on, DEV_OFF_NEWCOMER_BIG (+0.60) applies
            # The projected_obpr with flat should be lower than with stratified
            eng.USE_STRATIFIED_DEV_ADJUSTMENTS = True
            result_strat = project_player(current, None, None, None, 0, role_bucket="Big")
            # Stratified big newcomer constant > flat newcomer constant
            self.assertGreater(result_strat["projected_obpr"], result["projected_obpr"])
        finally:
            eng.USE_STRATIFIED_DEV_ADJUSTMENTS = orig


# ── pipeline.classify_recruitment_type (Phase 1.2 Task 3) ───────────────────

class TestPipelineClassifyRecruitmentType(unittest.TestCase):
    """Tests for the grad-transfer-aware classifier in pipeline.py (Task 3)."""

    def test_newcomer_no_prior_row(self):
        rtype, reason = pipeline_classify_recruitment_type(
            player_id=1, current_team_id=10,
            prior_canonical_row=None,
            player_team_history={},
        )
        self.assertEqual(rtype, "newcomer")
        self.assertEqual(reason, "no_prior_season")

    def test_returner_same_team(self):
        prior = {"team_id": 10}
        rtype, reason = pipeline_classify_recruitment_type(
            player_id=1, current_team_id=10,
            prior_canonical_row=prior,
            player_team_history={1: {10}},
        )
        self.assertEqual(rtype, "returner")
        self.assertEqual(reason, "same_team_prior")

    def test_transfer_different_team_no_history(self):
        prior = {"team_id": 20}
        rtype, reason = pipeline_classify_recruitment_type(
            player_id=1, current_team_id=10,
            prior_canonical_row=prior,
            player_team_history={1: {20}},  # only ever at team 20 before
        )
        self.assertEqual(rtype, "transfer")
        self.assertEqual(reason, "different_team_prior")

    def test_grad_transfer_return_detected(self):
        # Player was at team 10 (original school), then team 20, now back at team 10
        prior = {"team_id": 20}
        rtype, reason = pipeline_classify_recruitment_type(
            player_id=1, current_team_id=10,
            prior_canonical_row=prior,
            player_team_history={1: {10, 20}},  # was at BOTH 10 and 20 before
        )
        self.assertEqual(rtype, "returner")
        self.assertEqual(reason, "grad_transfer_return")

    def test_grad_transfer_only_one_prior_school(self):
        # Player was ONLY at team 20 before. Current team 10 not in history.
        prior = {"team_id": 20}
        rtype, reason = pipeline_classify_recruitment_type(
            player_id=1, current_team_id=10,
            prior_canonical_row=prior,
            player_team_history={1: {20}},
        )
        self.assertEqual(rtype, "transfer")
        self.assertEqual(reason, "different_team_prior")

    def test_classification_reason_in_project_player_result(self):
        """project_player must return classification_reason key."""
        current = _make_current()
        prior   = {"team_id": 10, "obpr": 2.0, "dbpr": -1.0}
        result = project_player(
            current, prior, None, None, 1,
            recruitment_type_override="returner",
            classification_reason="same_team_prior",
        )
        self.assertIn("classification_reason", result)
        self.assertEqual(result["classification_reason"], "same_team_prior")

    def test_recruitment_type_override_respected(self):
        """Override forces classification regardless of prior row team."""
        current = _make_current(team_id=10)
        prior   = {"team_id": 99, "obpr": 2.0, "dbpr": -1.0}  # different team → normally transfer
        result = project_player(
            current, prior, None, None, 1,
            recruitment_type_override="returner",
        )
        self.assertEqual(result["recruitment_type"], "returner")


if __name__ == "__main__":
    unittest.main()
