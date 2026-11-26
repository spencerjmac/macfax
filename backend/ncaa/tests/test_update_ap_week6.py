"""
update_ap_week6 (daily pipeline step): fetch AP Week 6 until it exists, then locked.

- Unlocked, no Week 6 column yet: warns, writes nothing, exits 0.
- First write: 25 matched -> ranks on every rating row of the season (live and snapshot);
  unmatched names are logged.
- Locked re-run: no request; snapshot rows created later get the stored ranks.
- A match count outside 25-26 writes nothing (a wrong first write would lock the season).
"""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ncaa.management.commands.backfill_ap_polls import parse_week6
from ncaa.models import Season, Team, TeamSeasonRatings

NAMES = ["Duke", "Kansas", "Kentucky", "Houston", "Auburn", "Alabama", "Tennessee", "Purdue", "Arizona",
         "Gonzaga", "Baylor", "Marquette", "Creighton", "Illinois", "Wisconsin", "Texas", "Florida",
         "Michigan", "Oregon", "Clemson", "Memphis", "Louisville", "Arkansas", "Indiana", "Missouri"]

GET = "ncaa.management.commands.backfill_ap_polls.requests.get"


def _page(weeks, schools):
    """In-season Sports-Reference layout: a current-poll table, then the week grid."""
    head = "".join(f"<th>{w}</th>" for w in weeks)
    rows = "".join(
        f"<tr><td>{name}</td><td>X</td>" + "".join(f"<td>{rank}</td>" for _ in weeks) + "</tr>"
        for rank, name in schools
    )
    return f"""<table id="current-poll"><thead><tr><th>Rk</th><th>School</th></tr></thead>
<tbody><tr><td>1</td><td>Duke</td></tr></tbody></table>
<table id="ap-polls"><thead>
<tr><th></th><th></th><th colspan="{len(weeks)}">Week Poll</th></tr>
<tr><th>School</th><th>Conf</th>{head}</tr></thead><tbody>{rows}</tbody></table>"""


def _resp(html):
    return mock.Mock(text=html, raise_for_status=mock.Mock())


class UpdateApWeek6Tests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2027, display_name="2026-27", is_current=True)
        self.teams = {n: Team.objects.create(slug=n.lower(), name=n, is_d1=True) for n in NAMES}
        for t in self.teams.values():
            TeamSeasonRatings.all_objects.create(team=t, season=self.season, is_pre_tournament=False)
        self.week6 = [(i + 1, n) for i, n in enumerate(NAMES)] + [(26, "Nowhere Tech")]

    def _run(self):
        out = StringIO()
        call_command("update_ap_week6", season=2027, stdout=out, stderr=StringIO())
        return out.getvalue()

    def _ranks(self, pre=False):
        return dict(TeamSeasonRatings.all_objects.filter(season=self.season, is_pre_tournament=pre)
                    .values_list("team__name", "ap_poll_week6"))

    def test_unlocked_without_week6_column_warns_and_writes_nothing(self):
        with mock.patch(GET, return_value=_resp(_page(["1", "2", "3", "4"], self.week6))) as get:
            out = self._run()
        get.assert_called_once()
        self.assertIn("/cbb/seasons/men/2027-polls.html", get.call_args.args[0])
        self.assertIn("AP Week 6 not out yet for 2027", out)
        self.assertTrue(all(v is None for v in self._ranks().values()))

    def test_first_write_sets_ranks_and_logs_unmatched(self):
        with mock.patch(GET, return_value=_resp(_page(["4", "5", "6"], self.week6))):
            out = self._run()
        self.assertEqual(self._ranks(), {n: i + 1 for i, n in enumerate(NAMES)})
        self.assertIn("AP Week 6 unmatched: #26 Nowhere Tech", out)
        self.assertIn("AP Week 6 written for 2027: 25 ranked", out)
        # every written team and rank is logged, in rank order
        lines = [l.strip() for l in out.splitlines() if l.strip().startswith("AP Week 6 2027: #")]
        self.assertEqual(lines, [f"AP Week 6 2027: #{i + 1:2d} {n}" for i, n in enumerate(NAMES)])

    def test_locked_rerun_makes_no_request_and_fills_snapshot_rows(self):
        with mock.patch(GET, return_value=_resp(_page(["6"], self.week6))):
            self._run()
        # Selection Sunday snapshot created afterwards, without ranks (as compute_adjusted_ratings does)
        for t in self.teams.values():
            TeamSeasonRatings.all_objects.create(team=t, season=self.season, is_pre_tournament=True)
        with mock.patch(GET, side_effect=AssertionError("no request when locked")) as get:
            out = self._run()
        get.assert_not_called()
        self.assertIn("AP Week 6 locked (25 ranked); filled 25 rating rows", out)
        self.assertEqual(self._ranks(pre=True), self._ranks(pre=False))
        # and a second locked run has nothing left to fill
        with mock.patch(GET, side_effect=AssertionError("no request when locked")):
            self.assertEqual(self._run().strip(), "AP Week 6 locked (25 ranked)")

    def test_match_count_outside_25_26_writes_nothing(self):
        short = self.week6[:10]
        with mock.patch(GET, return_value=_resp(_page(["6"], short))):
            with self.assertRaisesMessage(CommandError, "matched 10 teams (expected 25-26); nothing written"):
                self._run()
        self.assertTrue(all(v is None for v in self._ranks().values()))


class ParseWeek6Tests(TestCase):
    def test_picks_the_week_grid_not_the_current_poll_table(self):
        page = _page(["5", "6"], [(1, "Duke"), (2, "Kansas")])
        self.assertEqual(parse_week6(page), [(1, "Duke"), (2, "Kansas")])

    def test_no_week6_column_is_none(self):
        self.assertIsNone(parse_week6(_page(["1", "2"], [(1, "Duke")])))
