
"""
사건 정보와 외부 API 데이터를 하나로 통합
즉, 외부 데이터 수집 단계와 AI 판단 단계를 이어 주는 연결기능

주요 기능
1. PostgreSQL에서 기존 사건 정보 조회
2. 사건 위치를 기준으로 외부 API 요청 정보 생성
3. 기상청 강수량, 기상청 풍속, 수위, 교통 데이터, 병원,학교 등 주요시설과의 거리 수집
4. 수집한 데이터를 하나의 딕셔너리로 통합
5. ContextSnapshot 형태로 반환

※ 위험도 계산 및 DB 저장은 이 함수에서 수행하지 않음
"""

from datetime import datetime, timezone
from ai.contracts import ContextSnapshot
from ..db.session import get_connection
from ..incidents.repository import find_detail
from . import weather, water_level, traffic, places
from .auto_match_providers import nearby_event_measurement

# 기존 사건과 주변 외부 데이터를 통합하는 함수
def collect_context(incident_id, query_factory):

    with get_connection() as c:
        incident = find_detail(c, incident_id)

    if incident is None:
        raise ValueError('사건이 없습니다.')

    now = datetime.now(timezone.utc)
    queries = query_factory(incident, now)

    # 신규 관측이 설정되지 않은 CCTV는 출처별 NO_MAPPING으로 남깁니다.
    weather_query = {
        **queries.get('weather', {'mapped': False}),
        'now': now
    }
    weather_data = weather.fetch_observations(      # 기상청 API를 호출하여 강수량 데이터 수집
        weather_query
    )

    water_query = {
        **queries.get('water_level', {'mapped': False}),
        'now': now
    }
    water = water_level.fetch_data(                 # 수위 API를 호출하여 수위 데이터 수집
        water_query
    )

    # 수위 기준이 없으면 동일 관측소의 공식 기준 수위를 추가 조회합니다.
    # 관측소 ID와 제원 API 요청 정보는 query_factory에서 전달받습니다.
    water_risk = water_level.classify_risk_level(
        water_query,
        water
    )

    road = traffic.fetch_rule_data(                 # 교통 API를 호출하여 도로 관련 데이터 수집
        {
            **queries.get('traffic', {}),
            'now': now
        }
    )
    traffic_events = nearby_event_measurement(queries.get('traffic_nearby_events'))
    facilities = places.fetch_data(
        {
            **queries.get('places', {'mapped': False}),
            'now': now
        }
    )

    # 외부 API에서 가져온 데이터를 하나로 통합
    measurements = {
        **weather_data,
        'water_level_m': water,
        'water_risk_level': water_risk,
        **road,
        'traffic_nearby_events': traffic_events,
        **facilities,
        # 자동 매핑 미확정 사유는 Rule 입력과 별도 이름으로 보존합니다.
        # 위험 판단·기관 추천 정책은 변경하지 않습니다.
        **queries.get('mapping_references', {}),
    }

    # 사건 ID, 수집 시각, 외부 데이터, 출처를 ContextSnapshot 형식으로 묶음
    # 다음 위험도 판단 단계에 한 번에 전달하기 위함
    snapshot = ContextSnapshot(
        incident_id,
        now,
        measurements,
        tuple(
            sorted({
                v['source']
                for v in measurements.values()
            })
        )
    )

    return snapshot
