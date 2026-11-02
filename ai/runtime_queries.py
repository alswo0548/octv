"""CCTV별 검증된 요청 설정을 Context 함수의 query 형식으로 변환합니다.

입력: 실행 설정 JSON + 기존 환경변수 + DB 사건 + 현재 UTC 시각
처리: 해당 CCTV 설정 선택 → 인증값 주입 → 시각·timezone 변환
출력: weather / water_level / traffic / places 요청 딕셔너리

CCTV 정보를 바탕으로 외부 API가 사용할 요청 정보를 만들어 주는 역할
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from math import isfinite
from string import Template
from urllib.parse import urlsplit

KST = timezone(timedelta(hours=9))
TRAFFIC_FIELDS = (
    'traffic_level', 'blocked_lane_count', 'closures',
    'traffic_volume_level', 'population_density_level',
    'road_type', 'road_rank', 'closure_confirmed', 'traffic_control',
)


# JSON 문자열 안의 ${WEATHER_API_KEY} 같은 항목에 실제 설정값을 넣습니다.
# 그 과정에서 문자열뿐 아니라 딕셔너리와 리스트 내부까지 확인하기 위해 재귀 호출을 사용
def _substitute(value, variables):
    if isinstance(value, str):
        try:
            return Template(value).substitute(variables)
        except (KeyError, ValueError):
            raise ValueError('API 요청 템플릿의 변수 설정을 확인하세요.') from None
    if isinstance(value, dict):
        return {key: _substitute(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute(item, variables) for item in value]
    return value


# 실제 API를 호출 X. 요청에 사용할 정보를 준비하고 검사하는 함수
# 설정 복사 + 실제 변수값 채우기, 즉 원본 설정을 직접 변경하지 않고 새로운 요청 정보를 만든다
def _request_settings(settings: dict, variables: dict) -> dict:
    result = _substitute(deepcopy(settings), variables) # deepcopy(settings)으로 원본 설정을 복사해서 _substitute로 ${변수명}을 실제 값으로 변경.
    return _validate_request(result)


# 실제 API를 호출 X. 요청에 사용할 정보를 준비하고 검사하는 함수
# URL · params · headers 형식 검사
def _validate_request(result: dict) -> dict: 
    # 주소를 구성 요소별로 나눠주는 함수. 주소가 어떤 통신 방식을 사용하고, 어느 서버를 가리키는지 구분
    parsed = urlsplit(result.get('url', ''))
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('활성 API의 url을 확인하세요.')
    # url에 사용자 정보가 들어갔는지 검토
    if parsed.username or parsed.password:
        raise ValueError('URL 사용자정보 대신 API 인증 설정을 사용하세요.')
    result.setdefault('params', {})
    if not isinstance(result['params'], dict):
        raise ValueError('API params는 JSON 객체여야 합니다.')
    if result.get('headers') is not None and not isinstance(result['headers'], dict):
        raise ValueError('API headers는 JSON 객체여야 합니다.')
    return result


# 앞의 함수의 기능들을 활용하여 cctv별 외부 API 요청 정보를 최종적으로 준비하는 함수
"""
CCTV별 API 요청 설정
_prepare_query() 아래 다섯 가지를 처리
① CCTV 매핑 여부 확인
② 필요한 API Key 존재 여부 확인
③ API 요청 정보 완성·검증
④ 데이터 유효시간 기준 확인
⑤ 시간대 정보 변환
"""
def _prepare_query(settings, now, variables):
    if not isinstance(settings, dict):
        raise ValueError('CCTV별 API 요청 설정은 JSON 객체여야 합니다.')
    # CCTV에 API 매핑이 되어 있는지 확인
    if settings.get('mapped') is not True:
        return {'mapped': False, 'now': now}
    required = settings.get('required_env', [])
    if not isinstance(required, list) or any(not isinstance(k, str) for k in required):
        raise ValueError('required_env는 환경변수 이름의 리스트여야 합니다.')
    if any(not variables.get(key) for key in required):
        return {'mapped': False, 'now': now}
    result = _request_settings(settings, variables)
    try:
        age = float(result['max_age_sec'])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError('활성 API의 max_age_sec 설정이 필요합니다.') from None
    if not isfinite(age) or age <= 0:
        raise ValueError('max_age_sec는 유한한 양수여야 합니다.')
    result['max_age_sec'] = age
    result['now'] = now
    spec = result.get('spec')
    if isinstance(spec, dict) and 'timezone' in spec:
        zones = {'KST': KST, 'Asia/Seoul': KST, 'UTC': timezone.utc}
        zone = spec['timezone']
        if zone not in zones:
            raise ValueError('spec.timezone은 KST, Asia/Seoul, UTC 중 하나입니다.')
        spec['timezone'] = zones[zone]
    return result


# API별 변환 설정을 준비하는 함수를 만들어 config['query_factory']에 전달합니다.
# 즉, CCTV에 맞는 날씨·수위·교통·주요시설 API 요청 정보를 한 번에 준비하는 역할
"""
사건 예시 OCTV에서 침수 사건이 발생
- 사건 ID: 31번
- CCTV ID: 105번
- 위치: 서울의 특정 도로

