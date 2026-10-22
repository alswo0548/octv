"""외부 API 호출/DB 변경 없는 CCTV 외부 데이터 자동 후보·폴백 회귀검사."""

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from ai.runtime_queries import create_query_factory, TRAFFIC_FIELDS
from backend.app.integrations import cctv_mapping, auto_match_providers
from tests.test_cctv_auto_mapping_cache import FakeRedis


class AutoProviderMatchingTests(unittest.TestCase):
    def setUp(self):
        self.cctv = {
            "id": 3, "cctv_id": 3,
            "latitude": 37.1824818, "longitude": 127.0958378,
            "region_code": "41597", "provider": "UTIC",
            "name": "한강대교", "cctv_name": "한강대교", "address": "한강대교",
        }
        self.now = datetime(2026, 10, 22, 1, 0, tzinfo=timezone.utc)
        self.redis = FakeRedis()
        p = patch.object(cctv_mapping, "_redis", return_value=self.redis)
        p.start()
        self.addCleanup(p.stop)

    def station(self, **changes):
        station = {"wlobscd": "1018683", "obsnm": "한강대교",
                   "rvnm": "한강", "lat": 37.1824818, "lon": 127.0958378,
                   "wrnwl": 3.1, "almwl": 4.5, "srswl": 6.0}
        return {**station, **changes}

    def test_station_name_and_proximity_are_both_required(self):
        ok = auto_match_providers.choose_water_station(self.cctv, [self.station()])
        self.assertEqual(ok["status"], "VERIFIED_EXACT_COLOCATION")
        self.assertEqual(ok["station_id"], "1018683")
        different = auto_match_providers.choose_water_station(self.cctv, [self.station(obsnm="다른 관측소")])
        self.assertEqual(different["status"], "REVIEW_REQUIRED")
        far = auto_match_providers.choose_water_station(self.cctv, [self.station(lat=37.20)])
        self.assertNotEqual(far["status"], "VERIFIED_EXACT_COLOCATION")

    def test_missing_and_invalid_official_thresholds_fail_closed(self):
        for value in (None, "-", "NaN", "0"):
            with self.subTest(value=value):
                result = auto_match_providers.choose_water_station(
                    self.cctv, [self.station(almwl=value)])
                self.assertNotEqual(result["status"], "VERIFIED_EXACT_COLOCATION")

    def test_ambiguous_name_never_auto_confirmed(self):
        result = auto_match_providers.choose_water_station(
            self.cctv, [self.station(), self.station(wlobscd="1018684")])
        self.assertEqual(result["status"], "REVIEW_REQUIRED")

    def test_error_code_941_is_not_empty_success(self):
        with patch.object(auto_match_providers, "_safe_get_json", return_value={"code": "941", "message": "unauthorized"}):
            result = auto_match_providers.find_water_mapping(self.cctv, "FAKE")
        self.assertEqual(result["status"], "API_UNAVAILABLE_OR_UNAPPROVED")

    def test_cached_station_catalog_contains_no_secret(self):
        with patch.object(auto_match_providers, "_safe_get_json", return_value={"content": [self.station()]}) as call:
            result = auto_match_providers.find_water_mapping(self.cctv, "SECRET", self.redis)
            again = auto_match_providers.find_water_mapping(self.cctv, "SECRET", self.redis)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["status"], "VERIFIED_EXACT_COLOCATION")
        self.assertEqual(again["status"], "VERIFIED_EXACT_COLOCATION")
        self.assertNotIn("SECRET", json.dumps(self.redis.values))
        self.assertNotIn("api.hrfco.go.kr", json.dumps(self.redis.values))

    def test_traffic_nearby_link_still_requires_direction(self):
        payload = {"response": {"resultCode": "0", "data": [
            {"linkId": "999", "roadName": "구리로", "drcType": "1",
             "coordx": "127.0958378", "coordy": "37.1824818"}
        ]}}
        with patch.object(auto_match_providers, "_safe_get_json", return_value=payload) as call:
            result = auto_match_providers.find_traffic_mapping(self.cctv, "SECRET", self.redis)
            cached = auto_match_providers.find_traffic_mapping(self.cctv, "SECRET", self.redis)
        self.assertEqual(result["status"], "DIRECTION_UNVERIFIED")
        self.assertEqual(result["candidates"][0]["link_id"], "999")
        self.assertEqual(cached, result)
        self.assertEqual(call.call_count, 1)
        self.assertNotIn("SECRET", json.dumps(self.redis.values))

    def test_prewarm_saved_mapping_then_factory_uses_water_auto(self):
        env = {"OCTV_AUTO_MAPPING_ENABLED": "1", "WATER_LEVEL_API_KEY": "SECRET",
               "WEATHER_API_KEY": "WEATHER", "TRAFFIC_API_KEY": "TRAFFIC"}
        with patch.dict("os.environ", env), \
             patch.object(auto_match_providers, "_safe_get_json") as fetch:
            fetch.side_effect = [
                {"content": [self.station()]},
                {"response": {"resultCode": "0", "data": []}},
            ]
            status = cctv_mapping.prepare_cached_mapping(self.cctv)
            factory = create_query_factory({"cctvs": {}}, env)
            queries = factory(self.cctv, self.now)
        self.assertEqual(status, "CREATED")
        self.assertTrue(queries["water_level"]["mapped"])
        self.assertEqual(queries["water_level"]["spec"]["station_id"], "1018683")
        self.assertIn("SECRET", queries["water_level"]["url"])  # 요청 시에만 인증 사용
        self.assertNotIn("SECRET", json.dumps(self.redis.values))
        self.assertTrue(queries["weather"]["mapped"])
        for field in TRAFFIC_FIELDS:
            self.assertFalse(queries["traffic"][field]["mapped"])

    def test_auto_failure_retains_existing_manual_fallback(self):
        env = {"OCTV_AUTO_MAPPING_ENABLED": "1", "WEATHER_API_KEY": "W",
               "WATER_LEVEL_API_KEY": "S"}
        fallback = {"weather": {"mapped": True, "publication_delay_min": 10,
                                "max_age_sec": 3600, "url": "https://example.test/manual-weather",
                                "params": {"nx": 1, "ny": 2}}}
        invalid_location = {**self.cctv, "latitude": 999}
        factory = create_query_factory({"cctvs": {"3": fallback}}, env)
        value = factory(invalid_location, self.now)["weather"]
        self.assertEqual(value["url"], "https://example.test/manual-weather")

    def test_cache_location_and_name_fingerprint(self):
        with patch.dict("os.environ", {"OCTV_AUTO_MAPPING_ENABLED": "0"}):
            self.assertEqual(cctv_mapping.prepare_cached_mapping(self.cctv), "CREATED")
        moved = {**self.cctv, "name": "다른 CCTV", "cctv_name": "다른 CCTV"}
        self.assertIsNone(cctv_mapping.get_cached_mapping(moved))

    def test_no_key_means_no_api_calls_and_no_mapping(self):
        with patch.object(auto_match_providers, "_safe_get_json") as fetch:
            self.assertEqual(auto_match_providers.find_water_mapping(self.cctv, "")["status"], "MISSING_KEY")
            self.assertEqual(auto_match_providers.find_traffic_mapping(self.cctv, "")["status"], "MISSING_KEY")
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
