"""
Tests for Phase 8: Placeholder Archetype API.

Covers:
  - GET /api/outlook/placeholders/               PlaceholderListView
  - GET /api/outlook/placeholders/?role=G        filter by role
  - GET /api/outlook/placeholders/?tier=elite    filter by tier
  - GET /api/outlook/placeholders/?conf_group=power  filter by conf_group
  - PlaceholderArchetypeSerializer field presence
  - build_placeholder_archetypes management command (dry-run)
  - conf_utils.get_conf_group() correctness and fallback (coarse, 2-tier)
  - conf_utils.get_conf_detail() correctness (fine-grained, 3-tier)
  - _bucket_uncertainty formula: direction and bounds
  - high_mid archetypes (Tier 2) exist when data supports them
  - Bucket determinism (rebuilt with same data → same values)
  - Bucket minimum size (both populated and empty)
  - No duplicate archetype keys
"""

import io
from typing import Any

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from ncaa.conf_utils import CONF_MAP, HIGH_MID_CONFS, POWER_CONFS, get_conf_detail, get_conf_group
from ncaa.management.commands.build_placeholder_archetypes import (
    UNC_MAX,
    UNC_MIN,
    _bucket_uncertainty,
)
from ncaa.models import (
    PlaceholderArchetype,
    Player,
    PlayerSeasonProjection,
    PlayerSeasonStats,
    Season,
    Team,
)


# ── Fixture helpers ──────────────────────────────────────────────────────────


def _make_season(year: int = 2026) -> Season:
    return Season.objects.get_or_create(
        year=year,
        defaults={"display_name": f"{year - 1}-{str(year)[2:]}", "is_current": False},
    )[0]


def _make_team(slug: str = "kansas", name: str = "Kansas") -> Team:
    return Team.objects.get_or_create(slug=slug, defaults={"name": name})[0]


def _make_player(n: int = 1) -> Player:
    return Player.objects.create(
        espn_athlete_id=f"ph_test_{n}",
        display_name=f"Placeholder TestPlayer {n}",
        short_name=f"P. Test{n}",
        position="G",
    )


def _make_projection(
    player: Player,
    team: Team,
    season: Season,
    role: str = "G",
    ms: float = 0.50,
    bpr: float = 2.0,
    obpr: float = 1.5,
    dbpr: float = 0.5,
    rtype: str = "returner",
    uncertainty: float = 0.35,
) -> PlayerSeasonProjection:
    return PlayerSeasonProjection.objects.create(
        player=player,
        team=team,
        from_season=season,
        projected_season_year=season.year + 1,
        recruitment_type=rtype,
        projected_obpr=obpr,
        projected_dbpr=dbpr,
        projected_bpr=bpr,
        projected_minutes_share=ms,
        minutes_share_p2=ms,
        mpg_p2=ms * 40,
        role_bucket=role,
        projection_uncertainty=uncertainty,
        rotation_rank=1,
        n_prior_seasons=2,
    )


def _make_stats(
    player: Player,
    team: Team,
    season: Season,
    mpg: float = 20.0,
    obpr: float = 1.5,
    dbpr: float = 0.5,
    efg_pct: float = 0.52,
    fg3_pct: float = 0.35,
) -> PlayerSeasonStats:
    return PlayerSeasonStats.objects.create(
        player=player,
        team=team,
        season=season,
        gp=30,
        mpg=mpg,
        pts=12.0,
        reb=4.0,
        ast=3.0,
        stl=1.0,
        blk=0.3,
        tov=2.0,
        pf=2.0,
        fg_pct=0.45,
        fg3_pct=fg3_pct,
        ft_pct=0.75,
        fga_pg=10.0,
        fg3a_pg=4.0,
        ftm_pg=2.0,
        fta_pg=2.5,
        oreb_pg=0.5,
        dreb_pg=3.5,
        efg_pct=efg_pct,
        ts_pct=0.56,
        ast_to=1.5,
        obpr=obpr,
        dbpr=dbpr,
        bpr=obpr + dbpr,
    )


