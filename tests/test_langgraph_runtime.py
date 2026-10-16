"""실제 LangGraph·MCP·PostgreSQL 연결 테스트입니다.

라이브러리 없는 테스트는 SKIP이며 통과로 세지 않습니다.
PostgreSQL은 OCTV_TEST_DATABASE_URL을 명시한 개발용 DB에서만 실행합니다.
스키마 생성/변경/삭제는 없으며 테스트 트랜잭션은 항상 rollback합니다.
"""

import asyncio
import importlib.util
import os
import unittest
from contextlib import contextmanager
from dataclasses import replace
from datetime import timezone
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx

from ai.orchestration.pipeline import run_pipeline
from backend.app.incidents import analysis_storage as storage
from test_langgraph_core import (
    NOW, run_nodes, sample_config, sample_context, sample_incident, sample_settings,
)

HAS_GRAPH = importlib.util.find_spec('langgraph') is not None
HAS_MCP = importlib.util.find_spec('fastmcp') is not None
HAS_DB_DRIVER = importlib.util.find_spec('psycopg') is not None


@unittest.skipUnless(HAS_GRAPH, 'langgraph 미설치: 실제 그래프 실행 미검증')
class LangGraphTests(unittest.TestCase):
    def test_actual_compiled_graph_runs_all_nodes_with_mock_io(self):
        result = run_pipeline(1, sample_config())
        self.assertEqual(result['status'], 'TEST_SAVED')
        self.assertEqual(result['risk_score'], 100)

    def test_actual_graph_stops_on_already_assessed(self):
        config = sample_config()
        config['load_incident'] = lambda _: {**sample_incident(), 'risk_score': 40}
        saver = Mock()
        config['save_analysis'] = saver
        self.assertEqual(run_pipeline(1, config)['skipped'], 'ALREADY_ASSESSED')
        saver.assert_not_called()

    def test_actual_graph_does_not_save_after_route_timeout(self):
        config = sample_config()
        config['fetch_routes'] = Mock(side_effect=httpx.ReadTimeout('test'))
        saver = Mock()
        config['save_analysis'] = saver
        with self.assertRaises(httpx.ReadTimeout):
            run_pipeline(1, config)
        saver.assert_not_called()


@unittest.skipUnless(HAS_MCP and HAS_DB_DRIVER, 'fastmcp/psycopg 미설치: MCP 왕복 미검증')
class MCPTests(unittest.TestCase):
    def test_existing_mcp_roundtrip_uses_same_runtime_config(self):
        from ai.config import runtime_config_scope
        from ai.mcp.client import collect_via_mcp

        factory = lambda incident, now: {}
        config = {'query_factory': factory}
        with runtime_config_scope(config), patch(
            'ai.mcp.tools.collect_context', return_value=sample_context()
        ) as collect:
            result = asyncio.run(collect_via_mcp(1))
        collect.assert_called_once_with(1, factory)
        self.assertEqual(result, sample_context())


@unittest.skipUnless(HAS_DB_DRIVER, 'psycopg 미설치: 기존 Context 모듈 연결 미검증')
class ContextConnectionTests(unittest.TestCase):
    def test_existing_context_and_query_factory_connect_with_mock_db(self):
        from ai.runtime_queries import create_query_factory
        from backend.app.integrations.context import collect_context

        @contextmanager
        def connection():
            yield object()

        factory = create_query_factory(sample_settings(), {})
        with (
            patch('backend.app.integrations.context.get_connection', connection),
            patch(
                'backend.app.integrations.context.find_detail',
                return_value=sample_incident(),
            ),
        ):
            snapshot = collect_context(1, factory)
        self.assertEqual(snapshot.incident_id, 1)
        self.assertEqual(snapshot.measurements['rainfall_mm']['status'], 'NO_MAPPING')
        self.assertEqual(snapshot.measurements['wind_speed_mps']['status'], 'NO_MAPPING')
        self.assertEqual(snapshot.measurements['water_risk_level']['status'], 'NO_MAPPING')
        self.assertIn('traffic_control', snapshot.measurements)
        self.assertIn('nearby_school_distance_m', snapshot.measurements)


