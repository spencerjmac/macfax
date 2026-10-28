"""
update_daily gates + run_scheduler timing.

Invariants pinned here:
- NBA runs Oct 1 - Jun 30, NCAA Nov 1 - Apr 15; outside the window a league
  still runs while it has final games from the last 14 days.
- --skip-* beats --force-*; --force-* beats a closed gate.
- --dry-run runs nothing.
- One league failing (including the sys.exit its pipeline ends with) does not
  stop the other, and the command exits non-zero.
- next_run_at is strictly in the future and rolls to tomorrow when today's slot passed.
"""

from datetime import date, datetime, time, timezone
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ncaa.management.commands.run_scheduler import next_run_at, parse_at
from ncaa.management.commands.update_daily import decide
from ncaa.models import Game, Season, Team

CALL = "ncaa.management.commands.update_daily.call_command"


def run_daily(*args):
    out, err = StringIO(), StringIO()
    call_command("update_daily", *args, stdout=out, stderr=err)
    return out.getvalue()


class GateTests(TestCase):
    def test_mid_october_nba_runs_ncaa_waits(self):
        today = date(2026, 10, 27)
        self.assertEqual(decide("NBA", today, False, False)[0], True)
        self.assertEqual(decide("NCAA", today, False, False)[0], False)

    def test_ncaa_opens_nov_1(self):
        self.assertTrue(decide("NCAA", date(2026, 11, 1), False, False)[0])

    def test_summer_both_closed(self):
        today = date(2027, 8, 15)
        self.assertFalse(decide("NBA", today, False, False)[0])
        self.assertFalse(decide("NCAA", today, False, False)[0])

    def test_recent_final_game_opens_closed_gate(self):
        home = Team.objects.create(slug="h", name="H")
        away = Team.objects.create(slug="a", name="A")
        Game.objects.create(
            season_year=2027, game_date=date(2027, 4, 20), home_team=home, away_team=away,
            home_score=70, away_score=60, status="final", source="ncaa", source_game_id="late",
        )
        self.assertTrue(decide("NCAA", date(2027, 4, 25), False, False)[0])   # 5 days later
        self.assertFalse(decide("NCAA", date(2027, 6, 1), False, False)[0])   # long gone

    def test_skip_beats_force_and_force_beats_closed(self):
        today = date(2027, 8, 15)
        self.assertFalse(decide("NBA", today, True, True)[0])
        self.assertTrue(decide("NBA", today, False, True)[0])


class UpdateDailyCommandTests(TestCase):
    def test_dry_run_runs_nothing(self):
        with mock.patch(CALL) as cc:
            out = run_daily("--dry-run", "--today", "2026-10-27")
        cc.assert_not_called()
        self.assertIn("[GATE] NBA : RUN", out)
        self.assertIn("[GATE] NCAA: SKIP", out)
        self.assertIn("Season: 2027", out)

    def test_runs_only_open_leagues_with_season_in_play(self):
        with mock.patch(CALL) as cc:
            run_daily("--today", "2026-10-27")
        self.assertEqual([c.args[0] for c in cc.call_args_list], ["update_nba_all"])
        self.assertEqual(cc.call_args_list[0].kwargs["season"], 2027)

    def test_ncaa_gets_days_and_both_pipelines(self):
        with mock.patch(CALL) as cc:
            run_daily("--today", "2026-11-10", "--skip-nba", "--days", "5")
        names = [c.args[0] for c in cc.call_args_list]
        self.assertEqual(names, ["update_ncaa_teams", "update_ncaa_players"])
        self.assertEqual(cc.call_args_list[0].kwargs["days"], 5)
        self.assertEqual(cc.call_args_list[0].kwargs["season"], 2027)

    def test_nba_failure_does_not_stop_ncaa_and_exit_is_nonzero(self):
        def fake(name, **kwargs):
            if name == "update_nba_all":
                raise SystemExit(1)  # what the pipelines do when a step failed

        with mock.patch(CALL, side_effect=fake) as cc:
            with self.assertRaises(SystemExit) as ctx:
                run_daily("--today", "2026-11-10")
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(
            [c.args[0] for c in cc.call_args_list],
            ["update_nba_all", "update_ncaa_teams", "update_ncaa_players"],
        )

    def test_skip_ncaa_players(self):
        with mock.patch(CALL) as cc:
            run_daily("--today", "2026-11-10", "--skip-nba", "--skip-ncaa-players")
        self.assertEqual([c.args[0] for c in cc.call_args_list], ["update_ncaa_teams"])


class SchedulerTimingTests(TestCase):
    def test_next_run_later_today(self):
        now = datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)
        self.assertEqual(next_run_at(now, time(10, 0)), datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc))

    def test_next_run_rolls_to_tomorrow_after_the_slot(self):
        now = datetime(2026, 10, 27, 10, 0, 1, tzinfo=timezone.utc)
        self.assertEqual(next_run_at(now, time(10, 0)), datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc))

    def test_exactly_at_the_slot_waits_a_full_day(self):
        now = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(next_run_at(now, time(10, 0)), datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc))

    def test_rolls_over_month_end(self):
        now = datetime(2026, 10, 31, 23, 0, tzinfo=timezone.utc)
        self.assertEqual(next_run_at(now, time(10, 0)), datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc))

    def test_parse_at(self):
        self.assertEqual(parse_at("06:30"), time(6, 30))
        for bad in ("6", "25:00", "ab:cd", ""):
            with self.assertRaises(CommandError):
                parse_at(bad)