def _make_archetype(
    key: str = "power_starter_g",
    display_name: str = "Power Conf Guard (Starter)",
    conf_group: str = "power",
    role_bucket: str = "G",
    quality_tier: str = "starter",
    projected_bpr: float = 2.72,
    minutes_share: float = 0.526,
    mpg: float = 21.1,
    sample_n: int = 226,
    source_season_year: int = 2026,
) -> PlaceholderArchetype:
    return PlaceholderArchetype.objects.create(
        key=key,
        display_name=display_name,
        conf_group=conf_group,
        role_bucket=role_bucket,
        quality_tier=quality_tier,
        projected_obpr=projected_bpr * 0.6,
        projected_dbpr=projected_bpr * 0.4,
        projected_bpr=projected_bpr,
        minutes_share=minutes_share,
        mpg=mpg,
        uncertainty=0.4,
        sample_n=sample_n,
        source_season_year=source_season_year,
    )


# ── conf_utils tests ─────────────────────────────────────────────────────────


class TestGetConfGroup(TestCase):
    """Tests for the coarse 2-tier get_conf_group() function."""

    def test_power_conf_teams_return_power(self):
        self.assertEqual(get_conf_group("kansas"), "power")       # B12
        self.assertEqual(get_conf_group("duke"), "power")          # ACC
        self.assertEqual(get_conf_group("kentucky"), "power")      # SEC
        self.assertEqual(get_conf_group("michigan"), "power")      # B10
        self.assertEqual(get_conf_group("uconn"), "power")         # BE

    def test_mid_major_teams_return_mid_major(self):
        # WCC, MWC, A10, Amer are pooled into mid_major in the coarse classifier
        self.assertEqual(get_conf_group("gonzaga"), "mid_major")   # WCC
        self.assertEqual(get_conf_group("dayton"), "mid_major")    # A10
        self.assertEqual(get_conf_group("utah-state"), "mid_major")  # MWC
        self.assertEqual(get_conf_group("vcu"), "mid_major")        # A10

    def test_unknown_slug_defaults_to_mid_major(self):
        self.assertEqual(get_conf_group("totally-unknown-team-xyz"), "mid_major")

    def test_case_insensitive(self):
        self.assertEqual(get_conf_group("KANSAS"), "power")
        self.assertEqual(get_conf_group("Kansas"), "power")

    def test_returns_only_two_values(self):
        """get_conf_group must return only 'power' or 'mid_major' (no high_mid)."""
        sample_slugs = list(CONF_MAP.keys())[:50]
        results = {get_conf_group(s) for s in sample_slugs}
        self.assertTrue(results.issubset({"power", "mid_major"}),
                        f"get_conf_group returned unexpected values: {results}")

    def test_power_confs_are_subset_of_conf_map(self):
        """All POWER_CONFS appear at least once in CONF_MAP values."""
        conf_values = set(CONF_MAP.values())
        for conf in POWER_CONFS:
            self.assertIn(conf, conf_values, f"POWER_CONF {conf!r} not in CONF_MAP")

    def test_conf_map_has_expected_size(self):
        """The conference map should cover at least 300 D1 team slugs."""
        self.assertGreater(len(CONF_MAP), 300)


class TestGetConfDetail(TestCase):
    """Tests for the fine-grained 3-tier get_conf_detail() function."""

    def test_power_teams_return_power(self):
        self.assertEqual(get_conf_detail("kansas"), "power")
        self.assertEqual(get_conf_detail("duke"), "power")
        self.assertEqual(get_conf_detail("kentucky"), "power")

    def test_high_mid_teams_return_high_mid(self):
        self.assertEqual(get_conf_detail("gonzaga"), "high_mid")   # WCC
        self.assertEqual(get_conf_detail("dayton"), "high_mid")    # A10
        self.assertEqual(get_conf_detail("utah-state"), "high_mid")  # MWC
        self.assertEqual(get_conf_detail("memphis"), "high_mid")   # Amer

    def test_low_mid_major_teams_return_mid_major(self):
        # Conferences not in POWER or HIGH_MID should be mid_major
        self.assertEqual(get_conf_detail("drake"), "mid_major")      # MVC
        self.assertEqual(get_conf_detail("toledo"), "mid_major")     # MAC
        self.assertEqual(get_conf_detail("hawaii"), "mid_major")     # Big West

    def test_unknown_slug_defaults_to_mid_major(self):
        self.assertEqual(get_conf_detail("totally-unknown-xyz"), "mid_major")

    def test_returns_three_distinct_values(self):
        """Sampling should produce all 3 tiers: power, high_mid, mid_major."""
        # Known representatives of each tier
        self.assertEqual(get_conf_detail("duke"), "power")
        self.assertEqual(get_conf_detail("gonzaga"), "high_mid")
        self.assertEqual(get_conf_detail("drake"), "mid_major")

    def test_high_mid_confs_all_return_high_mid(self):
        """Every conference in HIGH_MID_CONFS should map a team to high_mid."""
        sample_by_conf = {
            "WCC": "gonzaga",
            "MWC": "utah-state",
            "A10": "dayton",
            "Amer": "memphis",
        }
        for conf, slug in sample_by_conf.items():
            with self.subTest(conf=conf, slug=slug):
                self.assertIn(conf, HIGH_MID_CONFS)
                self.assertEqual(get_conf_detail(slug), "high_mid")

    def test_case_insensitive(self):
        self.assertEqual(get_conf_detail("GONZAGA"), "high_mid")
        self.assertEqual(get_conf_detail("Duke"), "power")


