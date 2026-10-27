"""일반 사건의 Redis 매핑 조회가 사건 ID가 아닌 CCTV ID를 쓰는지 확인.

DB/API/Redis 접속 없이 기존 데이터와 Rule을 보호합니다.
"""

import unittest
from unittest.mock import patch

from backend.app.dashboard import service
from backend.app.integrations import cctv_mapping


class GeneralIncidentMappingTests(unittest.TestCase):
    incident = {
        "id": 2136,
        "incident_no": "OCTV_P2_2136_damage",
        "cctv_id": 3,
        "cctv_name": "일반 CCTV",
        "latitude": 37.1824818,
        "longitude": 127.0958378,
        "region_code": "41597",
        "provider": "UTIC",
        "address": "화성시",
    }

    def test_general_incident_reads_cctv_cache_not_incident_cache(self):
        cached = {
            "weather_grid": {"nx": 62, "ny": 118},
            "water_level": {"status": "NEARBY_STATION_NO_THRESHOLDS"},
            "traffic": {"status": "NEEDS_ROAD_DIRECTION_VERIFICATION"},
        }
        with patch.object(cctv_mapping, "auto_mapping_enabled", return_value=True), \
             patch.object(cctv_mapping, "get_cached_mapping", return_value=cached) as get:
            result = service._mapping_state(self.incident)
        requested = get.call_args.args[0]
        self.assertEqual(requested["id"], 3)
        self.assertEqual(requested["name"], "일반 CCTV")
        self.assertEqual(requested["provider"], "UTIC")
        self.assertEqual(requested["latitude"], self.incident["latitude"])
        self.assertEqual(result["weather"], "GRID_READY")
        self.assertEqual(result["water"], "NEARBY_STATION_NO_THRESHOLDS")
        self.assertEqual(result["traffic"], "NEEDS_ROAD_DIRECTION_VERIFICATION")

    def test_missing_cache_stays_unverified(self):
        with patch.object(cctv_mapping, "auto_mapping_enabled", return_value=True), \
             patch.object(cctv_mapping, "get_cached_mapping", return_value=None):
            self.assertEqual(service._mapping_state(self.incident), {
                "weather": "CACHE_NOT_READY", "water": "CACHE_NOT_READY",
                "traffic": "CACHE_NOT_READY",
            })

    def test_disabled_mapping_does_not_access_redis(self):
        with patch.object(cctv_mapping, "auto_mapping_enabled", return_value=False), \
             patch.object(cctv_mapping, "get_cached_mapping") as get:
            result = service._mapping_state(self.incident)
        get.assert_not_called()
        self.assertEqual(result["weather"], "AUTO_MAPPING_DISABLED")


if __name__ == "__main__":
    unittest.main()
