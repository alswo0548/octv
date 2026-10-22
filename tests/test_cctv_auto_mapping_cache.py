"""CCTV 자동 기상 매핑·캐시 회귀 검사. DB·Redis·외부 API 요청 없음."""

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from ai.runtime_queries import create_query_factory, TRAFFIC_FIELDS
from backend.app.integrations import cctv_mapping, weather


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.writes = 0

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, **kwargs):
        if kwargs.get("nx") and key in self.values:
            return False
        self.values[key] = value
        self.writes += 1
        return True

    def eval(self, _script, numkeys, key, token):
        assert numkeys == 1
        if self.values.get(key) == token:
            self.values.pop(key)
            return 1
        return 0


class CctvAutoMappingTests(unittest.TestCase):
    def setUp(self):
        self.cctv = {
            "id": 3, "latitude": 37.1824818,
            "longitude": 127.0958378,
            "region_code": "41597", "provider": "UTIC",
        }
        self.incident = {**self.cctv, "cctv_id": 3}
        self.now = datetime(2026, 10, 22, 0, 3, tzinfo=timezone.utc)
        self.redis = FakeRedis()
        self.redis_patch = patch.object(cctv_mapping, "_redis", return_value=self.redis)
        self.redis_patch.start()
        self.addCleanup(self.redis_patch.stop)

    def test_offline_grid_for_cctv3(self):
        self.assertEqual(cctv_mapping.kma_grid(37.1824818, 127.0958378), (62, 118))

    def test_cache_reuse_and_location_change(self):
        self.assertEqual(cctv_mapping.prepare_cached_mapping(self.cctv), "CREATED")
        self.assertEqual(cctv_mapping.prepare_cached_mapping(self.cctv), "CACHED")
        cached = cctv_mapping.get_cached_mapping(self.cctv)
        self.assertEqual(cached["weather_grid"], {"nx": 62, "ny": 118})
        self.assertEqual(cached["water_level"]["status"], "NEEDS_HYDROLOGY_VERIFICATION")
        self.assertEqual(cached["traffic"]["status"], "NEEDS_ROAD_DIRECTION_VERIFICATION")
        moved = {**self.cctv, "latitude": 37.5}
        self.assertIsNone(cctv_mapping.get_cached_mapping(moved))
        self.assertEqual(cctv_mapping.prepare_cached_mapping(moved), "CREATED")
        self.assertIsNone(cctv_mapping.get_cached_mapping(self.cctv))

    def test_missing_redis_uses_deterministic_grid(self):
        with patch.object(cctv_mapping, "_redis", side_effect=OSError("offline")):
            value = cctv_mapping.weather_request_for(self.incident)
        self.assertTrue(value["mapped"])
        self.assertEqual((value["params"]["nx"], value["params"]["ny"]), (62, 118))

    def test_invalid_coordinates_fail_closed(self):
        self.assertEqual(cctv_mapping.weather_request_for({**self.incident, "latitude": 999}), {"mapped": False})

    def test_factory_auto_weather_but_water_traffic_remain_unknown(self):
        factory = create_query_factory({"cctvs": {}}, {
            "OCTV_AUTO_MAPPING_ENABLED": "1", "WEATHER_API_KEY": "TEST_KEY",
        })
        query = factory(self.incident, self.now)
        self.assertTrue(query["weather"]["mapped"])
        self.assertEqual((query["weather"]["params"]["nx"], query["weather"]["params"]["ny"]), (62, 118))
        self.assertFalse(query["water_level"]["mapped"])
        for field in TRAFFIC_FIELDS:
            self.assertFalse(query["traffic"][field]["mapped"])

    def test_missing_api_key_keeps_weather_unmapped(self):
        factory = create_query_factory({"cctvs": {}}, {"OCTV_AUTO_MAPPING_ENABLED": "1"})
        self.assertFalse(factory(self.incident, self.now)["weather"]["mapped"])

    def test_existing_verified_manual_setting_not_overwritten(self):
        factory = create_query_factory({"cctvs": {"3": {"weather": {
            "mapped": True, "publication_delay_min": 5, "max_age_sec": 3600,
            "url": "https://example.test/manual", "params": {"nx": 1, "ny": 2},
        }}}}, {"OCTV_AUTO_MAPPING_ENABLED": "1", "WEATHER_API_KEY": "T"})
        query = factory(self.incident, self.now)["weather"]
        self.assertEqual(query["url"], "https://example.test/manual")
        self.assertEqual(query["params"]["nx"], 1)

    def test_weather_payload_cache_shared_by_same_grid_and_base_time(self):
        factory = create_query_factory({"cctvs": {}}, {
            "OCTV_AUTO_MAPPING_ENABLED": "1", "WEATHER_API_KEY": "SECRET_KEY",
        })
        query = factory(self.incident, self.now)["weather"]
        payload = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": [
            {"category": "RN1", "baseDate": "20261022", "baseTime": "0800", "obsrValue": "3"},
            {"category": "WSD", "baseDate": "20261022", "baseTime": "0800", "obsrValue": "5"},
        ]}}}}
        with patch.dict("os.environ", {"OCTV_AUTO_MAPPING_ENABLED": "1"}), patch.object(weather, "get_json", return_value=payload) as fetch:
            first = weather.fetch_observations(query)
            other_cctv = {**self.incident, "id": 4, "cctv_id": 4}
            same_grid_query = factory(other_cctv, self.now)["weather"]
            second = weather.fetch_observations(same_grid_query)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(first["rainfall_mm"]["status"], "OK")
        self.assertEqual(second["wind_speed_mps"]["status"], "OK")
        stored = json.dumps(self.redis.values)
        self.assertNotIn("SECRET_KEY", stored)
        self.assertTrue(all("SECRET_KEY" not in key for key in self.redis.values))

    def test_cache_revalidates_observation_age(self):
        factory = create_query_factory({"cctvs": {}}, {
            "OCTV_AUTO_MAPPING_ENABLED": "1", "WEATHER_API_KEY": "T",
        })
        query = factory(self.incident, self.now)["weather"]
        payload = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": [
            {"category": "RN1", "baseDate": "20261021", "baseTime": "0800", "obsrValue": "3"},
            {"category": "WSD", "baseDate": "20261021", "baseTime": "0800", "obsrValue": "5"},
        ]}}}}
        with patch.dict("os.environ", {"OCTV_AUTO_MAPPING_ENABLED": "1"}), patch.object(weather, "get_json", return_value=payload):
            first = weather.fetch_observations(query)
            second = weather.fetch_observations(query)
        self.assertEqual(first["rainfall_mm"]["status"], "STALE")
        self.assertEqual(second["wind_speed_mps"]["status"], "STALE")


if __name__ == "__main__":
    unittest.main()