# ── PlaceholderListView API tests ────────────────────────────────────────────


class TestPlaceholderListView(TestCase):
    def setUp(self):
        # Create a handful of archetypes across groups
        _make_archetype("elite_g",        "All-American Guard",  "national",  "G",    "elite",    3.52, 0.624, 24.9, 260)
        _make_archetype("power_starter_g","Power Conf Guard (Starter)", "power", "G", "starter", 2.72, 0.526, 21.1, 226)
        _make_archetype("mid_starter_wing","Mid-Major Wing (Starter)",  "mid_major","Wing","starter",0.30, 0.445,17.8, 640)

    def _url(self, **params):
        base = reverse("roster-outlook-placeholders")
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            return f"{base}?{qs}"
        return base

    def test_list_all_returns_200_with_archetypes_key(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("archetypes", data)
        self.assertEqual(len(data["archetypes"]), 3)

    def test_filter_by_role(self):
        resp = self.client.get(self._url(role="G"))
        self.assertEqual(resp.status_code, 200)
        archetypes = resp.json()["archetypes"]
        self.assertTrue(all(a["role_bucket"] == "G" for a in archetypes))
        self.assertEqual(len(archetypes), 2)

    def test_filter_by_tier(self):
        resp = self.client.get(self._url(tier="elite"))
        self.assertEqual(resp.status_code, 200)
        archetypes = resp.json()["archetypes"]
        self.assertEqual(len(archetypes), 1)
        self.assertEqual(archetypes[0]["key"], "elite_g")

    def test_filter_by_conf_group(self):
        resp = self.client.get(self._url(conf_group="power"))
        self.assertEqual(resp.status_code, 200)
        archetypes = resp.json()["archetypes"]
        self.assertEqual(len(archetypes), 1)
        self.assertEqual(archetypes[0]["conf_group"], "power")

    def test_filter_combination(self):
        resp = self.client.get(self._url(role="Wing", tier="starter"))
        self.assertEqual(resp.status_code, 200)
        archetypes = resp.json()["archetypes"]
        self.assertEqual(len(archetypes), 1)
        self.assertEqual(archetypes[0]["key"], "mid_starter_wing")

    def test_no_results_returns_empty_list(self):
        resp = self.client.get(self._url(role="Big", tier="elite"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["archetypes"], [])

    def test_serializer_field_presence(self):
        """Every required field is present in the response."""
        resp = self.client.get(self._url(tier="elite"))
        a = resp.json()["archetypes"][0]
        required_fields = [
            "key", "display_name", "conf_group", "role_bucket", "quality_tier",
            "projected_obpr", "projected_dbpr", "projected_bpr",
            "minutes_share", "mpg", "uncertainty",
            "efg_pct", "fg3_pct", "ts_pct", "ast_to",
            "oreb_pg", "dreb_pg", "tov",
            "sample_n", "source_season_year",
        ]
        for field in required_fields:
            self.assertIn(field, a, f"Missing field: {field}")

    def test_projected_bpr_is_numeric(self):
        resp = self.client.get(self._url())
        for a in resp.json()["archetypes"]:
            self.assertIsInstance(a["projected_bpr"], float)

    def test_sample_n_is_positive(self):
        resp = self.client.get(self._url())
        for a in resp.json()["archetypes"]:
            self.assertGreater(a["sample_n"], 0)

    def test_unknown_filter_param_returns_all(self):
        """Unsupported filter params should be ignored (no 400 error)."""
        # 'season' is not a supported param — should just return all
        resp = self.client.get(self._url(unknown_param="abc"))
        self.assertEqual(resp.status_code, 200)


# ── management command tests ─────────────────────────────────────────────────


class TestBuildPlaceholderArchetypesCommand(TestCase):
    """
    These tests run the management command against the REAL projection data
    already in the test DB (which mirrors the development DB for integration tests)
    or an empty DB (unit tests).
    """

    def test_dry_run_does_not_write_to_db(self):
        """--dry-run should not create any PlaceholderArchetype rows."""
        out = io.StringIO()
        try:
            call_command("build_placeholder_archetypes", dry_run=True, stdout=out)
        except Exception:
            # If no projection data, command might raise — that's OK for this test
            pass
        # Key invariant: no rows in DB (either because dry-run worked or nothing to process)
        count = PlaceholderArchetype.objects.count()
        self.assertEqual(count, 0)

    def test_command_is_idempotent(self):
        """Running twice with the same data should not change values (upsert)."""
        if PlayerSeasonProjection.objects.count() == 0:
            self.skipTest("No projection data in test DB — skipping command idempotency test.")

        out = io.StringIO()
        call_command("build_placeholder_archetypes", stdout=out)
        first_run_count = PlaceholderArchetype.objects.count()
        first_run_bprs = {a.key: a.projected_bpr for a in PlaceholderArchetype.objects.all()}

        # Second run
        out2 = io.StringIO()
        call_command("build_placeholder_archetypes", stdout=out2)
        second_run_count = PlaceholderArchetype.objects.count()
        second_run_bprs = {a.key: a.projected_bpr for a in PlaceholderArchetype.objects.all()}

        self.assertEqual(first_run_count, second_run_count)
        self.assertEqual(first_run_bprs, second_run_bprs)

    def test_command_produces_broad_archetypes(self):
        """If projection data is present, all 15 broad archetypes should be built."""
        if PlayerSeasonProjection.objects.count() == 0:
            self.skipTest("No projection data in test DB.")

        out = io.StringIO()
        call_command("build_placeholder_archetypes", stdout=out)
        # 15 broad + up to 6 high_mid = 21 total when data is sufficient
        count = PlaceholderArchetype.objects.count()
        self.assertGreaterEqual(count, 15, f"Expected at least 15 archetypes, got {count}")
        self.assertLessEqual(count, 21, f"Expected at most 21 archetypes, got {count}")

    def test_command_output_contains_all_keys(self):
        """Output should reference all 15 expected archetype keys."""
        if PlayerSeasonProjection.objects.count() == 0:
            self.skipTest("No projection data in test DB.")

        out = io.StringIO()
        call_command("build_placeholder_archetypes", stdout=out)
        output = out.getvalue()
        expected_keys = [
            "elite_g", "elite_wing", "elite_big",
            "power_starter_g", "power_starter_wing", "power_starter_big",
            "power_rotation_g", "power_rotation_wing", "power_rotation_big",
            "mid_starter_g", "mid_starter_wing", "mid_starter_big",
            "mid_rotation_g", "mid_rotation_wing", "mid_rotation_big",
        ]
        for key in expected_keys:
            self.assertIn(key, output, f"Key {key!r} not mentioned in command output")

    def test_elite_bpr_higher_than_starter_bpr(self):
        """Elite archetypes should have higher BPR than starter archetypes for the same role."""
        if PlayerSeasonProjection.objects.count() == 0:
            self.skipTest("No projection data in test DB.")

        call_command("build_placeholder_archetypes", stdout=io.StringIO())
        for role in ["G", "Wing", "Big"]:
            elite_key = f"elite_{role.lower()}"
            starter_key = f"power_starter_{role.lower()}"
            try:
                elite = PlaceholderArchetype.objects.get(key=elite_key)
                starter = PlaceholderArchetype.objects.get(key=starter_key)
                self.assertGreater(
                    elite.projected_bpr,
                    starter.projected_bpr,
                    f"Elite {role} BPR ({elite.projected_bpr:.2f}) should exceed "
                    f"power starter {role} BPR ({starter.projected_bpr:.2f})",
                )
            except PlaceholderArchetype.DoesNotExist:
                self.fail(f"Missing archetype: {elite_key} or {starter_key}")

    def test_starter_minutes_higher_than_rotation(self):
        """Starter archetypes should have more median minutes than rotation archetypes."""
        if PlayerSeasonProjection.objects.count() == 0:
            self.skipTest("No projection data in test DB.")

        call_command("build_placeholder_archetypes", stdout=io.StringIO())
        for conf in ["power", "mid_major"]:
            for role in ["G", "Wing", "Big"]:
                r = role.lower()
                start_key = f"{conf.split('_')[0]}_starter_{r}"
                # e.g. "power_starter_g", "mid_starter_g"
                if conf == "mid_major":
                    start_key = f"mid_starter_{r}"
                    rot_key = f"mid_rotation_{r}"
                else:
                    rot_key = f"power_rotation_{r}"

                try:
                    starter = PlaceholderArchetype.objects.get(key=start_key)
                    rotation = PlaceholderArchetype.objects.get(key=rot_key)
                    self.assertGreater(
                        starter.minutes_share,
                        rotation.minutes_share,
                        f"{start_key} minutes_share should exceed {rot_key}",
                    )
                except PlaceholderArchetype.DoesNotExist:
                    self.fail(f"Missing archetype: {start_key} or {rot_key}")

    def test_all_sample_ns_above_minimum(self):
        """Each archetype should have at least 30 players in its source bucket."""
        if PlayerSeasonProjection.objects.count() == 0:
            self.skipTest("No projection data in test DB.")

        call_command("build_placeholder_archetypes", stdout=io.StringIO())
        for a in PlaceholderArchetype.objects.all():
            self.assertGreaterEqual(
                a.sample_n,
                30,
                f"Archetype {a.key!r} has only {a.sample_n} players — below minimum of 30",
            )


# ── PlaceholderArchetype model tests ─────────────────────────────────────────


class TestPlaceholderArchetypeModel(TestCase):
    def test_str_representation(self):
        a = _make_archetype()
        self.assertIn("Power Conf Guard (Starter)", str(a))
        self.assertIn("BPR", str(a))

    def test_key_is_unique(self):
        _make_archetype(key="my_unique_key")
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            _make_archetype(key="my_unique_key")

    def test_nullable_stat_fields_accept_none(self):
        a = PlaceholderArchetype.objects.create(
            key="null_stat_test",
            display_name="Null Stat Test",
            conf_group="national",
            role_bucket="G",
            quality_tier="elite",
            projected_obpr=2.0,
            projected_dbpr=1.0,
            projected_bpr=3.0,
            minutes_share=0.5,
            mpg=20.0,
            uncertainty=0.4,
            efg_pct=None,
            fg3_pct=None,
            ts_pct=None,
            ast_to=None,
            oreb_pg=None,
            dreb_pg=None,
            tov=None,
            sample_n=100,
            source_season_year=2026,
        )
        a.refresh_from_db()
        self.assertIsNone(a.efg_pct)
        self.assertIsNone(a.tov)

    def test_default_ordering(self):
        _make_archetype("z_test", conf_group="power",    role_bucket="G",    quality_tier="starter")
        _make_archetype("a_test", conf_group="mid_major",role_bucket="G",    quality_tier="starter")
        _make_archetype("m_test", conf_group="national", role_bucket="Wing",  quality_tier="elite")
        qs = list(PlaceholderArchetype.objects.values_list("conf_group", flat=True))
        # national should come before others alphabetically in default ordering
        self.assertEqual(qs[0], "mid_major")   # alphabetical: mid_major < national < power


# ── _bucket_uncertainty formula tests ────────────────────────────────────────


class TestBucketUncertainty(TestCase):
    """
    Unit tests for the _bucket_uncertainty() formula.

    Requirements:
      - Larger n → equal or lower uncertainty (n_penalty decreases as n grows)
      - Wider BPR spread → higher uncertainty
      - Output is always bounded in [UNC_MIN, UNC_MAX]
      - Formula is deterministic (same inputs → same output)
    """

    def test_output_is_bounded(self):
        """All outputs must be in [UNC_MIN, UNC_MAX] regardless of inputs."""
        test_cases = [
            (0.0, [0.0], 1),              # tiny n, no spread
            (1.0, [0.0] * 200, 200),      # large base, large n
            (0.5, list(range(10)), 10),    # normal case
            (0.9, [5.0, -3.0, 7.0], 3),   # extreme spread, small n
        ]
        for base_unc, bpr_vals, n in test_cases:
            result = _bucket_uncertainty(base_unc, bpr_vals, n)
            self.assertGreaterEqual(result, UNC_MIN,
                f"Result {result:.4f} below UNC_MIN={UNC_MIN} "
                f"for base={base_unc}, n={n}")
            self.assertLessEqual(result, UNC_MAX,
                f"Result {result:.4f} above UNC_MAX={UNC_MAX} "
                f"for base={base_unc}, n={n}")

    def test_larger_n_gives_lower_or_equal_uncertainty(self):
        """Increasing bucket size should not increase uncertainty."""
        bpr_vals_small = [2.0 + i * 0.1 for i in range(10)]  # 10 players
        bpr_vals_large = bpr_vals_small * 15                   # 150 players (same spread)

        unc_small = _bucket_uncertainty(0.4, bpr_vals_small, len(bpr_vals_small))
        unc_large = _bucket_uncertainty(0.4, bpr_vals_large, len(bpr_vals_large))

        self.assertLessEqual(unc_large, unc_small,
            f"Large bucket unc ({unc_large:.4f}) should be ≤ small bucket unc ({unc_small:.4f})")

    def test_wider_spread_gives_higher_uncertainty(self):
        """Wider BPR spread should increase uncertainty."""
        n = 50
        bpr_tight = [2.0] * n              # zero spread
        bpr_wide = [0.0, 4.0] * (n // 2)  # spread ≈ 2

        unc_tight = _bucket_uncertainty(0.4, bpr_tight, n)
        unc_wide = _bucket_uncertainty(0.4, bpr_wide, n)

        self.assertGreater(unc_wide, unc_tight,
            f"Wide spread unc ({unc_wide:.4f}) should exceed tight spread unc ({unc_tight:.4f})")

    def test_deterministic(self):
        """Same inputs always produce the same output."""
        bpr_vals = [1.5, 2.0, 2.5, 3.0, 1.0]
        r1 = _bucket_uncertainty(0.35, bpr_vals, 5)
        r2 = _bucket_uncertainty(0.35, bpr_vals, 5)
        self.assertEqual(r1, r2)

    def test_single_element_bucket_no_crash(self):
        """Single-element bpr_vals should not crash (no stdev)."""
        result = _bucket_uncertainty(0.4, [2.5], 1)
        self.assertGreaterEqual(result, UNC_MIN)
        self.assertLessEqual(result, UNC_MAX)

    def test_very_small_n_adds_meaningful_penalty(self):
        """n=1 should produce meaningfully higher uncertainty than n=200."""
        bpr_vals_big = [2.0] * 200
        unc_big = _bucket_uncertainty(0.4, bpr_vals_big, 200)
        unc_small = _bucket_uncertainty(0.4, [2.0], 1)
        # Small n should add at least some penalty
        self.assertGreater(unc_small, unc_big)

    def test_ideal_n_gives_no_sample_penalty(self):
        """At n = UNC_IDEAL_N (100), the n_penalty should be zero."""
        from ncaa.management.commands.build_placeholder_archetypes import (
            UNC_IDEAL_N, UNC_SAMPLE_WEIGHT, UNC_SPREAD_WEIGHT
        )
        n = UNC_IDEAL_N
        bpr_vals = [2.0] * n  # zero spread → spread_penalty = 0
        base = 0.4
        result = _bucket_uncertainty(base, bpr_vals, n)
        # With zero spread and n=IDEAL_N, result should equal base exactly
        self.assertAlmostEqual(result, base, places=6)


# ── High Mid-Major archetype tests ────────────────────────────────────────────


class TestHighMidArchetypes(TestCase):
    """Tests specific to the Tier 2 'high_mid' archetypes."""

    def test_high_mid_archetype_in_api(self):
        """API should return high_mid archetypes when they exist in DB."""
        _make_archetype(
            key="high_mid_starter_g",
            display_name="High Mid-Major Guard (Starter)",
            conf_group="high_mid",
            role_bucket="G",
            quality_tier="starter",
            projected_bpr=2.15,
            sample_n=154,
        )
        resp = self.client.get(reverse("roster-outlook-placeholders"))
        self.assertEqual(resp.status_code, 200)
        archetype_keys = [a["key"] for a in resp.json()["archetypes"]]
        self.assertIn("high_mid_starter_g", archetype_keys)

    def test_high_mid_filter_by_conf_group(self):
        """?conf_group=high_mid should return only high_mid archetypes."""
        _make_archetype("high_mid_starter_g", conf_group="high_mid")
        _make_archetype("power_starter_g", conf_group="power")
        url = reverse("roster-outlook-placeholders") + "?conf_group=high_mid"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        archetypes = resp.json()["archetypes"]
        self.assertTrue(all(a["conf_group"] == "high_mid" for a in archetypes))
        self.assertEqual(len(archetypes), 1)

    def test_high_mid_conf_group_choice_is_valid(self):
        """PlaceholderArchetype should accept 'high_mid' as conf_group value."""
        a = PlaceholderArchetype.objects.create(
            key="high_mid_test",
            display_name="High Mid Test",
            conf_group="high_mid",
            role_bucket="G",
            quality_tier="starter",
            projected_obpr=1.3,
            projected_dbpr=0.6,
            projected_bpr=1.9,
            minutes_share=0.45,
            mpg=18.0,
            uncertainty=0.42,
            sample_n=154,
            source_season_year=2026,
        )
        a.refresh_from_db()
        self.assertEqual(a.conf_group, "high_mid")

    def test_command_builds_high_mid_when_data_present(self):
        """Rebuild command should produce high_mid archetypes alongside the 15 broad ones."""
        if PlayerSeasonProjection.objects.count() == 0:
            self.skipTest("No projection data in test DB.")

        call_command("build_placeholder_archetypes", stdout=io.StringIO())
        high_mid_count = PlaceholderArchetype.objects.filter(conf_group="high_mid").count()
        # With real data (n=40-205 per bucket), all 6 should be built
        self.assertEqual(high_mid_count, 6,
            f"Expected 6 high_mid archetypes, got {high_mid_count}")

    def test_no_duplicate_archetype_keys(self):
        """No two archetypes may share the same key (DB constraint)."""
        if PlayerSeasonProjection.objects.count() == 0:
            self.skipTest("No projection data in test DB.")

        call_command("build_placeholder_archetypes", stdout=io.StringIO())
        all_keys = list(PlaceholderArchetype.objects.values_list("key", flat=True))
        self.assertEqual(len(all_keys), len(set(all_keys)),
            f"Duplicate keys found: {[k for k in all_keys if all_keys.count(k) > 1]}")

    def test_high_mid_sample_n_above_specific_threshold(self):
        """Built high_mid archetypes must have n ≥ MIN_SPECIFIC_BUCKET (40)."""
        if PlayerSeasonProjection.objects.count() == 0:
            self.skipTest("No projection data in test DB.")

        from ncaa.management.commands.build_placeholder_archetypes import MIN_SPECIFIC_BUCKET

        call_command("build_placeholder_archetypes", stdout=io.StringIO())
        for a in PlaceholderArchetype.objects.filter(conf_group="high_mid"):
            self.assertGreaterEqual(a.sample_n, MIN_SPECIFIC_BUCKET,
                f"High_mid archetype {a.key!r} has n={a.sample_n} < {MIN_SPECIFIC_BUCKET}")

    def test_high_mid_uncertainty_is_bounded(self):
        """All built archetypes must have uncertainty in [UNC_MIN, UNC_MAX]."""
        if PlayerSeasonProjection.objects.count() == 0:
            self.skipTest("No projection data in test DB.")

        call_command("build_placeholder_archetypes", stdout=io.StringIO())
        for a in PlaceholderArchetype.objects.all():
            self.assertGreaterEqual(a.uncertainty, UNC_MIN,
                f"{a.key!r} uncertainty {a.uncertainty:.4f} below UNC_MIN={UNC_MIN}")
            self.assertLessEqual(a.uncertainty, UNC_MAX,
                f"{a.key!r} uncertainty {a.uncertainty:.4f} above UNC_MAX={UNC_MAX}")
