"""
Pure-Python tests for ncaa/analytics/staleness.py — no Django, no DB.
"""

import unittest
from datetime import datetime, timezone

from ncaa.analytics.staleness import check_staleness, check_team_staleness_bulk


def _dt(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


class TestCheckStaleness(unittest.TestCase):

    def test_no_warnings_when_all_current(self):
        psp = _dt(2026, 5, 1, 12, 0, 0)
        trf = _dt(2026, 5, 1, 12, 5, 0)   # 5 min after PSP
        tsp = _dt(2026, 5, 1, 12, 10, 0)  # 10 min after PSP
        warnings = check_staleness(2026, 1, psp, trf, tsp)
        self.assertEqual(warnings, [])

    def test_phase3_stale_warns(self):
        psp = _dt(2026, 5, 2, 10, 0, 0)   # PSP re-ran
        trf = _dt(2026, 5, 1, 10, 0, 0)   # TRF is 24h old
        tsp = _dt(2026, 5, 2, 10, 0, 0)
        warnings = check_staleness(2026, 1, psp, trf, tsp)
        self.assertGreaterEqual(len(warnings), 1)
        phase3_warn = next((w for w in warnings if w.downstream_phase == "Phase 3"), None)
        self.assertIsNotNone(phase3_warn)
        self.assertEqual(phase3_warn.severity, "error")   # > 24h stale

    def test_phase5_stale_warns(self):
        psp = _dt(2026, 5, 1, 10, 0, 0)
        trf = _dt(2026, 5, 1, 10, 5, 0)
        tsp = _dt(2026, 5, 1, 9, 0, 0)    # TSP older than both
        warnings = check_staleness(2026, 1, psp, trf, tsp)
        self.assertTrue(any(w.downstream_phase == "Phase 5" for w in warnings))

    def test_within_grace_period_no_warning(self):
        psp = _dt(2026, 5, 1, 12, 0, 0)
        trf = _dt(2026, 5, 1, 11, 58, 0)  # 2 min before PSP
        tsp = _dt(2026, 5, 1, 12, 10, 0)
        warnings = check_staleness(2026, 1, psp, trf, tsp, warn_threshold_seconds=300.0)
        self.assertEqual(warnings, [])   # 2 min < 5 min grace period

    def test_none_timestamps_not_warned(self):
        warnings = check_staleness(2026, 1, None, None, None)
        self.assertEqual(warnings, [])

    def test_severity_warning_not_error(self):
        psp = _dt(2026, 5, 1, 12, 0, 0)
        trf = _dt(2026, 5, 1, 11, 0, 0)  # 1h stale
        tsp = _dt(2026, 5, 1, 12, 5, 0)
        warnings = check_staleness(2026, 1, psp, trf, tsp)
        phase3_warn = next((w for w in warnings if w.downstream_phase == "Phase 3"), None)
        self.assertIsNotNone(phase3_warn)
        self.assertEqual(phase3_warn.severity, "warning")  # 1h < 24h → warning

    def test_message_is_human_readable(self):
        psp = _dt(2026, 5, 1, 12, 0, 0)
        trf = _dt(2026, 5, 1, 10, 0, 0)
        warnings = check_staleness(2026, 1, psp, trf, None)
        self.assertGreater(len(warnings[0].message), 20)

    def test_bulk_check_only_returns_teams_with_warnings(self):
        teams_data = [
            {
                "team_id": 1,
                "psp_computed_at": _dt(2026, 5, 1, 12, 0),
                "trf_computed_at": _dt(2026, 5, 1, 12, 5),
                "tsp_computed_at": _dt(2026, 5, 1, 12, 10),
            },   # clean
            {
                "team_id": 2,
                "psp_computed_at": _dt(2026, 5, 2, 12, 0),
                "trf_computed_at": _dt(2026, 5, 1, 10, 0),
                "tsp_computed_at": _dt(2026, 5, 2, 12, 5),
            },   # stale
        ]
        result = check_team_staleness_bulk(2026, teams_data)
        self.assertNotIn(1, result)
        self.assertIn(2, result)

    def test_naive_datetime_handled(self):
        # Naive datetimes should not crash (treated as UTC)
        psp = datetime(2026, 5, 1, 12, 0, 0)   # naive
        trf = datetime(2026, 5, 1, 10, 0, 0)   # naive, 2h before
        warnings = check_staleness(2026, 1, psp, trf, None)
        self.assertGreater(len(warnings), 0)


if __name__ == "__main__":
    unittest.main()
