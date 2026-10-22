"""공식 하천명 메타데이터 교차 확인: DB/Redis/HTTP 실호출 없는 단위 테스트."""

import unittest
from unittest.mock import Mock, patch

from scripts import check_cctv_station_rivers as script


class OfficialRiverMetadataTests(unittest.TestCase):
    def setUp(self):
        self.station = {
            'wlobscd': '1101641', 'obsnm': '화성시(느티교)', 'lat': 37.185,
            'lon': 127.096, 'wrnwl': '1.0', 'almwl': '2.0', 'srswl': '3.0',
        }
        self.report = {
            'status': 'OFFICIAL_GEO_CANDIDATES_UNVERIFIED',
            'cctv_id': 3,
            'nearby_candidates': [{
                'station_id': '1101641', 'station_name': '화성시(느티교)',
                'distance_m': 2097, 'same_river_or_flood_impact_verified': False,
            }],
            'water_risk_mapping_confirmed': False,
        }
        self.official = {'status': 'OFFICIAL_GIS_RESPONSE_RECEIVED', 'rows': [{
            'station_id': '1101641', 'station_name': '화성시(느티교)',
            'river': '오산천', 'latitude': 37.185, 'longitude': 127.096,
        }]}

    def test_same_id_name_coordinates_only_verifies_river_name(self):
        result = script.add_river_evidence(self.report, [self.station], self.official)
        first = result['nearby_candidates'][0]
        self.assertEqual(first['confirmed_river_name'], '오산천')
        self.assertEqual(first['river_name_evidence'], 'OFFICIAL_ID_NAME_COORDINATES_MATCH')
        self.assertFalse(first['same_river_or_flood_impact_verified'])
        self.assertFalse(result['water_risk_mapping_confirmed'])
        self.assertFalse(result['cctv_flood_impact_verified'])
        self.assertNotIn('confirmed_river_name', self.report['nearby_candidates'][0])

    def test_same_name_but_different_station_id_not_accepted(self):
        bad = {**self.official, 'rows': [{**self.official['rows'][0], 'station_id': '1101645'}]}
        result = script.add_river_evidence(self.report, [self.station], bad)
        self.assertIsNone(result['nearby_candidates'][0]['confirmed_river_name'])

    def test_coordinate_mismatch_rejected(self):
        bad = {**self.official, 'rows': [{**self.official['rows'][0], 'latitude': 37.3}]}
        result = script.add_river_evidence(self.report, [self.station], bad)
        self.assertEqual(result['nearby_candidates'][0]['river_name_evidence'], 'STATION_COORDINATE_MISMATCH')

    def test_name_mismatch_rejected(self):
        bad = {**self.official, 'rows': [{**self.official['rows'][0], 'station_name': '다른 다리'}]}
        result = script.add_river_evidence(self.report, [self.station], bad)
        self.assertEqual(result['nearby_candidates'][0]['river_name_evidence'], 'STATION_NAME_MISMATCH')

    def test_missing_river_name_stays_unknown(self):
        bad = {**self.official, 'rows': [{**self.official['rows'][0], 'river': ''}]}
        result = script.add_river_evidence(self.report, [self.station], bad)
        self.assertEqual(result['nearby_candidates'][0]['river_name_evidence'], 'IDENTITY_OR_RIVER_MISSING')

    def test_duplicate_official_records_rejected(self):
        bad = {**self.official, 'rows': self.official['rows'] * 2}
        result = script.add_river_evidence(self.report, [self.station], bad)
        self.assertEqual(result['nearby_candidates'][0]['river_name_evidence'], 'DUPLICATE_OFFICIAL_RECORDS')

    def test_provider_offline_is_not_no_risk(self):
        result = script.add_river_evidence(self.report, [self.station],
                                           {'status': 'OFFICIAL_GIS_REQUEST_FAILED', 'rows': []})
        self.assertEqual(result['river_metadata_status'], 'OFFICIAL_GIS_REQUEST_FAILED')
        self.assertFalse(result['water_risk_mapping_confirmed'])
        self.assertEqual(result['nearby_candidates'][0]['river_name_evidence'], 'PROVIDER_UNAVAILABLE')

    def test_http_query_is_bounded_and_keyless(self):
        response = Mock(status_code=200, content=b'{}')
        response.json.return_value = {'features': [{'attributes': {
            'WLOBSCD': 1101641, 'OBSNM': '화성시(느티교)', 'RIVNM': '오산천',
            'LAT': 37.185, 'LON': 127.096,
        }}]}
        client = Mock()
        client.get.return_value = response
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        with patch.object(script.httpx, 'Client', return_value=client):
            result = script.fetch_official_river_metadata(['1101641', 'invalid', '1101645'])
        self.assertEqual(result['status'], 'OFFICIAL_GIS_RESPONSE_RECEIVED')
        self.assertEqual(result['rows'][0]['river'], '오산천')
        called_url = client.get.call_args.args[0]
        params = client.get.call_args.kwargs['params']
        self.assertEqual(called_url, script.GIS_RIVER_QUERY_URL)
        self.assertEqual(params['where'], 'WLOBSCD IN (1101641,1101645)')
        self.assertNotIn('apiKey', params)

    def test_secondary_catalog_is_cached_without_credentials(self):
        class FakeRedis:
            def __init__(self):
                self.values = {}
            def get(self, key):
                return self.values.get(key)
            def set(self, key, value, ex=None):
                self.values[key] = value
        cache = FakeRedis()
        response = Mock(status_code=200, content=b'{}')
        response.json.return_value = {'features': [{'attributes': {
            'WLOBSCD': 1101641, 'OBSNM': '화성시(느티교)', 'RIVNM': '가상하천',
            'LAT': 37.185, 'LON': 127.096,
        }}]}
        client = Mock()
        client.get.return_value = response
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        with patch.object(script.httpx, 'Client', return_value=client):
            fresh = script.fetch_official_river_metadata(['1101641'], cache)
            cached = script.fetch_official_river_metadata(['1101641'], cache)
        self.assertEqual(fresh['metadata_catalog_source'], 'GIS_FRESH')
        self.assertEqual(cached['metadata_catalog_source'], 'GIS_CACHED')
        client.get.assert_called_once()
        self.assertNotIn('SECRET', str(cache.values))

    def test_arbitrary_server_error_is_not_misread_as_no_station(self):
        response = Mock(status_code=200, content=b'{}')
        response.json.return_value = {'error': {'code': 500, 'message': 'error'}}
        client = Mock()
        client.get.return_value = response
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        with patch.object(script.httpx, 'Client', return_value=client):
            result = script.fetch_official_river_metadata(['1101641'])
        self.assertEqual(result['status'], 'OFFICIAL_GIS_SCHEMA_OR_PROVIDER_ERROR')

    def test_no_candidates_does_not_call_http(self):
        with patch.object(script.httpx, 'Client') as client:
            result = script.fetch_official_river_metadata([])
        self.assertEqual(result['status'], 'NO_CANDIDATE_IDS')
        client.assert_not_called()

    def test_no_water_key_does_not_touch_db(self):
        with patch.object(script.diag, 'read_cctv') as read:
            result = script.inspect(3, '')
        self.assertEqual(result['status'], 'MISSING_WATER_LEVEL_API_KEY')
        read.assert_not_called()

    def test_station_catalog_reused_without_request_duplication(self):
        with patch.object(script.diag, 'read_cctv', return_value={
                'id': 3, 'latitude': 37.182, 'longitude': 127.095,
                'name': '동탄터널'}), \
             patch.object(script, '_read_station_catalog', return_value=([self.station], 'OK_CACHED')) as catalog, \
             patch.object(script, 'fetch_official_river_metadata', return_value=self.official) as extra:
            result = script.inspect(3, 'SECRET', redis_client=object())
        self.assertEqual(result['catalog_source'], 'OK_CACHED')
        catalog.assert_called_once()
        extra.assert_called_once()
        self.assertEqual(result['nearby_candidates'][0]['confirmed_river_name'], '오산천')
        self.assertNotIn('SECRET', str(result))


if __name__ == '__main__':
    unittest.main()
