"""
LangGraph가 계산한 판단 결과를 기존 PostgreSQL DB에 저장하는 역할
"""

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from math import isfinite


# 기존 사건 조회 함수를 재사용합니다. import만으로 DB에 접속하지 않습니다.
# LangGraph에서는 사건 ID만 전달받아서 판단 작업을 시작하는데, 
# 사건 ID만으로는 재난 유형이나 CCTV 위치를 알수 없기 때문에 DB에서 해당 사건의 상세 정보를 가지고 온다.
def load_incident(incident_id: int):
    from ..db.session import get_connection
    from .repository import find_detail

    with get_connection() as connection:
        return find_detail(connection, incident_id)


# 추천에 필요한 좌표·관할 정보까지 반환하는 기존 조회 함수를 재사용합니다.
# 위험도 계산이 끝난 뒤 재난에 대응할 기관들을 추천해줘야하기 때문에 관련 정보를 DB에서 가지고 온다.
def load_agencies():
    from ..agencies.repository import list_analysis_agencies
    from ..db.session import get_connection

    with get_connection() as connection:
        return list_analysis_agencies(connection)


# 공통 연결의 정상 종료 commit / 예외 rollback 동작을 그대로 사용합니다. 
# LangGraph가 모든 분석을 마쳤을때 state에 들어있는 결과들을 db에 저장해서 나중에 웹에서 확인할 수 있게 한다.
def save_analysis(state: dict) -> dict:
    from ..db.session import get_connection

    with get_connection() as connection:
        return save_analysis_on_connection(connection, state)


# JSON에 저장할 시각·Decimal을 변환하며, 비정상 숫자는 결측값으로 보존합니다.
# Decimal, datetime, NaN 값들을 바로 JSON으로 변환하려면 문제가 생기기때문에 JSON에 넣을수있는 자료형으로 변환함
def json_ready(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError('JSON 시각에는 시간대가 필요합니다.')
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float):
        return value if isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


# DB 테스트에서만 바꿀 수 있는 얇은 JSON 어댑터입니다. 운영에서는 psycopg를 사용합니다.
def _json(value):
    from psycopg.types.json import Jsonb
    return Jsonb(json_ready(value))


# 외부 API에서 가져온 측정값이 정상적인 숫자인지 확인
# 예를 들어 강수량, 수위, 차단된 차로 수 등을 저장할 때 사용. 조건을 만족하지 않으면 None을 반환
def _number(measurements: dict, field: str, maximum: float, integer=False):
    item = measurements.get(field, {})
    if item.get('status') != 'OK' or isinstance(item.get('value'), bool):
        return None
    try:
        value = float(item['value'])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not isfinite(value) or not 0 <= value <= maximum:
        return None
    if integer:
        return int(value) if value.is_integer() else None
    return value


# 위험도 평가에 반영된 병원과 학교 중 대표 시설 하나를 선택
# 가장 가까운 시설이 아닌 위험도 평가에서 더 높은 점수를 받은 시설을 선택
def _facility(assessment: dict):
    components = assessment['risk_breakdown'].get('components', {})
    values = [
        (name, kind, components[name])
        for name, kind in (
            ('nearby_hospital_distance_m', 'HOSPITAL'),
            ('nearby_school_distance_m', 'SCHOOL'),
        )
        if name in components
    ]
    if not values:
        return None, None
    _, kind, chosen = max(values, key=lambda item: item[2]['points'])
    return kind, round(float(chosen['value']))


