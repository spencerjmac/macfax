"""
Task 5.10b: consumers of obpr / dbpr / bpr / wins_added follow the season's rating scale.

- nba.rating_scale.native_scale gives a Scale only for a season with an
  NBASeasonRatingScale row AND native-1 rows; nba_compute_native_bpr --write
  writes that row.
- Native rows: unknown player = (-c_o, -c_d); replacement R = -1.918 (offense
  0.8 R, defense 0.2 R) in the serializer, the outlook allocator and the injury
  engine; the outlook RAPM cap compares raw ratings (centred + c) with box values;
  the API says which scale a row is on.
- A season without native rows keeps every earlier formula exactly
  (EarlierScaleUnchangedTests): the same numbers as the pre-5.10b code.
"""

from datetime import date

from django.test import TestCase

from nba.injury_engine import compute_nba_injury_adjustment
from nba.management.commands import nba_compute_native_bpr as nb
from nba.management.commands.compute_nba_team_outlooks import REPLACEMENT_LEVEL
from nba.management.commands.compute_nba_team_outlooks import Command as OutlookCommand
from nba.models import (NBAPlayer, NBAPlayerAvailability, NBAPlayerSeasonStats, NBASeason,
                        NBASeasonRatingScale, NBATeam)
from nba.rating_scale import Scale, native_scale
from nba.serializers import NBAPlayerSeasonStatsSerializer

C_O, C_D = 2.0, 0.5
R = -1.918


