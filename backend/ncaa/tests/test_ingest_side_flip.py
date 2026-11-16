"""
NCAA games stored with each team on the other's side, and finals frozen at a wrong score.

Found 2026-11-16 (2027 season):
- Kansas 89, Kentucky 69 (2026-11-10, NCAA 6650631) was stored as Kansas 69, Kentucky 89. The NCAA client gives
  teams per-game ids ("6650631_home"). The scheduled listing had Kansas home; the final listing had Kentucky home.
  _map_team trusted the id cached from the first run, so Kansas got the home side and the home score.
  Same bug: Saint Joseph's-South Florida, LMU-South Alabama, and Bethune-Cookman's opponent (Paine -> Stillman).
- Northwestern St. @ Little Rock (2026-11-14) was stored final 70-70: the scoreboard said final at the end of
  regulation, and the smart skip never fetched the final again (83-84 after OT).
- Stints: the plays' homeScore/awayScore are ESPN's home and away; reading them by our home team swapped every
  stint's points on NCAA-sourced games where ESPN's home is our away team (2026: 86 games).

Invariants pinned here:
- NCAA-sourced teams are mapped by name every time; the final listing decides the sides.
- A recent final (RECHECK_FINAL_DAYS) is skipped only while the scoreboard still agrees with it (teams and
  score); otherwise re-processed. Older finals are skipped as before.
- A tied non-0-0 "final" is stored in progress, so the next run fetches it again.
- Stints read homeScore/awayScore the way the plays run (scoring plays decide; ESPN's header can disagree).
- check_ncaa_integrity reports flipped games, tied finals and swapped stints.
"""

from datetime import date, timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from ncaa.management.commands.ingest_gamelogs import Command as Ingest
from ncaa.management.commands.sync_ncaa_pbp import espn_sides, plays_orientation
from ncaa.models import Game, Season, Team, TeamGameStats
from ncaa.utils.ncaa_api import ESPNAPIClient
from ncaa.utils.team_mapping import TeamMapper


def row(gid, home, hs, away, as_, status="final", day=None):
    """A get_scoreboard row as NCAAAPIClient normalizes it (game date: today unless given)."""
    return {
        "id": gid, "date": (day or date.today()).strftime("%m/%d/%Y"), "status": status, "neutral_site": False,
        "home": {"id": f"{gid}_home", "name": home, "score": hs},
        "away": {"id": f"{gid}_away", "name": away, "score": as_},
    }


def box(pts):
    return {"stats": {"points": pts, "fieldGoalsAttempted": 60, "offensiveRebounds": 10, "turnovers": 12,
                      "freeThrowsAttempted": 20}}


class IngestSideTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(year=2027, display_name="2026-27")
        for name in ("Kansas", "Kentucky", "Little Rock", "Northwestern St."):
            Team.objects.create(name=name, slug=name.lower().replace(" ", "-").replace(".", ""), is_d1=True)

    def process(self, data, details=None):
        api = mock.Mock()
        api.get_game_details.return_value = details or {"home": {}, "away": {}}
        cmd = Ingest(stdout=StringIO())
        cmd._process_game(data, self.season, api, TeamMapper(source="ncaa"), refresh=False, dry_run=False)
        return api

    def test_final_listing_decides_the_sides_after_a_home_away_swap(self):
        self.process(row("6650631", "Kansas", "", "Kentucky", "", status="scheduled"))
        g = Game.objects.get(source_game_id="6650631")
        self.assertEqual(g.home_team.name, "Kansas")

        # The final listing has Kentucky home; ids "6650631_home"/"_away" now name the other teams.
        self.process(row("6650631", "Kentucky", "69", "Kansas", "89"),
                     details={"home": box(69), "away": box(89)})
        g.refresh_from_db()
        self.assertEqual((g.home_team.name, g.home_score), ("Kentucky", 69))
        self.assertEqual((g.away_team.name, g.away_score), ("Kansas", 89))
        self.assertEqual(g.winner.name, "Kansas")
        pts = dict(TeamGameStats.objects.filter(game=g).values_list("team__name", "pts"))
        self.assertEqual(pts, {"Kansas": 89, "Kentucky": 69})

    def test_a_stored_final_with_swapped_sides_is_reprocessed(self):
        # As stored before the fix: Kansas home with the home score.
        self.process(row("6650631", "Kansas", "69", "Kentucky", "89"))
        api = self.process(row("6650631", "Kentucky", "69", "Kansas", "89"))
        api.get_game_details.assert_called_once()
        g = Game.objects.get(source_game_id="6650631")
        self.assertEqual(g.winner.name, "Kansas")

    def test_a_final_that_still_agrees_with_the_scoreboard_is_skipped(self):
        self.process(row("6650631", "Kentucky", "69", "Kansas", "89"))
        api = self.process(row("6650631", "Kentucky", "69", "Kansas", "89"))
        api.get_game_details.assert_not_called()

    def test_an_old_final_is_not_rechecked(self):
        # Hand-corrected past games (data_fixes/) must survive a plain re-ingest; --refresh re-fetches them.
        old = date.today() - timedelta(days=60)
        self.process(row("6650631", "Kansas", "69", "Kentucky", "89", day=old))
        api = self.process(row("6650631", "Kentucky", "69", "Kansas", "89", day=old))
        api.get_game_details.assert_not_called()

    def test_tied_final_is_kept_in_progress_until_the_real_final(self):
        self.process(row("6649814", "Little Rock", "70", "Northwestern St.", "70"))
        g = Game.objects.get(source_game_id="6649814")
        self.assertEqual((g.status, g.home_score, g.away_score), ("in_progress", 70, 70))

        self.process(row("6649814", "Little Rock", "84", "Northwestern St.", "83"))
        g.refresh_from_db()
        self.assertEqual((g.status, g.home_score, g.away_score), ("final", 84, 83))

    def test_a_score_corrected_after_final_is_picked_up(self):
        self.process(row("6649814", "Little Rock", "80", "Northwestern St.", "94"))
        self.process(row("6649814", "Little Rock", "79", "Northwestern St.", "92"))
        g = Game.objects.get(source_game_id="6649814")
        self.assertEqual((g.home_score, g.away_score), (79, 92))

    def test_zero_zero_placeholder_final_is_left_final(self):
        self.process(row("1", "Kansas", "0", "Kentucky", "0"))
        self.assertEqual(Game.objects.get(source_game_id="1").status, "final")


