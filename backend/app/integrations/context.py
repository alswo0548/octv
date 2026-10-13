
"""
사건 정보와 외부 API 데이터를 하나로 통합
즉, 외부 데이터 수집 단계와 AI 판단 단계를 이어 주는 연결기능

주요 기능
1. PostgreSQL에서 기존 사건 정보 조회
2. 사건 위치를 기준으로 외부 API 요청 정보 생성
3. 기상청 강수량, 수위, 교통 데이터 수집
4. 수집한 데이터를 하나의 딕셔너리로 통합
5. ContextSnapshot 형태로 반환

※ 위험도 계산 및 DB 저장은 이 함수에서 수행하지 않음
"""

from datetime import datetime, timezone
from ai.contracts import ContextSnapshot
from ..db.session import get_connection
from ..incidents.repository import find_detail
from . import weather, water_level, traffic

# 기존 사건과 주변 외부 데이터를 통합하는 함수
def collect_context(incident_id, query_factory):

    with get_connection() as c:
        incident = find_detail(c, incident_id)

    if incident is None:
        raise ValueError('사건이 없습니다.')

    now = datetime.now(timezone.utc)
    queries = query_factory(incident, now)

    rain = weather.fetch_data(                      # 기상청 API를 호출하여 강수량 데이터 수집
        queries['weather']
    )

    water = water_level.fetch_data(                 # 수위 API를 호출하여 수위 데이터 수집
        queries['water_level']
    )
    
    road = traffic.fetch_data(                      # 교통 API를 호출하여 도로 관련 데이터 수집
        queries['traffic']
    )

    # 외부 API에서 가져온 데이터를 하나로 통합
    measurements = {
        'rainfall_mm': rain,
        'water_level_m': water,
        **road
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
