"""
Phase P P.3b: with NBA.com rotation data, lineups come from GameRotation and
play-by-play supplies score, box counts and event order. On a real cached
game (0022500304, ATL@PHI, double overtime) every player's stint seconds
match the box score within 1 and every stint plus-minus matches exactly.
"""

import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from nba.management.commands.nba_sync_play_by_play import _clock_rewinds, _parse_game
from nba.providers.nba_api_provider import NBAApiProvider

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pbp"
GAME_ID = "0022500304"


class RotationLineupsOnCachedGameTests(SimpleTestCase):
    def setUp(self):
        self.box = json.loads((FIXTURES / f"{GAME_ID}_box.json").read_text())
        provider = NBAApiProvider(cache_dir=FIXTURES)
        with mock.patch("nba_api.stats.library.http.NBAStatsHTTP.send_api_request",
                        side_effect=AssertionError("fixture game must not call NBA.com")):
            self.events = provider.get_play_by_play(GAME_ID)
            self.rotation = provider.get_game_rotation(GAME_ID)

        # NBA.com ids double as pks here.
        home, away = self.box["home_team_id"], self.box["away_team_id"]
        self.game = SimpleNamespace(
            game_id=GAME_ID,
            home_team=SimpleNamespace(nba_team_id=home),
            away_team=SimpleNamespace(nba_team_id=away),
        )
        self.player_pk_map = {p["player_id"]: p["player_id"] for p in self.box["players"]}
        self.team_pk_map = {home: home, away: away}
        self.roster = defaultdict(set)
        for p in self.box["players"]:
            self.roster[p["team_id"]].add(p["player_id"])
        names = mock.patch(
            "nba.management.commands.nba_sync_play_by_play._build_roster_name_lookup",
            return_value={},
        )
        names.start()
        self.addCleanup(names.stop)

    def test_stints_match_the_box_score(self):
        stints, quality_flag, msg, _ = _parse_game(
            self.game, self.events, self.player_pk_map, self.team_pk_map, {}, self.roster, self.rotation,
        )

        self.assertIn("lineups=rotation", msg)
        self.assertIn(" 0 dropped", msg)
        self.assertFalse(quality_flag, msg)
        self.assertEqual(_clock_rewinds(self.events), 0)

        seconds, plus_minus = defaultdict(int), defaultdict(int)
        windows = {}
        for s in stints:
            seconds[s["player_pk"]] += s["secs_on"]
            plus_minus[s["player_pk"]] += s["plus_minus"]
            if s["team_pk"] == self.box["home_team_id"]:
                windows[(s["period"], s["clock_start_secs"], s["clock_end_secs"], s["window"])] = s["pts_scored"], s["pts_allowed"]

        for p in self.box["players"]:
            pid = p["player_id"]
            with self.subTest(player=pid):
                self.assertLessEqual(abs(seconds.get(pid, 0) - p["seconds"]), 1)
                self.assertEqual(plus_minus.get(pid, 0), p["plus_minus"])
        self.assertEqual(sum(w[0] for w in windows.values()), self.box["home_score"])
        self.assertEqual(sum(w[1] for w in windows.values()), self.box["away_score"])
