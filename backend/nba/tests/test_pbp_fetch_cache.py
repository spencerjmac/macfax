"""
Phase P P.3a: play-by-play and rotation fetches retry NBA.com's transient
HTTP 500s, cache the raw response, and remember games they gave up on.
"""

import json
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase
from nba_api.stats.endpoints.gamerotation import GameRotation
from nba_api.stats.library.http import NBAStatsResponse

from nba.providers.nba_api_provider import GAME_FETCH_TRIES, FetchSkipped, NBAApiProvider

GAME_ID = "0022500748"


def _rotation_json() -> str:
    headers = GameRotation.expected_data["AwayTeam"]

    def row(team_id, person_id, last, in_time, out_time):
        values = {"GAME_ID": GAME_ID, "TEAM_ID": team_id, "PERSON_ID": person_id,
                  "PLAYER_FIRST": "Test", "PLAYER_LAST": last,
                  "IN_TIME_REAL": in_time, "OUT_TIME_REAL": out_time}
        return [values.get(h) for h in headers]

    return json.dumps({"resource": "gamerotation", "parameters": {}, "resultSets": [
        {"name": "AwayTeam", "headers": headers, "rowSet": [row(1610612745, 201142, "Durant", 0.0, 7200.0)]},
        {"name": "HomeTeam", "headers": headers, "rowSet": [row(1610612760, 1628983, "Gilgeous-Alexander", 0.0, 4210.0)]},
    ]})


def _flaky_rotation(failures: int):
    """GameRotation whose first `failures` requests fail like NBA.com's empty HTTP 500."""

    class FlakyGameRotation(GameRotation):
        requests = 0

        def get_request(self):
            cls = type(self)
            cls.requests += 1
            failing = cls.requests <= failures
            self.nba_response = NBAStatsResponse(
                response="" if failing else _rotation_json(),
                status_code=500 if failing else 200, url=None,
            )
            self.load_response()   # an empty body raises, as the real endpoint does

    return FlakyGameRotation


class CachedGameFetchTests(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache_dir = Path(tmp.name)
        sleep = mock.patch("nba.providers.nba_api_provider.time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def _provider(self):
        return NBAApiProvider(sleep_seconds=0, cache_dir=self.cache_dir)

    def _patch_endpoint(self, endpoint):
        patcher = mock.patch("nba_api.stats.endpoints.gamerotation.GameRotation", endpoint)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_retries_flaky_endpoint_then_serves_second_fetch_from_cache(self):
        endpoint = _flaky_rotation(failures=3)
        self._patch_endpoint(endpoint)

        first = self._provider().get_game_rotation(GAME_ID)

        self.assertEqual(endpoint.requests, 4)
        self.assertEqual([(s.person_id, s.in_time, s.out_time) for s in first],
                         [(201142, 0.0, 7200.0), (1628983, 0.0, 4210.0)])
        self.assertTrue((self.cache_dir / f"{GAME_ID}_gamerotation.json").exists())

        second = self._provider().get_game_rotation(GAME_ID)

        self.assertEqual(endpoint.requests, 4)   # no API call
        self.assertEqual(second, first)

    def test_gives_up_after_max_tries_and_resumed_run_skips_the_game(self):
        endpoint = _flaky_rotation(failures=GAME_FETCH_TRIES)
        self._patch_endpoint(endpoint)

        with self.assertRaises(RuntimeError):
            self._provider().get_game_rotation(GAME_ID)

        self.assertEqual(endpoint.requests, GAME_FETCH_TRIES)
        record = json.loads((self.cache_dir / f"{GAME_ID}_gamerotation.failed").read_text())
        self.assertIn("failed_at", record)
        self.assertFalse((self.cache_dir / f"{GAME_ID}_gamerotation.json").exists())

        with self.assertRaises(FetchSkipped):
            self._provider().get_game_rotation(GAME_ID)
        self.assertEqual(endpoint.requests, GAME_FETCH_TRIES)   # no API call