@unittest.skipUnless(
    HAS_DB_DRIVER and bool(os.environ.get('OCTV_TEST_DATABASE_URL')),
    '개발용 OCTV_TEST_DATABASE_URL/psycopg 미설정: 실제 DB 저장 미검증',
)
class PostgreSQLTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        from backend.app.incidents.repository import save_detection

        self.connection = psycopg.connect(
            os.environ['OCTV_TEST_DATABASE_URL'], row_factory=dict_row,
            connect_timeout=5,
        )
        self.addCleanup(self.connection.close)
        self.addCleanup(self.connection.rollback)
        cctv = self.connection.execute('SELECT id FROM cctvs ORDER BY id LIMIT 1').fetchone()
        agency = self.connection.execute('SELECT id FROM agencies ORDER BY id LIMIT 1').fetchone()
        if not cctv or not agency:
            self.skipTest('기존 cctvs·agencies에 테스트 가능한 데이터가 필요합니다.')
        token = uuid4().hex
        candidate = {
            'cctv_id': cctv['id'], 'hazard_type': 'flood', 'confidence': 0.9,
            'model_version': 'OCTV05_TEST', 'detection_image_path': 'test://octv05',
            'detection_bbox_json': {'box': [0, 0, 1, 1]},
            'dedup_key': 'octv05-test-' + token,
            'detected_at': NOW.astimezone(timezone.utc).replace(tzinfo=None),
        }
        incident = save_detection(self.connection, candidate)
        duplicate = save_detection(self.connection, candidate)
        self.assertEqual(incident['id'], duplicate['id'])
        self.incident_id = incident['id']
        state = run_nodes(save=False)
        state['incident_id'] = self.incident_id
        state['context'] = replace(state['context'], incident_id=self.incident_id)
        recommendation = state['recommendations'][0]
        routes = state['routes_by_agency'][recommendation['agency_id']]
        recommendation['agency_id'] = agency['id']
        state['recommendations'] = [recommendation]
        state['routes_by_agency'] = {agency['id']: routes}
        state['route_fetches'] = {agency['id']: {'status': 'OK', 'source': 'TEST_FIXTURE'}}
        self.state = state

    def test_existing_schema_save_read_and_duplicate(self):
        from backend.app.incidents.repository import find_detail

        result = storage.save_analysis_on_connection(self.connection, self.state)
        self.assertEqual(result['status'], 'SAVED')
        again = storage.save_analysis_on_connection(self.connection, self.state)
        self.assertEqual(again['skipped'], 'ALREADY_ASSESSED')
        detail = find_detail(self.connection, self.incident_id)
        self.assertEqual(float(detail['risk_score']), 100)
        self.assertEqual(detail['status'], 'DETECTED')
        self.assertEqual(detail['priority'], 'P1')
        record = self.connection.execute(
            'SELECT recommendation_status FROM incident_agency_recommendations '
            'WHERE incident_id = %s', (self.incident_id,),
        ).fetchone()
        self.assertEqual(record['recommendation_status'], 'RECOMMENDED')
        tables = (
            'incident_contexts', 'incident_assessments',
            'incident_agency_recommendations',
        )
        for table in tables:
            count = self.connection.execute(
                f'SELECT count(*) AS n FROM {table} WHERE incident_id = %s',
                (self.incident_id,),
            ).fetchone()['n']
            self.assertEqual(count, 1)

    def test_route_save_failure_rolls_back_whole_analysis(self):
        # setUp의 사건만 유지하고, 이 savepoint 안의 분석 INSERT는 모두 rollback합니다.
        with self.assertRaises(RuntimeError):
            with self.connection.transaction():
                with patch.object(storage, '_save_route', side_effect=RuntimeError('TEST_FAILURE')):
                    storage.save_analysis_on_connection(self.connection, self.state)
        tables = (
            'incident_contexts', 'incident_assessments',
            'incident_agency_recommendations',
        )
        for table in tables:
            count = self.connection.execute(
                f'SELECT count(*) AS n FROM {table} WHERE incident_id = %s',
                (self.incident_id,),
            ).fetchone()['n']
            self.assertEqual(count, 0)
        result = storage.save_analysis_on_connection(self.connection, self.state)
        self.assertEqual(result['status'], 'SAVED')


if __name__ == '__main__':
    unittest.main()
