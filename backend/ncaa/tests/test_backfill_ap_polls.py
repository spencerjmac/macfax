"""
backfill_ap_polls: Sports-Reference poll names the NCAA-name mapper can't resolve.

- Pitt, NC State, UMass and Florida Atlantic resolve through SR_TEAM_ALIASES (exact Team.name), including with
  Sports-Reference's postseason tag ('Pitt NCAA') and before the ' State' -> ' St.' rewrite.
- Other names still go through the mapper.
- A command run on a Sports-Reference-shaped page writes week-6 ranks for the alias teams (pre and post rows).
"""

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from ncaa.management.commands.backfill_ap_polls import SR_TEAM_ALIASES, resolve_sr_team
from ncaa.models import Season, Team, TeamSeasonRatings

PAGE = """<table>
<thead>
<tr><th></th><th colspan="2">Week Poll</th></tr>
<tr><th>School</th><th>5</th><th>6</th></tr>
</thead>
<tbody>
<tr><td>Pitt NCAA</td><td>9</td><td>10</td></tr>
<tr><td>NC State NCAA</td><td>13</td><td>12</td></tr>
<tr><td>UMass</td><td>20</td><td>22</td></tr>
<tr><td>Florida Atlantic NIT</td><td>16</td><td>15</td></tr>
<tr><td>Nowhere Tech</td><td>25</td><td>25</td></tr>
</tbody>
</table>"""


class ResolveSrTeamTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teams = {name: Team.objects.create(slug=name.lower().replace(" ", "-"), name=name)
                     for name in ("Pittsburgh", "NC State", "Massachusetts", "Florida Atlantic")}

    def test_every_alias_names_an_existing_team(self):
        self.assertEqual(set(SR_TEAM_ALIASES.values()), set(self.teams))

    def test_aliases_resolve_without_the_mapper(self):
        mapper = mock.Mock()
        for raw, name in (("Pitt", "Pittsburgh"), ("Pitt\xa0NCAA", "Pittsburgh"), ("NC State NCAA", "NC State"),
                          ("UMass", "Massachusetts"), ("Florida Atlantic", "Florida Atlantic")):
            team, _ = resolve_sr_team(raw, mapper)
            self.assertEqual(team, self.teams[name], raw)
        mapper.find_team.assert_not_called()

    def test_other_names_go_through_the_mapper(self):
        mapper = mock.Mock()
        mapper.find_team.return_value = (None, 0.0, False)
        self.assertEqual(resolve_sr_team("Kansas State", mapper), (None, "Kansas St."))
        mapper.find_team.assert_called_once_with("Kansas St.", min_confidence=0.88)


class BackfillCommandTests(TestCase):
    def test_alias_teams_get_week6_ranks(self):
        season = Season.objects.create(year=2005, display_name="2004-05")
        want = {"Pittsburgh": 10, "NC State": 12, "Massachusetts": 22, "Florida Atlantic": 15}
        for name in want:
            team = Team.objects.create(slug=name.lower().replace(" ", "-"), name=name)
            for pre in (True, False):
                TeamSeasonRatings.objects.create(team=team, season=season, is_pre_tournament=pre)
        resp = mock.Mock(text=PAGE, raise_for_status=mock.Mock())
        with mock.patch("ncaa.management.commands.backfill_ap_polls.requests.get", return_value=resp), \
                mock.patch("ncaa.management.commands.backfill_ap_polls.time.sleep"):
            call_command("backfill_ap_polls", season=2005, stdout=StringIO(), stderr=StringIO())
        got = {}
        for r in TeamSeasonRatings.all_objects.filter(season=season).select_related("team"):
            got.setdefault(r.team.name, set()).add(r.ap_poll_week6)
        self.assertEqual(got, {name: {rank} for name, rank in want.items()})
