"""
Tests for the Placeholder Archetype feature (Phase 8).

A placeholder archetype is a "typical player" (for example a power-conference
starting guard) that the Roster Outlook scenario tool can drop into a roster.

Covers:
  - GET /api/outlook/placeholders/ and its filters (PlaceholderListView)
  - the PlaceholderArchetype model
  - ncaa.conf_utils: which conference group a team belongs to
  - the build_placeholder_archetypes command, run against a small seeded pool
    of player projections
  - the _bucket_uncertainty formula
"""

import io
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from ncaa.conf_utils import CONF_MAP, HIGH_MID_CONFS, POWER_CONFS, get_conf_detail, get_conf_group
from ncaa.management.commands import build_placeholder_archetypes as build_command
from ncaa.management.commands.build_placeholder_archetypes import (
    _ARCHETYPES,
    UNC_IDEAL_N,
    UNC_MAX,
    UNC_MIN,
    _bucket_uncertainty,
)
from ncaa.models import PlaceholderArchetype, Player, PlayerSeasonProjection, Season, Team


# ── Fixture helpers ──────────────────────────────────────────────────────────


def _make_season(year: int = 2026) -> Season:
    return Season.objects.get_or_create(
        year=year,
        defaults={"display_name": f"{year - 1}-{str(year)[2:]}", "is_current": False},
    )[0]


def _make_team(slug: str, name: str) -> Team:
    return Team.objects.get_or_create(slug=slug, defaults={"name": name})[0]


def _make_player(n: int) -> Player:
    return Player.objects.create(
        espn_athlete_id=f"ph_test_{n}",
        display_name=f"Placeholder TestPlayer {n}",
        short_name=f"P. Test{n}",
        position="G",
    )


