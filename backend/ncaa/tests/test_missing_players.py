"""
ncaa.utils.missing_players: matching ncaa.com box scores to our games and finding players ESPN left out.

- eastern_date uses the US-Eastern date of a UTC tip (a 02:30Z tip is the previous evening).
- match_contests matches the final score pair in either orientation; bind_side picks a side by points and
  rejects it when FGA disagrees.
- missing_lines: players with no row, or a blanked row, come back; name variants (suffix, accent, short first
  name with a unique last name) count as present; DNPs are ignored.
- MissingPlayerGameStats allows NULL stats and keeps one row per (game, team, source, external_id).
"""

from datetime import date

from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase

from ncaa.models import Game, MissingPlayerGameStats, Team
from ncaa.utils.missing_players import (bind_side, eastern_date, expected_minutes, match_contests,
                                        missing_lines, scoreboard_contests)


def player(pid, first, last, minutes, points, **kw):
    return {"id": pid, "firstName": first, "lastName": last, "minutesPlayed": str(minutes), "points": str(points),
            "number": kw.get("number", ""), "position": "G", "starter": False, "fieldGoalsMade": "1",
            "fieldGoalsAttempted": "3", "threePointsMade": "0", "threePointsAttempted": "1", "freeThrowsMade": "0",
            "freeThrowsAttempted": "0", "offensiveRebounds": "1", "totalRebounds": "4", "assists": "2",
            "turnovers": "1", "personalFouls": "2", "steals": "0", "blockedShots": "0"}


class HelperTests(SimpleTestCase):
    def test_expected_minutes(self):
        self.assertEqual([expected_minutes(p) for p in (2, 3, 4)], [200, 225, 250])

    def test_eastern_date(self):
        self.assertEqual(eastern_date("2023-12-02T01:30Z"), date(2023, 12, 1))
        self.assertEqual(eastern_date("2023-12-02T17:00Z"), date(2023, 12, 2))

    def test_scoreboard_and_match(self):
        sb = {"games": [
            {"game": {"url": "/game/6197575", "gameState": "final", "home": {"score": "80", "names": {"seo": "depaul"}},
                      "away": {"score": "99", "names": {"seo": "iowa-st"}}}},
            {"game": {"url": "/game/1", "gameState": "pre", "home": {"score": "", "names": {"seo": "a"}},
                      "away": {"score": "", "names": {"seo": "b"}}}},
        ]}
        contests = scoreboard_contests(sb)
        self.assertEqual([c["contest_id"] for c in contests], ["6197575"])
        self.assertEqual(len(match_contests(80, 99, contests)), 1)
        self.assertEqual(len(match_contests(99, 80, contests)), 1)   # home/away flipped
        self.assertEqual(match_contests(80, 98, contests), [])

    def test_bind_side(self):
        box = {"teamBoxscore": [{"teamId": "1", "teamStats": {"points": "80", "fieldGoalsAttempted": "60"}},
                                {"teamId": "2", "teamStats": {"points": "99", "fieldGoalsAttempted": "64"}}]}
        self.assertEqual(bind_side(box, 99, 64)["teamId"], "2")
        self.assertEqual(bind_side(box, 99, None)["teamId"], "2")
        self.assertIsNone(bind_side(box, 99, 70))       # FGA disagrees
        self.assertIsNone(bind_side(box, 75, None))     # no side with that score

    def test_missing_lines(self):
        ours = [("Tamin Lipsey", 32, 10), ("Keshon Gilbert", 30, 17), ("Tre King", 28, 15),
                ("Hason Ward", 0, 0), ("Curtis Jones Jr.", 25, 18)]
        ncaa = [player(1, "Tamin", "Lipsey", 32, 10), player(2, "Robert", "Jones", 20, 12),
                player(3, "Keshon", "Gilbert", 30, 17), player(4, "Tré", "King", 28, 15),
                player(5, "Hason", "Ward", 15, 6), player(6, "Curtis", "Jones", 25, 18),
                player(7, "Walk", "On", 0, 0)]
        got = {l["name"]: l["note"] for l in missing_lines(ncaa, ours)}
        self.assertEqual(got, {"Robert Jones": "", "Hason Ward": "blanked"})

    def test_repeated_ncaa_rows_count_once(self):
        ncaa = [player(33, "Jaden", "Brownell", 10, 0), player(33, "Jaden", "Brownell", 10, 0)]
        self.assertEqual([l["name"] for l in missing_lines(ncaa, [])], ["Jaden Brownell"])

    def test_short_name_match_needs_a_unique_row(self):
        ours = [("Jon Smith", 20, 5), ("Josh Smith", 18, 4)]
        self.assertEqual(missing_lines([player(1, "J.", "Smith", 20, 5)], ours), [])   # ambiguous -> present
        self.assertEqual([l["name"] for l in missing_lines([player(1, "K", "Smith", 10, 2)], ours)], ["K Smith"])

    def test_player_line_fields(self):
        line = missing_lines([player(9, "Robert", "Jones", 20, 12)], [])[0]
        self.assertEqual((line["external_id"], line["minutes"], line["points"], line["defensive_rebounds"]),
                         ("9", 20.0, 12, 3))


class SideTableTests(TestCase):
    def test_nullable_stats_and_uniqueness(self):
        home, away = Team.objects.create(slug="h", name="H"), Team.objects.create(slug="a", name="A")
        game = Game.objects.create(home_team=home, away_team=away, game_date=date(2024, 1, 1), season_year=2024)
        MissingPlayerGameStats.objects.create(game=game, team=home, source="ncaa", external_id="4", name="X Y")
        row = MissingPlayerGameStats.objects.get()
        self.assertIsNone(row.minutes); self.assertIsNone(row.player)
        with self.assertRaises(IntegrityError):
            MissingPlayerGameStats.objects.create(game=game, team=home, source="ncaa", external_id="4", name="X Y")
