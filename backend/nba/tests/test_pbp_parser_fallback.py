"""
Phase P P.3c: the play-by-play lineup parser, used when a game has no
rotation data. Each period's starters come from that period's events (the
parser used to carry the last five across the break); "J. Williams" resolves
by initial among this game's roster only; and a name no one on either roster
matches is a missed lookup, never a namesake from elsewhere in the database.

P.3d: free throws listed after a substitution run, but awarded for a foul
listed earlier in the same second, belong to the five on court at the foul.
"""

from collections import defaultdict

from django.test import SimpleTestCase

from nba.providers.base import RawPlayEvent
from nba.tests.test_pbp_score import (
    AWAY_TEAM_ID, AWAY_TEAM_PK, HOME_TEAM_ID, HOME_TEAM_PK, PbpGameFixture, _pk, _player_id,
)


class _PeriodEvents:
    """Events across several periods, in response order."""

    def __init__(self):
        self.events: list[RawPlayEvent] = []

    def add(self, period, clock, action_type, team_id=None, person_id=None, sub_type="",
            description="", score=(None, None)):
        n = len(self.events) + 1
        self.events.append(RawPlayEvent(
            game_id="0029900001", action_number=n, clock_secs=clock, period=period,
            team_id=team_id, person_id=person_id, action_type=action_type,
            sub_type=sub_type, shot_result=None, is_field_goal=False,
            score_home=score[0], score_away=score[1], points_total=0,
            description=description, order_number=n,
        ))

    def start(self, period):
        self.add(period, 720, "period", 0, sub_type="start")

    def end(self, period):
        self.add(period, 0, "period", 0, sub_type="end")

    def touch(self, period, clock, side, n):
        team_id = HOME_TEAM_ID if side == "home" else AWAY_TEAM_ID
        self.add(period, clock, "foul", team_id, _player_id(side, n), description="P.FOUL")

    def sub(self, period, clock, side, out_n, description):
        team_id = HOME_TEAM_ID if side == "home" else AWAY_TEAM_ID
        self.add(period, clock, "substitution", team_id, _player_id(side, out_n),
                 description=description)


def _seconds(stints) -> dict[tuple[int, int], int]:
    """(player pk, period) → seconds on court."""
    secs = defaultdict(int)
    for s in stints:
        secs[(s["player_pk"], s["period"])] += s["secs_on"]
    return secs


