import unittest
from copy import deepcopy
from backend.app.demo.traffic_overlay import overlay_candidates


def route(n, score, status="VERIFIED"):
    return dict(id=n, route_name=f"경로 {n}", duration_sec=600+n*60, distance_m=2000+n*200,
                total_score=score, verification_status=status,
                disqualify_reason=None, navigation_available=True, requires_review=False,
                route_path_json={"type": "LineString", "coordinates": [[127.0, 37.5], [127.01, 37.51]]})


class TrafficOverlayTests(unittest.TestCase):
    def apply(self, routes):
        return overlay_candidates(routes, duration_scale_sec=1800, distance_scale_m=20000)

    def test_three_routes_preserve_original(self):
        original = [route(1, 70), route(2, 65), route(3, 60)]
        frozen = deepcopy(original)
        output = self.apply(original)
        self.assertEqual(original, frozen)
        a = next(x for x in output if x["id"] == 1)
        b = next(x for x in output if x["id"] == 2)
        self.assertEqual(a["demo_rank_status"], "SIMULATED_EXCLUDED")
        self.assertEqual(a["navigation_available"], True)
        self.assertEqual(a["total_score"], 70)
        self.assertEqual(a["demo_traffic"]["point"], [127.01, 37.51])
        self.assertEqual(b["demo_duration_sec"], original[1]["duration_sec"]+1800)
        self.assertNotEqual(b["demo_total_score"], b["total_score"])
        self.assertEqual(output[0]["id"], 3)

    def test_two_routes_no_forced_closure(self):
        out = self.apply([route(1, 70), route(2, 65)])
        self.assertFalse(any(x.get("demo_rank_status") == "SIMULATED_EXCLUDED" for x in out))

    def test_real_disqualification_stays_real(self):
        r = [route(1, 70), route(2, 65), route(3, 60)]
        r[0]["verification_status"] = "DISQUALIFIED"
        r[0]["disqualify_reason"] = "실제 통제"
        result = self.apply(r)
        self.assertEqual(result[-1]["id"], 1)
        self.assertNotIn("demo_traffic", result[-1])

    def test_empty_and_one_route(self):
        self.assertEqual(self.apply([]), [])
        self.assertEqual(self.apply([route(1, 70)]), [route(1, 70)])

    def test_invalid_scales_rejected(self):
        with self.assertRaises(ValueError):
            overlay_candidates([route(1, 70), route(2, 65)], duration_scale_sec=0, distance_scale_m=20000)


if __name__ == "__main__":
    unittest.main()
