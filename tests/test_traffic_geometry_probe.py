"""Offline, read-only verification: geometry candidates never imply closure."""
import unittest
from backend.app.integrations.traffic_geometry_probe import (
    query_spatial_link_candidates, compare_with_its, _polyline_distance_m)


class LinkGeometryProbeTests(unittest.TestCase):
    cctv_lat, cctv_lon = 37.20, 127.10

    def good(self, url, params):
        self.assertTrue(url.startswith("https://portal.esrikr.com/arcgis/"))
        self.assertEqual(params["outSR"], 4326)
        if url.endswith("/0/query"):
            return {"features": [{
                "attributes": {"LINK_ID": "1000014301", "ROAD_NAME": "테스트 도로"},
                "geometry": {"paths": [[[127.0999, 37.1999], [127.1001, 37.2001]]]},
            }]}
        return {"features": []}

    def test_same_link_id_yields_candidate_but_not_verified_control(self):
        result = query_spatial_link_candidates(self.cctv_lat, self.cctv_lon, fetch_json=self.good)
        self.assertEqual(result["status"], "SPATIAL_CANDIDATES_FOUND")
        compared = compare_with_its(result, [{"linkId": "1000014301", "roadName": "테스트 도로"}])
        self.assertEqual(compared["status"], "LINK_IDS_MATCHED_DIRECTION_UNVERIFIED")
        self.assertFalse(compared["camera_direction_verified"])
        self.assertFalse(compared["closure_verified"])
        self.assertEqual(compared["matching_links"][0]["link_id"], "1000014301")

    def test_real_arcgis_lowercase_fields_are_accepted(self):
        def lower(url, params):
            self.assertIn("link_id", params["outFields"])
            if url.endswith("/0/query"):
                return {"features": [{
                    "attributes": {"link_id": "1000014301", "road_name": "테스트 도로"},
                    "geometry": {"paths": [[[127.0999, 37.1999], [127.1001, 37.2001]]]},
                }]}
            return {"features": []}
        result = query_spatial_link_candidates(self.cctv_lat, self.cctv_lon, fetch_json=lower)
        self.assertEqual(result["status"], "SPATIAL_CANDIDATES_FOUND")
        self.assertEqual(result["links"][0]["road_name"], "테스트 도로")
        self.assertEqual(result["layers_received"], 4)

    def test_arcgis_error_is_explained_without_response_text(self):
        def bad(url, params):
            return {"error": {"code": 400, "message": "secret server message"}}
        result = query_spatial_link_candidates(self.cctv_lat, self.cctv_lon, fetch_json=bad)
        self.assertEqual(result["status"], "SPATIAL_SOURCE_UNAVAILABLE")
        self.assertEqual(result["layer_checks"][0]["status"], "ARCGIS_ERROR_400")
        self.assertNotIn("secret", str(result))

    def test_partial_source_is_not_misread_as_id_mismatch(self):
        def partial(url, params):
            return {"features": []} if url.endswith("/0/query") else None
        source = query_spatial_link_candidates(self.cctv_lat, self.cctv_lon, fetch_json=partial)
        result = compare_with_its(source, [{"linkId": "1000014301"}])
        self.assertEqual(result["status"], "SPATIAL_RESULT_INCOMPLETE")

    def test_mismatched_link_id_does_not_match_even_same_road(self):
        result = query_spatial_link_candidates(self.cctv_lat, self.cctv_lon, fetch_json=self.good)
        comp = compare_with_its(result, [{"linkId": "1000014302", "roadName": "테스트 도로"}])
        self.assertEqual(comp["status"], "LINK_ID_NOT_MATCHED_OR_DATASET_OUTDATED")
        self.assertEqual(comp["matching_links"], [])

    def test_provider_unavailable_is_not_no_traffic(self):
        result = query_spatial_link_candidates(self.cctv_lat, self.cctv_lon, fetch_json=lambda u,p: None)
        self.assertEqual(result["status"], "SPATIAL_SOURCE_UNAVAILABLE")
        self.assertEqual(result["layers_failed"], 4)

    def test_invalid_projection_is_rejected(self):
        self.assertIsNone(_polyline_distance_m(self.cctv_lat,self.cctv_lon, {
            "paths": [[[950000, 1950000], [950100, 1950100]]]}))

    def test_distance_to_segment_finds_onroad_even_far_from_endpoints(self):
        dist = _polyline_distance_m(self.cctv_lat, self.cctv_lon, {
            "paths": [[[127.098,37.20],[127.102,37.20]]]
        })
        self.assertLess(dist, 1)

    def test_response_partial_never_claims_complete(self):
        def fetch(url, params):
            if url.endswith('/0/query'):
                return {"exceededTransferLimit":True, "features": []}
            return None
        res = query_spatial_link_candidates(self.cctv_lat,self.cctv_lon,fetch_json=fetch)
        self.assertEqual(res['status'],'SPATIAL_RESULT_INCOMPLETE')

if __name__ == '__main__':
    unittest.main()