def _make_projection(player, team, season, role="G", ms=0.50, bpr=2.0) -> PlayerSeasonProjection:
    return PlayerSeasonProjection.objects.create(
        player=player,
        team=team,
        from_season=season,
        projected_season_year=season.year + 1,
        recruitment_type="returner",
        projected_obpr=bpr * 0.6,
        projected_dbpr=bpr * 0.4,
        projected_bpr=bpr,
        projected_minutes_share=ms,
        minutes_share_p2=ms,
        mpg_p2=ms * 40,
        role_bucket=role,
        projection_uncertainty=0.35,
        rotation_rank=1,
        n_prior_seasons=2,
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


# ── conf_utils (pure functions, no database) ─────────────────────────────────


class TestGetConfGroup(SimpleTestCase):
    """The coarse 2-tier grouping: power vs mid_major."""

    def test_power_conf_teams_return_power(self):
        self.assertEqual(get_conf_group("kansas"), "power")       # B12
        self.assertEqual(get_conf_group("duke"), "power")         # ACC
        self.assertEqual(get_conf_group("kentucky"), "power")     # SEC
        self.assertEqual(get_conf_group("michigan"), "power")     # B10
        self.assertEqual(get_conf_group("uconn"), "power")        # BE

    def test_mid_major_teams_return_mid_major(self):
        # WCC, MWC, A10, Amer are pooled into mid_major in the coarse classifier
        self.assertEqual(get_conf_group("gonzaga"), "mid_major")     # WCC
        self.assertEqual(get_conf_group("dayton"), "mid_major")      # A10
        self.assertEqual(get_conf_group("utah-state"), "mid_major")  # MWC
        self.assertEqual(get_conf_group("vcu"), "mid_major")         # A10

    def test_unknown_slug_defaults_to_mid_major(self):
        self.assertEqual(get_conf_group("totally-unknown-team-xyz"), "mid_major")

    def test_case_insensitive(self):
        self.assertEqual(get_conf_group("KANSAS"), "power")
        self.assertEqual(get_conf_group("Kansas"), "power")

    def test_only_ever_returns_power_or_mid_major(self):
        results = {get_conf_group(slug) for slug in CONF_MAP}
        self.assertEqual(results, {"power", "mid_major"})

    def test_power_confs_are_subset_of_conf_map(self):
        conf_values = set(CONF_MAP.values())
        for conf in POWER_CONFS:
            self.assertIn(conf, conf_values, f"POWER_CONF {conf!r} not in CONF_MAP")

    def test_conf_map_has_expected_size(self):
        """The conference map should cover at least 300 D1 team slugs."""
        self.assertGreater(len(CONF_MAP), 300)


class TestGetConfDetail(SimpleTestCase):
    """The fine 3-tier grouping: power, high_mid, mid_major."""

    def test_power_teams_return_power(self):
        self.assertEqual(get_conf_detail("kansas"), "power")
        self.assertEqual(get_conf_detail("duke"), "power")
        self.assertEqual(get_conf_detail("kentucky"), "power")

    def test_high_mid_conferences_return_high_mid(self):
        """One team from each high-mid conference."""
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

    def test_other_conferences_return_mid_major(self):
        self.assertEqual(get_conf_detail("drake"), "mid_major")    # MVC
        self.assertEqual(get_conf_detail("toledo"), "mid_major")   # MAC
        self.assertEqual(get_conf_detail("hawaii"), "mid_major")   # Big West

    def test_unknown_slug_defaults_to_mid_major(self):
        self.assertEqual(get_conf_detail("totally-unknown-xyz"), "mid_major")

    def test_case_insensitive(self):
        self.assertEqual(get_conf_detail("GONZAGA"), "high_mid")
        self.assertEqual(get_conf_detail("Duke"), "power")


# ── PlaceholderArchetype model ───────────────────────────────────────────────


class TestPlaceholderArchetypeModel(TestCase):
    def test_str_representation(self):
        a = _make_archetype()
        self.assertIn("Power Conf Guard (Starter)", str(a))
        self.assertIn("BPR", str(a))

    def test_key_is_unique(self):
        _make_archetype(key="my_unique_key")
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

    def test_default_ordering_is_conf_group_then_role_then_tier(self):
        _make_archetype("z_test", conf_group="power", role_bucket="G", quality_tier="starter")
        _make_archetype("a_test", conf_group="mid_major", role_bucket="G", quality_tier="starter")
        _make_archetype("m_test", conf_group="national", role_bucket="Wing", quality_tier="elite")
        keys = list(PlaceholderArchetype.objects.values_list("key", flat=True))
        # conf_group sorts alphabetically: mid_major < national < power
        self.assertEqual(keys, ["a_test", "m_test", "z_test"])


# ── PlaceholderListView: GET /api/outlook/placeholders/ ──────────────────────


class TestPlaceholderListView(TestCase):
    def setUp(self):
        _make_archetype("elite_g", "All-American Guard", "national", "G", "elite", 3.52, 0.624, 24.9, 260)
        _make_archetype("power_starter_g", "Power Conf Guard (Starter)", "power", "G", "starter", 2.72, 0.526, 21.1, 226)
        _make_archetype("mid_starter_wing", "Mid-Major Wing (Starter)", "mid_major", "Wing", "starter", 0.30, 0.445, 17.8, 640)

    def _get(self, **params):
        return self.client.get(reverse("roster-outlook-placeholders"), params)

    def _keys(self, response):
        return [a["key"] for a in response.json()["archetypes"]]

    def test_list_all(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self._keys(resp)), 3)

    def test_filter_by_role(self):
        resp = self._get(role="G")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(sorted(self._keys(resp)), ["elite_g", "power_starter_g"])

    def test_filter_by_tier(self):
        self.assertEqual(self._keys(self._get(tier="elite")), ["elite_g"])

    def test_filter_by_conf_group(self):
        self.assertEqual(self._keys(self._get(conf_group="power")), ["power_starter_g"])

    def test_filter_by_high_mid_conf_group(self):
        _make_archetype("high_mid_starter_g", conf_group="high_mid")
        self.assertEqual(self._keys(self._get(conf_group="high_mid")), ["high_mid_starter_g"])

    def test_filters_combine(self):
        self.assertEqual(self._keys(self._get(role="Wing", tier="starter")), ["mid_starter_wing"])

    def test_no_match_returns_empty_list(self):
        resp = self._get(role="Big", tier="elite")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["archetypes"], [])

    def test_unknown_filter_param_is_ignored(self):
        resp = self._get(unknown_param="abc")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self._keys(resp)), 3)

    def test_every_field_is_present(self):
        a = self._get(tier="elite").json()["archetypes"][0]
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

    def test_numeric_fields_have_the_right_types(self):
        for a in self._get().json()["archetypes"]:
            self.assertIsInstance(a["projected_bpr"], float)
            self.assertGreater(a["sample_n"], 0)


