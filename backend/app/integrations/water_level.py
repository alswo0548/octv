
"""
수위 API에서 관측 데이터 호출

주요 기능
1. 지정된 관측소의 최신 수위 데이터 추출 후, 수위 데이터를 미터(m) 단위로 정규화
2. 관측 시각과 데이터 유효성 검사 후, 위험도 판단에 사용할 수위 정보 반환
3. 동일 관측소의 공식 주의보·경보·심각 수위 기준을 조회해 위험 단계 계산에 사용
"""

import httpx
from .normalization import fetch_metric, parse_mapped, get_json

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

# 한강홍수통제소 관측소 제원 API에서 공식 기준 수위 3종을 조회하는 함수
# WRNWL(홍수주의보) → CAUTION / ALMWL(홍수경보) → WARNING / SRSWL(심각) → DANGER
# 현재 수위와 같은 관측소 코드의 기준값만 사용하며, 누락된 기준값을 임의로 보충하지 않습니다.
def fetch_station_thresholds(query: dict) -> dict:
    result = {
        'risk_thresholds_m': None,
        'risk_thresholds_verified': False,
        'source': 'HRFCO_WATERLEVEL_INFO',
        'status': 'NO_MAPPING',
    }
    spec = query.get('spec')
    info = query.get('station_info')

    # station_info의 URL·인증 정보는 실행 설정에서 전달합니다.
    if (
        not query.get('mapped')
        or not isinstance(spec, dict)
        or not spec.get('station_id')
        or not isinstance(info, dict)
        or not info.get('url')
    ):
        return result

    try:
        payload = get_json(
            info['url'],
            info.get('params', {}),
            info.get('headers')
        )
    except httpx.TimeoutException:
        return {**result, 'status': 'TIMEOUT'}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return {**result, 'status': 'ERROR'}

    try:
        # 한강홍수통제소 waterlevel/info.json의 관측소 제원 목록을 사용합니다.
        rows = payload['content']
        if not isinstance(rows, list):
            raise ValueError('관측소 제원 목록 형식 오류')

        station_id = str(spec['station_id']).strip()
        matches = [
            row for row in rows
            if isinstance(row, dict)
            and str(
                row.get('wlobscd', row.get('WLOBSCD', ''))
            ).strip() == station_id
        ]
        if not matches:
            return result
        if len(matches) != 1:
            return {**result, 'status': 'INVALID'}

        row = matches[0]
        limits = {}
        for label, field in (
            ('CAUTION', 'wrnwl'),
            ('WARNING', 'almwl'),
            ('DANGER', 'srswl'),
        ):
            # API 응답의 소문자·대문자 필드명을 지원합니다.
            raw = row.get(field, row.get(field.upper()))
            if (
                raw is None
                or str(raw).strip().lower() in ('', '-', 'null')
            ):
                raise ValueError('관측소 기준 수위 누락')
            limits[label] = float(raw)

        from math import isfinite
        caution, warning, danger = (
            limits[name] for name in ('CAUTION', 'WARNING', 'DANGER')
        )
        if not (
            all(map(isfinite, (caution, warning, danger)))
            and 0 <= caution < warning < danger
        ):
            raise ValueError('유효하지 않은 관측소 기준 수위')
    except (KeyError, TypeError, ValueError, OverflowError):
        return {**result, 'status': 'INVALID'}

    return {
        **result,
        'risk_thresholds_m': limits,
        'risk_thresholds_verified': True,
        'status': 'OK',
    }

# 선택한 관측소의 확인된 주의·경계·위험 수위 기준으로 수위 위험 단계 생성
# 이 값은 CCTV 도로의 실제 침수 깊이나 싱크홀 지하수위를 뜻하지 않습니다.
def classify_risk_level(query: dict, water: dict) -> dict:
    result = {
        'value': None,
        'observed_at': water.get('observed_at'),
        'source': water.get('source', 'WATER_PROVIDER'),
        'unit': 'category',
        'status': water.get('status', 'NO_DATA'),
    }

    if result['status'] != 'OK':
        return result

    limits = query.get('risk_thresholds_m')
    if (
        query.get('risk_thresholds_verified') is not True
        or not isinstance(limits, dict)
    ):
        # 기존 기준값이 없으면 동일 관측소의 공식 제원 API에서 조회합니다.
        official = fetch_station_thresholds(query)
        if official['status'] != 'OK':
            return {**result, 'status': official['status']}
        limits = official['risk_thresholds_m']

    try:
        caution, warning, danger = (
            float(limits[name]) for name in ('CAUTION', 'WARNING', 'DANGER')
        )
        from math import isfinite
        if not (
            all(map(isfinite, (caution, warning, danger)))
            and 0 <= caution < warning < danger
        ):
            raise ValueError('유효하지 않은 관측소 기준 수위')

        level = float(water['value'])
        if not isfinite(level) or level < 0:
            raise ValueError('유효하지 않은 관측 수위')
    except (KeyError, TypeError, ValueError, OverflowError):
        return {**result, 'status': 'INVALID'}

    label = (
        'DANGER' if level >= danger
        else 'WARNING' if level >= warning
        else 'CAUTION' if level >= caution
        else 'NORMAL'
    )
    return {**result, 'value': label}
