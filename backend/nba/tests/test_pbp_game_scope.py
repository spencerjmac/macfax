"""
Phase P P.2b: only this game's teams and rosters count. Instant-replay events
carry team_id 0; the parser used to treat them as away-team events, and their
person_id could match an unrelated player (a 1996-97 player became a 2026
Bucks starter).
"""

from django.test import SimpleTestCase

from nba.tests.test_pbp_score import (
    AWAY_TEAM_ID, AWAY_TEAM_PK, HOME_TEAM_ID, PbpGameFixture, _Events, _pk, _player_id,
)

STRANGER_ID = 29   # NBA.com id that matches some other player in the database
STRANGER_PK = 1    # low pk: with six away "starters", the old code kept this one


class GameScopeTests(PbpGameFixture, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.player_pk_map[STRANGER_ID] = STRANGER_PK   # known player, not on either roster

    def test_team_zero_event_does_not_put_an_outsider_on_court(self):
        e = _Events()
        e.add(720, "period", sub_type="start")
        for side, team_id in (("home", HOME_TEAM_ID), ("away", AWAY_TEAM_ID)):
            for n in range(1, 6):
                e.add(715, "foul", team_id, _player_id(side, n), description="P.FOUL")
        e.add(700, "instant replay", 0, STRANGER_ID, sub_type="coach challenge overturn ruling",
              description="Instant Replay1st Period")
        e.add(650, "made shot", AWAY_TEAM_ID, _player_id("away", 1),
              shot_result="Made", score=(0, 2), description="away1 Layup (2 PTS)")
        e.add(0, "period", sub_type="end")

        stints, quality_flag, msg, _, _ = self.parse(e.events)

        self.assertFalse(quality_flag, msg)
        on_court = {s["player_pk"] for s in stints if s["team_pk"] == AWAY_TEAM_PK}
        self.assertEqual(on_court, {_pk("away", n) for n in range(1, 6)})
        self.assertNotIn(STRANGER_PK, {s["player_pk"] for s in stints})
