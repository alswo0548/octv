
"""
수위 API에서 관측 데이터 호출

주요 기능
1. 지정된 관측소의 최신 수위 데이터 추출 후, 수위 데이터를 미터(m) 단위로 정규화
2. 관측 시각과 데이터 유효성 검사 후, 위험도 판단에 사용할 수위 정보 반환
"""

from .normalization import fetch_metric, parse_mapped

# 수위 API를 호출하고 관측 데이터를 반환하는 함수
def fetch_data(query: dict) -> dict:

    return fetch_metric(
        query,                                      # API 주소, 관측소 정보, 인증 정보 등
        lambda payload: parse_mapped(               # normalization.py의  parse_mapped() 함수를 사용하여 API 응답(payload)과 매핑 설정(spec)을 전달
            payload,
            query['spec']
        ),
        # source가 있으면 해당 값을 사용
        # 없으면 WATER_PROVIDER를 기본값으로 사용
        query.get('source', 'WATER_PROVIDER'),
        'm'
    )
