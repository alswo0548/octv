
"""
외부 API에서 수집한 데이터가 정상적인 데이터인지 확인

주요 기능
1. 외부 API 데이터의 출처와 단위 보관
2. 결측·오류·오래된 데이터(NO_DATA / INVALID / STALE) 구분 후 정상 데이터(OK)만 다음 판단 단계에서 사용

추후 확인
현재 모든 음수를 INVALID 로 처리하는 조건이 있다. 
영하의 기온처럼 음수가 정상인 데이터에는 적용하면 안되며, 
숫자 형태가 아닌 문자열 관측값을 거르는 검증은 아직 없다.
"""

from datetime import datetime, timezone
from math import isfinite
import httpx

# 외부 API에서 가져온 관측 데이터가 유효한지 검사하는 함수
def measurement(
    value,              # 관측값
    observed_at,        # 실제 관측된 시각
    source,             # 데이터 제공 기관
    unit,               # 관측값의 단위
    now,
    max_age_sec
):
    base = {
        'value': None,
        'observed_at': None,
        'source': source,
        'unit': unit
    }
    # 관측값이나 관측 시각이 없으면 데이터 없음으로 처리
    if value is None or observed_at is None:
        return {
            **base,
            'status': 'NO_DATA'
        }
    # 관측 시각과 현재 시각에 시간대 정보가 있는지 확인 (UTC/KST 혼동으로 잘못된 시간 계산을 방지)
    if observed_at.tzinfo is None or now.tzinfo is None:
        raise ValueError(
            '외부 시각에는 시간대가 필요합니다.'
        )
    # 숫자가 무한대, NaN 또는 음수인지 검사 (강수량등 파악할때 사용)
    if isinstance(value, (int, float)) and (
        not isfinite(value) or value < 0
    ):
        return {
            **base,
            'status': 'INVALID'
        }
    age = (now - observed_at).total_seconds()

    # 데이터가 허용 시간 이내인지 확인, 0초 이상이고 최대 허용 시간 이하이면 정상. 그 외에는 오래된 데이터로 구분
    status = (
        'OK'
        if 0 <= age <= max_age_sec
        else 'STALE'
    )

    return {
        **base,
        'value': value,
        'status': status,
        'observed_at': (
            observed_at
            .astimezone(timezone.utc)
            .isoformat()
        )
    }

# 정상적인 (상태값이 'OK'일 경우) 관측값만 다음 단계에서 사용하도록 하는 함수
def usable(item):

    return (
        item.get('value')
        if item.get('status') == 'OK'
        else None
    )


"""
외부 API 호출 및 오류 처리를 위한 공통 함수
ex) 응답이 너무 늦을 경우 (5초 후 타임 아웃), 서버 일시적 장애, API 키 오류 등
"""

def get_json(url, params, headers=None):

    with httpx.Client(
        timeout=httpx.Timeout(5.0),
        follow_redirects=False
    ) as client:

        for attempt in range(2):

            try:
                response = client.get(
                    url,
                    params=params,
                    headers=headers or {}
                )
                response.raise_for_status()
                return response.json()

            except (
                httpx.TimeoutException,
                httpx.TransportError
            ):
                if attempt == 1:
                    raise

            except httpx.HTTPStatusError as exc:

                if (
                    attempt == 1
                    or exc.response.status_code < 500
                ):
                    raise

# 외부 API 호출부터 관측값 검증까지 연결하는 함수
def fetch_metric(query, parser, source, unit):
    now = query['now']
    # API 조회 실패 시 반환할 기본 데이터
    empty = {
        'value': None,
        'observed_at': None,
        'source': source,
        'unit': unit
    }
    # 관측소나 지역 매핑 정보가 없는 경우
    if not query.get('mapped'):
        return {
            **empty,
            'status': 'NO_MAPPING'
        }

    try:
        # 외부 API 요청 및 JSON 데이터 가져오기
        payload = get_json(
            query['url'],
            query['params'],
            query.get('headers')
        )

        value, observed_at = parser(payload)

        return measurement(
            value,
            observed_at,
            source,
            unit,
            now,
            query['max_age_sec']
        )

    except httpx.TimeoutException:
        return {
            **empty,
            'status': 'TIMEOUT'
        }

    except (
        httpx.HTTPError,
        ValueError,
        KeyError,
        TypeError
    ):
        return {
            **empty,
            'status': 'ERROR'
        }


"""
수위·도로 API에서 받아온 JSON 데이터 추출 및 변환
"""

# 수위·도로 API의 JSON 응답에서 필요한 관측값을 추출하는 함수
def parse_mapped(payload, spec):
    # payload: 외부 API에서 받은 JSON 데이터
    
    """
    spec: 데이터를 추출하기 위한 필드 매핑 정보
    강수량의 경우는 RN1 이라는 정해진 항목으로 추출했지만,
    수위,도로 API는 기관마다 JSON 구조와 필드명이 다르다.
    그래서 spec가 JSON에서 각각 어떤 필드를 찾아야 하는지 알려주는 설정이다.
    """

    rows = payload

    for key in spec['rows_path']:
        rows = rows[key]

    # 데이터가 딕셔너리 한 개라면 리스트로 변환
    if isinstance(rows, dict):
        rows = [rows]

    # 요청한 관측소 ID와 일치하는 데이터만 추출
    matches = [
        r for r in rows
        if str(r[spec['station_key']])
        == str(spec['station_id'])
    ]

    if not matches:
        return None, None

    # 관측소 데이터 중 가장 최신 시각의 데이터 선택
    row = max(
        matches,
        key=lambda r: r[spec['time_key']]
    )

    raw = row[spec['value_key']]

    if raw is None or str(raw).strip() in {
        '',
        '-',
        'null'
    }:
        return None, None

    at = datetime.strptime(
        row[spec['time_key']],
        spec['time_format']
    ).replace(
        tzinfo=spec['timezone']
    )

    # 숫자 데이터는 float으로 변환하고 단위 보정
    # 예: 250cm × 0.01 = 2.5m
    value = (
        raw
        if spec.get('numeric') is False
        else float(raw) * spec.get('scale', 1)
    )

    return value, at
