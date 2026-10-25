"""Read-only scoped Demo prewarm: no live network, credentials, DB updates."""
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from backend.app.demo_v5_media import mapping


class Connection:
    def __init__(self):
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((query, params))
        return self

    def fetchall(self):
        return [
            {'id': i, 'provider': 'DEMO', 'external_cctv_id': identifier,
             'name': identifier, 'latitude': 37.5, 'longitude': 127.0,
             'address': None, 'region_code': 'TEST'}
            for i, identifier in enumerate(mapping.DEMO_IDENTIFIERS, 4)
        ]


class DemoMappingTests(unittest.TestCase):
    def test_prepare_only_approved_three_and_db_read_only(self):
        conn = Connection()

        @contextmanager
        def open_connection():
            yield conn

        with (patch.object(mapping, 'get_connection', open_connection),
              patch.object(mapping, 'auto_mapping_enabled', return_value=True),
              patch.object(mapping, 'prepare_cached_mapping', return_value='CREATED') as prep,
              patch.object(mapping, 'get_cached_mapping', return_value={
                  'weather_grid': {'nx': 61, 'ny': 125},
                  'water_level': {'status': 'RADIUS_MAPPING_NOT_PREPARED',
                                  'reason': 'PROVIDER_REJECTED_941'},
                  'traffic': {'status': 'NEEDS_ROAD_DIRECTION_VERIFICATION',
                              'reason': 'DIRECTION_UNVERIFIED'},
              })):
            response = mapping.prepare_mapping()
        self.assertEqual(prep.call_count, 3)
        self.assertEqual(len(response['items']), 3)
        self.assertTrue(all(item['cache_ready'] for item in response['items']))
        self.assertTrue(all(not item['water_mapped'] for item in response['items']))
        self.assertTrue(all(not item['traffic_rule_mapped'] for item in response['items']))
        self.assertEqual(conn.queries[0][0], 'SET TRANSACTION READ ONLY')
        self.assertEqual(conn.queries[1][1], (list(mapping.DEMO_IDENTIFIERS),))
        self.assertFalse(any('UPDATE ' in sql or 'DELETE ' in sql
                             for sql, _ in conn.queries))

    def test_disabled_mapping_makes_no_preparation_call(self):
        with (patch.object(mapping, '_demo_cameras', return_value=[
                 {'external_cctv_id': key} for key in mapping.DEMO_IDENTIFIERS]),
              patch.object(mapping, 'auto_mapping_enabled', return_value=False),
              patch.object(mapping, 'get_cached_mapping', return_value=None),
              patch.object(mapping, 'prepare_cached_mapping') as prep):
            response = mapping.prepare_mapping()
        self.assertFalse(response['auto_mapping_enabled'])
        self.assertTrue(all(item['preparation'] == 'DISABLED' for item in response['items']))
        prep.assert_not_called()

    def test_missing_demo_identity_does_not_initiate_mapping(self):
        conn = Connection()
        conn.fetchall = lambda: [
            {'id': 4, 'provider': 'DEMO', 'external_cctv_id': 'DEMO-N001'},
        ]

        @contextmanager
        def open_connection():
            yield conn

        with (patch.object(mapping, 'get_connection', open_connection),
              patch.object(mapping, 'prepare_cached_mapping') as prep):
            with self.assertRaises(ValueError):
                mapping.prepare_mapping()
        prep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
