"""Read-only dashboard MCP refresh cache (no network or DB dependency)."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.dashboard import live_external


class DashboardLiveExternalTests(unittest.TestCase):
    def setUp(self):
        live_external._CACHE.clear()

    def tearDown(self):
        live_external._CACHE.clear()

    def test_one_live_fetch_is_reused_without_retry_storm(self):
        now = datetime.now(timezone.utc)
        snap = SimpleNamespace(incident_id=2136, captured_at=now, measurements={
            "rainfall_mm": {"status": "OK", "value": 0},
            "water_level_m": {"status": "OK", "value": 0.84},
        })
        with patch.object(live_external, "_query_mcp", return_value=snap) as provider:
            first = live_external.latest_context(2136)
            second = live_external.latest_context(2136)
        self.assertEqual(first[1], "OK")
        self.assertEqual(second[1], "OK")
        self.assertIs(first[0], snap)
        self.assertIs(first[0], second[0])
        provider.assert_called_once_with(2136)

    def test_provider_failure_is_not_a_success_or_fake_zero(self):
        with patch.object(live_external, "_query_mcp", side_effect=RuntimeError("secret-url")) as provider:
            first = live_external.latest_context(2136)
            second = live_external.latest_context(2136)
        self.assertIsNone(first[0])
        self.assertEqual(first[1], "FAILED")
        self.assertEqual(second[1], "FAILED")
        provider.assert_called_once_with(2136)

    def test_wrong_incident_context_cannot_be_displayed(self):
        wrong = SimpleNamespace(incident_id=99, captured_at=datetime.now(timezone.utc), measurements={})
        with patch.object(live_external, "_query_mcp", return_value=wrong):
            snapshot, status, _ = live_external.latest_context(2136)
        self.assertIsNone(snapshot)
        self.assertEqual(status, "FAILED")

    def test_nearby_events_are_reference_only(self):
        self.assertIsNone(live_external.nearby_reference_count({
            "traffic_nearby_events": {"status": "NO_MAPPING", "value": 4}
        }))
        self.assertEqual(live_external.nearby_reference_count({
            "traffic_nearby_events": {"status": "REFERENCE_ONLY", "value": 0}
        }), 0)
        self.assertIsNone(live_external.nearby_reference_count({
            "traffic_nearby_events": {"status": "REFERENCE_ONLY", "value": True}
        }))

    def test_expired_cache_refreshes(self):
        snap = SimpleNamespace(incident_id=3, captured_at=datetime.now(timezone.utc), measurements={})
        with patch.object(live_external, "_query_mcp", return_value=snap) as provider:
            live_external.latest_context(3)
            old = live_external._CACHE[3]
            live_external._CACHE[3] = (old[0] - 1000, *old[1:])
            live_external.latest_context(3)
        self.assertEqual(provider.call_count, 2)


if __name__ == "__main__":
    unittest.main()
