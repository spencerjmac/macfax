"""
Phase P P.3a: play-by-play and rotation fetches retry NBA.com's transient
HTTP 500s, cache the raw response (gzipped), and skip games they gave up on
for FAILED_RECORD_TTL.
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase
from nba_api.stats.endpoints.gamerotation import GameRotation
from nba_api.stats.endpoints.playbyplayv3 import PlayByPlayV3
from nba_api.stats.library.http import NBAStatsResponse

from nba.providers.nba_api_provider import ROTATION_FETCH_TRIES, FetchSkipped, NBAApiProvider

GAME_ID = "0022500748"
PBP_TRIES = 3   # what nba_sync_play_by_play passes as max_retries


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


def _pbp_json() -> str:
    def action(n, clock, action_type, sub_type="", team_id=0, person_id=0, home="", away="", desc=""):
        return {"gameId": GAME_ID, "actionNumber": n, "clock": clock, "period": 1,
                "teamId": team_id, "personId": person_id, "actionType": action_type,
                "subType": sub_type, "scoreHome": home, "scoreAway": away,
                "description": desc, "shotResult": "Made" if action_type == "Made Shot" else ""}

    return json.dumps({"meta": {}, "game": {"gameId": GAME_ID, "videoAvailable": 0, "actions": [
        action(1, "PT12M00.00S", "period", "start", desc="Period Start"),
        action(2, "PT11M36.00S", "Made Shot", team_id=1610612760, person_id=1628983,
               home="2", away="0", desc="Gilgeous-Alexander 2' Layup (2 PTS)"),
    ]}})


def _flaky(endpoint_cls, body: str, failures: int):
    """endpoint_cls whose first `failures` requests fail like NBA.com's empty HTTP 500."""

    class Flaky(endpoint_cls):
        requests = 0

        def get_request(self):
            cls = type(self)
            cls.requests += 1
            failing = cls.requests <= failures
            self.nba_response = NBAStatsResponse(
                response="" if failing else body, status_code=500 if failing else 200, url=None,
            )
            self.load_response()   # an empty body raises, as the real endpoint does

    return Flaky


class CachedGameFetchTests(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache_dir = Path(tmp.name)
        sleep = mock.patch("nba.providers.nba_api_provider.time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def _provider(self):
        return NBAApiProvider(sleep_seconds=0, max_retries=PBP_TRIES, cache_dir=self.cache_dir)

    def _patch(self, target, endpoint):
        patcher = mock.patch(target, endpoint)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _patch_rotation(self, failures):
        endpoint = _flaky(GameRotation, _rotation_json(), failures)
        self._patch("nba_api.stats.endpoints.gamerotation.GameRotation", endpoint)
        return endpoint

    def _patch_pbp(self, failures):
        endpoint = _flaky(PlayByPlayV3, _pbp_json(), failures)
        self._patch("nba_api.stats.endpoints.playbyplayv3.PlayByPlayV3", endpoint)
        return endpoint

    def _write_failure(self, age: timedelta):
        failed_at = (datetime.now(timezone.utc) - age).isoformat(timespec="seconds")
        (self.cache_dir / f"{GAME_ID}_gamerotation.failed").write_text(
            json.dumps({"failed_at": failed_at, "tries": ROTATION_FETCH_TRIES, "error": "x"}))

    def test_rotation_retries_flaky_endpoint_then_serves_second_fetch_from_cache(self):
        endpoint = self._patch_rotation(failures=3)

        first = self._provider().get_game_rotation(GAME_ID)

        self.assertEqual(endpoint.requests, 4)
        self.assertEqual([(s.person_id, s.in_time, s.out_time) for s in first],
                         [(201142, 0.0, 7200.0), (1628983, 0.0, 4210.0)])
        self.assertTrue((self.cache_dir / f"{GAME_ID}_gamerotation.json.gz").exists())

        second = self._provider().get_game_rotation(GAME_ID)

        self.assertEqual(endpoint.requests, 4)   # no API call
        self.assertEqual(second, first)

    def test_rotation_gives_up_after_its_tries_and_resumed_run_skips_the_game(self):
        endpoint = self._patch_rotation(failures=ROTATION_FETCH_TRIES)

        with self.assertRaises(RuntimeError):
            self._provider().get_game_rotation(GAME_ID)

        self.assertEqual(endpoint.requests, ROTATION_FETCH_TRIES)
        record = json.loads((self.cache_dir / f"{GAME_ID}_gamerotation.failed").read_text())
        self.assertIn("failed_at", record)

        with self.assertRaises(FetchSkipped):
            self._provider().get_game_rotation(GAME_ID)
        self.assertEqual(endpoint.requests, ROTATION_FETCH_TRIES)   # no API call

    def test_failure_record_expires_after_24_hours(self):
        endpoint = self._patch_rotation(failures=0)

        self._write_failure(age=timedelta(hours=23))
        with self.assertRaises(FetchSkipped):
            self._provider().get_game_rotation(GAME_ID)
        self.assertEqual(endpoint.requests, 0)

        self._write_failure(age=timedelta(hours=25))
        self.assertEqual(len(self._provider().get_game_rotation(GAME_ID)), 2)
        self.assertEqual(endpoint.requests, 1)
        self.assertFalse((self.cache_dir / f"{GAME_ID}_gamerotation.failed").exists())

    def test_reads_an_older_plain_json_cache_file(self):
        endpoint = self._patch_rotation(failures=0)
        (self.cache_dir / f"{GAME_ID}_gamerotation.json").write_text(_rotation_json())

        self.assertEqual(len(self._provider().get_game_rotation(GAME_ID)), 2)
        self.assertEqual(endpoint.requests, 0)

    def test_play_by_play_uses_max_retries_and_serves_second_fetch_from_cache(self):
        endpoint = self._patch_pbp(failures=PBP_TRIES - 1)

        first = self._provider().get_play_by_play(GAME_ID)

        self.assertEqual(endpoint.requests, PBP_TRIES)
        self.assertEqual([(e.action_type, e.clock_secs, e.score_home) for e in first],
                         [("period", 720, None), ("made shot", 696, 2)])
        self.assertTrue((self.cache_dir / f"{GAME_ID}_playbyplayv3.json.gz").exists())

        second = self._provider().get_play_by_play(GAME_ID)

        self.assertEqual(endpoint.requests, PBP_TRIES)   # no API call
        self.assertEqual(second, first)

    def test_play_by_play_gives_up_after_max_retries(self):
        endpoint = self._patch_pbp(failures=PBP_TRIES)

        with self.assertRaises(RuntimeError):
            self._provider().get_play_by_play(GAME_ID)
        self.assertEqual(endpoint.requests, PBP_TRIES)

    def test_rotation_tries_is_per_call(self):
        endpoint = self._patch_rotation(failures=5)

        with self.assertRaises(RuntimeError):
            self._provider().get_game_rotation(GAME_ID, tries=3)

        self.assertEqual(endpoint.requests, 3)
        self.assertEqual(json.loads((self.cache_dir / f"{GAME_ID}_gamerotation.failed").read_text())["tries"], 3)

    def test_retry_failed_tries_again_despite_a_recent_failure(self):
        endpoint = self._patch_rotation(failures=0)
        self._write_failure(age=timedelta(hours=1))

        rotation = self._provider().get_game_rotation(GAME_ID, retry_failed=True)

        self.assertEqual(endpoint.requests, 1)
        self.assertEqual(len(rotation), 2)
        self.assertFalse((self.cache_dir / f"{GAME_ID}_gamerotation.failed").exists())
