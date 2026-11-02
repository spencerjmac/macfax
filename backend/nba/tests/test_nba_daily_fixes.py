"""
Fixes from the first full 2026-27 NBA run (Nov 2026).

Invariants pinned here:
- Games played counts only games the player actually played. The box score also lists
  players who sat out; counting them inflated GP and deflated per-game averages
  (Curry 24.3 PPG vs NBA.com's 29.2) and created all-zero rows for players who never played.
- Season-stat rows left from the old logic (no minutes at all) are removed.
- The ESPN injury fetch retries transient failures and only fails after every attempt.
- Leftover "Player #id" stubs are resolved by id.
- Play-in / playoff game fetches are skipped while they cannot exist (Oct-Mar of the
  season in play) but still run for past seasons and from April.
"""

from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from nba.management.commands import nba_sync_injury_report as injury
from nba.management.commands.update_nba_all import Command as UpdateNBAAll
from nba.models import NBAGame, NBAPlayer, NBAPlayerGameStats, NBAPlayerSeasonStats, NBASeason, NBATeam


class PlayerStatsGamesPlayedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = NBASeason.objects.create(year=2027, display_name="2026-27", is_current=True)
        cls.home = NBATeam.objects.create(
            nba_team_id=1, slug="h", name="H", abbreviation="HOM", city="H", conference="East", division="A")
        cls.away = NBATeam.objects.create(
            nba_team_id=2, slug="a", name="A", abbreviation="AWY", city="A", conference="West", division="B")
        cls.star = NBAPlayer.objects.create(player_id=100, name="Star")
        cls.bench = NBAPlayer.objects.create(player_id=101, name="Never Played")
        cls.games = [
            NBAGame.objects.create(
                game_id=f"g{i}", season=cls.season, date=date(2026, 10, 20 + i), home_team=cls.home,
                away_team=cls.away, home_score=100, away_score=90, season_type="regular",
                counts_toward_regular_season=True, status="Final")
            for i in range(4)
        ]

    def box(self, player, game, seconds, pts=0):
        return NBAPlayerGameStats.objects.create(
            game=game, player=player, team=self.home, seconds_played=seconds, pts=pts)

    def compute(self):
        call_command("nba_compute_player_stats", season=2027, stdout=StringIO())

    def stat(self, player):
        return NBAPlayerSeasonStats.objects.filter(player=player, season=self.season, season_type="regular").first()

    def test_sat_out_games_do_not_count_as_games_played(self):
        # played 2 of 4 games, 30 pts each; the other two are DNP rows (no minutes)
        self.box(self.star, self.games[0], 1800, 30)
        self.box(self.star, self.games[1], 1800, 30)
        self.box(self.star, self.games[2], None)
        self.box(self.star, self.games[3], None)
        self.compute()
        s = self.stat(self.star)
        self.assertEqual(s.gp, 2)
        self.assertEqual(s.pts, 30.0)          # was 15.0 when DNP games were counted
        self.assertEqual(s.mpg, 30.0)

    def test_player_who_never_played_gets_no_row(self):
        self.box(self.bench, self.games[0], None)
        self.box(self.star, self.games[0], 1200, 10)
        self.compute()
        self.assertIsNone(self.stat(self.bench))
        self.assertIsNotNone(self.stat(self.star))

    def test_stale_no_minutes_rows_from_the_old_logic_are_removed(self):
        self.box(self.star, self.games[0], 1200, 10)
        NBAPlayerSeasonStats.objects.create(player=self.bench, season=self.season, team=self.home,
                                            season_type="regular", gp=4)
        self.compute()
        self.assertIsNone(self.stat(self.bench))
        self.assertIsNotNone(self.stat(self.star))

    def test_other_seasons_and_types_are_not_touched_by_cleanup(self):
        old = NBASeason.objects.create(year=2026, display_name="2025-26")
        keep = NBAPlayerSeasonStats.objects.create(player=self.bench, season=old, team=self.home,
                                                   season_type="regular", gp=50)
        self.box(self.star, self.games[0], 1200, 10)
        self.compute()
        self.assertTrue(NBAPlayerSeasonStats.objects.filter(id=keep.id).exists())


