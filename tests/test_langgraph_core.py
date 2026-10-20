"""05번 순수 함수·실행 노드·저장 계약 테스트. 실제 API·DB 연결을 사용하지 않습니다.

실행: python -m unittest discover -s tests -p "test_langgraph*.py" -v
테스트 숫자·관측소·지역·기관은 테스트 전용이며 운영 설정으로 사용하지 않습니다.
"""

import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from ai.config import (
    _environment, get_runtime_config, runtime_config_scope, validate_settings,
)
from ai.contracts import ContextSnapshot
from ai.orchestration.nodes import create_nodes
from ai.orchestration.state import create_state
from ai.risk_priority.rules import RISK_POLICIES, assess, assign_priorities
from ai.runtime_queries import KST, TRAFFIC_FIELDS, create_query_factory
from backend.app.incidents import analysis_storage as storage
from backend.app.integrations import normalization, places, traffic, water_level, weather

NOW = datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc)


def item(value=None, status='OK', unit='category', **extra):
    return {
        'value': value, 'status': status, 'source': 'TEST_FIXTURE',
        'unit': unit, 'observed_at': NOW.isoformat(), **extra,
    }


def sample_incident():
    return {
        'id': 1, 'cctv_id': 9, 'status': 'DETECTED', 'hazard_type': 'flood',
        'latitude': Decimal('37.5'), 'longitude': Decimal('127.0'),
        'region_code': 'TEST_REGION', 'risk_score': None, 'detected_at': NOW,
    }


def sample_context():
    return ContextSnapshot(1, NOW, {
        'rainfall_mm': item(30, unit='mm'),
        'wind_speed_mps': item(25, unit='m/s'),
        'water_level_m': item(7, unit='m'),
        'water_risk_level': item('WARNING'),
        'traffic_level': item('HIGH'),
        'blocked_lane_count': item(2, unit='lanes'),
        'road_type': item('UNDERPASS'),
        'road_rank': item('101'),
        'traffic_volume_level': item('HIGH'),
        'population_density_level': item('HIGH'),
        'nearby_hospital_distance_m': item(100, unit='m'),
        'nearby_school_distance_m': item(450, unit='m'),
        'traffic_control': item('FULL', level='FULL'),
        'closure_confirmed': item(True, unit='boolean'),
        'closures': item([], unit='GeoJSON', blocked_zones_verified=True),
    }, ('TEST_FIXTURE',))


def sample_agencies():
    return [
        {
            'id': aid, 'agency_type': kind, 'latitude': 37.5 + aid / 1000,
            'longitude': 127, 'region_code': 'TEST_REGION',
            'service_region_codes': ['TEST_REGION'],
        }
        for aid, kind in (
            (10, 'FIRE'), (20, 'ROAD_MANAGEMENT'),
            (30, 'POLICE'), (40, 'LOCAL_GOVERNMENT'),
        )
    ]


def sample_routes(query=None):
    return {
        'status': 'OK', 'source': 'KAKAO_MOBILITY', 'attempts': ['RECOMMEND'],
        'candidates': [{
            'route_name': '후보 1', 'duration_sec': 600, 'distance_m': 5000,
            'route_path_json': {
                'type': 'LineString', 'coordinates': [[127, 37.5], [127.01, 37.51]],
            },
            'destination_kind': 'INCIDENT',
        }],
    }


def sample_settings():
    return {
        'context_transport': 'direct',
        'agency_policy': {
            'version': 'TEST_AGENCY', 'max_distance_m': 10000,
            'limit': 4, 'min_score': 0,
        },
        'route_policy': {
            'version': 'TEST_ROUTE', 'duration_scale_sec': 600,
            'distance_scale_m': 5000, 'time_points': 70, 'distance_points': 30,
        },
        'cctvs': {},
    }


def sample_config():
    settings = sample_settings()
    return {
        **settings, 'risk_policies': deepcopy(RISK_POLICIES),
        'route_api_key': 'TEST_ONLY_NOT_A_REAL_KEY',
        'load_incident': lambda incident_id: sample_incident(),
        'load_agencies': sample_agencies,
        'context_loader': lambda incident_id: sample_context(),
        'fetch_routes': sample_routes,
        'save_analysis': lambda state: {
            'incident_id': state['incident_id'], 'status': 'TEST_SAVED',
            'risk_score': state['assessment']['risk_score'],
        },
    }