class ParserFallbackTests(PbpGameFixture, SimpleTestCase):

    def test_lineup_change_between_q1_and_q2(self):
        e = _PeriodEvents()
        e.start(1)
        for side in ("home", "away"):
            for n in range(1, 6):
                e.touch(1, 700, side, n)
        e.end(1)
        # Q2: home6 starts in place of home1, who comes back in for home3.
        e.start(2)
        e.touch(2, 700, "home", 6)
        e.touch(2, 690, "home", 2)
        e.sub(2, 600, "home", 3, "SUB: home1 FOR home3")
        for n in range(1, 6):
            e.touch(2, 500, "away", n)
        e.end(2)

        stints, quality_flag, msg, failed = self.parse(e.events)

        self.assertFalse(quality_flag, msg)
        self.assertIn("0 dropped", msg)
        self.assertEqual(failed, [])
        secs = _seconds(stints)
        # home3 had no Q2 event before being subbed out; home4 and home5 had
        # none at all: all three come from Q1's last five. home1 was subbed IN
        # this period, so he is not a Q2 starter.
        self.assertEqual(secs[(_pk("home", 6), 2)], 720)
        self.assertEqual(secs[(_pk("home", 1), 2)], 600)
        self.assertEqual(secs[(_pk("home", 3), 2)], 120)
        for n in (2, 4, 5):
            self.assertEqual(secs[(_pk("home", n), 2)], 720)
        self.assertEqual(secs[(_pk("home", 6), 1)], 0)

    def test_same_surname_teammates_subbing_in_together(self):
        self.name_to_pk.update({
            "jalen williams": _pk("home", 6),
            "kenrich williams": _pk("home", 7),
            "williams": _pk("home", 7),     # surname key: last writer wins
        })
        self.player_pk_map[_player_id("home", 7)] = _pk("home", 7)
        self.roster[HOME_TEAM_PK].add(_pk("home", 7))

        e = _PeriodEvents()
        e.start(1)
        for side in ("home", "away"):
            for n in range(1, 6):
                e.touch(1, 700, side, n)
        e.sub(1, 600, "home", 1, "SUB: J. Williams FOR home1")
        e.sub(1, 600, "home", 2, "SUB: K. Williams FOR home2")
        e.end(1)

        stints, quality_flag, msg, failed = self.parse(e.events)

        self.assertFalse(quality_flag, msg)
        self.assertIn("0 dropped", msg)
        self.assertEqual(failed, [])
        secs = _seconds(stints)
        self.assertEqual(secs[(_pk("home", 6), 1)], 600)
        self.assertEqual(secs[(_pk("home", 7), 1)], 600)
        self.assertEqual(secs[(_pk("home", 1), 1)], 120)
        self.assertEqual(secs[(_pk("home", 2), 1)], 120)

    def test_namesake_on_neither_roster_is_a_missed_lookup(self):
        namesake_pk = 9999      # someone in the database, on neither roster
        self.name_to_pk["carter"] = namesake_pk

        e = _PeriodEvents()
        e.start(1)
        for side in ("home", "away"):
            for n in range(1, 6):
                e.touch(1, 700, side, n)
        e.sub(1, 600, "home", 1, "SUB: Carter FOR home1")
        e.end(1)

        stints, _, msg, failed = self.parse(e.events)

        self.assertNotIn(namesake_pk, {s["player_pk"] for s in stints})
        self.assertEqual(failed, ["carter"])     # logged once
        self.assertIn("missed sub lookups", msg)
        # The unresolved sub is skipped: home1 plays on.
        self.assertEqual(_seconds(stints)[(_pk("home", 1), 1)], 720)
        self.assertEqual({s["player_pk"] for s in stints if s["team_pk"] == AWAY_TEAM_PK},
                         {_pk("away", n) for n in range(1, 6)})

    def test_free_throws_credit_the_five_on_court_at_the_foul(self):
        e = _PeriodEvents()
        e.start(1)
        for side in ("home", "away"):
            for n in range(1, 6):
                e.touch(1, 700, side, n)
        # All in one second: foul, a sub run, FT 1, another sub run, FT 2.
        e.touch(1, 300, "away", 1)
        e.sub(1, 300, "home", 1, "SUB: home6 FOR home1")
        e.add(1, 300, "free throw", HOME_TEAM_ID, _player_id("home", 2),
              description="home2 Free Throw 1 of 2 (1 PTS)", score=(1, 0))
        e.sub(1, 300, "away", 2, "SUB: away6 FOR away2")
        e.add(1, 300, "free throw", HOME_TEAM_ID, _player_id("home", 2),
              description="home2 Free Throw 2 of 2 (2 PTS)", score=(2, 0))
        e.end(1)

        stints, quality_flag, msg, failed = self.parse(e.events)

        self.assertFalse(quality_flag, msg)
        self.assertIn(" 0 dropped", msg)
        self.assertEqual(failed, [])
        plus_minus, secs = defaultdict(int), _seconds(stints)
        for s in stints:
            plus_minus[s["player_pk"]] += s["plus_minus"]
        for n in range(1, 6):
            self.assertEqual(plus_minus[_pk("home", n)], 2, f"home{n}")
            self.assertEqual(plus_minus[_pk("away", n)], -2, f"away{n}")
        self.assertEqual(plus_minus[_pk("home", 6)], 0)
        self.assertEqual(plus_minus[_pk("away", 6)], 0)
        # Both sub runs still take effect at 300.
        self.assertEqual(secs[(_pk("home", 1), 1)], 420)
        self.assertEqual(secs[(_pk("home", 6), 1)], 300)
        self.assertEqual(secs[(_pk("away", 2), 1)], 420)
        self.assertEqual(secs[(_pk("away", 6), 1)], 300)