class InjuryFetchRetryTests(SimpleTestCase):
    def test_retries_then_succeeds(self):
        calls = [TimeoutError("read timed out"), OSError("reset"), [{"team": "x"}]]

        def fake():
            r = calls.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with mock.patch.object(injury, "_fetch_espn_once", side_effect=fake), \
             mock.patch.object(injury.time, "sleep") as sleep:
            self.assertEqual(injury._fetch_espn(), [{"team": "x"}])
        self.assertEqual(sleep.call_count, 2)

    def test_raises_after_every_attempt_fails(self):
        with mock.patch.object(injury, "_fetch_espn_once", side_effect=TimeoutError("read timed out")) as once, \
             mock.patch.object(injury.time, "sleep"):
            with self.assertRaises(TimeoutError):
                injury._fetch_espn()
        self.assertEqual(once.call_count, injury.ESPN_ATTEMPTS)

    def test_first_success_does_not_sleep(self):
        with mock.patch.object(injury, "_fetch_espn_once", return_value=[]), \
             mock.patch.object(injury.time, "sleep") as sleep:
            injury._fetch_espn()
        sleep.assert_not_called()


class PlayerNameLookupTests(TestCase):
    def test_stub_names_are_resolved_by_id_and_real_names_untouched(self):
        from nba.management.commands import nba_sync_team_logs as logs

        stub = NBAPlayer.objects.create(player_id=1642923, name="Player #1642923")
        real = NBAPlayer.objects.create(player_id=2544, name="LeBron James")
        provider = mock.Mock()
        provider.get_all_players.return_value = []          # the active list knows nobody
        season = NBASeason.objects.create(year=2027, display_name="2026-27", is_current=True)
        with mock.patch.object(logs, "NBAApiProvider", return_value=provider), \
             mock.patch.object(logs, "_lookup_player_name", return_value="Otega Oweh") as lookup, \
             mock.patch.object(logs.time, "sleep"):
            logs.Command()._backfill_names(season.year, dry_run=False)
        stub.refresh_from_db(); real.refresh_from_db()
        self.assertEqual(stub.name, "Otega Oweh")
        self.assertEqual(real.name, "LeBron James")
        lookup.assert_called_once_with(1642923)


    def test_players_nba_com_does_not_know_are_marked_once_and_not_retried(self):
        from nba.management.commands import nba_sync_team_logs as logs

        ghost = NBAPlayer.objects.create(player_id=1628454, name="Player #1628454")
        provider = mock.Mock()
        provider.get_all_players.return_value = []
        with mock.patch.object(logs, "NBAApiProvider", return_value=provider), \
             mock.patch.object(logs, "_lookup_player_name", side_effect=logs.PlayerNotFound(1628454)) as lookup, \
             mock.patch.object(logs.time, "sleep"):
            logs.Command()._backfill_names(2027, dry_run=False)
            ghost.refresh_from_db()
            self.assertEqual(ghost.name, "Unknown Player #1628454")
            logs.Command()._backfill_names(2027, dry_run=False)   # next day's run: nothing left to look up
        self.assertEqual(lookup.call_count, 1)

    def test_transient_lookup_failure_leaves_the_stub_for_next_time(self):
        from nba.management.commands import nba_sync_team_logs as logs

        stub = NBAPlayer.objects.create(player_id=1642923, name="Player #1642923")
        provider = mock.Mock()
        provider.get_all_players.return_value = []
        with mock.patch.object(logs, "NBAApiProvider", return_value=provider), \
             mock.patch.object(logs, "_lookup_player_name", return_value=None), \
             mock.patch.object(logs.time, "sleep"):
            logs.Command()._backfill_names(2027, dry_run=False)
        stub.refresh_from_db()
        self.assertEqual(stub.name, "Player #1642923")


class PostseasonFetchGatingTests(SimpleTestCase):
    skip = staticmethod(UpdateNBAAll._skip_reason_postseason)

    def test_skipped_before_april_for_the_season_in_play(self):
        for d in (date(2026, 10, 27), date(2026, 12, 31), date(2027, 3, 31)):
            self.assertIsNotNone(self.skip(2027, "PlayIn", d), d)
            self.assertIsNotNone(self.skip(2027, "Playoffs", d), d)

    def test_runs_from_april_through_the_summer(self):
        for d in (date(2027, 4, 1), date(2027, 5, 20), date(2027, 6, 30), date(2027, 8, 15)):
            self.assertIsNone(self.skip(2027, "Playoffs", d), d)

    def test_past_seasons_always_run(self):
        # backfilling 2025-26 in November must still fetch its postseason
        self.assertIsNone(self.skip(2026, "Playoffs", date(2026, 11, 2)))
        self.assertIsNone(self.skip(2025, "PlayIn", date(2026, 1, 15)))
