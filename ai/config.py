"""
LangGraph가 판단 작업을 실행할 때 필요한 설정을 준비하고 검증하는 파일

주요기능
1. 위험도 계산, 기관 추천, 견로 평가 함수실행시 여러 설정값을 모아서 다른 파일들이 사용할 수 있도록 전달.
"""

import json
import os
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
from math import isfinite
from pathlib import Path

from dotenv import dotenv_values

from .risk_priority.rules import RISK_POLICIES
from .runtime_queries import create_query_factory

# ai/config.py를 기준으로 프로젝트 최상위 풀더를 찾는 코드 
# 나중에 .env 와 JSON 설정 파일의 경로를 읽을 때 사용.
ROOT = Path(__file__).resolve().parents[1]
_ACTIVE_CONFIG = ContextVar('octv_active_runtime_config', default=None)


# 전역 변수를 덮어쓰지 않고, 현재 MCP 호출 범위에만 같은 설정을 공유합니다.
# 즉, 작업하는 동안만 설정값을 빌려 쓰고, 작업이 끝나면 원래 상태로 되돌리는 함수
@contextmanager                                 # 함수를 with 문으로 사용할 수 있게 만듦.
def runtime_config_scope(config: dict):         # 설정값이 담긴 딕셔너리 config 를 전달받는 함수
    token = _ACTIVE_CONFIG.set(config)          # 현재 사용할 설정을 등록. token은 설정값 자체가 아닌, 나중에 원래 설정으로 복구하기 위해 받는 복구 티켓
    try:                                        # 여기서 with 안에 있는 실제 작업을 실행. -> ai/orchestration/nodes.py의 _collect_context() with runtime_config_scope(config)
        yield                                   # 즉, 설정을 등록한 상태로 MCP 작업을 실행할 수 있게 됨
    finally:                                    
        _ACTIVE_CONFIG.reset(token)             # MCP 작업이 끝나면 앞에서 발급받은 token을 이용해서 원래 설정으로 돌아감


# 기존 .env는 읽기만 하며, 실제 환경변수가 파일의 값보다 우선됨.
# 외부 api를 호출하기 위해 필요한 여러곳에 저장된 환경변수를 하나의 딕셔너리로 합쳐서 반환하는 함수.
def _environment() -> dict:
    values = {}
    for path in (ROOT / '.env', ROOT / 'backend' / '.env'):
        values.update({
            key: value
            for key, value in dotenv_values(path, interpolate=False).items()
            if value is not None
        })
    values.update(os.environ)
    return values


# 가져온 설정값 중 거리,시간 같은 숫자가 올바른지 검사하는 함수.
def _positive_number(settings: dict, name: str) -> float:
    raw = settings.get(name)
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f'{name}: 확정한 양수 설정값을 입력하세요.') from None
    if isinstance(raw, bool) or not isfinite(value) or value <= 0:
        raise ValueError(f'{name}: 유한한 양수여야 합니다.')
    return value


