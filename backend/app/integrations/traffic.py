
"""
도로 교통·차단·위험구역 외부 API 데이터를 수집

주요 기능
1. 도로 교통 혼잡 수준 / 차단된 차로 수 / 도로 통제 구역 정보 등 외부 API 응답 데이터 정규화
2. 위험도 및 경로 판단에 필요한 정보 반환
"""

from .normalization import fetch_metric, parse_mapped, parse_configured_metric


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

# Rule 및 기관 상황 적합성에 필요한 추가 관측 항목
_RULE_UNITS = {
    'traffic_volume_level': 'category',
    'population_density_level': 'category',
    'road_type': 'category',
    'road_rank': 'code',
    'closure_confirmed': 'boolean',
    'traffic_control': 'category',
}


def _normalize_rule_item(field, item, config):
    if item.get('status') != 'OK':
        return item

    raw = item['value']
    try:
        if field in ('traffic_volume_level', 'population_density_level'):
            if (
                isinstance(raw, str)
                and raw.upper() in ('LOW', 'MEDIUM', 'HIGH')
            ):
                if config.get('category_verified') is not True:
                    raise ValueError('등급 분류 기준 미확인')
                value = raw.upper()
            else:
                low, high = (float(v) for v in config['category_thresholds'])
                from math import isfinite
                if not (
                    isfinite(low)
                    and isfinite(high)
                    and 0 <= low < high
                ):
                    raise ValueError('등급 경계값 오류')
                number = float(raw)
                if not isfinite(number) or number < 0:
                    raise ValueError('관측값 오류')
                value = (
                    'LOW' if number < low
                    else 'MEDIUM' if number < high
                    else 'HIGH'
                )
                item = {
                    **item,
                    'raw_value': number,
                    'raw_unit': config.get('raw_unit')
                }
        elif field == 'road_type':
            value = str(raw).upper()
            if value not in (
                'UNDERPASS', 'NORMAL', 'OVERPASS', 'BRIDGE', 'TUNNEL'
            ):
                raise ValueError('도로 유형 오류')
        elif field == 'road_rank':
            if isinstance(raw, (int, float)) and float(raw).is_integer():
                value = str(int(raw))
            else:
                value = str(raw)
            if value not in (
                '101', '102', '103', '104', '105', '106', '107', '108'
            ):
                raise ValueError('도로 등급 오류')
        elif field == 'closure_confirmed':
            if raw in (True, 1, '1', 'TRUE', 'true'):
                value = True
            elif raw in (False, 0, '0', 'FALSE', 'false'):
                value = False
            else:
                raise ValueError('통제 여부 오류')
        elif field == 'traffic_control':
            value = str(raw).upper()
            if value not in ('NONE', 'PARTIAL', 'FULL'):
                raise ValueError('통제 수준 오류')
        else:
            value = raw
    except (TypeError, ValueError, KeyError, OverflowError):
        return {**item, 'value': None, 'status': 'INVALID'}

    result = {**item, 'value': value}
    if field == 'traffic_control':
        result['level'] = value
    return result


# 기존 3종 결과에 확인된 지역·도로의 추가 Rule 관측을 합칩니다.
def fetch_rule_data(query: dict) -> dict:
    result = fetch_data(query)
    for field, unit in _RULE_UNITS.items():
        config = query.get(field, {'mapped': False})
        # 외부 응답을 현재 사건의 도로 링크·행정구역에 매칭한 경우에만 사용합니다.
        config = {
            **config,
            'mapped': (
                config.get('mapped') is True
                and config.get('scope_verified') is True
            ),
            'now': query['now'],
        }
        item = fetch_metric(
            config,
            lambda payload, spec=config.get('spec', {}): parse_configured_metric(
                payload,
                spec
            ),
            config.get('source', 'TRAFFIC_OR_SPATIAL_PROVIDER'),
            unit,
        )
        result[field] = _normalize_rule_item(field, item, config)

    # 도로 차로 수와 차단 구역은 위치·방향 확인 전에는 검증 완료로 처리하지 않습니다.
    lane_query = query.get('blocked_lane_count', {})
    if lane_query.get('road_match_verified') is not True:
        old = result['blocked_lane_count']
        result['blocked_lane_count'] = {
            **old, 'value': None, 'status': 'NO_MAPPING',
        }
    closures = result['closures']
    closures['blocked_zones_verified'] = (
        closures.get('status') == 'OK'
        and query.get('closures', {}).get('blocked_zones_verified') is True
        and isinstance(closures.get('value'), list)
    )

    # 검증된 도로 통제 수준에서 위험도 판단에 사용할 통제 여부를 구합니다.
    if result['closure_confirmed']['status'] == 'NO_MAPPING':
        control = result['traffic_control']
        if control.get('status') == 'OK':
            result['closure_confirmed'] = {
                'value': control['value'] in ('PARTIAL', 'FULL'),
                'observed_at': control.get('observed_at'),
                'source': control['source'],
                'unit': 'boolean', 'status': 'OK',
                'derived_from': 'traffic_control',
            }
    return result
