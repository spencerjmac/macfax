"""
March automation: Selection Sunday, the pre-tournament snapshot, tournament seeds.

Invariants pinned here:
- selection_sunday_for reproduces the real Selection Sunday of every recent season
  (2027 = Sunday, March 14), so a new season needs no manual date.
- Every season row the pipeline creates or touches gets its Selection Sunday set, and an
  existing (possibly hand-edited) date is never overwritten.
- Before Selection Sunday the March steps do nothing. After it: the six-command
  pre-tournament snapshot runs once (skipped when complete), seeds refresh every run,
  and a failing command never fails the run.
"""

from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from ncaa.management.commands import _pipeline_base as base
from ncaa.models import Season, Team, TeamSeasonRatings
from ncaa.seasons import selection_sunday_for

BASE_CALL = "ncaa.management.commands._pipeline_base.call_command"

# Real dates (the Sunday the field is announced). 2020 had no tournament.
REAL_SELECTION_SUNDAYS = {
    2019: date(2019, 3, 17), 2021: date(2021, 3, 14), 2022: date(2022, 3, 13), 2023: date(2023, 3, 12),
    2024: date(2024, 3, 17), 2025: date(2025, 3, 16), 2026: date(2026, 3, 15),
}


class SelectionSundayRuleTests(SimpleTestCase):
    def test_matches_real_dates(self):
        for year, expected in REAL_SELECTION_SUNDAYS.items():
            self.assertEqual(selection_sunday_for(year), expected, year)

    def test_upcoming_seasons(self):
        self.assertEqual(selection_sunday_for(2027), date(2027, 3, 14))
        self.assertEqual(selection_sunday_for(2028), date(2028, 3, 12))

    def test_always_a_sunday(self):
        for year in range(2005, 2041):
            self.assertEqual(selection_sunday_for(year).weekday(), 6, year)


class EnsureSeasonTests(TestCase):
    def ensure(self, year):
        cmd = base.BasePipelineCommand()
        cmd.stdout, cmd.stderr = StringIO(), StringIO()
        return cmd._ensure_season(year)

    def test_new_season_gets_selection_sunday(self):
        self.assertEqual(self.ensure(2027).selection_sunday_date, date(2027, 3, 14))

    def test_existing_season_without_one_gets_it(self):
        Season.objects.create(year=2027, display_name="2026-27")
        self.assertEqual(self.ensure(2027).selection_sunday_date, date(2027, 3, 14))

    def test_a_hand_edited_date_is_kept(self):
        Season.objects.create(year=2027, display_name="2026-27", selection_sunday_date=date(2027, 3, 15))
        self.assertEqual(self.ensure(2027).selection_sunday_date, date(2027, 3, 15))


class TournamentStepsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(year=2027, display_name="2026-27", selection_sunday_date=date(2027, 3, 14))
        cls.team = Team.objects.create(slug="t", name="T")

    def run_steps(self, today, side_effect=None):
        cmd = base.BasePipelineCommand()
        cmd.stdout, cmd.stderr = StringIO(), StringIO()
        steps = []
        with mock.patch(BASE_CALL, side_effect=side_effect) as cc:
            cmd._run_tournament_steps(2027, steps, today=today)
        return [(c.args[0], c.kwargs) for c in cc.call_args_list], steps

    def add_snapshot(self, n=2):
        for i in range(n):
            team = Team.objects.create(slug=f"s{i}", name=f"S{i}")
            TeamSeasonRatings.objects.create(team=team, season=self.season, is_pre_tournament=True, wab=1.0)

    def test_nothing_before_or_on_selection_sunday(self):
        for day in (date(2027, 1, 15), date(2027, 3, 13), date(2027, 3, 14)):
            called, steps = self.run_steps(day)
            self.assertEqual(called, [], day)
            self.assertIn("before Selection Sunday", steps[0][2])

    def test_day_after_runs_the_snapshot_then_seeds(self):
        called, steps = self.run_steps(date(2027, 3, 15))
        self.assertEqual(
            [name for name, _ in called],
            ["compute_team_metrics", "compute_adjusted_ratings", "compute_adjusted_four_factors",
             "compute_four_factor_index", "compute_sos", "compute_wab", "backfill_tournament"],
        )
        for name, kwargs in called[:6]:
            self.assertEqual(kwargs, {"season": 2027, "pre_tournament": True}, name)
        self.assertEqual(called[6][1], {"season": 2027})

    def test_complete_snapshot_is_not_rebuilt_but_seeds_still_refresh(self):
        self.add_snapshot(2)
        with mock.patch.object(base, "MIN_SNAPSHOT_TEAMS", 2):
            called, steps = self.run_steps(date(2027, 3, 20))
        self.assertEqual([name for name, _ in called], ["backfill_tournament"])
        self.assertTrue(any("already complete" in (s[2] or "") for s in steps))

    def test_incomplete_snapshot_is_rebuilt(self):
        self.add_snapshot(1)
        with mock.patch.object(base, "MIN_SNAPSHOT_TEAMS", 2):
            called, _ = self.run_steps(date(2027, 3, 20))
        self.assertEqual(len(called), 7)

    def test_a_failing_command_does_not_stop_the_rest_or_raise(self):
        def fake(name, **kwargs):
            if name == "compute_sos":
                raise RuntimeError("boom")

        called, steps = self.run_steps(date(2027, 3, 16), side_effect=fake)
        self.assertEqual(len(called), 7)                       # kept going after the failure
        self.assertEqual([s for s in steps if not s[1]][0][0], "Pre-tournament: compute_sos")

    def test_runs_through_the_tournament_and_into_april(self):
        for day in (date(2027, 3, 25), date(2027, 4, 5), date(2027, 4, 12)):
            called, _ = self.run_steps(day)
            self.assertEqual(called[-1][0], "backfill_tournament", day)


class TournamentTeamMatchingTests(TestCase):
    """The six teams that never matched (and left 6 of 68 tournament teams unseeded every year)."""

    def resolve(self, as_written, cleaned=None, mapper_result=None):
        from ncaa.management.commands.backfill_tournament import Command

        mapper = mock.Mock()
        mapper.find_team.return_value = (mapper_result, 0.0 if mapper_result is None else 1.0, False)
        return Command._resolve_team(mapper, as_written, cleaned or as_written), mapper

    def test_canonical_names_match_exactly(self):
        for name in ("St. John's", "NC State", "South Florida", "Northern Iowa", "Queens", "Prairie View A&M"):
            team = Team.objects.create(slug=name.lower().replace(" ", "-").replace(".", "").replace("'", ""), name=name)
            resolved, mapper = self.resolve(name, name.replace(" State", " St."))   # the old rewrite: "NC State" -> "NC St."
            self.assertEqual(resolved, team, name)
            mapper.find_team.assert_not_called()

    def test_falls_back_to_the_ncaa_style_mapper(self):
        michigan = Team.objects.create(slug="michigan-st", name="Michigan St.")
        resolved, mapper = self.resolve("Michigan State", "Michigan St.", mapper_result=michigan)
        self.assertEqual(resolved, michigan)

    def test_non_d1_team_with_the_same_name_is_ignored(self):
        Team.objects.create(slug="queens-ny", name="Queens", is_d1=False)
        resolved, _ = self.resolve("Queens")
        self.assertIsNone(resolved)

    def test_unknown_school_returns_none(self):
        resolved, _ = self.resolve("Nowhere State", "Nowhere St.")
        self.assertIsNone(resolved)