# 같은 실행 노드를 순서대로 호출하는 단위 테스트 보조 함수입니다.
# LangGraph 자체 실행은 test_langgraph_runtime.py에서 별도로 검증합니다.
def run_nodes(config=None, save=True):
    state = create_state(1)
    nodes = create_nodes(config or sample_config())
    for name, node in nodes.items():
        if not save and name == 'save_results':
            break
        state.update(node(state))
        if state['result']:
            break
    return state


class ConfigurationTests(unittest.TestCase):
    def test_positive_incident_id_only(self):
        self.assertEqual(create_state(1)['incident_id'], 1)
        for invalid in (0, -1, True, '1', 1.0, None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                create_state(invalid)

    def test_policy_input_is_not_mutated(self):
        settings = sample_settings()
        before = deepcopy(settings)
        agency, route = validate_settings(settings)
        self.assertEqual(settings, before)
        self.assertIsNot(agency, settings['agency_policy'])
        self.assertEqual(route['time_points'], 70)

    def test_no_invented_radius_or_scale(self):
        for group, name in (
            ('agency_policy', 'max_distance_m'),
            ('route_policy', 'duration_scale_sec'),
            ('route_policy', 'distance_scale_m'),
        ):
            for value in (None, 0, -1, True, 'nan', 'inf'):
                settings = sample_settings()
                settings[group][name] = value
                with self.subTest(group=group, value=value), self.assertRaises(ValueError):
                    validate_settings(settings)

    def test_rejects_changed_weights(self):
        settings = sample_settings()
        settings['route_policy']['time_points'] = 60
        with self.assertRaises(ValueError):
            validate_settings(settings)

    def test_rejects_fallback_smaller_than_radius(self):
        settings = sample_settings()
        settings['agency_policy']['fallback_max_distance_m'] = 1
        with self.assertRaises(ValueError):
            validate_settings(settings)

    def test_rejects_unknown_role_override(self):
        settings = sample_settings()
        settings['agency_policy']['primary_types'] = ['POLICE']
        with self.assertRaises(ValueError):
            validate_settings(settings)

    def test_runtime_reads_explicit_json_and_existing_key_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'runtime.json'
            path.write_text(json.dumps(sample_settings()), encoding='utf-8')
            with patch('ai.config._environment', return_value={'ROUTE_API_KEY': 'key'}):
                config = get_runtime_config(path)
        self.assertEqual(config['route_api_key'], 'key')
        self.assertEqual(config['risk_policies'], RISK_POLICIES)
        self.assertIsNot(config['risk_policies'], RISK_POLICIES)

    def test_missing_config_path_fails_without_secret_echo(self):
        with patch('ai.config._environment', return_value={}):
            with self.assertRaisesRegex(ValueError, 'OCTV_RUNTIME_CONFIG'):
                get_runtime_config()

    def test_environment_has_precedence_and_does_not_write(self):
        with patch('ai.config.dotenv_values', side_effect=[
            {'ROUTE_API_KEY': 'root', 'WEATHER_API_KEY': 'root-weather'},
            {'ROUTE_API_KEY': 'backend'},
        ]), patch.dict(os.environ, {'ROUTE_API_KEY': 'process'}, clear=True):
            values = _environment()
        self.assertEqual(values['ROUTE_API_KEY'], 'process')
        self.assertEqual(values['WEATHER_API_KEY'], 'root-weather')

    def test_mcp_runtime_scope_is_restored(self):
        first, second = {'test': 1}, {'test': 2}
        with runtime_config_scope(first):
            self.assertIs(get_runtime_config(), first)
            with runtime_config_scope(second):
                self.assertIs(get_runtime_config(), second)
            self.assertIs(get_runtime_config(), first)
        with patch('ai.config._environment', return_value={}):
            with self.assertRaises(ValueError):
                get_runtime_config()


class QueryFactoryTests(unittest.TestCase):
    def test_unmapped_has_no_fabricated_observations(self):
        result = create_query_factory(sample_settings(), {})(sample_incident(), NOW)
        self.assertFalse(result['weather']['mapped'])
        self.assertFalse(result['water_level']['mapped'])
        self.assertFalse(result['places']['mapped'])
        for name in TRAFFIC_FIELDS:
            self.assertFalse(result['traffic'][name]['mapped'])
            self.assertEqual(result['traffic'][name]['now'], NOW)

    def test_weather_midnight_rollover(self):
        settings = sample_settings()
        settings['cctvs']['9'] = {'weather': {
            'mapped': True, 'max_age_sec': 7200, 'publication_delay_min': 10,
            'url': 'https://example.test/weather',
            'params': {
                'serviceKey': '${WEATHER_API_KEY}',
                'base_date': '${KMA_BASE_DATE}', 'base_time': '${KMA_BASE_TIME}',
            },
        }}
        now = datetime(2026, 10, 14, 15, 5, tzinfo=timezone.utc)
        factory = create_query_factory(settings, {'WEATHER_API_KEY': 'test-key'})
        query = factory(sample_incident(), now)['weather']
        self.assertEqual(query['params']['base_date'], '20261014')
        self.assertEqual(query['params']['base_time'], '2300')
        self.assertEqual(query['params']['serviceKey'], 'test-key')

    def test_known_cctv_mapping_only(self):
        settings = sample_settings()
        settings['cctvs']['99'] = {'weather': {'mapped': True}}
        self.assertFalse(create_query_factory(settings, {})(sample_incident(), NOW)
                         ['weather']['mapped'])

    def test_water_station_settings_and_timezone(self):
        settings = sample_settings()
        settings['cctvs']['9'] = {'water_level': {
            'mapped': True, 'max_age_sec': 1200,
            'url': 'https://example.test/${WATER_LEVEL_API_KEY}/water.json',
            'params': {}, 'spec': {'station_id': 'TEST_STATION', 'timezone': 'KST'},
            'station_info': {'url': 'https://example.test/${WATER_LEVEL_API_KEY}/info.json'},
            'risk_thresholds_m': {'CAUTION': 1, 'WARNING': 2, 'DANGER': 3},
            'risk_thresholds_verified': True,
        }}
        before = deepcopy(settings)
        factory = create_query_factory(settings, {'WATER_LEVEL_API_KEY': 'test$key'})
        query = factory(sample_incident(), NOW)['water_level']
        self.assertEqual(query['spec']['station_id'], 'TEST_STATION')
        self.assertEqual(query['spec']['timezone'], KST)
        self.assertIn('test$key', query['station_info']['url'])
        self.assertNotIn('risk_thresholds_m', query)
        self.assertEqual(settings, before)
        query['spec']['station_id'] = 'CHANGED'
        self.assertEqual(factory(sample_incident(), NOW)['water_level']
                         ['spec']['station_id'], 'TEST_STATION')

    def test_required_traffic_key_absent_disables_query(self):
        settings = sample_settings()
        settings['cctvs']['9'] = {'traffic': {'closures': {
            'mapped': True, 'required_env': ['TRAFFIC_API_KEY'],
            'url': 'https://example.test', 'params': {}, 'max_age_sec': 600,
        }}}
        query = create_query_factory(settings, {})(sample_incident(), NOW)
        self.assertFalse(query['traffic']['closures']['mapped'])

    def test_bad_template_does_not_echo_credentials(self):
        settings = sample_settings()
        settings['cctvs']['9'] = {'traffic': {'closures': {
            'mapped': True, 'url': 'https://example.test/${MISSING_VARIABLE}',
            'max_age_sec': 600,
        }}}
        with self.assertRaises(ValueError) as raised:
            create_query_factory(settings, {})(sample_incident(), NOW)
        self.assertNotIn('https://', str(raised.exception))

    def test_naive_now_rejected(self):
        with self.assertRaises(ValueError):
            create_query_factory(sample_settings(), {})(sample_incident(), NOW.replace(tzinfo=None))

    def test_places_reuses_existing_route_key_and_cctv_coordinates(self):
        query = create_query_factory(sample_settings(), {'ROUTE_API_KEY': 'test-key'})(
            sample_incident(), NOW
        )['places']
        self.assertTrue(query['mapped'])
        self.assertEqual(query['latitude'], Decimal('37.5'))
        self.assertEqual(query['api_key'], 'test-key')


class Existing02ContractTests(unittest.TestCase):
    def test_weather_one_fetch_produces_rain_and_wind(self):
        payload = {'response': {'header': {'resultCode': '00'}, 'body': {'items': {
            'item': [
                {'category': name, 'obsrValue': value, 'baseDate': '20261014', 'baseTime': '1500'}
                for name, value in (('RN1', '30'), ('WSD', '25'))
            ]
        }}}}
        query = {'mapped': True, 'url': 'https://example.test', 'params': {},
                 'now': NOW, 'max_age_sec': 7200}
        with patch.object(weather, 'get_json', return_value=payload) as request:
            result = weather.fetch_observations(query)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(result['rainfall_mm']['value'], 30)
        self.assertEqual(result['wind_speed_mps']['value'], 25)

    def test_official_thresholds_same_station_only(self):
        query = {'mapped': True, 'spec': {'station_id': 'A'},
                 'station_info': {'url': 'https://example.test/info'}}
        payload = {'content': [
            {'wlobscd': 'OTHER', 'wrnwl': '1', 'almwl': '2', 'srswl': '3'},
            {'wlobscd': 'A', 'wrnwl': '4', 'almwl': '6', 'srswl': '8'},
        ]}
        with patch.object(water_level, 'get_json', return_value=payload):
            result = water_level.classify_risk_level(query, item(7, unit='m'))
        self.assertEqual(result['value'], 'WARNING')
        self.assertEqual(result['status'], 'OK')

    def test_missing_official_threshold_not_fabricated(self):
        query = {'mapped': True, 'spec': {'station_id': 'A'},
                 'station_info': {'url': 'https://example.test/info'}}
        payload = {'content': [{'WLOBSCD': 'A', 'WRNWL': '4', 'ALMWL': '6', 'SRSWL': '-'}]}
        with patch.object(water_level, 'get_json', return_value=payload):
            result = water_level.fetch_station_thresholds(query)
        self.assertEqual(result['status'], 'INVALID')
        self.assertIsNone(result['risk_thresholds_m'])

    def test_stale_water_not_classified(self):
        with patch.object(water_level, 'fetch_station_thresholds') as request:
            result = water_level.classify_risk_level({}, item(100, status='STALE'))
        request.assert_not_called()
        self.assertEqual(result['status'], 'STALE')
        self.assertIsNone(result['value'])

    def test_no_traffic_mapping_stays_unknown(self):
        query = create_query_factory(sample_settings(), {})(sample_incident(), NOW)['traffic']
        result = traffic.fetch_rule_data(query)
        self.assertEqual(result['blocked_lane_count']['status'], 'NO_MAPPING')
        self.assertFalse(result['closures']['blocked_zones_verified'])
        self.assertIsNone(result['closure_confirmed']['value'])

    def test_no_place_within_500m_is_not_zero_distance(self):
        with patch.object(places, 'get_json', return_value={'documents': []}):
            result = places.fetch_data({
                'mapped': True, 'api_key': 'test', 'now': NOW,
                'latitude': 37.5, 'longitude': 127,
            })
        self.assertIsNone(result['nearby_hospital_distance_m']['value'])
        self.assertEqual(result['nearby_school_distance_m']['status'], 'NO_DATA')

    def test_age_and_zero_value_contract(self):
        zero = normalization.measurement(0, NOW, 'TEST', 'mm', NOW, 600)
        stale = normalization.measurement(30, NOW - timedelta(hours=1), 'TEST', 'mm', NOW, 600)
        self.assertEqual(zero['status'], 'OK')
        self.assertEqual(zero['value'], 0)
        self.assertEqual(stale['status'], 'STALE')


class NodeTests(unittest.TestCase):
    def test_current_flood_policy_reaches_100_and_final_agencies_only(self):
        state = run_nodes()
        self.assertEqual(state['assessment']['risk_score'], 100)
        self.assertEqual(state['assessment']['priority'], 'P1')
        self.assertEqual(len(state['recommendations']), 3)
        self.assertNotIn(40, [r['agency_id'] for r in state['recommendations']])
        for recommendation in state['recommendations']:
            self.assertEqual(recommendation['score_breakdown_json']['candidate_stage'], 'FINAL')
            self.assertEqual(recommendation['score_breakdown_json']['access_status'], 'VERIFIED')
        self.assertNotIn('TEST_ONLY_NOT_A_REAL_KEY', repr(state))

    def test_base_only_score_is_provisional_not_failure(self):
        config = sample_config()
        config['context_loader'] = lambda _: ContextSnapshot(1, NOW, {}, ())
        state = run_nodes(config)
        self.assertEqual(state['assessment']['risk_score'], 40)
        self.assertEqual(state['assessment']['priority'], 'P2')
        self.assertTrue(state['assessment']['risk_breakdown']['provisional'])

    def test_four_hazard_policies_keep_original_worsening_caps(self):
        cases = (
            ('flood', 100), ('fallen_tree', 90),
            ('severe_road_damage', 90), ('road_obstacle', 90),
        )
        for hazard, expected in cases:
            with self.subTest(hazard=hazard):
                result = assess(sample_context(), RISK_POLICIES[hazard])
                self.assertEqual(result['risk_score'], expected)

    def test_risk_boundaries_and_tie_sort(self):
        rows = [
            {'id': i, 'risk_score': score, 'detected_at': NOW}
            for i, score in ((3, 40), (2, 70), (1, 39), (4, 70))
        ]
        result = assign_priorities(rows)
        self.assertEqual([r['id'] for r in result], [2, 4, 3, 1])
        self.assertEqual([r['priority'] for r in result], ['P1', 'P1', 'P2', 'P3'])

    def test_missing_incident_skips_remaining_nodes(self):
        config = sample_config()
        config['load_incident'] = lambda _: None
        loader = Mock()
        config['context_loader'] = loader
        self.assertEqual(run_nodes(config)['result']['skipped'], 'NOT_FOUND')
        loader.assert_not_called()

    def test_zero_risk_already_assessed_is_skipped(self):
        config = sample_config()
        config['load_incident'] = lambda _: {**sample_incident(), 'risk_score': 0}
        self.assertEqual(run_nodes(config)['result']['skipped'], 'ALREADY_ASSESSED')

    def test_inactive_incidents_not_reopened(self):
        for status in ('SENT', 'RESOLVED', 'FALSE_POSITIVE'):
            config = sample_config()
            config['load_incident'] = lambda _, s=status: {**sample_incident(), 'status': s}
            with self.subTest(status=status):
                self.assertEqual(run_nodes(config)['result']['skipped'], 'INACTIVE')

    def test_context_id_mismatch_rejected_before_save(self):
        config = sample_config()
        config['context_loader'] = lambda _: ContextSnapshot(2, NOW, {}, ())
        with self.assertRaises(ValueError):
            run_nodes(config)

    def test_bad_coordinates_rejected(self):
        config = sample_config()
        config['load_incident'] = lambda _: {**sample_incident(), 'latitude': float('nan')}
        with self.assertRaises(ValueError):
            run_nodes(config)

    def test_closures_unverified_means_review(self):
        snapshot = sample_context()
        snapshot.measurements['closures']['blocked_zones_verified'] = False
        config = sample_config()
        config['context_loader'] = lambda _: snapshot
        state = run_nodes(config)
        route = state['routes_by_agency'][10][0]
        self.assertEqual(route['score_breakdown_json']['verification_status'], 'NEEDS_REVIEW')

    def test_full_closure_crossing_is_disqualified(self):
        snapshot = sample_context()
        snapshot.measurements['closures']['value'] = [{
            'type': 'Polygon', 'coordinates': [[
                [126.99, 37.49], [127.02, 37.49], [127.02, 37.52],
                [126.99, 37.52], [126.99, 37.49],
            ]],
        }]
        config = sample_config()
        config['context_loader'] = lambda _: snapshot
        state = run_nodes(config)
        route = state['routes_by_agency'][10][0]
        self.assertEqual(route['score_breakdown_json']['verification_status'], 'DISQUALIFIED')
        self.assertIsNone(route['total_score'])
        self.assertEqual(state['recommendations'][0]['score_breakdown_json']['access_status'],
                         'NO_AVAILABLE_ROUTE')

    def test_malformed_closure_not_verified(self):
        snapshot = sample_context()
        snapshot.measurements['closures']['value'] = [{'invalid': True}]
        config = sample_config()
        config['context_loader'] = lambda _: snapshot
        state = run_nodes(config)
        self.assertEqual(state['routes_by_agency'][10][0]['score_breakdown_json']
                         ['verification_status'], 'NEEDS_REVIEW')
        self.assertEqual(state['route_fetches'][10]['closure_status'], 'INVALID')

    def test_no_route_not_fabricated(self):
        config = sample_config()
        config['fetch_routes'] = lambda _: {'status': 'NO_ROUTE', 'candidates': []}
        state = run_nodes(config)
        self.assertEqual(state['routes_by_agency'][10], [])
        breakdown = state['recommendations'][0]['score_breakdown_json']
        self.assertEqual(breakdown['access_time_points'], 0)

    def test_missing_route_key_no_external_request(self):
        config = sample_config()
        config['route_api_key'] = ''
        request = Mock()
        config['fetch_routes'] = request
        state = run_nodes(config)
        request.assert_not_called()
        self.assertEqual(state['route_fetches'][10]['status'], 'NO_MAPPING')

    def test_route_timeout_propagates_before_any_save(self):
        config = sample_config()
        saver = Mock()
        config['save_analysis'] = saver
        config['fetch_routes'] = Mock(side_effect=httpx.ReadTimeout('test timeout'))
        with self.assertRaises(httpx.ReadTimeout):
            run_nodes(config)
        saver.assert_not_called()

    def test_malformed_route_fails_instead_of_scoring(self):
        config = sample_config()
        response = sample_routes()
        response['candidates'][0]['duration_sec'] = -1
        config['fetch_routes'] = lambda _: response
        with self.assertRaises(ValueError):
            run_nodes(config)

    def test_candidate_stage_stays_preliminary_until_finalize(self):
        state = run_nodes(save=False)
        self.assertTrue(all(r['score_breakdown_json']['candidate_stage'] == 'PRELIMINARY_NO_ROUTE'
                            for r in state['preliminary']))
        self.assertTrue(all(r['score_breakdown_json']['candidate_stage'] == 'FINAL'
                            for r in state['recommendations']))


class FakeCursor:
    def __init__(self, result):
        self.result = result

    def fetchone(self):
        return self.result


class FakeConnection:
    def __init__(self, status='DETECTED', assessed=False, partial=False):
        self.status, self.assessed, self.partial = status, assessed, partial
        self.calls = []
        self.isolation = 'read committed'

    def execute(self, sql, params=None):
        text = ' '.join(sql.split())
        self.calls.append((text, params))
        if text.startswith('SET LOCAL'):
            result = None
        elif text.startswith('SHOW'):
            result = {'transaction_isolation': self.isolation}
        elif text.startswith('SELECT id, status'):
            result = {'id': 1, 'status': self.status}
        elif text.startswith('SELECT id FROM incident_assessments'):
            result = {'id': 102} if self.assessed else None
        elif text.startswith('SELECT EXISTS'):
            result = {'present': self.partial}
        elif text.startswith('INSERT INTO incident_contexts'):
            result = {'id': 101}
        elif text.startswith('INSERT INTO incident_assessments'):
            result = {'id': 102}
        else:
            raise AssertionError('예상하지 않은 SQL: ' + text)
        return FakeCursor(result)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.state = run_nodes(save=False)
        self.connection = FakeConnection()

    def test_saves_full_normalized_context_without_new_columns(self):
        original = deepcopy(self.state['assessment'])
        with patch.object(storage, '_json', side_effect=storage.json_ready), \
                patch.object(storage, '_save_recommendation', return_value={'id': 201}) as agency, \
                patch.object(storage, '_save_route') as route:
            result = storage.save_analysis_on_connection(self.connection, self.state)
        self.assertEqual(result['status'], 'SAVED')
        self.assertEqual(result['route_count'], 3)
        self.assertEqual(agency.call_count, 3)
        self.assertEqual(route.call_count, 3)
        assessment_params = next(p for sql, p in self.connection.calls
                                 if sql.startswith('INSERT INTO incident_assessments'))
        measured = assessment_params['risk_breakdown_json']['context_snapshot']['measurements']
        self.assertEqual(measured['wind_speed_mps']['value'], 25)
        self.assertEqual(self.state['assessment'], original)
        self.assertFalse(any(sql.startswith(('CREATE ', 'ALTER ', 'DROP ', 'DELETE ', 'UPDATE '))
                             for sql, _ in self.connection.calls))

    def test_duplicate_assessment_is_not_saved_again(self):
        self.connection.assessed = True
        result = storage.save_analysis_on_connection(self.connection, self.state)
        self.assertEqual(result['skipped'], 'ALREADY_ASSESSED')
        self.assertFalse(any(sql.startswith('INSERT') for sql, _ in self.connection.calls))

    def test_status_rechecked_after_external_calls(self):
        self.connection.status = 'SENT'
        result = storage.save_analysis_on_connection(self.connection, self.state)
        self.assertEqual(result['skipped'], 'INACTIVE')
        self.assertFalse(any(sql.startswith('INSERT') for sql, _ in self.connection.calls))

    def test_existing_partial_rows_not_overwritten(self):
        self.connection.partial = True
        with self.assertRaisesRegex(ValueError, '일부 분석'):
            storage.save_analysis_on_connection(self.connection, self.state)
        self.assertFalse(any(sql.startswith('INSERT') for sql, _ in self.connection.calls))

    def test_preliminary_score_cannot_be_saved(self):
        self.state['recommendations'] = self.state['preliminary']
        with self.assertRaisesRegex(ValueError, '최종 기관'):
            storage.save_analysis_on_connection(self.connection, self.state)

    def test_read_committed_required_for_duplicate_guard(self):
        self.connection.isolation = 'repeatable read'
        with self.assertRaisesRegex(ValueError, 'READ COMMITTED'):
            storage.save_analysis_on_connection(self.connection, self.state)

    def test_context_utc_and_unknown_null(self):
        snapshot = self.state['context']
        snapshot.measurements['rainfall_mm'] = item(100, status='STALE')
        self.state['context'] = ContextSnapshot(1, NOW.astimezone(KST), snapshot.measurements,
                                               snapshot.sources)
        storage._save_context(self.connection, self.state)
        params = self.connection.calls[-1][1]
        self.assertEqual(params['captured_at'], NOW.replace(tzinfo=None))
        self.assertIsNone(params['rainfall_mm'])

    def test_wrapper_uses_one_connection_and_rolls_back_on_error(self):
        outcomes = []
        module = types.ModuleType('backend.app.db.session')

        @contextmanager
        def fake_connection():
            try:
                yield self.connection
                outcomes.append('commit')
            except Exception:
                outcomes.append('rollback')
                raise
        module.get_connection = fake_connection
        with (
            patch.dict(sys.modules, {'backend.app.db.session': module}),
            patch.object(
                storage, 'save_analysis_on_connection',
                side_effect=RuntimeError('test'),
            ),
        ):
            with self.assertRaises(RuntimeError):
                storage.save_analysis(self.state)
        self.assertEqual(outcomes, ['rollback'])

    def test_json_ready_and_integer_contract(self):
        value = storage.json_ready({'d': Decimal('1.5'), 'at': NOW, 'invalid': float('nan')})
        self.assertEqual(value['d'], 1.5)
        self.assertIsNone(value['invalid'])
        json.dumps(value, allow_nan=False)
        self.assertIsNone(storage._number({'lanes': item(1.5)}, 'lanes', 10, integer=True))


if __name__ == '__main__':
    unittest.main()
