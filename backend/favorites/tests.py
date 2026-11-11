"""
Tests for /api/favorites/.

Throttling counts requests in the cache. The real cache is Redis (shared with
the dev server), so these tests use a private in-memory cache, emptied before
every test.
"""

import uuid

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from ncaa.models import Team

from .models import FavoriteTeam

URL = "/api/favorites/"
LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=LOCMEM_CACHE)
class FavoritesAPITest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.slugs = [f"team-{i}" for i in range(60)]
        Team.objects.bulk_create(Team(slug=s, name=s.title()) for s in cls.slugs)

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.device = str(uuid.uuid4())

    def get(self, device_id):
        return self.client.get(URL, {"device_id": device_id})

    def post(self, device_id, team_slugs):
        return self.client.post(
            URL, {"device_id": device_id, "team_slugs": team_slugs}, format="json"
        )

    def test_get_unknown_device_returns_empty_list(self):
        resp = self.get(self.device)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"device_id": self.device, "team_slugs": []})

    def test_post_then_get_returns_same_list_in_same_order(self):
        slugs = ["team-5", "team-1", "team-9"]
        resp = self.post(self.device, slugs)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"device_id": self.device, "team_slugs": slugs})

        resp = self.get(self.device)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["team_slugs"], slugs)
        positions = list(
            FavoriteTeam.objects.filter(device_id=self.device).values_list(
                "team_slug", "position"
            )
        )
        self.assertEqual(positions, [("team-5", 0), ("team-1", 1), ("team-9", 2)])

    def test_second_post_replaces_list(self):
        self.post(self.device, ["team-1", "team-2", "team-3"])
        resp = self.post(self.device, ["team-3", "team-4"])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.get(self.device).json()["team_slugs"], ["team-3", "team-4"])
        self.assertEqual(FavoriteTeam.objects.filter(device_id=self.device).count(), 2)

    def test_post_empty_list_clears(self):
        self.post(self.device, ["team-1", "team-2"])
        resp = self.post(self.device, [])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["team_slugs"], [])
        self.assertFalse(FavoriteTeam.objects.filter(device_id=self.device).exists())

    def test_bad_uuid_returns_400(self):
        for resp in (
            self.get("not-a-uuid"),
            self.client.get(URL),
            self.post("not-a-uuid", ["team-1"]),
            self.client.post(URL, {"team_slugs": ["team-1"]}, format="json"),
        ):
            self.assertEqual(resp.status_code, 400)
            self.assertIn("device_id", resp.json()["error"])
        self.assertEqual(FavoriteTeam.objects.count(), 0)

    def test_team_slugs_not_list_of_strings_returns_400(self):
        for bad in ("team-1", ["team-1", 7], None):
            resp = self.post(self.device, bad)
            self.assertEqual(resp.status_code, 400)
            self.assertIn("list of strings", resp.json()["error"])

    def test_unknown_slug_returns_400_and_lists_it(self):
        self.post(self.device, ["team-1"])
        resp = self.post(self.device, ["team-2", "no-such-team", "also-fake"])
        self.assertEqual(resp.status_code, 400)
        error = resp.json()["error"]
        self.assertIn("no-such-team", error)
        self.assertIn("also-fake", error)
        self.assertNotIn("team-2", error)
        # Rejected POST leaves the saved list alone.
        self.assertEqual(self.get(self.device).json()["team_slugs"], ["team-1"])

    def test_more_than_50_returns_400(self):
        resp = self.post(self.device, self.slugs[:51])
        self.assertEqual(resp.status_code, 400)
        self.assertIn("50", resp.json()["error"])
        self.assertEqual(self.post(self.device, self.slugs[:50]).status_code, 200)

    def test_duplicates_return_400(self):
        resp = self.post(self.device, ["team-1", "team-2", "team-1"])
        self.assertEqual(resp.status_code, 400)
        self.assertIn("duplicates", resp.json()["error"])
        self.assertIn("team-1", resp.json()["error"])

    def test_post_for_one_device_leaves_other_device_alone(self):
        device_b = str(uuid.uuid4())
        self.post(device_b, ["team-7", "team-8"])
        self.post(self.device, ["team-1"])
        self.post(self.device, [])
        self.assertEqual(self.get(device_b).json()["team_slugs"], ["team-7", "team-8"])

    def test_throttled_after_60_requests_per_minute(self):
        for _ in range(60):
            self.assertEqual(self.get(self.device).status_code, 200)
        self.assertEqual(self.get(self.device).status_code, 429)
