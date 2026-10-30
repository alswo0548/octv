"""Read-only scoped Demo prewarm: no live network, credentials, DB updates."""
import sys
import unittest
from types import SimpleNamespace
from contextlib import contextmanager
from unittest.mock import MagicMock, call, patch

from backend.app.demo_v5_media import mapping
from backend.app.demo import router as demo_router, schemas


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


class DemoStartMappingDispatchTests(unittest.TestCase):
    """One DEMO start schedules the existing analysis queue; no API calls here."""

    @staticmethod
    def response():
        return schemas.DemoStartResponse(
            scenario='main_demo', ready=True, started=True,
            case_count=2, resolved_cctv_count=2, fake_alert_count=2,
            cctvs=[
                schemas.DemoResolvedCctv(
                    id=4, provider='DEMO', external_cctv_id='DEMO-N001',
                    name='N001', region_code='11',
                ),
                schemas.DemoResolvedCctv(
                    id=6, provider='DEMO', external_cctv_id='DEMO-N003',
                    name='N003', region_code='11',
                ),
            ],
        )

    def test_success_dispatches_only_activated_demo_cctvs(self):
        response = self.response()
        task = MagicMock()
        with (
            patch.object(demo_router.service, 'start_demo', return_value=response) as start,
            patch('backend.app.integrations.cctv_mapping.auto_mapping_enabled',
                  return_value=True),
            patch.dict(sys.modules, {
                'backend.app.workers': SimpleNamespace(prewarm_context_mapping=task),
            }),
        ):
            got = demo_router.start_demo(schemas.DemoStartRequest(scenario='main_demo'))
        self.assertIs(got, response)
        start.assert_called_once_with('main_demo')
        self.assertEqual(task.apply_async.call_args_list, [
            call(args=(4,)), call(args=(6,)),
        ])

    def test_mapping_disabled_does_not_dispatch(self):
        task = MagicMock()
        with (
            patch.object(demo_router.service, 'start_demo', return_value=self.response()),
            patch('backend.app.integrations.cctv_mapping.auto_mapping_enabled',
                  return_value=False),
            patch.dict(sys.modules, {
                'backend.app.workers': SimpleNamespace(prewarm_context_mapping=task),
            }),
        ):
            got = demo_router.start_demo(schemas.DemoStartRequest())
        self.assertTrue(got.started)
        task.apply_async.assert_not_called()

    def test_worker_failure_does_not_cancel_demo_or_skip_other_cctvs(self):
        response = self.response()
        task = MagicMock()
        task.apply_async.side_effect = [OSError('broker unavailable'), None]
        with (
            patch.object(demo_router.service, 'start_demo', return_value=response),
            patch('backend.app.integrations.cctv_mapping.auto_mapping_enabled',
                  return_value=True),
            patch.dict(sys.modules, {
                'backend.app.workers': SimpleNamespace(prewarm_context_mapping=task),
            }),
        ):
            got = demo_router.start_demo(schemas.DemoStartRequest())
        self.assertIs(got, response)
        self.assertEqual(task.apply_async.call_args_list, [
            call(args=(4,)), call(args=(6,)),
        ])

    def test_demo_start_failure_never_queues_mapping(self):
        task = MagicMock()
        with (
            patch.object(demo_router.service, 'start_demo',
                         side_effect=RuntimeError('not ready')),
            patch.dict(sys.modules, {
                'backend.app.workers': SimpleNamespace(prewarm_context_mapping=task),
            }),
        ):
            with self.assertRaises(Exception):
                demo_router.start_demo(schemas.DemoStartRequest())
        task.apply_async.assert_not_called()


if __name__ == '__main__':
    unittest.main()
