"""
NCAA ingest when the API has nothing for a date.

Found in the first 2026-27 rehearsal: the NCAA API answers 403 for a date with no games
(Oct 31, a day before the season; later Dec 25 and other off-days). get_scoreboard retried 3 times and
then raised tenacity's RetryError, which the per-date handler (`except NCAAAPIError`) did not
catch, so one empty day aborted every later date in the daily 3-day window.

Invariants pinned here:
- get_scoreboard re-raises the real NCAAAPIError after its retries (never RetryError).
- One failing date is logged and skipped; the remaining dates are still fetched.
- Every date failing (an outage or a block) fails the run, so the scheduler reports it.
- The "too early for this season" exit still fails the run when an earlier step failed.
"""

from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ncaa.models import Season
from ncaa.utils.ncaa_api import NCAAAPIClient, NCAAAPIError


class ScoreboardRetryTests(TestCase):
    def test_reraises_the_original_error_not_tenacity_retryerror(self):
        client = NCAAAPIClient()
        with mock.patch.object(client, "_make_request", side_effect=NCAAAPIError("HTTP 403: Forbidden")) as req, \
             mock.patch("tenacity.nap.time.sleep"):
            with self.assertRaises(NCAAAPIError):
                client.get_scoreboard(date(2026, 10, 31))
        self.assertEqual(req.call_count, 3)   # still retried 3 times first

    def test_repeated_428_still_means_skip_the_date(self):
        client = NCAAAPIClient()
        with mock.patch.object(client, "_make_request", side_effect=NCAAAPIError("HTTP 428: x")), \
             mock.patch("tenacity.nap.time.sleep"):
            self.assertEqual(client.get_scoreboard(date(2026, 10, 31)), [])


class IngestDateFailureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Season.objects.create(year=2027, display_name="2026-27")

    def ingest(self, scoreboard):
        fake_client = mock.Mock()
        fake_client.get_scoreboard.side_effect = scoreboard
        out = StringIO()
        with mock.patch("ncaa.management.commands.ingest_gamelogs.NCAAAPIClient", return_value=fake_client), \
             mock.patch("ncaa.management.commands.ingest_gamelogs.Command._build_team_mappings", return_value=mock.Mock()):
            call_command("ingest_gamelogs", season=2027, start="2026-10-31", end="2026-11-02", stdout=out)
        return fake_client, out.getvalue()

    def test_one_failing_date_does_not_stop_the_later_dates(self):
        def scoreboard(day):
            if day == date(2026, 10, 31):
                raise NCAAAPIError("HTTP 403: Forbidden")
            return []

        client, out = self.ingest(scoreboard)
        self.assertEqual(
            [c.args[0] for c in client.get_scoreboard.call_args_list],
            [date(2026, 10, 31), date(2026, 11, 1), date(2026, 11, 2)],
        )
        self.assertIn("skipping date", out)

    def test_every_date_failing_fails_the_run(self):
        with self.assertRaises(CommandError) as ctx:
            self.ingest(NCAAAPIError("HTTP 403: Forbidden"))
        self.assertIn("all 3 dates", str(ctx.exception))

    def test_a_date_with_no_games_is_not_an_error(self):
        client, _ = self.ingest(lambda day: [])
        self.assertEqual(client.get_scoreboard.call_count, 3)


class EarlyExitKeepsEarlierFailuresTests(TestCase):
    def test_failed_ingest_is_not_masked_by_the_too_early_skip(self):
        def fake(name, **kwargs):
            if name == "ingest_gamelogs":
                raise CommandError("NCAA API failed for all 3 dates")

        with mock.patch("ncaa.management.commands._pipeline_base.call_command", side_effect=fake), \
             mock.patch("ncaa.management.commands.update_ncaa_teams.connection"):
            with self.assertRaises(SystemExit) as ctx:
                call_command("update_ncaa_teams", season=2027, stdout=StringIO(), stderr=StringIO())
        self.assertEqual(ctx.exception.code, 1)

    def test_too_early_with_a_healthy_ingest_still_exits_cleanly(self):
        with mock.patch("ncaa.management.commands._pipeline_base.call_command"), \
             mock.patch("ncaa.management.commands.update_ncaa_teams.connection"):
            call_command("update_ncaa_teams", season=2027, stdout=StringIO(), stderr=StringIO())   # no SystemExit


class BoxScoreFetchTests(TestCase):
    """Unplayed games have no box score; asking for one cost ~1 minute of 428 retries per game."""

    @classmethod
    def setUpTestData(cls):
        from ncaa.models import Team

        cls.season = Season.objects.create(year=2027, display_name="2026-27")
        cls.home = Team.objects.create(slug="home", name="Home")
        cls.away = Team.objects.create(slug="away", name="Away")

    def process(self, status, game_id):
        from ncaa.management.commands.ingest_gamelogs import Command

        client = mock.Mock()
        client.get_game_details.return_value = {}
        game_data = {
            "id": game_id, "status": status, "date": "11/02/2026", "neutral_site": False, "venue": None,
            "home": {"id": f"{game_id}_home", "name": "Home", "score": "70" if status == "final" else None},
            "away": {"id": f"{game_id}_away", "name": "Away", "score": "60" if status == "final" else None},
        }
        cmd = Command()
        cmd.stdout, cmd.stderr = StringIO(), StringIO()
        with mock.patch.object(Command, "_map_team", side_effect=[self.home, self.away]):
            cmd._process_game(game_data=game_data, season=self.season, api_client=client,
                              mapper=mock.Mock(), refresh=False, dry_run=False)
        return client

    def test_scheduled_games_do_not_request_a_box_score(self):
        for status in ("scheduled", "postponed", "canceled"):
            client = self.process(status, f"g-{status}")
            client.get_game_details.assert_not_called()

    def test_scheduled_game_is_still_recorded(self):
        from ncaa.models import Game

        self.process("scheduled", "g-sched")
        self.assertEqual(Game.objects.get(source_game_id="g-sched").status, "scheduled")

    def test_final_and_live_games_still_request_a_box_score(self):
        for status in ("final", "in_progress"):
            client = self.process(status, f"g-{status}")
            client.get_game_details.assert_called_once_with(f"g-{status}")