# 외부 상황 데이터를 기존 DB 컬럼에 맞춰 저장하고, 생성된 Context ID를 반환하는 함수.
def _save_context(connection, state):
    snapshot = state['context']
    if snapshot.captured_at.tzinfo is None:
        raise ValueError('Context 시각에는 시간대가 필요합니다.')
    measurements = snapshot.measurements
    facility, distance = _facility(state['assessment'])
    if state['assessment']['risk_breakdown'].get('demo_simulation', {}).get('enabled'):
        # Demo risk is simulated, but incident_contexts must contain real API data.
        # Never store a hypothetical distance as a measured facility distance.
        facility, distance = None, None
        for field, kind in (('nearby_hospital_distance_m', 'HOSPITAL'),
                            ('nearby_school_distance_m', 'SCHOOL')):
            real = _number(snapshot.measurements, field, 100000.0)
            if real is not None and (distance is None or real < distance):
                facility, distance = kind, round(real)
    traffic = measurements.get('traffic_level', {})
    road = measurements.get('road_type', {})
    params = {
        'incident_id': state['incident_id'],
        'rainfall_mm': _number(measurements, 'rainfall_mm', 99999.99),
        'water_level_m': _number(measurements, 'water_level_m', 99999.99),
        'traffic_level': (
            str(traffic['value']) if traffic.get('status') == 'OK'
            and traffic.get('value') is not None else None
        ),
        'blocked_lane_count': _number(
            measurements, 'blocked_lane_count', 2147483647, integer=True
        ),
        'road_type': (
            str(road['value']) if road.get('status') == 'OK'
            and road.get('value') is not None else None
        ),
        'nearby_facility_type': facility,
        'nearby_facility_distance_m': distance,
        # 기존 TIMESTAMP WITHOUT TIME ZONE 컬럼에는 UTC 숫자 시각을 저장합니다.
        'captured_at': snapshot.captured_at.astimezone(timezone.utc).replace(
            tzinfo=None
        ),
    }
    if params['traffic_level'] is not None and len(params['traffic_level']) > 30:
        params['traffic_level'] = None
    return connection.execute(
        """
        INSERT INTO incident_contexts (
            incident_id, rainfall_mm, water_level_m, traffic_level,
            blocked_lane_count, road_type, nearby_facility_type,
            nearby_facility_distance_m, captured_at
        ) VALUES (
            %(incident_id)s, %(rainfall_mm)s, %(water_level_m)s,
            %(traffic_level)s, %(blocked_lane_count)s, %(road_type)s,
            %(nearby_facility_type)s, %(nearby_facility_distance_m)s,
            %(captured_at)s
        ) RETURNING id
        """,
        params,
    ).fetchone()['id']


# 기존 Rule 결과는 바꾸지 않고, 측정값·출처·수집 상태를 추가 기록합니다.
def _save_assessment(connection, state, context_id):
    assessment = state['assessment']
    snapshot = state['context']
    breakdown = deepcopy(assessment['risk_breakdown'])
    breakdown['context_snapshot'] = {
        'context_id': context_id,
        'captured_at': snapshot.captured_at,
        'sources': snapshot.sources,
        'measurements': snapshot.measurements,
    }
    breakdown['orchestration'] = {
        'route_fetches': state['route_fetches'],
        'no_agency_candidates': not bool(state['recommendations']),
    }
    params = {
        **assessment,
        'incident_id': state['incident_id'],
        'risk_breakdown_json': _json(breakdown),
        'priority_breakdown_json': _json(assessment['priority_breakdown']),
    }
    return connection.execute(
        """
        INSERT INTO incident_assessments (
            incident_id, risk_score, risk_level, risk_breakdown_json,
            priority_score, priority, priority_breakdown_json, rule_version
        ) VALUES (
            %(incident_id)s, %(risk_score)s, %(risk_level)s,
            %(risk_breakdown_json)s, %(priority_score)s, %(priority)s,
            %(priority_breakdown_json)s, %(rule_version)s
        ) RETURNING id
        """,
        params,
    ).fetchone()['id']


# 기존 Repository를 재사용해서 최종 기관 추천 결과를 저장하는 함수.
def _save_recommendation(connection, incident_id, recommendation):
    from ..agencies.repository import save_recommendation
    return save_recommendation(connection, incident_id, recommendation)

# 기관 추천에 연결된 경로 평가 결과를 기존 save_evaluation() 함수로 저장
def _save_route(connection, recommendation_id, route):
    from ..routes.repository import save_evaluation
    return save_evaluation(connection, recommendation_id, route)


