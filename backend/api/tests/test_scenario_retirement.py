"""
Phase 3.5 regression guard: the Sprint-3 scenario layer is retired.

The /api/scenarios/* routes were removed (DEAD: no frontend callers, no
saved ScenarioSnapshot rows, no test coverage) because they computed rank
ranges under the pre-Phase-3 flat-sigma convention — the last endpoint
inconsistent with the sigma_o/d/em band model. If these routes come back,
they must be built on the engine sigma functions and the D1-only rank pool
(see api/urls.py tombstone). /api/outlook/scenario/ is the single surviving
scenario endpoint.
"""

from django.test import TestCase


class ScenarioRetirementTests(TestCase):
    """The retired Sprint-3 routes must 404; the survivor must not."""

    def test_scenarios_compute_is_gone(self):
        self.assertEqual(self.client.post("/api/scenarios/compute/").status_code, 404)

    def test_scenarios_save_is_gone(self):
        self.assertEqual(self.client.post("/api/scenarios/save/").status_code, 404)

    def test_scenarios_detail_is_gone(self):
        self.assertEqual(self.client.get("/api/scenarios/1/").status_code, 404)

    def test_scenarios_list_is_gone(self):
        self.assertEqual(self.client.get("/api/scenarios/").status_code, 404)

    def test_outlook_scenario_survives(self):
        # POST-only view: GET returns 405 (routed), never 404 (removed).
        self.assertEqual(self.client.get("/api/outlook/scenario/").status_code, 405)
