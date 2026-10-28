"""
Conference realignment for 2026-27 (ncaa/conferences.py + ncaa/data/conferences/2027.csv).

Invariants pinned here:
- The 2027 data file is complete and consistent: 365 unique teams, every conference
  name known, and conference sizes match the announced 2026-27 alignment.
- Seasons <= 2026 and season=None keep the frozen CONF_MAP exactly, so history and
  every existing caller (archetypes, backtests, market value) are unchanged.
- Season-aware lookups use the data file; later seasons reuse the newest file.
- seed_conferences assigns TeamSeasonMetrics from the file, is idempotent, and only
  touches the requested season.
- /api/conferences/ lists only the conferences a season actually has.
"""

import collections
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from ncaa import conferences as conf
from ncaa.conf_utils import (
    CONF_MAP,
    HIGH_MID_CONFS,
    get_conf_detail,
    get_conf_group,
    get_team_conference,
)
from ncaa.models import Conference, Season, Team, TeamSeasonMetrics

# Announced 2026-27 membership sizes (conference code -> teams)
EXPECTED_SIZES = {
    "P12": 9, "MWC": 10, "BW": 12, "UAC": 9, "ASun": 8, "SB": 14, "CUSA": 10, "WCC": 10,
    "Sum": 8, "BSky": 11, "Horz": 12, "MAC": 12, "SC": 11, "OVC": 9, "NEC": 9, "Metro": 13,
    "ACC": 18, "B10": 18, "B12": 16, "SEC": 16, "BE": 11,
}


class DataFileTests(SimpleTestCase):
    def test_file_covers_365_unique_teams(self):
        m = conf.season_conference_map(2027)
        self.assertEqual(len(m), 365)

    def test_every_conference_name_in_the_file_is_known(self):
        conf._load_file.cache_clear()
        conf.season_conference_map(2027)  # raises ConferenceDataError on an unknown name

    def test_conference_sizes_match_the_announced_alignment(self):
        sizes = collections.Counter(conf.season_conference_map(2027).values())
        for code, n in EXPECTED_SIZES.items():
            self.assertEqual(sizes[code], n, code)

    def test_retired_conferences_are_empty_in_2027(self):
        sizes = collections.Counter(conf.season_conference_map(2027).values())
        self.assertEqual(sizes["MAAC"], 0)   # renamed Metro
        self.assertEqual(sizes["WAC"], 0)    # became the UAC

    def test_registry_codes_are_unique_and_fit_the_column(self):
        codes = [c.code for c in conf.CONFERENCES]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(len(c) <= 10 for c in codes))   # Conference.code max_length


class SeasonRoutingTests(SimpleTestCase):
    def test_moves_apply_in_2027(self):
        for slug, expected in [
            ("gonzaga", "P12"), ("boise-st", "P12"), ("san-diego-st", "P12"), ("texas-st", "P12"),
            ("utep", "MWC"), ("uc-davis", "MWC"), ("louisiana-tech", "SB"), ("denver", "WCC"),
            ("sacramento-st", "BW"), ("austin-peay", "UAC"), ("iona", "Metro"),
        ]:
            self.assertEqual(get_team_conference(slug, 2027), expected, slug)

    def test_history_is_frozen(self):
        self.assertEqual(get_team_conference("gonzaga", 2026), "WCC")
        self.assertEqual(get_team_conference("boise-st", 2026), "MWC")
        self.assertEqual(get_team_conference("iona", 2026), "MAAC")
        self.assertEqual(get_team_conference("gonzaga"), "WCC")        # season=None
        self.assertEqual(get_team_conference("gonzaga", 2025), "WCC")

    def test_frozen_map_is_untouched_for_every_team(self):
        for slug, code in CONF_MAP.items():
            self.assertEqual(get_team_conference(slug, 2026), code, slug)
            self.assertEqual(get_team_conference(slug), code, slug)

    def test_later_seasons_reuse_the_newest_file(self):
        self.assertEqual(conf.file_year_for(2028), 2027)
        self.assertEqual(get_team_conference("gonzaga", 2028), "P12")
        self.assertIsNone(conf.file_year_for(2026))

    def test_team_missing_from_the_file_falls_back_to_the_frozen_map(self):
        # Saint Francis left D1 after 2025-26 and is not in 2027.csv
        self.assertEqual(get_team_conference("saint-francis", 2027), CONF_MAP["saint-francis"])

    def test_unknown_slug(self):
        self.assertEqual(get_team_conference("not-a-team", 2027), "Unknown")

    def test_p12_is_high_mid_not_power(self):
        self.assertIn("P12", HIGH_MID_CONFS)
        self.assertEqual(get_conf_detail("gonzaga", 2027), "high_mid")
        self.assertEqual(get_conf_group("gonzaga", 2027), "mid_major")
        self.assertEqual(get_conf_detail("duke", 2027), "power")
        self.assertEqual(get_conf_detail("iona", 2027), "mid_major")


class SeedConferencesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s26 = Season.objects.create(year=2026, display_name="2025-26", is_current=True)
        cls.s27 = Season.objects.create(year=2027, display_name="2026-27")
        cls.gonzaga = Team.objects.create(slug="gonzaga", name="Gonzaga")
        cls.iona = Team.objects.create(slug="iona", name="Iona")
        cls.sf = Team.objects.create(slug="saint-francis", name="Saint Francis")
        for team in (cls.gonzaga, cls.iona):
            for season in (cls.s26, cls.s27):
                TeamSeasonMetrics.objects.create(team=team, season=season)

    def seed(self, season):
        out = StringIO()
        call_command("seed_conferences", season=season, stdout=out, stderr=StringIO())
        return out.getvalue()

    def code(self, team, season):
        return TeamSeasonMetrics.objects.get(team=team, season=season).conference.code

    def test_assigns_each_season_from_its_own_source(self):
        self.seed(2027)
        self.seed(2026)
        self.assertEqual(self.code(self.gonzaga, self.s27), "P12")
        self.assertEqual(self.code(self.iona, self.s27), "Metro")
        self.assertEqual(self.code(self.gonzaga, self.s26), "WCC")   # history untouched
        self.assertEqual(self.code(self.iona, self.s26), "MAAC")

    def test_seeding_one_season_does_not_touch_another(self):
        self.seed(2027)
        self.assertIsNone(TeamSeasonMetrics.objects.get(team=self.gonzaga, season=self.s26).conference)

    def test_idempotent(self):
        self.seed(2027)
        out = self.seed(2027)
        self.assertIn("0 updated", out)

    def test_creates_every_registry_conference_row(self):
        self.seed(2027)
        self.assertEqual(Conference.objects.count(), len(conf.CONFERENCES))
        for code in ("P12", "Metro", "UAC", "MAAC", "WAC"):
            self.assertTrue(Conference.objects.filter(code=code).exists(), code)

    def test_reports_data_file_teams_missing_from_the_db(self):
        out = self.seed(2027)
        self.assertIn("west-florida", out)   # in 2027.csv; no Team row in this test DB

    def test_dry_run_changes_nothing(self):
        before = Conference.objects.count()
        call_command("seed_conferences", season=2027, dry_run=True, stdout=StringIO(), stderr=StringIO())
        self.assertEqual(Conference.objects.count(), before)
        self.assertIsNone(TeamSeasonMetrics.objects.get(team=self.gonzaga, season=self.s27).conference)


class ConferencesEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s26 = Season.objects.create(year=2026, display_name="2025-26", is_current=True)
        cls.s27 = Season.objects.create(year=2027, display_name="2026-27")
        # P12 / Metro / UAC already exist: migration 0070 seeds them
        cls.wcc = Conference.objects.create(code="WCC", name="West Coast Conference")
        cls.p12 = Conference.objects.get(code="P12")
        cls.maac = Conference.objects.create(code="MAAC", name="Metro Atlantic")
        cls.metro = Conference.objects.get(code="Metro")
        team_a = Team.objects.create(slug="a", name="A")
        team_b = Team.objects.create(slug="b", name="B")
        TeamSeasonMetrics.objects.create(team=team_a, season=cls.s26, conference=cls.wcc)
        TeamSeasonMetrics.objects.create(team=team_b, season=cls.s26, conference=cls.maac)
        TeamSeasonMetrics.objects.create(team=team_a, season=cls.s27, conference=cls.p12)
        TeamSeasonMetrics.objects.create(team=team_b, season=cls.s27, conference=cls.metro)

    def codes(self, query=""):
        resp = self.client.get(f"/api/conferences/{query}")
        self.assertEqual(resp.status_code, 200)
        return sorted(c["code"] for c in resp.json())

    def test_default_is_the_current_season(self):
        self.assertEqual(self.codes(), ["MAAC", "WCC"])

    def test_season_param(self):
        self.assertEqual(self.codes("?season=2027"), ["Metro", "P12"])
        self.assertEqual(self.codes("?season=2026"), ["MAAC", "WCC"])

    def test_all_flag_and_empty_season_fall_back_to_everything(self):
        everything = ["MAAC", "Metro", "P12", "UAC", "WCC"]
        self.assertEqual(self.codes("?all=true"), everything)
        self.assertEqual(self.codes("?season=2031"), everything)


class RankingsSerializerFallbackTests(TestCase):
    """A team with no stored conference (its first game hasn't happened yet) still gets the right one."""

    @classmethod
    def setUpTestData(cls):
        cls.s26 = Season.objects.create(year=2026, display_name="2025-26", is_current=True)
        cls.s27 = Season.objects.create(year=2027, display_name="2026-27")
        cls.gonzaga = Team.objects.create(slug="gonzaga", name="Gonzaga")
        cls.nobody = Team.objects.create(slug="not-a-real-team", name="Nobody")

    def conference(self, team, season):
        from types import SimpleNamespace

        from api.serializers import RankingsSerializer

        return RankingsSerializer().get_conference(SimpleNamespace(team=team, season=season))

    def test_fallback_is_season_aware(self):
        self.assertEqual(self.conference(self.gonzaga, self.s27), "P12")
        self.assertEqual(self.conference(self.gonzaga, self.s26), "WCC")

    def test_unknown_team_is_independent(self):
        self.assertEqual(self.conference(self.nobody, self.s27), "Ind")

    def test_stored_conference_wins_over_the_fallback(self):
        mac = Conference.objects.create(code="TEST", name="Test")
        TeamSeasonMetrics.objects.create(team=self.gonzaga, season=self.s27, conference=mac)
        self.assertEqual(self.conference(self.gonzaga, self.s27), "TEST")