class EspnOrientationTests(TestCase):
    def test_sides_follow_espn_home(self):
        self.assertEqual(espn_sides("2305", "96", "96"), ("96", "2305"))   # ESPN home = our away: swap
        self.assertEqual(espn_sides("2305", "96", "2305"), ("2305", "96"))
        self.assertEqual(espn_sides("2305", "96", None), ("2305", "96"))   # unknown: keep ours
        self.assertEqual(espn_sides("2305", "96", "999"), ("2305", "96"))  # alias id: keep ours

    @staticmethod
    def plays(*events):
        """Scoring plays: (team id, home score, away score) after each."""
        return [{"team": {"id": t}, "homeScore": h, "awayScore": a} for t, h, a in events]

    def test_plays_decide_over_the_header(self):
        # ESPN's header names North Dakota (155) home, but its plays' homeScore is Coastal's (324): 2026 game 1125.
        plays = self.plays(("324", 2, 0), ("155", 2, 3), ("324", 4, 3), ("155", 4, 5))
        self.assertTrue(plays_orientation(plays, "324", "155"))
        self.assertEqual(espn_sides("324", "155", "155", plays), ("324", "155"))
        self.assertEqual(espn_sides("155", "324", "155", plays), ("324", "155"))

    def test_no_scoring_evidence_falls_back_to_header(self):
        plays = [{"homeScore": 0, "awayScore": 0}, {"team": {"id": "999"}, "homeScore": 2, "awayScore": 0}]
        self.assertIsNone(plays_orientation(plays, "324", "155"))
        self.assertEqual(espn_sides("324", "155", "155", plays), ("155", "324"))

    def test_home_team_id_from_summary_header(self):
        data = {"header": {"competitions": [{"competitors": [
            {"homeAway": "away", "team": {"id": "2305"}}, {"homeAway": "home", "team": {"id": "96"}}]}]}}
        self.assertEqual(ESPNAPIClient.home_team_id(data), "96")
        self.assertIsNone(ESPNAPIClient.home_team_id({}))


class IntegrityCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Season.objects.create(year=2027, display_name="2026-27")
        ku = Team.objects.create(name="Kansas", slug="kansas", is_d1=True)
        uk = Team.objects.create(name="Kentucky", slug="kentucky", is_d1=True)
        lr = Team.objects.create(name="Little Rock", slug="little-rock", is_d1=True)
        nw = Team.objects.create(name="Northwestern St.", slug="northwestern-st", is_d1=True)
        # Stored flipped: raw says Kentucky home, Kansas away; stored the other way round.
        Game.objects.create(season_year=2027, game_date="2026-11-10", home_team=ku, away_team=uk, status="final",
                            home_score=69, away_score=89, source="ncaa", source_game_id="6650631",
                            raw_json=row("6650631", "Kentucky", "69", "Kansas", "89"))
        Game.objects.create(season_year=2027, game_date="2026-11-14", home_team=lr, away_team=nw, status="final",
                            home_score=70, away_score=70, source="ncaa", source_game_id="6649814",
                            raw_json=row("6649814", "Little Rock", "70", "Northwestern St.", "70"))

    def test_reports_flipped_and_tied_finals(self):
        out = StringIO()
        with self.assertRaises(SystemExit):
            call_command("check_ncaa_integrity", season=2027, stdout=out)
        text = out.getvalue()
        self.assertIn("[FAIL] source_side_mismatch: 1 fail", text)
        self.assertIn("FLIPPED: stored Kentucky 89 @ Kansas 69, source Kansas @ Kentucky", text)
        self.assertIn("[FAIL] tied_final: 1 fail", text)
