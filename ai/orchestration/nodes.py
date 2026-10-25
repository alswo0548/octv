"""LangGraph의 각 단계에서 기존 함수를 호출합니다.

workers.py 에서 사건 ID를 받아 LangGraph 실행요청한 뒤, pipeline.py 에서 노드들의 실행 순서와 종료 조건을 설정한뒤 
nodes.py 현재 파일에서 실제 단계별 작업을 진행한다.
- 외부 정보가 필요하면 → Context 수집 기능 호출
- 위험도를 계산해야 하면 → Rule 호출
- 기관을 추천해야 하면 → 추천 함수 호출
- 경로를 평가해야 하면 → 경로 평가 함수 호출
- 결과를 저장해야 하면 → 기존 DB 저장 함수 호출

사건 조회 → Context → 위험도 → 기관 사전 선정 → 경로 평가 → 최종 기관 → 저장
점수 계산식은 이 파일에 복사하지 않습니다. 기존 Rule 함수를 호출합니다.
함수 주입은 외부 API·DB 없이 동일한 노드를 시험하기 위한 연결 지점입니다.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from math import isfinite

from ai.agency_recommendation.recommender import (
    finalize_recommendations,
    recommend,
)
from ai.contracts import ContextSnapshot
from ai.risk_priority.rules import InsufficientContext, assess
from ai.route_evaluation.evaluator import evaluate, intersects_geojson
from backend.app.incidents import analysis_storage
from backend.app.integrations.maps import fetch_data as fetch_routes


# 좌표가 잘못되면 거리·경로 점수를 계산하지 않고 데이터 확인을 요청합니다.
def _check_coordinates(row: dict):
    try:
        latitude = float(row['latitude'])
        longitude = float(row['longitude'])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError('사건 또는 기관의 좌표 형식을 확인하세요.') from None
    if not (
        isfinite(latitude) and isfinite(longitude)
        and -90 <= latitude <= 90 and -180 <= longitude <= 180
    ):
        raise ValueError('사건 또는 기관의 좌표 범위를 확인하세요.')


"""
지도 도형을 검사하는 함수
geometry 는 지도 위의 점,선,영역 같은 공간 데이터를 의미
point (지점) / LineString (이동 경로) / Polygon (통제 구역)
카카오모빌리티 API로 가져온 이동 경로가 선(LineString)이라면, 도로 통제 구역은 다각형(Polygon)으로 표현됨
이 함수는 Shapely 라이브러리를 이용해서 이러한 GeoJSON 도형이 정상인지 확인
"""
def _check_geometry(geometry, route=False):
    from shapely.geometry import shape

    if not isinstance(geometry, dict) or geometry.get('crs') is not None:
        raise ValueError('WGS84 GeoJSON 도형이 필요합니다.')
    allowed = ('LineString', 'MultiLineString') if route else (
        'Point', 'MultiPoint', 'LineString', 'MultiLineString',
        'Polygon', 'MultiPolygon',
    )
    if geometry.get('type') not in allowed:
        raise ValueError('지원하지 않는 경로·통제 도형입니다.')
    try:
        shape_value = shape(geometry)
        west, south, east, north = shape_value.bounds
        valid = (
            not shape_value.is_empty and shape_value.is_valid
            and all(isfinite(v) for v in (west, south, east, north))
            and -180 <= west <= east <= 180
            and -90 <= south <= north <= 90
        )
    except Exception:
        raise ValueError('경로·통제 GeoJSON 형식 오류입니다.') from None
    if not valid:
        raise ValueError('경로·통제 GeoJSON 좌표를 확인하세요.')


# 실제 경로 결과를 검사한 다음 기존 evaluator.py에 전달합니다.
def _check_routes(candidates):
    if not isinstance(candidates, list):
        raise ValueError('경로 후보 결과는 리스트여야 합니다.')
    for route in candidates[:3]:
        if not isinstance(route, dict):
            raise ValueError('경로 후보 형식 오류입니다.')
        for name in ('distance_m', 'duration_sec'):
            raw = route.get(name)
            if type(raw) is not int or not 0 <= raw <= 2147483647:
                raise ValueError('경로 시간·거리는 음수가 아닌 정수여야 합니다.')
        name = route.get('route_name')
        if not isinstance(name, str) or not 1 <= len(name) <= 100:
            raise ValueError('경로 이름을 확인하세요.')
        _check_geometry(route.get('route_path_json'), route=True)
    return candidates[:3]

# 통제 정보의 신뢰성 확인
# 도로 통제 데이터가 정상적으로 수집되었는지, 전면 통제 구역 정보라는 점이 확인되었는지, 통제 구역이 리스트 형태로 준비되었는지
# 미확인 통제 데이터를 빈 목록으로 바꾸어 VERIFIED로 만드는 것을 방지합니다.
def _route_context(snapshot: ContextSnapshot, policy: dict) -> dict:
    closure = snapshot.measurements.get('closures', {})
    zones = closure.get('value')
    verified = (
        closure.get('status') == 'OK'
        and closure.get('blocked_zones_verified') is True
        and isinstance(zones, list)
    )
    status = closure.get('status', 'NO_MAPPING')
    if verified:
        try:
            for zone in zones:
                _check_geometry(zone)
        except ValueError:
            # 위치 대조가 불가능하면 제외/통행 가능을 단정하지 않습니다.
            status, verified = 'INVALID', False
    return {
        'policy': policy,
        'rule_version': policy['version'],
        'blocked_zones': zones,
        'blocked_zones_verified': verified,
        'closure_status': status,
    }


# 기존 MCP 클라이언트를 사용하거나, 설정한 direct 방식으로 Context를 수집합니다.
def _collect_context(incident_id: int, config: dict) -> ContextSnapshot:
    if config.get('context_transport', 'mcp') == 'direct':
        from backend.app.integrations.context import collect_context
        return collect_context(incident_id, config['query_factory'])

    from fastmcp.exceptions import ToolError
    from ai.config import runtime_config_scope
    from ai.mcp.client import collect_via_mcp

    try:
        # 같은 실행의 MCP 도구도 동일한 실행 설정을 사용합니다.
        with runtime_config_scope(config):
            return asyncio.run(collect_via_mcp(incident_id))
    except (ToolError, TimeoutError):
        # MCP가 감싼 일시적 DB/도구 오류도 기존 Worker의 재시도 대상으로 전달합니다.
        raise InsufficientContext('MCP Context 수집 실패: 연결 상태 확인 필요') from None


# 각 함수는 상태 전체를 덮어쓰지 않고 이번 단계의 변경 항목만 반환.
# 앞의 함수들에서 준비 검증이 끝났다면 이 함수가 실제 LangGraph 를 7개의 실행단계로 만듦.
def create_nodes(config: dict) -> dict:
    """
    State에 새로 들어가는 결과: incident
    """
    def load_incident(state):
        loader = config.get('load_incident', analysis_storage.load_incident)
        incident = loader(state['incident_id'])
        reason = None
        if incident is None:
            reason = 'NOT_FOUND'
        elif incident['status'] not in ('DETECTED', 'CONFIRMED'):
            reason = 'INACTIVE'
        elif incident.get('risk_score') is not None:
            reason = 'ALREADY_ASSESSED'
        if reason:
            return {'result': {
                'incident_id': state['incident_id'],
                'status': 'SKIPPED', 'skipped': reason,
            }}
        if incident['id'] != state['incident_id']:
            raise ValueError('조회한 사건 ID가 요청한 사건과 다릅니다.')
        if incident['hazard_type'] not in config['risk_policies']:
            raise ValueError('기존 03번 Rule에 없는 재난 유형입니다.')
        _check_coordinates(incident)
        return {'incident': incident}
    """
    State에 새로 들어가는 결과: context
    """
    def collect_context(state):
        loader = config.get('context_loader')
        snapshot = (
            loader(state['incident_id'])
            if loader else _collect_context(state['incident_id'], config)
        )
        if not isinstance(snapshot, ContextSnapshot):
            raise TypeError('ContextSnapshot 반환값이 필요합니다.')
        if snapshot.incident_id != state['incident_id']:
            raise ValueError('다른 사건의 Context는 사용할 수 없습니다.')
        if snapshot.captured_at.tzinfo is None:
            raise ValueError('Context 수집 시각에는 시간대가 필요합니다.')
        return {'context': snapshot}
    """
    State에 새로 들어가는 결과: assessment
    """
    def assess_risk(state):
        policy = config['risk_policies'][state['incident']['hazard_type']]
        assessor = config.get('risk_assessor')
        return {'assessment': assessor(state['context'], policy, state['incident']) if assessor else assess(state['context'], policy)}
    """
    State에 새로 들어가는 결과: agencies, preliminary
    """
    def select_agencies(state):
        loader = config.get('load_agencies', analysis_storage.load_agencies)
        agencies = loader()
        for agency in agencies:
            _check_coordinates(agency)
        if len({row['id'] for row in agencies}) != len(agencies):
            raise ValueError('중복된 기관 ID가 조회되었습니다.')
        measurements = state['context'].measurements
        # 구조·행정 지원은 명시적으로 확인된 자료가 있을 때만 전달합니다.
        situation = {
            key: measurements[key]
            for key in ('traffic_control', 'rescue_support', 'admin_support')
            if key in measurements
        }
        preliminary = recommend(
            state['incident'], agencies, config['agency_policy'], situation
        )
        return {'agencies': agencies, 'preliminary': preliminary}
    """
    State에 새로 들어가는 결과: routes_by_agency, route_fetches
    """
    def evaluate_routes(state):
        agencies = {row['id']: row for row in state['agencies']}
        context = _route_context(state['context'], config['route_policy'])
        fetcher = config.get('fetch_routes', fetch_routes)

        def for_agency(candidate):
            agency_id = candidate['agency_id']
            agency = agencies[agency_id]
            key = config.get('route_api_key')
            if not key:
                return agency_id, [], {'status': 'NO_MAPPING', 'source': 'KAKAO_MOBILITY'}
            query = {
                'api_key': key,
                'origin_lat': float(agency['latitude']),
                'origin_lon': float(agency['longitude']),
                'destination_lat': float(state['incident']['latitude']),
                'destination_lon': float(state['incident']['longitude']),
            }
            # 통신 예외는 숨기지 않습니다. 저장 전 중단하여 Worker가 재시도합니다.
            response = fetcher(query)
            candidates = _check_routes(response['candidates'])
            if response.get('status') not in ('OK', 'NO_ROUTE'):
                raise ValueError('경로 조회 결과 상태를 확인하세요.')
            if (response['status'] == 'OK') != bool(candidates):
                raise ValueError('경로 조회 상태와 후보 수가 일치하지 않습니다.')
            routes = evaluate(context, candidates, intersects_geojson)
            # 원본 요청·인증키는 저장하지 않고 안전한 결과 항목만 남깁니다.
            fetch_info = {
                'status': response['status'],
                'source': response.get('source', 'KAKAO_MOBILITY'),
                'attempts': response.get('attempts', []),
                'failure_result_codes': response.get('failure_result_codes', []),
                'closure_status': context['closure_status'],
            }
            return agency_id, routes, fetch_info

        # 최대 4개 기관의 독립적인 API 요청을 병렬 처리하여 Worker 대기 시간을 줄입니다.
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(for_agency, state['preliminary']))
        return {
            'routes_by_agency': {aid: rows for aid, rows, _ in results},
            'route_fetches': {aid: info for aid, _, info in results},
        }
    """
    State에 새로 들어가는 결과: recommendations
    """
    def finalize_agencies(state):
        result = finalize_recommendations(
            state['preliminary'], state['routes_by_agency'],
            config['agency_policy'], config['route_policy'],
        )
        return {'recommendations': result}
    """
    State에 새로 들어가는 결과: result
    """
    def save_results(state):
        saver = config.get('save_analysis', analysis_storage.save_analysis)
        return {'result': saver(state)}

    return {
        'load_incident': load_incident,
        'collect_context': collect_context,
        'assess_risk': assess_risk,
        'select_agencies': select_agencies,
        'evaluate_routes': evaluate_routes,
        'finalize_agencies': finalize_agencies,
        'save_results': save_results,
    }
