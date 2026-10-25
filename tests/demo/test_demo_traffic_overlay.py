"""Regression tests for read-only demo traffic projections."""
import unittest

from backend.app.demo.traffic_overlay import overlay_candidates


def _route(id: int, status: str = "NEEDS_REVIEW"):
    return {
        "id": id,
        "total_score": 60.0 - id,
        "duration_sec": 100 + id,
        "distance_m": 1000 + id,
        "disqualify_reason": None,
        "verification_status": status,
        "navigation_available": True,
        "requires_review": True,
    }


class DemoTrafficOverlayTests(unittest.TestCase):
    def test_three_candidates_simulate_closure_and_delay(self):
        originals = [_route(1), _route(2), _route(3)]
        projected = overlay_candidates(4, originals)
        self.assertEqual([x["id"] for x in projected], [3, 2, 1])
        self.assertEqual(projected[-1]["demo_rank_status"], "EXCLUDED")
        self.assertFalse(projected[-1]["navigation_available"])
        self.assertEqual(projected[1]["demo_rank_status"], "DEPRIORITIZED")
        self.assertTrue(projected[1]["navigation_available"])
        self.assertEqual(originals[0]["navigation_available"], True)
        self.assertFalse(any("demo_traffic" in row for row in originals))

    def test_non_demo_incident_unmodified(self):
        self.assertEqual(overlay_candidates(20, [_route(1), _route(2)]), [_route(1), _route(2)])

    def test_two_candidates_no_forced_exclusion(self):
        result = overlay_candidates(5, [_route(1), _route(2)])
        self.assertNotIn("EXCLUDED", [item.get("demo_rank_status") for item in result])

    def test_single_route_no_forced_impact(self):
        self.assertEqual(overlay_candidates(19, [_route(1)]), [_route(1)])

    def test_real_disqualification_not_reversed(self):
        original = [_route(1), _route(2), _route(3)]
        original[0]["disqualify_reason"] = "확인된 통제"
        original[0]["verification_status"] = "DISQUALIFIED"
        result = overlay_candidates(19, original)
        self.assertEqual(result[-1]["disqualify_reason"], "확인된 통제")
        self.assertFalse(any(row.get("demo_rank_status") == "EXCLUDED" for row in result))


if __name__ == "__main__":
    unittest.main()