# LangGraph 실행에 사용할 기관 추천,경로 평가 설정이 기존 정책에 맞는지 검사하는 함수
"""
실행 설정 JSON (기관 추천 설정, 경로 평가 설정) -> 
validate_settings()가 아래의 내용을 실행
① 설정이 딕셔너리인지 검사
② 허용된 설정 항목만 있는지 검사
③ 확정된 정책값 유지 여부 확인
④ 버전과 필수 숫자 검사
⑤ 검증된 설정 반환
"""
def validate_settings(settings: dict) -> tuple[dict, dict]:
    if not isinstance(settings, dict):
        raise ValueError('실행 설정의 최상위 값은 JSON 객체여야 합니다.')
    # 기관 추천, 경로 평가 설정 복사 여기서는 원본 설정을 건드리지 않기 위해 deepcopy() 를 사용
    agency = deepcopy(settings.get('agency_policy'))
    route = deepcopy(settings.get('route_policy'))
    if not isinstance(agency, dict) or not isinstance(route, dict):
        raise ValueError('agency_policy와 route_policy 설정이 필요합니다.')

    # 확정된 역할·점수·최대 후보 수를 설정 파일로 바꾸지 못하게 제한합니다.
    # 여기서 {} 는 딕셔너리가 아닌 집합(set)
    allowed_agency = {
        'version', 'max_distance_m', 'fallback_max_distance_m',
        'limit', 'min_score',
    }
    allowed_route = {
        'version', 'duration_scale_sec', 'distance_scale_m',
        'time_points', 'distance_points',
    }
    # -연산자 집합에서의 차집합, 즉 앞쪽에 있는데 뒤쪽에 없는 항목을 찾는 기능
    if set(agency) - allowed_agency or set(route) - allowed_route:
        raise ValueError('지원하지 않는 기관·경로 정책 설정입니다.')
    if agency.get('limit', 4) != 4 or agency.get('min_score', 0) != 0:
        raise ValueError('현재 연결은 최대 4개 기관·최소 점수 0 기준을 유지합니다.')
    if route.get('time_points', 70) != 70 or route.get('distance_points', 30) != 30:
        raise ValueError('경로 점수는 시간 70점·거리 30점을 유지해야 합니다.')

    for policy in (agency, route):
        version = policy.get('version')
        if not isinstance(version, str) or not version.strip() or len(version) > 50:
            raise ValueError('기관·경로 규칙 버전은 1~50자 문자열이어야 합니다.')
    agency['max_distance_m'] = _positive_number(agency, 'max_distance_m')
    if 'fallback_max_distance_m' in agency:
        agency['fallback_max_distance_m'] = _positive_number(
            agency, 'fallback_max_distance_m'
        )
        if agency['fallback_max_distance_m'] < agency['max_distance_m']:
            raise ValueError('확대 반경은 기본 반경보다 작을 수 없습니다.')
    # 확대 반경을 생략하면 기존 recommend()가 기본 반경을 그대로 사용합니다.
    route['duration_scale_sec'] = _positive_number(route, 'duration_scale_sec')
    route['distance_scale_m'] = _positive_number(route, 'distance_scale_m')
    return agency, route


# workers.py와 기존 MCP tools.py에서 같은 함수 이름으로 호출합니다.
"""
프로젝트에서 사건을 판단할 때 필요한 다양한 설정을 get_runtime_config()에서 한 번에 준비
- 외부 API 인증키와 CCTV별 관측소 매핑
- 재난 유형별 위험도 점수 정책
- 기관 추천 반경과 추천 조건
- 경로 평가의 시간·거리 기준
- 외부 데이터를 MCP로 수집할지 직접 수집할지
"""
def get_runtime_config(config_path: str | Path | None = None) -> dict:
    # 이미 현재 작업에 사용할 설정을 가지고있는지 확인
    active = _ACTIVE_CONFIG.get()
    if active is not None and config_path is None:
        return active
    # 설정이 없을경우, .env를 읽어서 어떤 JSON 파일을 사용해야하는지 찾음
    values = _environment()
    selected = config_path or values.get('OCTV_RUNTIME_CONFIG')
    if not selected:
        raise ValueError('OCTV_RUNTIME_CONFIG에 실행 설정 JSON 경로를 지정하세요.')
    path = Path(selected).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    try:
        settings = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        # 원문 JSON·경로·인증키가 예외 로그에 노출되지 않게 합니다.
        raise ValueError('실행 설정 JSON을 읽을 수 없습니다. 파일을 확인하세요.') from None

    # JSON 파을을 Python이 사용할 수 있는 데이터로 변경
    agency, route = validate_settings(settings)
    transport = settings.get('context_transport', 'mcp')
    if transport not in ('mcp', 'direct'):
        raise ValueError('context_transport는 mcp 또는 direct여야 합니다.')
    return {
        'query_factory': create_query_factory(settings, values),        # 외부 API 요청 정보를 만드는 함수
        'risk_policies': deepcopy(RISK_POLICIES),                       # 위험도 계산 규칙
        'agency_policy': agency,                                        # 기관 추천 규칙, 설정
        'route_policy': route,                                          # 경로 평가 규칙, 설정
        'context_transport': transport,                                 # MCP로 수집할지, 직접 수집할지 # 직접 수집은 MCP 호출 실패에 대비한 '테스트·문제 진단용 우회 경로 (direct 방식으로 별도 테스트 → MCP를 건너뛰고 기존 Context 수집 함수 직접 실행)
        'route_api_key': values.get('ROUTE_API_KEY', '').strip(),       # 지도 경로 조회용 인증키
    }
