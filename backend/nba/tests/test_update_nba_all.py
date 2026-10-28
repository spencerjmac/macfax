"""
update_nba_all skips steps whose prerequisites don't exist yet.

Invariants pinned here (found running the 2026-27 pipeline in October: three
steps failed for expected reasons and made the daily run exit 1 every day):
- Playoff steps run only once the season has playoff games.
- Box BPR runs only with >= 20 players carrying RAPM targets.
- Final BPR runs only when the season's LEBRON CSV exists.
- A skipped step is recorded with its reason and does not fail the run.
- A step that DOES run and fails still fails the run (exit 1).
"""

from datetime import date
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from nba.models import NBAGame, NBAPlayer, NBAPlayerSeasonStats, NBASeason, NBATeam

CALL = "nba.management.commands.update_nba_all.call_command"
LEBRON = "nba.management.commands.update_nba_all.lebron_csv_path"


def run(*args):
    out = StringIO()
    call_command("update_nba_all", "--season", "2027", "--skip-ingest", *args, stdout=out, stderr=StringIO())
    return out.getvalue()


def names(cc):
    """Sub-commands invoked, with their season_type if any."""
    return [(c.args[0], c.kwargs.get("season_type")) for c in cc.call_args_list]


class UpdateNBAAllSkipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = NBASeason.objects.create(year=2027, display_name="2026-27")
        cls.home = NBATeam.objects.create(
            nba_team_id=1, slug="h", name="H", abbreviation="HOM", city="H", conference="East", division="A"
        )
        cls.away = NBATeam.objects.create(
            nba_team_id=2, slug="a", name="A", abbreviation="AWY", city="A", conference="West", division="B"
        )

    def add_playoff_game(self):
        NBAGame.objects.create(
            game_id="po1", season=self.season, date=date(2027, 4, 20), home_team=self.home, away_team=self.away,
            home_score=100, away_score=90, season_type="playoffs", counts_toward_regular_season=False, status="Final",
        )

    def add_rapm_players(self, n):
        for i in range(n):
            p = NBAPlayer.objects.create(player_id=1000 + i, name=f"P{i}")
            NBAPlayerSeasonStats.objects.create(
                player=p, team=self.home, season=self.season, gp=10, baseline_obpr=0.1, baseline_dbpr=0.1,
            )

    def test_regular_season_skips_playoffs_and_bpr_without_failing(self):
        with mock.patch(CALL) as cc, mock.patch(LEBRON, return_value=Path("/nope/lebron-data-2027.csv")):
            out = run()
        called = names(cc)
        self.assertNotIn(("nba_compute_ratings", "playoffs"), called)
        self.assertNotIn(("nba_compute_player_stats", "playoffs"), called)
        self.assertNotIn(("nba_compute_box_bpr", None), called)
        self.assertNotIn(("nba_compute_final_bpr", None), called)
        self.assertIn(("nba_compute_ratings", "regular"), called)       # real work still runs
        self.assertIn("no playoff games for 2027 yet", out)
        self.assertIn("no RAPM targets for 2027", out)
        self.assertIn("missing LEBRON prior lebron-data-2027.csv", out)
        self.assertIn("ALL STEPS SUCCESSFUL", out)

    def test_playoff_steps_run_once_playoff_games_exist(self):
        self.add_playoff_game()
        with mock.patch(CALL) as cc:
            run()
        called = names(cc)
        self.assertIn(("nba_compute_ratings", "playoffs"), called)
        self.assertIn(("nba_compute_player_stats", "playoffs"), called)

    def test_box_bpr_needs_twenty_rapm_players(self):
        self.add_rapm_players(19)
        with mock.patch(CALL) as cc:
            run()
        self.assertNotIn(("nba_compute_box_bpr", None), names(cc))
        self.add_rapm_players(0)
        NBAPlayerSeasonStats.objects.create(
            player=NBAPlayer.objects.create(player_id=5000, name="Extra"),
            team=self.home, season=self.season, gp=10, baseline_obpr=0.2, baseline_dbpr=0.2,
        )
        with mock.patch(CALL) as cc:
            run()
        self.assertIn(("nba_compute_box_bpr", None), names(cc))

    def test_final_bpr_runs_when_lebron_file_exists(self):
        with mock.patch(CALL) as cc, mock.patch(LEBRON, return_value=Path(__file__)):  # any existing file
            run()
        self.assertIn(("nba_compute_final_bpr", None), names(cc))

    def test_a_step_that_runs_and_fails_still_fails_the_run(self):
        def fake(name, **kwargs):
            if name == "nba_compute_ratings" and kwargs.get("season_type") == "regular":
                raise RuntimeError("boom")

        with mock.patch(CALL, side_effect=fake):
            with self.assertRaises(SystemExit) as ctx:
                run()
        self.assertEqual(ctx.exception.code, 1)
