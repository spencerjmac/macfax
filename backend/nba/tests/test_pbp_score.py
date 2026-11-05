"""
Phase P P.2: the PBP running score never goes down. Some seasons' PlayByPlayV3
responses carry a 0 score on non-scoring events; accepting it reset the running
score mid-game and inflated stint points (2016-17 stints averaged 2.3x the
final score).
"""

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from nba.management.commands.nba_sync_play_by_play import _parse_game
from nba.providers.base import RawPlayEvent

HOME_TEAM_ID, AWAY_TEAM_ID = 1610612737, 1610612738
HOME_TEAM_PK, AWAY_TEAM_PK = 1, 2


def _player_id(side: str, n: int) -> int:
    return (100 if side == "home" else 200) + n


def _pk(side: str, n: int) -> int:
    return 1000 + _player_id(side, n)


class _Events:
    def __init__(self):
        self.events: list[RawPlayEvent] = []

    def add(self, clock, action_type, team_id=None, person_id=None, sub_type="",
            shot_result=None, score=(None, None), description=""):
        n = len(self.events) + 1
        self.events.append(RawPlayEvent(
            game_id="0029900001", action_number=n, clock_secs=clock, period=1,
            team_id=team_id, person_id=person_id, action_type=action_type,
            sub_type=sub_type, shot_result=shot_result,
            is_field_goal=action_type == "made shot",
            score_home=score[0], score_away=score[1], points_total=0,
            description=description, order_number=n,
        ))


class PbpGameFixture:
    """Two six-man rosters, NBA id → pk maps, and a stand-in game. Mix into a SimpleTestCase."""

    def setUp(self):
        self.player_pk_map = {
            _player_id(side, n): _pk(side, n)
            for side in ("home", "away") for n in range(1, 7)
        }
        self.name_to_pk = {
            f"{side}{n}": _pk(side, n) for side in ("home", "away") for n in range(1, 7)
        }
        self.team_pk_map = {HOME_TEAM_ID: HOME_TEAM_PK, AWAY_TEAM_ID: AWAY_TEAM_PK}
        self.game = SimpleNamespace(
            game_id="0029900001",
            home_team=SimpleNamespace(nba_team_id=HOME_TEAM_ID),
            away_team=SimpleNamespace(nba_team_id=AWAY_TEAM_ID),
        )
        self.roster = {
            HOME_TEAM_PK: {_pk("home", n) for n in range(1, 7)},
            AWAY_TEAM_PK: {_pk("away", n) for n in range(1, 7)},
        }
        # The roster name lookup reads NBAPlayer; serve it from this fixture instead.
        patcher = mock.patch(
            "nba.management.commands.nba_sync_play_by_play._build_roster_name_lookup",
            side_effect=lambda pks: {k: v for k, v in self.name_to_pk.items() if v in pks},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def parse(self, events):
        return _parse_game(self.game, events, self.player_pk_map, self.team_pk_map, self.roster)


class RunningScoreNeverDecreasesTests(PbpGameFixture, SimpleTestCase):

    def _events_with_zero_score_mid_game(self) -> list[RawPlayEvent]:
        e = _Events()
        e.add(720, "period", sub_type="start")
        for side, team_id in (("home", HOME_TEAM_ID), ("away", AWAY_TEAM_ID)):
            for n in range(1, 6):   # every starter shows up before any sub
                e.add(715, "foul", team_id, _player_id(side, n), description="P.FOUL")
        e.add(700, "made shot", HOME_TEAM_ID, _player_id("home", 2),
              shot_result="Made", score=(2, 0), description="home2 Layup (2 PTS)")
        e.add(680, "substitution", HOME_TEAM_ID, _player_id("home", 1),
              description="SUB: home6 FOR home1")
        e.add(660, "made shot", AWAY_TEAM_ID, _player_id("away", 2),
              shot_result="Made", score=(2, 2), description="away2 Layup (2 PTS)")
        # Non-scoring event carrying a bogus 0-0 score.
        e.add(650, "rebound", HOME_TEAM_ID, _player_id("home", 3),
              score=(0, 0), description="home3 REBOUND (Off:0 Def:1)")
        e.add(640, "substitution", HOME_TEAM_ID, _player_id("home", 6),
              description="SUB: home1 FOR home6")
        e.add(600, "made shot", HOME_TEAM_ID, _player_id("home", 4),
              shot_result="Made", score=(4, 2), description="home4 Jump Shot (2 PTS)")
        e.add(0, "period", sub_type="end")
        return e.events

    def _windows(self, stints):
        """Home team's (pts_scored, pts_allowed) per lineup window, in clock order."""
        home = {}
        for s in stints:
            if s["team_pk"] == HOME_TEAM_PK:
                home[(s["clock_start_secs"], s["clock_end_secs"])] = (s["pts_scored"], s["pts_allowed"])
        return [home[k] for k in sorted(home, reverse=True)]

    def test_zero_score_on_non_scoring_event_does_not_inflate_stint_points(self):
        stints, quality_flag, msg, failed = self.parse(self._events_with_zero_score_mid_game())

        self.assertFalse(quality_flag, msg)
        self.assertEqual(failed, [])
        windows = self._windows(stints)
        # 720-680: 2-0, 680-640: 0-2, 640-0: 2-0
        self.assertEqual(windows, [(2, 0), (0, 2), (2, 0)])
        self.assertEqual(sum(w[0] for w in windows), 4)   # final home score
        self.assertEqual(sum(w[1] for w in windows), 2)   # final away score