이때 OCTV는 CCTV 105번 위치를 기준으로 외부 데이터를 수집. 그때 CCTV마다 기상 관측소, 수위 관측소, 도로 정보가 다를 수 있다 
그래서 CCTV ID를 확인해서 해당 CCTV에 맞는 API 요청 정보를 만들어주는 것이 이 함수의 목적
"""
def create_query_factory(settings: dict, environment: dict):
    mapping = deepcopy(settings.get('cctvs', {}))
    if not isinstance(mapping, dict):
        raise ValueError('cctvs 설정은 CCTV ID를 키로 가진 JSON 객체여야 합니다.')
    auto_mapping = str(environment.get('OCTV_AUTO_MAPPING_ENABLED', '0')).strip() == '1'
    secrets = {
        key: str(environment.get(key, '') or '').strip()
        for key in (
            'WEATHER_API_KEY', 'WATER_LEVEL_API_KEY',
            'TRAFFIC_API_KEY', 'ROUTE_API_KEY', 'PLACES_API_KEY',
        )
    }

    """
    create_query_factory() 는 API 요청을 만드는 전용함수를 제작
    query_factory() 는 만들어진 함수로 실제 사건에 맞는 요청 정보를 만드는 작업
    이러한 구조를 Python에서는 클로저(closure)와 관련된 패턴이라고 함.
    내부함수인 query_factory() 가 외부 함수에서 만든 mapping, secrets 를 기억해서 사용함.
    """
    def query_factory(incident: dict, now: datetime) -> dict:
        if now.tzinfo is None:
            raise ValueError('요청 생성 시각에는 시간대가 필요합니다.')
        cctv = deepcopy(mapping.get(str(incident['cctv_id']), {}))
        if not isinstance(cctv, dict):
            raise ValueError('해당 CCTV의 요청 설정을 확인하세요.')
        variables = {
            **secrets,
            'CCTV_ID': str(incident['cctv_id']),
            'LATITUDE': str(incident['latitude']),
            'LONGITUDE': str(incident['longitude']),
            'REGION_CODE': str(incident.get('region_code') or ''),
        }

        # 기본값은 자동 매핑. 자동으로 확인하지 못한 항목에 한해서만
        # 기존에 명시적으로 mapped=true로 검증한 JSON 설정을 보존합니다.
        # 수위는 공식 관측소 반경 기반으로 연결. 교통의 미확정 링크는 Rule에서 제외합니다.
        reference_metadata = {}
        if auto_mapping:
            from backend.app.integrations.cctv_mapping import (
                weather_request_for, water_request_for, traffic_request_for,
                mapping_reference_for,
            )
            # Opt-in lazy repair: expired Redis mappings otherwise remain absent
            # until monitoring is toggled or a manual prewarm is run.
            if str(environment.get('OCTV_MAPPING_REPAIR_ON_MISS', '0')) == '1':
                from backend.app.integrations.cctv_mapping import ensure_mapping
                ensure_mapping(incident)
            reference_metadata = mapping_reference_for(incident)
            automatic_weather = weather_request_for(incident)
            if automatic_weather.get('mapped') is True:
                cctv['weather'] = automatic_weather
            automatic_water = water_request_for(incident)
            if automatic_water.get('mapped') is True:
                cctv['water_level'] = automatic_water
            automatic_traffic = traffic_request_for(incident)
            if any(isinstance(item, dict) and item.get('mapped') is True
                   for item in automatic_traffic.values()):
                previous = cctv.get('traffic', {})
                cctv['traffic'] = {
                    **(previous if isinstance(previous, dict) else {}),
                    **automatic_traffic,
                }
        from backend.app.integrations.verified_traffic import reviewed_query
        traffic_link_query = reviewed_query(incident, cctv.get('traffic_link_review'), now, environment)
        weather = cctv.get('weather', {'mapped': False})
        if not isinstance(weather, dict):
            raise ValueError('weather 설정은 JSON 객체여야 합니다.')
        if weather.get('mapped') is True:
            # 제공 지연 시간은 신청한 API 명세를 확인하여 설정합니다.
            # 날짜가 바뀌는 경우에도 이전 날짜·시간을 함께 계산합니다.
            delay = weather.get('publication_delay_min')
            if type(delay) is not int or not 0 <= delay < 60:
                raise ValueError('weather.publication_delay_min: 0~59 정수 필요')
            base = now.astimezone(KST) - timedelta(minutes=delay)
            variables['KMA_BASE_DATE'] = base.strftime('%Y%m%d')
            variables['KMA_BASE_TIME'] = base.strftime('%H00')
            if not secrets['WEATHER_API_KEY']:
                weather = {'mapped': False}
        weather_query = _prepare_query(weather, now, variables)
        weather_query['previous_hour_fallback'] = str(environment.get('OCTV_WEATHER_PREVIOUS_HOUR_ENABLED', '0')) == '1'

        water = cctv.get('water_level', {'mapped': False})
        if not isinstance(water, dict):
            raise ValueError('water_level 설정은 JSON 객체여야 합니다.')
        if water.get('mapped') is True and not secrets['WATER_LEVEL_API_KEY']:
            water = {'mapped': False}
        water_query = _prepare_query(water, now, variables)
        if water_query.get('mapped'):
            spec = water_query.get('spec', {})
            if (not isinstance(spec, dict) or spec.get('station_id') is None
                    or not str(spec.get('station_id', '')).strip()):
                raise ValueError('수위 spec.station_id가 필요합니다.')
            info = water_query.get('station_info')
            if info:
                water_query['station_info'] = _validate_request(info)
            # 임의 기준값 입력을 우회 경로로 사용하지 않고 공식 제원 조회를 사용합니다.
            water_query.pop('risk_thresholds_m', None)
            water_query.pop('risk_thresholds_verified', None)

        # 돌발정보는 실시간 변동 데이터이므로 감시 ON 매핑 캐시와 분리하여
        # 사건 수집 시 최대 90초 공유 캐시를 재사용합니다.
        traffic_events_query = {'mapped': False, 'now': now}
        if auto_mapping and secrets['TRAFFIC_API_KEY']:
            from backend.app.integrations.auto_match_providers import traffic_event_radius_m
            traffic_events_query = {
                'mapped': True, 'api_key': secrets['TRAFFIC_API_KEY'],
                'latitude': incident['latitude'], 'longitude': incident['longitude'],
                'radius_m': traffic_event_radius_m(environment), 'now': now,
            }

        traffic = cctv.get('traffic', {})
        if not isinstance(traffic, dict):
            raise ValueError('traffic 설정은 JSON 객체여야 합니다.')
        traffic_query = {'now': now}
        for name in TRAFFIC_FIELDS:
            item = traffic.get(name, {'mapped': False})
            # 예전 3개 교통 항목에도 now를 각각 넣어 KeyError를 방지합니다.
            traffic_query[name] = _prepare_query(item, now, variables)

        # 시설 좌표는 저장된 CCTV 좌표를 사용합니다. API 결과를 추정하지 않습니다.
        places_key = secrets['PLACES_API_KEY'] or secrets['ROUTE_API_KEY']
        return {
            'weather': weather_query,
            'water_level': water_query,
            'traffic': traffic_query,
            'traffic_nearby_events': traffic_events_query,
            'traffic_link_observation': traffic_link_query,
            'mapping_references': reference_metadata,
            'places': {
                'mapped': bool(places_key),
                'api_key': places_key,
                'latitude': incident['latitude'],
                'longitude': incident['longitude'],
                'now': now,
            },
        }

    return query_factory

"""
    return query_factory 가 필요한 이유?
    create_query_factory() 가 호출되면 내부의 query_factory()를 만들어 반환한다 
    그리고 LangGraph는 나중에 사건을 분석할 때 그 함수를 실행.

    실제 실행순서.

    ① 설정 준비 시점 (CCTV 매핑과 API Key를 기억하는 함수 생성)
    factory = create_query_factory(settings, environment)

    ② 사건 분석 시점 (해당 CCTV의 API 요청 정보 생성)
    queries = factory(incident, now)

    ③ 외부 데이터 수집
    기상 · 수위 · 교통 · 주요시설 API 호출

    이 구조의 장점은 사건이 들어올 때마다 설정 파일과 환경변수를 다시 읽을 필요가 없음.
    다만 함수가 만들어질 때의 매핑과 인증값을 기억하므로, .env를 수정했다고 해서 이미 생성된 함수에 자동으로 반영되는 것은 아니다.
"""
