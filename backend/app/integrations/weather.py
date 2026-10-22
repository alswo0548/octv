"""
기상청 초단기실황 API 데이터 처리

주요 기능
1. 기상청 API 응답에서 강수량(RN1) 데이터 및 풍속(WSD, m/s) 데이터 추출 후 최신 관측값 선택 [RN1: 1시간 강수량(mm)]
2. 추출한 데이터은 float 로 변환하여 관측시간을 UTC로 반환한다.
3. normalization.py 에서 만든 measurement()로 데이터 유효성 검사 진행
4. API 한번의 호출로, 강수량과 풍속은 각각 따로 추출하고 검증
"""

from datetime import datetime, timezone, timedelta
from .normalization import fetch_metric, get_json, measurement
import httpx

KST = timezone(timedelta(hours=9))

# 기상청 API를 호출하고 강수량 데이터를 검증하는 함수
def fetch_data(query: dict) -> dict:
    return fetch_metric(
        query,
        parse_rainfall,
        'KMA_ULTRA_NCST',
        'mm'
    )

# 기상청 API 응답에서 강수량을 추출
def parse_rainfall(payload):
    response = payload["response"]

    if str(response["header"]["resultCode"]) != "00": # "00"은 정상적으로 응답했다는 의미
        raise ValueError("기상 API 업무 오류")

    # 응답 데이터에서 실제 관측 목록을 가져옴. 관측 목록이 없으면 빈 리스트를 사용
    items = response["body"].get(
        "items", {}
    ).get("item", [])

    if isinstance(items, dict):
        items = [items]

    # 여러 관측 항목 중 가장 최신 데이터의 RN1(1시간 강수량)만 선택
    rows = [
        x for x in items
        if x.get("category") == "RN1"
    ]

    if not rows:
        return None, None

    row = max(
        rows,
        key=lambda x: (
            x["baseDate"],
            x["baseTime"]
        )
    )

    value = float(row["obsrValue"])

    if value < 0:
        return None, None

    at = datetime.strptime(
        row["baseDate"] + row["baseTime"],
        "%Y%m%d%H%M"
    ).replace(tzinfo=KST)

    return value, at.astimezone(timezone.utc)

# 강수량과 같은 초단기실황 응답에서 풍속(WSD, m/s)을 추출합니다.
def parse_wind(payload):
    response = payload['response']

    if str(response['header']['resultCode']) != '00':
        raise ValueError('기상 API 업무 오류')

    items = response['body'].get(
        'items', {}
    ).get('item', [])

    if isinstance(items, dict):
        items = [items]

    rows = [
        row for row in items
        if row.get('category') == 'WSD'
    ]

    if not rows:
        return None, None

    row = max(
        rows,
        key=lambda x: (
            x['baseDate'],
            x['baseTime']
        )
    )
    value = float(row['obsrValue'])

    if value < 0:
        return None, None

    at = datetime.strptime(
        row['baseDate'] + row['baseTime'],
        '%Y%m%d%H%M'
    ).replace(
        tzinfo=KST
    )
    return value, at.astimezone(timezone.utc)


# 강수량과 풍속 API를 계약으로 변환하며 KMA 호출은 한 번만 수행합니다.
# 측 API는 한 번 호출하지만, 강수량과 풍속은 각각 따로 추출하고 검증한다.
def fetch_observations(query: dict) -> dict:
    specs = {                                   # specs는 어떤 데이터를 어떤 함수로 추출할지 정의한 딕셔너리
        'rainfall_mm': (parse_rainfall, 'mm'),
        'wind_speed_mps': (parse_wind, 'm/s'),
    }
    source = 'KMA_ULTRA_NCST'                   # 데이터 출처

    # 데이터 수집 실패 시 사용할 함수
    def unavailable(status):
        return {
            name: {
                'value': None,
                'observed_at': None,
                'source': source,
                'unit': unit,
                'status': status,
            }
            for name, (_, unit) in specs.items()
        }

    if not query.get('mapped'):
        return unavailable('NO_MAPPING')

    # Celery가 자동 매핑 작업 실행
    # 같은 격자·발표시각은 Redis의 짧은 TTL 캐시를 공유합니다.
    # 관측값의 STALE 검사는 아래 measurement()에서 매 요청마다 다시 수행.
    from .cctv_mapping import get_cached_weather_payload, cache_weather_payload
    try:
        payload = get_cached_weather_payload(query)
        if payload is None:
            payload = get_json(
                query['url'],
                query['params'],
                query.get('headers'),
            )
            cache_weather_payload(query, payload)
    except httpx.TimeoutException:
        return unavailable('TIMEOUT')
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return unavailable('ERROR')

    # 여기서 강수량과 풍속을 각각 추출
    result = {}
    for name, (parser, unit) in specs.items():
        try:
            value, observed_at = parser(payload)
            result[name] = measurement(
                value,
                observed_at,
                source,
                unit,
                query['now'],
                query['max_age_sec'],
            )
        except (ValueError, KeyError, TypeError, OverflowError):
            result[name] = unavailable('ERROR')[name]

    return result
