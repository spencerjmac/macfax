"""
Neutral-site flags for NCAA-sourced games.

The NCAA scoreboard has no neutral-site field, so every 2026+ game was stored as a home game (home-court
advantage applied in ratings) unless backfill_neutral_flags was run by hand. It was not part of the daily
job, and it matched ESPN games by (home, away) in order, so it missed neutral games where NCAA and ESPN
list different home teams. Kansas-Kentucky (United Center, 2026-11-10) stayed non-neutral.

Invariants pinned here:
- backfill_neutral_flags matches a game by date and team pair in either order, and only within --start/--end.
- Re-ingesting an NCAA-sourced game (scheduled -> final) never clears a neutral flag set from ESPN.
- update_ncaa_teams runs backfill_neutral_flags after ingest, over the ingest window plus lookahead.
- When backfill_neutral_flags sets or clears a flag, the game's box rows follow: 'N' on a neutral game,
  'H' / 'A' by Game.home_team on a cleared one (sync_home_away_to_site). Before, rows stayed 'H' / 'A' on
  flagged games, so everything reading home_away gave those games home-court advantage.
"""

from datetime import date, timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from ncaa.management.commands.ingest_gamelogs import Command as Ingest
from ncaa.management.commands.update_ncaa_teams import NEUTRAL_LOOKAHEAD_DAYS
from ncaa.models import Game, Season, Team, TeamExternalId, TeamGameStats
from ncaa.utils.team_mapping import TeamMapper


def espn_event(home_id, away_id, neutral):
    """A row as ESPNAPIClient.get_scoreboard normalizes it."""
    return {"home": {"id": home_id}, "away": {"id": away_id}, "neutral_site": neutral}


class BackfillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Season.objects.create(year=2027, display_name="2026-27")
        cls.ku = Team.objects.create(name="Kansas", slug="kansas", is_d1=True)
        cls.uk = Team.objects.create(name="Kentucky", slug="kentucky", is_d1=True)
        TeamExternalId.objects.create(team=cls.ku, source="espn", external_id="2305", external_name="Kansas",
                                      confidence=1.0)
        TeamExternalId.objects.create(team=cls.uk, source="espn", external_id="96", external_name="Kentucky",
                                      confidence=1.0)

    def game(self, gid, day, home, away):
        return Game.objects.create(season_year=2027, game_date=day, home_team=home, away_team=away, status="final",
                                   home_score=69, away_score=89, source="ncaa", source_game_id=gid)

    def backfill(self, scoreboard, **kw):
        client = mock.Mock()
        client.get_scoreboard.side_effect = scoreboard
        with mock.patch("ncaa.utils.ncaa_api.ESPNAPIClient", return_value=client):
            call_command("backfill_neutral_flags", season=2027, stdout=StringIO(), **kw)
        return client

    def test_matches_the_team_pair_in_either_order(self):
        # Stored with Kansas home; ESPN lists Kentucky home (and neutral).
        g = self.game("6650631", date(2026, 11, 10), self.ku, self.uk)
        self.backfill(lambda d: [espn_event("96", "2305", True)])
        g.refresh_from_db()
        self.assertTrue(g.neutral_site)

    def _rows(self, g):
        return dict(TeamGameStats.objects.filter(game=g).values_list("team__slug", "home_away"))

    def test_box_rows_follow_the_flag(self):
        g = self.game("6650631", date(2026, 11, 10), self.ku, self.uk)
        TeamGameStats.objects.create(game=g, team=self.ku, opponent=self.uk, home_away="H", pts=69)
        TeamGameStats.objects.create(game=g, team=self.uk, opponent=self.ku, home_away="A", pts=89)
        self.backfill(lambda d: [espn_event("96", "2305", True)])
        self.assertEqual(self._rows(g), {"kansas": "N", "kentucky": "N"})
        # ESPN later says not neutral: cleared with --allow-clear, rows back to H/A by Game.home_team
        self.backfill(lambda d: [espn_event("2305", "96", False)], allow_clear=True)
        self.assertEqual(self._rows(g), {"kansas": "H", "kentucky": "A"})

    def test_only_dates_in_the_window_are_fetched(self):
        self.game("1", date(2026, 11, 3), self.ku, self.uk)
        g = self.game("2", date(2026, 11, 10), self.uk, self.ku)
        client = self.backfill(lambda d: [espn_event("96", "2305", True)], start="2026-11-09", end="2026-11-12")
        self.assertEqual([c.args[0] for c in client.get_scoreboard.call_args_list], [date(2026, 11, 10)])
        g.refresh_from_db()
        self.assertTrue(g.neutral_site)
        self.assertFalse(Game.objects.get(source_game_id="1").neutral_site)


class IngestKeepsNeutralTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(year=2027, display_name="2026-27")
        Team.objects.create(name="Kansas", slug="kansas", is_d1=True)
        Team.objects.create(name="Kentucky", slug="kentucky", is_d1=True)

    def process(self, status, hs, as_):
        data = {"id": "6650631", "date": date.today().strftime("%m/%d/%Y"), "status": status, "neutral_site": False,
                "home": {"id": "6650631_home", "name": "Kentucky", "score": hs},
                "away": {"id": "6650631_away", "name": "Kansas", "score": as_}}
        api = mock.Mock()
        api.get_game_details.return_value = {"home": {}, "away": {}}
        Ingest(stdout=StringIO())._process_game(data, self.season, api, TeamMapper(source="ncaa"),
                                               refresh=False, dry_run=False)

    def test_reprocessing_does_not_clear_espn_neutral_flag(self):
        self.process("scheduled", "", "")
        Game.objects.filter(source_game_id="6650631").update(neutral_site=True)   # set from ESPN
        self.process("final", "69", "89")
        g = Game.objects.get(source_game_id="6650631")
        self.assertEqual((g.status, g.neutral_site), ("final", True))


class PipelineStepTests(TestCase):
    def test_update_ncaa_teams_runs_backfill_over_the_ingest_window(self):
        Season.objects.create(year=2027, display_name="2026-27")
        with mock.patch("ncaa.management.commands._pipeline_base.call_command") as cc, \
             mock.patch("ncaa.management.commands.update_ncaa_teams.connection"):
            call_command("update_ncaa_teams", season=2027, days=3, stdout=StringIO(), stderr=StringIO())
        calls = {c.args[0]: c.kwargs for c in cc.call_args_list}
        names = [c.args[0] for c in cc.call_args_list]
        self.assertLess(names.index("ingest_gamelogs"), names.index("backfill_neutral_flags"))
        today = date.today()
        self.assertEqual(calls["backfill_neutral_flags"], {
            "season": 2027,
            "start": (today - timedelta(days=2)).isoformat(),
            "end": (today + timedelta(days=NEUTRAL_LOOKAHEAD_DAYS)).isoformat(),
        })
