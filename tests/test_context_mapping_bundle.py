"""신규 Context 참고정보·ITS JSON 분기·캐시 변경 테스트 (외부 요청 없음)."""

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from ai.contracts import ContextSnapshot
from ai.risk_priority.rules import RISK_POLICIES, assess
from ai.runtime_queries import create_query_factory
from backend.app.integrations import cctv_mapping as cm, auto_match_providers as providers
from tests.test_cctv_auto_mapping_cache import FakeRedis


class ContextReferenceTests(unittest.TestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.cctv = {
            "id": 3, "cctv_id": 3, "name": "동탄터널", "cctv_name": "동탄터널",
            "latitude": 37.1824818, "longitude": 127.0958378,
            "region_code": "41597", "provider": "UTIC", "address": "화성시",
        }
        self.patcher = patch.object(cm, "_redis", return_value=self.redis)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        # 활성화 상태도 Redis 지문의 일부라 검증 동안 고정합니다.
        self.env_patcher = patch.dict('os.environ', {'OCTV_AUTO_MAPPING_ENABLED': '1'})
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

    def test_cache_status_is_visible_but_never_marked_ok(self):
        with patch.dict('os.environ', {"OCTV_AUTO_MAPPING_ENABLED": "1"}), \
             patch.object(providers, "find_water_mapping", return_value={
                 "status": "REVIEW_REQUIRED", "candidates": [
                     {"station_id": "1101641", "distance_m": 2097, "name": "화성시(느티교)"}
                 ]}), \
             patch.object(providers, "find_traffic_mapping", return_value={
                 "status": "LINK_GEOMETRY_UNAVAILABLE", "candidates": [
                     {"link_id": "2345678910", "distance_m": None, "road_name": "국도1호선"}
                 ]}):
            self.assertEqual(cm.prepare_cached_mapping(self.cctv), "CREATED")
        refs = cm.mapping_reference_for(self.cctv)
        self.assertEqual(refs["water_station_mapping"]["status"], "REVIEW_REQUIRED")
        self.assertEqual(refs["traffic_link_mapping"]["status"], "REVIEW_REQUIRED")
        self.assertFalse(refs["water_station_mapping"]["flood_impact_verified"])
        self.assertFalse(refs["traffic_link_mapping"]["road_direction_verified"])
        self.assertIsNone(refs["traffic_link_mapping"]["value"])
        self.assertNotIn('url', json.dumps(refs))

        env = {"OCTV_AUTO_MAPPING_ENABLED": "1", "WEATHER_API_KEY": "WX_SECRET",
               "WATER_LEVEL_API_KEY": "WATER_SECRET", "TRAFFIC_API_KEY": "ITS_SECRET"}
        factory = create_query_factory({"cctvs": {}}, env)
        prepared = factory(self.cctv, datetime.now(timezone.utc))
        self.assertEqual(prepared["mapping_references"], refs)
        self.assertFalse(prepared["water_level"]["mapped"])
        self.assertTrue(all(not q.get('mapped') for q in prepared['traffic'].values()
                            if isinstance(q, dict)))
        self.assertNotIn('SECRET', json.dumps(refs))

    def test_missing_cache_is_not_safe(self):
        result = cm.mapping_reference_for(self.cctv)
        self.assertEqual(result['water_station_mapping']['status'], 'NO_MAPPING')
        self.assertEqual(result['traffic_link_mapping']['mapping_reason'], 'CACHE_NOT_READY')
        self.assertIsNone(result['water_station_mapping']['value'])

    def test_failed_provider_is_error_not_no_traffic(self):
        with patch.dict('os.environ', {"OCTV_AUTO_MAPPING_ENABLED": "1"}), \
             patch.object(providers, 'find_water_mapping', return_value={
                 'status': 'PROVIDER_RESPONSE_ERROR', 'candidates': []}), \
             patch.object(providers, 'find_traffic_mapping', return_value={
                 'status': 'API_UNAVAILABLE_OR_UNKNOWN_SCHEMA', 'candidates': []}):
            self.assertEqual(cm.prepare_cached_mapping(self.cctv), 'CREATED')
        refs = cm.mapping_reference_for(self.cctv)
        self.assertEqual(refs['water_station_mapping']['status'], 'ERROR')
        self.assertEqual(refs['traffic_link_mapping']['status'], 'ERROR')

    def test_unverified_references_do_not_change_risk_score(self):
        context = ContextSnapshot(1, datetime.now(timezone.utc), {}, ())
        first = assess(context, RISK_POLICIES['flood'])
        context.measurements.update({
            'traffic_link_mapping': {'value': None, 'status': 'REVIEW_REQUIRED'},
            'water_station_mapping': {'value': None, 'status': 'REVIEW_REQUIRED'},
        })
        second = assess(context, RISK_POLICIES['flood'])
        self.assertEqual(first['risk_score'], second['risk_score'])
        self.assertEqual(first['risk_level'], second['risk_level'])

    def test_cache_fingerprint_invalidates_renamed_cctv(self):
        with patch.dict('os.environ', {"OCTV_AUTO_MAPPING_ENABLED": "0"}):
            self.assertEqual(cm.prepare_cached_mapping(self.cctv), 'CREATED')
        self.assertIsNone(cm.get_cached_mapping({**self.cctv, 'name': '새 이름', 'cctv_name': '새 이름'}))

    def test_nested_its_body_supported_but_error_not_empty(self):
        payload = {'response': {'header': {'resultCode': '0'},
                                'body': {'items': {'item': [{'linkId': '1234567890'}]}}}}
        self.assertEqual(providers._traffic_records(payload), [{'linkId': '1234567890'}])
        self.assertIsNone(providers._traffic_records({'response': {
            'header': {'resultCode': '1'}, 'body': {'items': {'item': []}}}}))
        self.assertIsNone(providers._traffic_records({'code': '941', 'data': []}))

    def test_its_cache_reacts_to_name_change(self):
        payload = {'response': {'resultCode': '0', 'data': [
            {'linkId': '1234567890', 'roadName': '국도1호선', 'drcType': ''}]}}
        with patch.object(providers, '_safe_get_json', return_value=payload) as fetch:
            first = providers.find_traffic_mapping(self.cctv, 'KEY', self.redis)
            self.assertEqual(first['status'], 'LINK_GEOMETRY_UNAVAILABLE')
            providers.find_traffic_mapping({**self.cctv, 'name':'국도1호선 CCTV'}, 'KEY', self.redis)
        self.assertEqual(fetch.call_count, 2)


if __name__ == '__main__':
    unittest.main()
