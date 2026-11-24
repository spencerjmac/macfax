"""
sync_team_season_membership: the live season always gets TeamSeasonMembership rows (Task 6f.1).

Invariants pinned here:
- A season with no ESPN group-50 rows gets one D1 row per listed team, mapped by ESPN id only.
- An unmapped listed ESPN id stops the run with nothing written (never matched by name), except ids
  in LISTED_NOT_D1 (programs ESPN still lists after leaving D1).
- Teams with games that season but not in the list get is_d1=False rows (is_reclassifying NULL).
- The season in play re-fetches every run; a derived_games non-D1 row of a listed team is upgraded to D1.
- Reviewed rows (manual etc.) are never changed; a past season that already has rows makes no request.
- is_reclassifying: a team whose first D1 season is within the last 3 seasons is flagged (assumed window).
"""

from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ncaa.models import Game, Season, Team, TeamExternalId, TeamSeasonMembership

FETCH = "ncaa.management.commands.sync_team_season_membership.fetch_group50_ids"
IN_PLAY = "ncaa.seasons.season_in_play"


class MembershipSyncTests(TestCase):
    def setUp(self):
        self.s26 = Season.objects.create(year=2026, display_name="2025-26", is_current=False)
        self.s27 = Season.objects.create(year=2027, display_name="2026-27", is_current=False)
        self.old = Team.objects.create(name="Old U", slug="old-u", is_d1=True)
        self.newp = Team.objects.create(name="New U", slug="new-u", is_d1=True)
        self.nond1 = Team.objects.create(name="Small College", slug="small-college", is_d1=False)
        TeamExternalId.objects.create(team=self.old, source="espn", external_id="1", external_name="Old U", confidence=1.0)
        TeamExternalId.objects.create(team=self.newp, source="espn", external_id="2", external_name="New U", confidence=1.0)
        TeamSeasonMembership.objects.create(season=self.s26, team=self.old, is_d1=True, is_reclassifying=False,
                                            source="espn_group50")
        for y in (2010, 2015, 2020):   # Old U has a long D1 history
            s = Season.objects.create(year=y, display_name=str(y), is_current=False)
            TeamSeasonMembership.objects.create(season=s, team=self.old, is_d1=True, is_reclassifying=False, source="espn_group50")
        Game.objects.create(season_year=2027, game_date=date(2026, 11, 10), home_team=self.old, away_team=self.nond1,
                            status="final", home_score=90, away_score=50, source="espn", source_game_id="t1")

    def run_sync(self, year, ids, in_play=2027):
        out = StringIO()
        fetch_kw = {"side_effect": ids} if isinstance(ids, Exception) else {"return_value": ids}
        with mock.patch(FETCH, **fetch_kw) as fetch, mock.patch(IN_PLAY, return_value=in_play):
            call_command("sync_team_season_membership", season=year, stdout=out)
        return fetch, out.getvalue()

    def test_new_season_gets_d1_and_non_d1_rows(self):
        fetch, out = self.run_sync(2027, ["1", "2"])
        fetch.assert_called_once_with(2027)
        rows = {m.team_id: m for m in TeamSeasonMembership.objects.filter(season=self.s27)}
        self.assertEqual(set(rows), {self.old.id, self.newp.id, self.nond1.id})
        self.assertTrue(rows[self.old.id].is_d1)
        self.assertFalse(rows[self.old.id].is_reclassifying)
        self.assertTrue(rows[self.newp.id].is_reclassifying)          # first D1 season is this one
        self.assertFalse(rows[self.nond1.id].is_d1)
        self.assertIsNone(rows[self.nond1.id].is_reclassifying)

    def test_unmapped_listed_id_stops_with_nothing_written(self):
        # Boston College on prod 2027: listed by ESPN, no mapping -> was marked non-D1 from its games
        with self.assertRaises(CommandError) as ctx:
            self.run_sync(2027, ["1", "2", "999"])
        self.assertIn("999", str(ctx.exception))
        self.assertFalse(TeamSeasonMembership.objects.filter(season=self.s27).exists())

    def test_listed_not_d1_ids_are_ignored(self):
        # ESPN group 50 still lists Hartford (42) after it left D1; no team has that id here
        fetch, _ = self.run_sync(2027, ["1", "2", "42"])
        self.assertEqual(TeamSeasonMembership.objects.filter(season=self.s27, is_d1=True).count(), 2)

    def test_season_in_play_upgrades_derived_row_once_listed(self):
        # First run: ESPN omits New U, which has games -> derived non-D1 row
        Game.objects.create(season_year=2027, game_date=date(2026, 11, 12), home_team=self.newp, away_team=self.old,
                            status="final", home_score=70, away_score=60, source="espn", source_game_id="t2")
        self.run_sync(2027, ["1"])
        row = TeamSeasonMembership.objects.get(season=self.s27, team=self.newp)
        self.assertEqual((row.is_d1, row.source), (False, "derived_games"))
        # Next nightly run: ESPN lists New U (now mapped) -> upgraded, not left non-D1
        fetch, out = self.run_sync(2027, ["1", "2"])
        fetch.assert_called_once_with(2027)
        row.refresh_from_db()
        self.assertEqual((row.is_d1, row.source), (True, "espn_group50"))
        self.assertTrue(row.is_reclassifying)
        self.assertIn("upgraded from derived_games", row.note)
        self.assertIn("New U", out)

    def test_reviewed_rows_untouched(self):
        TeamSeasonMembership.objects.create(season=self.s27, team=self.old, is_d1=False, is_reclassifying=None,
                                            source="manual", note="ruling")
        TeamSeasonMembership.objects.create(season=self.s27, team=self.newp, is_d1=True, is_reclassifying=True,
                                            source="espn_group50")
        fetch, _ = self.run_sync(2027, ["1", "2"])
        fetch.assert_called_once_with(2027)                          # season in play re-checks
        kept = TeamSeasonMembership.objects.get(season=self.s27, team=self.old)
        self.assertEqual((kept.is_d1, kept.source, kept.note), (False, "manual", "ruling"))
        self.assertTrue(TeamSeasonMembership.objects.filter(season=self.s27, team=self.nond1, is_d1=False).exists())

    def test_past_season_with_rows_makes_no_request(self):
        TeamSeasonMembership.objects.create(season=self.s27, team=self.newp, is_d1=True, is_reclassifying=True,
                                            source="espn_group50")
        fetch, _ = self.run_sync(2027, ["1", "2"], in_play=2028)
        fetch.assert_not_called()

    def test_in_play_fetch_failure_still_adds_derived_rows(self):
        TeamSeasonMembership.objects.create(season=self.s27, team=self.old, is_d1=True, is_reclassifying=False,
                                            source="espn_group50")
        fetch, out = self.run_sync(2027, OSError("ESPN down"))
        self.assertIn("fetch failed", out)
        self.assertTrue(TeamSeasonMembership.objects.filter(season=self.s27, team=self.nond1, is_d1=False).exists())

    def test_first_run_fetch_failure_raises(self):
        with self.assertRaises(OSError):
            self.run_sync(2027, OSError("ESPN down"))

    def test_one_row_per_season_team(self):
        self.run_sync(2027, ["1", "2"])
        self.run_sync(2027, ["1", "2"])
        self.assertEqual(TeamSeasonMembership.objects.filter(season=self.s27).count(), 3)
