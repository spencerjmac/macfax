"""
Shared test base classes for the api tests.
"""
from django.core.cache import cache
from django.test import TestCase, override_settings

# A private in-memory cache. The real setting points at Redis, which is shared
# with the dev server and survives between test runs.
LOCMEM_CACHE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@override_settings(CACHES=LOCMEM_CACHE)
class IsolatedCacheTestCase(TestCase):
    """
    TestCase for tests that call views which cache their responses
    (/api/matchup/, /api/rankings/, ...).

    Without this, every test that asks for the same URL reads the first test's
    cached answer (not its own data), and test data leaks into the dev
    server's Redis cache. The cache is emptied before every test.

    Subclasses that define setUp must call super().setUp().
    """

    def setUp(self):
        super().setUp()
        cache.clear()