class Fixture(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.legacy = NBASeason.objects.create(year=2025, display_name="2024-25")
        cls.native = NBASeason.objects.create(year=2026, display_name="2025-26")
        cls.team = NBATeam.objects.create(
            nba_team_id=1610612743, slug="denver-nuggets", name="Denver Nuggets",
            abbreviation="DEN", city="Denver", conference="West", division="Northwest")
        cls.star = NBAPlayer.objects.create(player_id=203999, name="Star Center")
        cls.role = NBAPlayer.objects.create(player_id=1630000, name="Role Guard")
        cls.rows = {}
        for season, model in ((cls.legacy, "lebron"), (cls.native, "native-1")):
            for p, (o, d) in ((cls.star, (6.0, 2.0)), (cls.role, (-0.5, 0.3))):
                cls.rows[(season.year, p.player_id)] = NBAPlayerSeasonStats.objects.create(
                    player=p, season=season, team=cls.team, season_type="regular", gp=70, mpg=30.0,
                    obpr=o, dbpr=d, bpr=o + d, bpr_model=model, box_obpr=o - 3.0, box_dbpr=d,
                    obpr_raw=(o + C_O) if model == "native-1" else None,
                    dbpr_raw=(d + C_D) if model == "native-1" else None)
        NBASeasonRatingScale.objects.create(season=cls.native, centre_obpr=C_O, centre_dbpr=C_D,
                                            wins_divisor=37.73, replacement=R)


class NativeScaleTests(Fixture):

    def test_scale_only_for_native_seasons(self):
        self.assertIsNone(native_scale(self.legacy))
        self.assertIsNone(native_scale(2025))
        sc = native_scale(self.native)
        self.assertEqual((sc.unknown_obpr, sc.unknown_dbpr, sc.unknown_bpr), (-C_O, -C_D, -C_O - C_D))
        self.assertAlmostEqual(sc.replacement_obpr, 0.8 * R)
        self.assertAlmostEqual(sc.replacement_dbpr, 0.2 * R)
        self.assertEqual(native_scale(2026), sc)

    def test_scale_row_without_native_rows_is_not_native(self):
        NBASeasonRatingScale.objects.create(season=self.legacy, centre_obpr=1.0, centre_dbpr=1.0,
                                            wins_divisor=37.73, replacement=R)
        self.assertIsNone(native_scale(self.legacy))

    def test_native_command_writes_the_scale_row(self):
        NBASeasonRatingScale.objects.all().delete()
        o = {203999: 8.0, 1630000: 1.5}
        d = {203999: 2.5, 1630000: 0.8}
        nb.write_native(2026, o, d, 1.25, 0.4)
        row = NBASeasonRatingScale.objects.get(season=self.native)
        self.assertEqual((row.bpr_model, row.centre_obpr, row.centre_dbpr, row.wins_divisor, row.replacement),
                         ("native-1", 1.25, 0.4, 37.73, R))

    def test_serializer_native_row(self):
        data = NBAPlayerSeasonStatsSerializer(self.rows[(2026, 203999)]).data
        self.assertEqual(data["rating_scale"], "native-1")
        self.assertEqual(data["bpr_replacement_adjusted"], round(8.0 - R, 3))
        self.assertEqual(data["obpr_replacement_adjusted"], round(6.0 - 0.8 * R, 3))
        self.assertEqual(data["dbpr_replacement_adjusted"], round(2.0 - 0.2 * R, 3))

    def test_injury_fills_absent_minutes_at_replacement(self):
        NBAPlayerAvailability.objects.create(player=self.star, team=self.team, game_date=date(2026, 1, 5), season=self.native,
                                             status="out")
        res = compute_nba_injury_adjustment(self.team, self.native, date(2026, 1, 5))
        share, w = min(30.0 / 48.0, 0.85), 1.0
        self.assertAlmostEqual(res["players"][0]["off_adj"], round((6.0 - 0.8 * R) * share * w, 2))
        self.assertAlmostEqual(res["adj_off_delta"], round(-(6.0 - 0.8 * R) * share * w, 3))
        self.assertAlmostEqual(res["adj_def_delta"], round((2.0 - 0.2 * R) * share * w, 3))

    def _cmd(self, season):
        cmd = OutlookCommand()
        cmd.native_scale = native_scale(season)
        cmd._scale_cache = {}
        cmd.rapm_gap_sigma = 1.0
        cmd.source_year = season.year
        return cmd

    def test_outlook_unknown_player_and_replacement(self):
        cmd = self._cmd(self.native)
        self.assertEqual(cmd._unknown_rating(), (-C_O, -C_D, -C_O - C_D))
        self.assertEqual(cmd._or_unknown(None, "o"), -C_O)
        self.assertEqual(cmd._or_unknown(None, "b"), -C_O - C_D)
        self.assertEqual(cmd._or_unknown(0.0, "o"), 0.0)            # 0 is a real (average) rating
        # allocator: an unrated slot (projected_bpr None) is worth the unknown rating (-2.5),
        # below replacement (-1.918), so its bpr demand is 0; on the earlier scale it was 0 + 2.0.
        slots = [{"projected_bpr": b, "mpg": 24.0, "acquisition_type": "returner", "player_name": str(i)}
                 for i, b in enumerate((3.0, 1.0, None, -1.0, 2.0, 0.5, -0.5, 1.5, 0.0, -1.5, 2.5, -2.0, 0.2, -0.2))]
        native = cmd._allocate_minutes([dict(x) for x in slots])
        legacy_cmd = OutlookCommand()
        legacy = legacy_cmd._allocate_minutes([dict(x) for x in slots])
        self.assertLess(native[2]["minutes_share"], legacy[2]["minutes_share"])

    def test_outlook_cap_compares_raw_with_box(self):
        cmd = self._cmd(self.native)
        stats = self.rows[(2026, 203999)]           # centred 8.0, raw 10.5, box 5.0 -> gap 5.5 > 1.6
        slot = {"acquisition_type": "returner", "obpr": 6.0, "dbpr": 2.0, "bpr": 8.0,
                "stats_obj": stats, "player_obj": None, "age": None, "player_name": "Star Center"}
        cmd.stdout = _Null()
        o, d, b = cmd._project_bpr(slot, 0.0, 0.0, 0.0)
        proj = 0.9 * 8.0                             # 10% shrink toward 0
        gap_raw = proj + C_O + C_D - 5.0
        self.assertAlmostEqual(b, proj - (gap_raw - 1.6))


class EarlierScaleUnchangedTests(Fixture):
    """A season without native rows: every changed path returns the pre-5.10b formula exactly."""

    def test_serializer_legacy_row_unchanged(self):
        data = NBAPlayerSeasonStatsSerializer(self.rows[(2025, 203999)]).data
        self.assertEqual(data["rating_scale"], "legacy")
        self.assertEqual(data["bpr_replacement_adjusted"], round(8.0 + 2.0, 3))
        self.assertEqual(data["obpr_replacement_adjusted"], round(6.0 + 1.0, 3))
        self.assertEqual(data["dbpr_replacement_adjusted"], round(2.0 + 1.0, 3))

    def test_injury_legacy_season_unchanged(self):
        NBAPlayerAvailability.objects.create(player=self.star, team=self.team, game_date=date(2025, 1, 5), season=self.legacy,
                                             status="out")
        res = compute_nba_injury_adjustment(self.team, self.legacy, date(2025, 1, 5))
        share = min(30.0 / 48.0, 0.85)
        self.assertEqual(res["adj_off_delta"], round(-6.0 * share, 3))
        self.assertEqual(res["adj_def_delta"], round(2.0 * share, 3))
        self.assertEqual(res["players"][0]["off_adj"], round(6.0 * share, 2))

    def test_outlook_helpers_equal_the_old_expressions(self):
        cmd = OutlookCommand()
        cmd.native_scale = native_scale(self.legacy)
        self.assertIsNone(cmd.native_scale)
        self.assertEqual(cmd._unknown_rating(), (0.0, 0.0, 0.0))
        for v in (None, 0.0, 1.5, -2.25):
            for side in "odb":
                self.assertEqual(cmd._or_unknown(v, side), v or 0.0)
        # a command never run through handle() (offline tools) is on the earlier scale too
        self.assertEqual(OutlookCommand()._or_unknown(None, "o"), 0.0)

    def test_outlook_allocator_legacy_demand_unchanged(self):
        cmd = OutlookCommand()
        cmd.native_scale = None
        slots = [{"projected_bpr": b, "mpg": m, "acquisition_type": "returner", "player_name": str(i)}
                 for i, (b, m) in enumerate(((5.0, 34.0), (1.0, 28.0), (-1.0, 20.0), (None, 15.0), (-3.0, 10.0)))]
        cmd.rookie_pin = False
        got = [s["minutes_share"] for s in cmd._allocate_minutes([dict(s) for s in slots])]
        cmd2 = OutlookCommand()          # no native_scale attribute at all: the same allocation
        cmd2.rookie_pin = False
        self.assertEqual(got, [s["minutes_share"] for s in cmd2._allocate_minutes([dict(s) for s in slots])])
        # and the demand it used is the old one: bpr + REPLACEMENT_LEVEL
        self.assertEqual(REPLACEMENT_LEVEL, 2.0)

    def test_outlook_cap_legacy_row_unchanged(self):
        cmd = OutlookCommand()
        cmd.native_scale = None
        cmd.rapm_gap_sigma = 1.0
        cmd.source_year = 2025
        cmd.stdout = _Null()
        stats = self.rows[(2025, 203999)]           # bpr 8.0, box 5.0 -> gap 0.9*8 - 5 = 2.2 > 1.6
        slot = {"acquisition_type": "returner", "obpr": 6.0, "dbpr": 2.0, "bpr": 8.0,
                "stats_obj": stats, "player_obj": None, "age": None, "player_name": "Star Center"}
        o, d, b = cmd._project_bpr(slot, 0.0, 0.0, 0.0)
        proj = 0.9 * 8.0
        self.assertAlmostEqual(b, proj - ((proj - 5.0) - 1.6))


class _Null:
    def write(self, *a, **k):
        pass