# ── build_placeholder_archetypes command ─────────────────────────────────────

# One team per conference group. Slugs must exist in ncaa.conf_utils.CONF_MAP.
# (slug, name, BPR offset): stronger conferences get higher BPR.
_POOL_TEAMS = {
    "power": ("duke", "Duke", 3.0),            # ACC
    "high_mid": ("gonzaga", "Gonzaga", 1.5),   # WCC
    "mid_major": ("belmont", "Belmont", 0.0),  # MVC
}
# minutes_share_p2 that puts a player in each tier (starter >= 0.375,
# rotation 0.20-0.375, bench 0.05-0.20).
_TIER_MINUTES = {"starter": 0.50, "rotation": 0.28, "bench": 0.10}
_PLAYERS_PER_BUCKET = 4


def _seed_projection_pool(season: Season) -> None:
    """3 teams x 3 roles x 3 tiers x 4 players = 108 projections."""
    n = 0
    for slug, name, base_bpr in _POOL_TEAMS.values():
        team = _make_team(slug, name)
        for role in ("G", "Wing", "Big"):
            for tier, ms in _TIER_MINUTES.items():
                for i in range(_PLAYERS_PER_BUCKET):
                    n += 1
                    bpr = base_bpr + (1.0 if tier == "starter" else 0.0) + i * 0.5
                    _make_projection(_make_player(n), team, season, role=role, ms=ms, bpr=bpr)


class TestBuildCommandWithoutData(TestCase):
    def test_no_projections_raises_command_error(self):
        with self.assertRaises(CommandError):
            call_command("build_placeholder_archetypes", stdout=io.StringIO())
        self.assertEqual(PlaceholderArchetype.objects.count(), 0)


