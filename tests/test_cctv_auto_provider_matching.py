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

    def test_station_uses_radius_and_no_camera_direction(self):
        ok = auto_match_providers.choose_water_station(self.cctv, [self.station()])
        self.assertEqual(ok["status"], "VERIFIED_EXACT_COLOCATION")
        self.assertEqual(ok["station_id"], "1018683")
        different = auto_match_providers.choose_water_station(self.cctv, [self.station(obsnm="다른 관측소")])
        self.assertEqual(different["status"], "NEARBY_STATION_WITH_THRESHOLDS")
        far = auto_match_providers.choose_water_station(self.cctv, [self.station(lat=37.20)])
        self.assertEqual(far["status"], "NEARBY_STATION_WITH_THRESHOLDS")

    def test_missing_and_invalid_official_thresholds_fail_closed(self):
        for value in (None, "-", "NaN", "0"):
            with self.subTest(value=value):
                result = auto_match_providers.choose_water_station(
                    self.cctv, [self.station(almwl=value)])
                self.assertEqual(result["status"], "NEARBY_STATION_NO_THRESHOLDS")

    def test_ambiguous_name_never_auto_confirmed(self):
        result = auto_match_providers.choose_water_station(
            self.cctv, [self.station(), self.station(wlobscd="1018684")])
        self.assertEqual(result["status"], "AMBIGUOUS_NEARBY_STATIONS")

    def test_error_code_941_is_not_empty_success(self):
        with patch.object(auto_match_providers, "_safe_get_json", return_value={"code": "941", "message": "unauthorized"}):
            result = auto_match_providers.find_water_mapping(self.cctv, "FAKE")
        self.assertEqual(result["status"], "PROVIDER_REJECTED_941")

    def test_cached_station_catalog_contains_no_secret(self):
        with patch.object(auto_match_providers, "_safe_get_json", return_value={"content": [self.station()]}) as call:
            result = auto_match_providers.find_water_mapping(self.cctv, "SECRET", self.redis)
            again = auto_match_providers.find_water_mapping(self.cctv, "SECRET", self.redis)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["status"], "VERIFIED_EXACT_COLOCATION")
        self.assertEqual(again["status"], "VERIFIED_EXACT_COLOCATION")
        self.assertNotIn("SECRET", json.dumps(self.redis.values))
        self.assertNotIn("api.hrfco.go.kr", json.dumps(self.redis.values))

    def test_hydrology_dms_coordinates_converted_to_decimal(self):
        # 실제 제공기관 좌표 예: 위도 37-10-56.93448, 경도 127-05-45.01608
        station = self.station(lat="37-10-56.93448", lon="127-05-45.01608")
        parsed = auto_match_providers._canonical_station(station)
        self.assertAlmostEqual(parsed["latitude"], self.cctv["latitude"], places=6)
        self.assertAlmostEqual(parsed["longitude"], self.cctv["longitude"], places=6)
        confirmed = auto_match_providers.choose_water_station(self.cctv, [station])
        self.assertEqual(confirmed["status"], "VERIFIED_EXACT_COLOCATION")

    def test_invalid_dms_does_not_make_a_fake_station(self):
        for lat, lon in (("37-60-00", "127-05-00"),
                         ("37-12-60", "127-05-00"),
                         ("91-00-00", "127-05-00"),
                         ("37-12-00", "181-00-00"),
                         ("bad-value", "127-05-00")):
            with self.subTest(lat=lat, lon=lon):
                self.assertIsNone(auto_match_providers._canonical_station(
                    self.station(lat=lat, lon=lon)))
        status = auto_match_providers.choose_water_station(self.cctv,
                [self.station(lat="37-60-00")])
        self.assertEqual(status["status"], "STATION_COORDINATES_UNAVAILABLE")

    def test_dms_catalog_cached_once_without_keys(self):
        with patch.object(auto_match_providers, "_safe_get_json",
                          return_value={"content": [self.station(lat="37-10-56.93448",
                                                                   lon="127-05-45.01608")]}) as fetch:
            first = auto_match_providers.find_water_mapping(self.cctv, "SECRET", self.redis)
            second = auto_match_providers.find_water_mapping(self.cctv, "SECRET", self.redis)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(first["status"], "VERIFIED_EXACT_COLOCATION")
        self.assertEqual(second, first)
        self.assertNotIn("SECRET", json.dumps(self.redis.values))
        self.assertTrue(all("station_catalog:v1" not in key for key in self.redis.values))

    def test_legacy_empty_catalog_cache_is_ignored_without_deleting_it(self):
        legacy_key = "octv:context:hrfco:station_catalog:v1"
        self.redis.values[legacy_key] = "[]"
        with patch.object(auto_match_providers, "_safe_get_json",
                          return_value={"content": [self.station(lat="37-10-56.93448",
                                                                   lon="127-05-45.01608")]}) as fetch:
            result = auto_match_providers.find_water_mapping(self.cctv, "SECRET", self.redis)
        self.assertEqual(result["status"], "VERIFIED_EXACT_COLOCATION")
        fetch.assert_called_once()
        self.assertEqual(self.redis.values[legacy_key], "[]")
        self.assertIn(auto_match_providers.CATALOG_CACHE_KEY, self.redis.values)

    def test_unparseable_stations_are_not_cached_as_empty_catalog(self):
        with patch.object(auto_match_providers, "_safe_get_json",
                          return_value={"content": [self.station(lat="bad")]}):
            actual = auto_match_providers.find_water_mapping(self.cctv, "SECRET", self.redis)
        self.assertEqual(actual["status"], "STATION_COORDINATES_UNAVAILABLE")
        self.assertNotIn(auto_match_providers.CATALOG_CACHE_KEY, self.redis.values)

    def test_previously_cached_no_nearby_mapping_is_invalidated_by_version(self):
        stale = {"version": 3, "fingerprint": cctv_mapping._fingerprint(self.cctv),
                 "weather_grid": {"nx": 62, "ny": 118},
                 "water_level": {"reason": "NO_NEARBY_STATION"}}
        self.redis.values["octv:context:mapping:v3:3"] = json.dumps(stale)
        self.assertIsNone(cctv_mapping.get_cached_mapping(self.cctv))
        self.assertEqual(cctv_mapping.MAPPING_VERSION, 6)

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

    def test_its_missing_link_geometry_is_unknown_not_no_nearby(self):
        # 공식 ITS 소통정보에는 링크의 좌표가 필수 제공되지 않습니다.
        payload = {"response": {"resultCode": "0", "data": [
            {"linkId": "94123", "roadName": "경부고속도로", "drcType": "up",
             "speed": "35", "createdDate": "20261022140000"},
        ]}}
        with patch.object(auto_match_providers, "_safe_get_json", return_value=payload) as fetch:
            actual = auto_match_providers.find_traffic_mapping(self.cctv, "SECRET", self.redis)
            again = auto_match_providers.find_traffic_mapping(self.cctv, "SECRET", self.redis)
        self.assertEqual(actual["status"], "LINK_GEOMETRY_UNAVAILABLE")
        self.assertEqual(actual["records_without_geometry"], 1)
        self.assertEqual(again, actual)
        self.assertEqual(fetch.call_count, 1)

    def test_same_road_name_without_geometry_is_only_unverified_candidate(self):
        camera = {**self.cctv, "name": "경부고속도로 동탄", "address": "화성시"}
        payload = {"response": {"resultCode": "0", "data": [
            {"linkId": "99", "roadName": "경부고속도로", "drcType": "up"},
        ]}}
        with patch.object(auto_match_providers, "_safe_get_json", return_value=payload):
            result = auto_match_providers.find_traffic_mapping(camera, "SECRET")
        self.assertEqual(result["status"], "DIRECTION_UNVERIFIED")
        self.assertFalse(result["candidates"][0]["geometry_verified"])
        self.assertIsNone(result["candidates"][0]["distance_m"])

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
