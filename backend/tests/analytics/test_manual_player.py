"""
Tests for manual_player.py — pure Python, no Django.

Covers the ManualPlayerSpec resolver: all four resolution priorities,
JUCO flag, source-tier assignment, and synthetic ID sign.
"""

import unittest

from ncaa.analytics.player_value.scenario.manual_player import (
    ManualPlayerSpec,
    SOURCE_TIER_BPR_OVERRIDE,
    SOURCE_TIER_RANK_ELITE,
    SOURCE_TIER_RANK_HIGH,
    SOURCE_TIER_RANK_MID,
    SOURCE_TIER_RANK_LOW,
    SOURCE_TIER_STARS,
    SOURCE_TIER_PLACEHOLDER,
    SOURCE_TIER_DEFAULT,
    SOURCE_TIER_JUCO,
    resolve_manual_player,
    resolve_db_player,
)

# ── Shared fixtures ────────────────────────────────────────────────────────────

_PLACEHOLDER_LOOKUP = {
    "power_starter_g": {
        "projected_obpr": 1.5,
        "projected_dbpr": 0.6,
        "projected_bpr": 2.1,
        "uncertainty": 0.45,
        "display_name": "Power Conf Guard (Starter)",
        "oreb_pg": 0.5,
        "dreb_pg": 2.0,
        "tov": 1.2,
        "fg3a_pg": 3.1,
        "conf_group": "power",
        "role_bucket": "G",
        "quality_tier": "starter",
    },
    "power_starter_big": {
        "projected_obpr": 0.8,
        "projected_dbpr": 1.2,
        "projected_bpr": 2.0,
        "uncertainty": 0.42,
        "display_name": "Power Conf Big (Starter)",
        "fg3a_pg": 0.5,
        "conf_group": "power",
        "role_bucket": "Big",
        "quality_tier": "starter",
    },
}


def _spec(**kwargs) -> ManualPlayerSpec:
    """Helper: build a ManualPlayerSpec with sensible defaults."""
    defaults = {
        "display_name": "Test Player",
        "position": "G",
        "recruitment_type": "newcomer",
    }
    defaults.update(kwargs)
    return ManualPlayerSpec(**defaults)


class TestBprOverridePriority(unittest.TestCase):
    """BPR override should win even when national_rank is also set."""

    def test_bpr_override_selected_over_rank(self):
        spec = _spec(projected_obpr=2.0, projected_dbpr=1.0, national_rank=5)
        result = resolve_manual_player(spec, _PLACEHOLDER_LOOKUP, -1)
        self.assertEqual(result.resolution_method, "bpr_override")
        self.assertAlmostEqual(result.projected_obpr, 2.0)
        self.assertAlmostEqual(result.projected_dbpr, 1.0)
        self.assertEqual(result.source_tier, SOURCE_TIER_BPR_OVERRIDE)

    def test_bpr_override_selected_over_placeholder(self):
        spec = _spec(projected_obpr=3.0, projected_dbpr=-0.5, placeholder_key="power_starter_g")
        result = resolve_manual_player(spec, _PLACEHOLDER_LOOKUP, -1)
        self.assertEqual(result.resolution_method, "bpr_override")
        self.assertAlmostEqual(result.projected_obpr, 3.0)


class TestRankLookupElite(unittest.TestCase):
    def test_rank_15_returns_elite_tier(self):
        spec = _spec(national_rank=15)
        result = resolve_manual_player(spec, {}, -1)
        self.assertEqual(result.source_tier, SOURCE_TIER_RANK_ELITE)
        self.assertEqual(result.resolution_method, "rank_lookup")
        self.assertGreater(result.projected_obpr, 0.0)

    def test_rank_30_boundary_is_elite(self):
        spec = _spec(national_rank=30)
        result = resolve_manual_player(spec, {}, -1)
        self.assertEqual(result.source_tier, SOURCE_TIER_RANK_ELITE)

    def test_rank_31_is_high(self):
        spec = _spec(national_rank=31)
        result = resolve_manual_player(spec, {}, -1)
        self.assertEqual(result.source_tier, SOURCE_TIER_RANK_HIGH)

    def test_rank_100_is_high(self):
        spec = _spec(national_rank=100)
        result = resolve_manual_player(spec, {}, -1)
        self.assertEqual(result.source_tier, SOURCE_TIER_RANK_HIGH)

    def test_rank_201_is_low(self):
        spec = _spec(national_rank=201)
        result = resolve_manual_player(spec, {}, -1)
        self.assertEqual(result.source_tier, SOURCE_TIER_RANK_LOW)


class TestRankLookupStarsFallback(unittest.TestCase):
    def test_stars_fallback_when_rank_none(self):
        spec = _spec(national_rank=None, stars=4)
        result = resolve_manual_player(spec, {}, -1)
        self.assertEqual(result.source_tier, SOURCE_TIER_STARS)
        self.assertGreaterEqual(result.projected_obpr, 0.0)

    def test_stars_label_formatted(self):
        spec = _spec(national_rank=None, stars=3)
        result = resolve_manual_player(spec, {}, -1)
        self.assertIn("3", result.display_label)