class TestBuildPlaceholderArchetypesCommand(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = _make_season(2026)
        _seed_projection_pool(cls.season)

    def _build(self, **options) -> str:
        out = io.StringIO()
        call_command("build_placeholder_archetypes", stdout=out, **options)
        return out.getvalue()

    def _keys(self) -> set:
        return set(PlaceholderArchetype.objects.values_list("key", flat=True))

    def test_dry_run_writes_nothing(self):
        output = self._build(dry_run=True)
        self.assertIn("[dry-run]", output)
        self.assertEqual(PlaceholderArchetype.objects.count(), 0)

    def test_builds_every_archetype_in_the_spec_except_high_mid(self):
        """Elite, all-conference, power, mid-major and bench archetypes all get built."""
        self._build()
        expected = {key for key, _name, conf_group, _role, _tier in _ARCHETYPES if conf_group != "high_mid"}
        self.assertLessEqual(expected, self._keys())

    def test_high_mid_archetypes_are_skipped_when_the_bucket_is_too_small(self):
        """4 players per bucket is far below MIN_SPECIFIC_BUCKET (40)."""
        self._build()
        self.assertFalse(PlaceholderArchetype.objects.filter(conf_group="high_mid").exists())

    def test_high_mid_archetypes_are_built_when_the_bucket_is_big_enough(self):
        with mock.patch.object(build_command, "MIN_SPECIFIC_BUCKET", 1):
            self._build()
        tier_two_keys = {
            f"high_mid_{tier}_{role}"
            for tier in ("starter", "rotation")
            for role in ("g", "wing", "big")
        }
        self.assertLessEqual(tier_two_keys, self._keys())
        starter = PlaceholderArchetype.objects.get(key="high_mid_starter_g")
        self.assertEqual(starter.conf_group, "high_mid")
        self.assertEqual(starter.sample_n, _PLAYERS_PER_BUCKET)

    def test_per_conference_archetypes_are_built_when_the_bucket_is_big_enough(self):
        with mock.patch.object(build_command, "MIN_CONFERENCE_BUCKET", _PLAYERS_PER_BUCKET):
            self._build()
        acc = PlaceholderArchetype.objects.get(key="acc_starter_g")
        self.assertEqual((acc.conference, acc.conf_group, acc.sample_n), ("ACC", "power", _PLAYERS_PER_BUCKET))
        wcc = PlaceholderArchetype.objects.get(key="wcc_starter_g")
        self.assertEqual((wcc.conference, wcc.conf_group), ("WCC", "high_mid"))

    def test_running_twice_gives_the_same_result(self):
        """Archetypes are upserted by key, not duplicated."""
        self._build()
        first = dict(PlaceholderArchetype.objects.values_list("key", "projected_bpr"))
        self._build()
        second = dict(PlaceholderArchetype.objects.values_list("key", "projected_bpr"))
        self.assertEqual(first, second)

    def test_elite_bpr_is_above_power_starter_bpr(self):
        self._build()
        for role in ("g", "wing", "big"):
            with self.subTest(role=role):
                elite = PlaceholderArchetype.objects.get(key=f"elite_{role}")
                starter = PlaceholderArchetype.objects.get(key=f"power_starter_{role}")
                self.assertGreater(elite.projected_bpr, starter.projected_bpr)

    def test_starters_play_more_minutes_than_rotation_players(self):
        self._build()
        for group in ("power", "mid"):
            for role in ("g", "wing", "big"):
                with self.subTest(group=group, role=role):
                    starter = PlaceholderArchetype.objects.get(key=f"{group}_starter_{role}")
                    rotation = PlaceholderArchetype.objects.get(key=f"{group}_rotation_{role}")
                    self.assertGreater(starter.minutes_share, rotation.minutes_share)

    def test_uncertainty_is_within_bounds(self):
        with mock.patch.object(build_command, "MIN_SPECIFIC_BUCKET", 1):
            self._build()
        for a in PlaceholderArchetype.objects.all():
            self.assertGreaterEqual(a.uncertainty, UNC_MIN, a.key)
            self.assertLessEqual(a.uncertainty, UNC_MAX, a.key)


# ── _bucket_uncertainty formula (pure function, no database) ─────────────────


class TestBucketUncertainty(SimpleTestCase):
    """
    The formula combines the players' own uncertainty with a small-sample
    penalty and a wide-spread penalty, then clips to [UNC_MIN, UNC_MAX].
    """

    def test_output_is_bounded(self):
        test_cases = [
            (0.0, [0.0], 1),              # tiny n, no spread
            (1.0, [0.0] * 200, 200),      # large base, large n
            (0.5, list(range(10)), 10),   # normal case
            (0.9, [5.0, -3.0, 7.0], 3),   # extreme spread, small n
        ]
        for base_unc, bpr_vals, n in test_cases:
            result = _bucket_uncertainty(base_unc, bpr_vals, n)
            self.assertGreaterEqual(result, UNC_MIN, f"base={base_unc}, n={n}")
            self.assertLessEqual(result, UNC_MAX, f"base={base_unc}, n={n}")

    def test_larger_bucket_gives_lower_or_equal_uncertainty(self):
        small = [2.0 + i * 0.1 for i in range(10)]
        large = small * 15  # same spread, 150 players
        self.assertLessEqual(
            _bucket_uncertainty(0.4, large, len(large)),
            _bucket_uncertainty(0.4, small, len(small)),
        )

    def test_wider_spread_gives_higher_uncertainty(self):
        n = 50
        tight = _bucket_uncertainty(0.4, [2.0] * n, n)
        wide = _bucket_uncertainty(0.4, [0.0, 4.0] * (n // 2), n)
        self.assertGreater(wide, tight)

    def test_same_inputs_give_the_same_output(self):
        bpr_vals = [1.5, 2.0, 2.5, 3.0, 1.0]
        self.assertEqual(
            _bucket_uncertainty(0.35, bpr_vals, 5),
            _bucket_uncertainty(0.35, bpr_vals, 5),
        )

    def test_single_player_bucket_does_not_crash(self):
        """One value has no standard deviation; the formula must cope."""
        result = _bucket_uncertainty(0.4, [2.5], 1)
        self.assertGreaterEqual(result, UNC_MIN)
        self.assertLessEqual(result, UNC_MAX)

    def test_tiny_bucket_is_less_certain_than_a_big_one(self):
        big = _bucket_uncertainty(0.4, [2.0] * 200, 200)
        tiny = _bucket_uncertainty(0.4, [2.0], 1)
        self.assertGreater(tiny, big)

    def test_ideal_size_bucket_with_no_spread_adds_no_penalty(self):
        """At n = UNC_IDEAL_N with zero spread, the result equals the base."""
        n = UNC_IDEAL_N
        self.assertAlmostEqual(_bucket_uncertainty(0.4, [2.0] * n, n), 0.4, places=6)
