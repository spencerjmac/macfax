"""
sync_team_season_membership: the live season always gets TeamSeasonMembership rows (Task 6f.1).

Invariants pinned here:
- A season with no ESPN group-50 rows gets one D1 row per listed team, mapped by ESPN id only.
- Unmapped ESPN ids are reported, never matched by name.
- Teams with games that season but not in the list get is_d1=False rows (is_reclassifying NULL).
- Existing rows are never changed; a season that already has group-50 rows makes no request.
- is_reclassifying: a team whose first D1 season is within the last 3 seasons is flagged (assumed window).
"""

from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from ncaa.models import Game, Season, Team, TeamExternalId, TeamSeasonMembership

FETCH = "ncaa.management.commands.sync_team_season_membership.fetch_group50_ids"


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

    def run_sync(self, year, ids):
        out = StringIO()
        with mock.patch(FETCH, return_value=ids) as fetch:
            call_command("sync_team_season_membership", season=year, stdout=out)
        return fetch, out.getvalue()

    def test_new_season_gets_d1_and_non_d1_rows(self):
        fetch, out = self.run_sync(2027, ["1", "2", "999"])
        fetch.assert_called_once_with(2027)
        rows = {m.team_id: m for m in TeamSeasonMembership.objects.filter(season=self.s27)}
        self.assertEqual(set(rows), {self.old.id, self.newp.id, self.nond1.id})
        self.assertTrue(rows[self.old.id].is_d1)
        self.assertFalse(rows[self.old.id].is_reclassifying)
        self.assertTrue(rows[self.newp.id].is_reclassifying)          # first D1 season is this one
        self.assertFalse(rows[self.nond1.id].is_d1)
        self.assertIsNone(rows[self.nond1.id].is_reclassifying)
        self.assertIn("999", out)                                    # unmapped id reported

    def test_existing_rows_untouched_and_no_fetch(self):
        TeamSeasonMembership.objects.create(season=self.s27, team=self.old, is_d1=False, is_reclassifying=None,
                                            source="manual", note="ruling")
        TeamSeasonMembership.objects.create(season=self.s27, team=self.newp, is_d1=True, is_reclassifying=True,
                                            source="espn_group50")
        fetch, _ = self.run_sync(2027, ["1", "2"])
        fetch.assert_not_called()
        kept = TeamSeasonMembership.objects.get(season=self.s27, team=self.old)
        self.assertEqual((kept.is_d1, kept.source, kept.note), (False, "manual", "ruling"))
        self.assertTrue(TeamSeasonMembership.objects.filter(season=self.s27, team=self.nond1, is_d1=False).exists())

    def test_one_row_per_season_team(self):
        self.run_sync(2027, ["1", "2"])
        self.run_sync(2027, ["1", "2"])
        self.assertEqual(TeamSeasonMembership.objects.filter(season=self.s27).count(), 3)