class TestJucoFlag(unittest.TestCase):
    def test_juco_reduces_uncertainty_vs_hs(self):
        spec_juco   = _spec(national_rank=80, is_juco=True)
        spec_nojuco = _spec(national_rank=80, is_juco=False)
        r_juco   = resolve_manual_player(spec_juco,   {}, -1)
        r_nojuco = resolve_manual_player(spec_nojuco, {}, -1)
        self.assertLess(r_juco.projection_uncertainty, r_nojuco.projection_uncertainty)

    def test_juco_source_tier(self):
        spec = _spec(national_rank=50, is_juco=True)
        result = resolve_manual_player(spec, {}, -1)
        self.assertEqual(result.source_tier, SOURCE_TIER_JUCO)

    def test_juco_bpr_higher_than_same_rank_hs(self):
        spec_juco   = _spec(national_rank=50, is_juco=True)
        spec_nojuco = _spec(national_rank=50, is_juco=False)
        r_juco   = resolve_manual_player(spec_juco,   {}, -1)
        r_nojuco = resolve_manual_player(spec_nojuco, {}, -1)
        self.assertGreater(r_juco.projected_obpr, r_nojuco.projected_obpr)


class TestPlaceholderLookup(unittest.TestCase):
    def test_placeholder_key_used(self):
        spec = _spec(placeholder_key="power_starter_g")
        result = resolve_manual_player(spec, _PLACEHOLDER_LOOKUP, -1)
        self.assertEqual(result.resolution_method, "placeholder")
        self.assertAlmostEqual(result.projected_bpr, 2.1)
        self.assertEqual(result.source_tier, SOURCE_TIER_PLACEHOLDER)

    def test_placeholder_display_name(self):
        spec = _spec(placeholder_key="power_starter_g")
        result = resolve_manual_player(spec, _PLACEHOLDER_LOOKUP, -1)
        self.assertEqual(result.display_label, "Power Conf Guard (Starter)")

    def test_missing_placeholder_key_falls_to_default(self):
        spec = _spec(placeholder_key="nonexistent_key")
        result = resolve_manual_player(spec, _PLACEHOLDER_LOOKUP, -1)
        self.assertNotEqual(result.resolution_method, "placeholder")


class TestDefaultFallback(unittest.TestCase):
    def test_newcomer_default_zero_bpr(self):
        spec = _spec(recruitment_type="newcomer")
        result = resolve_manual_player(spec, {}, -1)
        self.assertEqual(result.resolution_method, "default")
        self.assertAlmostEqual(result.projected_obpr, 0.0)
        self.assertAlmostEqual(result.projected_dbpr, 0.0)

    def test_default_auto_matches_placeholder(self):
        """Auto-match by conf_group + role_bucket + quality_tier."""
        spec = _spec(
            position="G", conf_group="power", quality_tier="starter",
            recruitment_type="newcomer",
        )
        result = resolve_manual_player(spec, _PLACEHOLDER_LOOKUP, -1)
        # Should match power_starter_g
        self.assertEqual(result.resolution_method, "default")
        self.assertAlmostEqual(result.projected_obpr, 1.5)


class TestSyntheticId(unittest.TestCase):
    def test_synthetic_id_is_negative(self):
        spec = _spec()
        result = resolve_manual_player(spec, {}, -5)
        self.assertLess(result.player_id, 0)
        self.assertEqual(result.player_id, -5)


class TestReturnersIgnoreRankLookup(unittest.TestCase):
    def test_returner_with_rank_skips_rank_lookup(self):
        """Priority 2 only fires for newcomers/JUCOs — a returner with rank falls to P3/P4."""
        spec = _spec(national_rank=5, recruitment_type="returner")
        result = resolve_manual_player(spec, {}, -1)
        self.assertNotEqual(result.resolution_method, "rank_lookup")

    def test_transfer_with_rank_skips_rank_lookup(self):
        spec = _spec(national_rank=5, recruitment_type="transfer")
        result = resolve_manual_player(spec, {}, -1)
        self.assertNotEqual(result.resolution_method, "rank_lookup")


class TestResolveDbPlayer(unittest.TestCase):
    def test_db_player_is_not_manual(self):
        proj = {
            "id": 99, "player_id": 42, "player_name": "Test Player",
            "projected_obpr": 2.0, "projected_dbpr": 1.0, "projected_bpr": 3.0,
            "projection_uncertainty": 0.4, "recruitment_type": "returner",
            "n_prior_seasons": 2,
        }
        stats = {"mpg": 28.0, "gp": 30, "off_poss": 600.0, "def_poss": 600.0,
                 "ast": 2.0, "blk": 0.2, "reb": 4.0, "fg3a_pg": 2.5}
        result = resolve_db_player(proj, stats, "G")
        self.assertFalse(result.is_manual)
        self.assertEqual(result.source_tier, "db")
        self.assertEqual(result.player_id, 42)
        self.assertAlmostEqual(result.prior_poss, 1200.0)
        self.assertAlmostEqual(result.prior_mpg, 28.0)


class TestBprConsistency(unittest.TestCase):
    def test_projected_bpr_equals_sum(self):
        spec = _spec(projected_obpr=2.5, projected_dbpr=-0.3)
        result = resolve_manual_player(spec, {}, -1)
        self.assertAlmostEqual(result.projected_bpr, result.projected_obpr + result.projected_dbpr, places=3)

    def test_rank_bpr_consistency(self):
        spec = _spec(national_rank=20)
        result = resolve_manual_player(spec, {}, -1)
        self.assertAlmostEqual(result.projected_bpr, result.projected_obpr + result.projected_dbpr, places=3)


if __name__ == "__main__":
    unittest.main()
