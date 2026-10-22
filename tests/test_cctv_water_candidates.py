"""CCTV 수위 후보 진단: DB/API/Redis 실제 요청 없이 단위 테스트."""

import unittest
from unittest.mock import patch

from scripts import check_cctv_water_candidates as script


class CctvWaterCandidateTests(unittest.TestCase):
    def setUp(self):
        self.cctv = {
            'id': 3, 'name': '동탄터널',
            'latitude': 37.1824818, 'longitude': 127.0958378,
        }
        self.station = {
            'wlobscd': '1018683', 'obsnm': '가상관측소', 'rvnm': '가상하천',
            'lat': 37.185, 'lon': 127.096,
            'wrnwl': 8.5, 'almwl': 10.5, 'srswl': 13.3,
        }

    def test_close_station_is_candidate_not_verified(self):
        report = script.build_report(self.cctv, [self.station])
        self.assertEqual(report['status'], 'OFFICIAL_GEO_CANDIDATES_UNVERIFIED')
        self.assertEqual(report['nearby_candidates'][0]['station_id'], '1018683')
        self.assertFalse(report['water_risk_mapping_confirmed'])
        self.assertFalse(report['nearby_candidates'][0]['same_river_or_flood_impact_verified'])

    def test_dms_station_appears_as_candidate_not_confirmed_flood_risk(self):
        # 소수점 좌표와 DMS 좌표는 같은 관측소를 가리켜야 함.
        station = {**self.station, 'lat': '37-11-06', 'lon': '127-05-45'}
        report = script.build_report(self.cctv, [station])
        self.assertEqual(report['status'], 'OFFICIAL_GEO_CANDIDATES_UNVERIFIED')
        self.assertEqual(len(report['nearby_candidates']), 1)
        self.assertFalse(report['water_risk_mapping_confirmed'])

    def test_no_nearby_is_not_safe_or_no_impact(self):
        station = {**self.station, 'lat': 35.1, 'lon': 129.0}
        report = script.build_report(self.cctv, [station])
        self.assertEqual(report['status'], 'NO_STATION_WITHIN_SEARCH_RADIUS')
        self.assertEqual(report['nearby_candidates'], [])
        self.assertEqual(len(report['nearest_station_any_distance']), 1)
        self.assertFalse(report['water_risk_mapping_confirmed'])

    def test_unknown_coordinates_not_classified_as_no_nearby(self):
        report = script.build_report(self.cctv, [{**self.station, 'lat': None}])
        self.assertEqual(report['status'], 'STATION_COORDINATES_UNAVAILABLE')
        self.assertFalse(report['water_risk_mapping_confirmed'])

    def test_missing_key_does_not_query_db_or_api(self):
        with patch.object(script.diag, 'read_cctv') as get_cctv, \
             patch.object(script, '_read_station_catalog') as get_catalog:
            report = script.inspect(3, '')
        self.assertEqual(report['status'], 'MISSING_WATER_LEVEL_API_KEY')
        get_cctv.assert_not_called()
        get_catalog.assert_not_called()

    def test_catalog_cache_is_reused(self):
        with patch.object(script.diag, 'read_cctv', return_value=self.cctv), \
             patch.object(script, '_read_station_catalog', return_value=([self.station], 'OK_CACHED')) as catalog:
            report = script.inspect(3, 'SECRET', redis_client=object())
        self.assertEqual(catalog.call_count, 1)
        self.assertEqual(report['catalog_source'], 'OK_CACHED')
        self.assertNotIn('SECRET', str(report))

    def test_api_error_retains_error_not_no_nearby(self):
        with patch.object(script.diag, 'read_cctv', return_value=self.cctv), \
             patch.object(script, '_read_station_catalog', return_value=(None, 'PROVIDER_RESPONSE_ERROR')):
            report = script.inspect(3, 'SECRET')
        self.assertEqual(report['status'], 'PROVIDER_RESPONSE_ERROR')
        self.assertNotIn('nearby_candidates', report)


if __name__ == '__main__':
    unittest.main()