# 연결 자체의 commit/rollback은 호출자가 관리합니다. DDL·삭제·상태 변경 없음
"""
LangGraph 분석 결과를 저장하기 전에 안전성을 검사하고, 모든 결과를 하나의 트랜잭션으로 저장하는 함수
아래 세가지 작업을 진행함
1. 저장해도 되는 사건인지 확인
2. 중복 저장이나 잘못된 결과인지 확인 
3. Context → 위험도 → 기관 추천 → 경로 평가 순서로 DB 저장
"""
def save_analysis_on_connection(connection, state: dict) -> dict:
    # 저장하려는 사건 ID 확인
    incident_id = state['incident_id']
    if state['context'].incident_id != incident_id:
        raise ValueError('저장할 사건과 Context의 ID가 다릅니다.')
    result = {'incident_id': incident_id, 'status': 'SKIPPED'}
    connection.execute("SET LOCAL TIME ZONE 'UTC'")
    # 대기 후 최신 평가를 다시 확인하기 위해 READ COMMITTED 연결을 사용합니다.
    """ 
    여기서 READ COMMITTED 란? 다른 작업이 저장을 확정(COMMIT)한 결과를 이후 SQL에서 볼 수 있도록 하는 격리 수준
    이 프로젝트에서 사건을 여러 Worker가 동시에 분석할 가능서이 있는데
    그럴 때 먼저 저장한 Worker의 결과를 뒤에 실행되는 Worker가 확인할 수 있어야 중복 저장을 막을 수 있음
    """
    isolation = connection.execute('SHOW transaction_isolation').fetchone()
    if isolation['transaction_isolation'] != 'read committed':
        raise ValueError('05번 저장 연결은 READ COMMITTED 격리가 필요합니다.')
    # FOR UPDATE: Worker A와 Worker B가 동시에 같은 사건을 분석 결과를 저장하려고 할때
    # 해당 사건 행에 잠금(Lock)을 걸어 기다리게 하는 기능
    incident = connection.execute(
        'SELECT id, status FROM incidents WHERE id = %s FOR UPDATE',
        (incident_id,),
    ).fetchone()
    if incident is None:
        return {**result, 'skipped': 'NOT_FOUND'}
    if incident['status'] not in ('DETECTED', 'CONFIRMED'):
        return {**result, 'skipped': 'INACTIVE'}
    existing = connection.execute(
        'SELECT id FROM incident_assessments '
        'WHERE incident_id = %s ORDER BY id DESC LIMIT 1',
        (incident_id,),
    ).fetchone()
    if existing:
        return {**result, 'skipped': 'ALREADY_ASSESSED', 'assessment_id': existing['id']}

    # 예전 작업에서 일부만 저장된 자료는 지우거나 덮어쓰지 않고 확인을 요청합니다.
    partial = connection.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM incident_contexts WHERE incident_id = %s
            UNION ALL
            SELECT 1 FROM incident_agency_recommendations WHERE incident_id = %s
        ) AS present
        """,
        (incident_id, incident_id),
    ).fetchone()
    if partial['present']:
        raise ValueError('기존 일부 분석 결과가 있습니다. 자동 덮어쓰기를 중단합니다.')
    for recommendation in state['recommendations']:
        if recommendation['score_breakdown_json'].get('candidate_stage') != 'FINAL':
            raise ValueError('사전 추천 점수가 아닌 최종 기관 점수만 저장할 수 있습니다.')

    context_id = _save_context(connection, state)
    assessment_id = _save_assessment(connection, state, context_id)
    # 기관별 경로를 저장하는 반복문
    recommendation_ids, route_count = [], 0
    for recommendation in state['recommendations']:
        row = _save_recommendation(connection, incident_id, recommendation)
        recommendation_ids.append(row['id'])
        for route in state['routes_by_agency'].get(recommendation['agency_id'], []):
            _save_route(connection, row['id'], route)
            route_count += 1
    # DB 새로 저장 코드가 아닌 저장 작업의 결과를 호출자에게 알려주는 반환값
    return {
        'incident_id': incident_id,                                             # 분석한 ID
        'status': 'SAVED',                                                      # SAVED (판단 결과 저장 작업이 성공했다는 의미)
        'context_id': context_id,                                               # 생성된 Context 기록 ID
        'assessment_id': assessment_id,                                         # 생성된 위험도 평가 기록 ID
        'recommendation_ids': recommendation_ids,                               # 저장된 기관 추천 기록 ID 목록
        'route_count': route_count,                                             # 저장한 경로 평가 개수
        'risk_score': state['assessment']['risk_score'],                        # 위험도 점수
        'risk_level': state['assessment']['risk_level'],                        # 위험도 등급
        'priority': state['assessment']['priority'],                            # 사건 우선순위
        'missing_fields': state['assessment']['risk_breakdown']['missing'],     # 평가 시 부족했던 데이터 항목
    }
