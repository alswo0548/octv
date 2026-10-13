
"""
도로 교통·차단·위험구역 외부 API 데이터를 수집

주요 기능
1. 도로 교통 혼잡 수준 / 차단된 차로 수 / 도로 통제 구역 정보 등 외부 API 응답 데이터 정규화
2. 위험도 및 경로 판단에 필요한 정보 반환
"""

from .normalization import fetch_metric, parse_mapped


# 교통·도로 통제 데이터를 수집하는 함수
def fetch_data(query: dict) -> dict:
    units = {
        'traffic_level': 'category',
        'blocked_lane_count': 'lanes',
        'closures': 'GeoJSON'
    }

    result = {}

    for field, unit in units.items():

        q = query.get(
            field,
            {
                'mapped': False,
                'now': query['now']
            }
        )

        # 공통 API 호출 및 데이터 검증 함수 실행
        result[field] = fetch_metric(
            q,                                      # 현재 교통 항목의 API 요청 정보
            lambda payload, q=q: parse_mapped(      # q=q는 반복문에서 현재 설정을 유지하기 위함
                payload,
                q['spec']
            ),
            q.get('source', 'TRAFFIC_PROVIDER'),
            unit
        )

    # 수집한 교통 데이터 3종을 딕셔너리로 반환
    return result
