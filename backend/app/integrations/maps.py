"""
recommender.py 에서 추천된 기관에서 재난 현장까지 실제로 이동할 수 있는 경로를 카카오모빌리티 API로 조회
이 파일에서는 경로를 확보까지만 하며, 점수 계산은 하지 않는다.
점수 계산은 evaluator.py 에서 진행
"""

import httpx

# 카카오 API에서 받은 복잡한 JSON 응답을 OCTV에서 사용하기 쉬운 경로 정보로 정리해주는 함수
def parse_routes(payload):      # payload: 카카오 API 응답 데이터
    result = []                 # result: 최종 경로 후보를 담을 리스트
    seen_paths = set()          # seen_paths: 이미 처리한 경로를 확인하기 위한 집합(set), 카카오에서 동일한 경로 중복 반환시 사용
    for route in payload.get('routes', []):
        if route.get('result_code') != 0:
            continue
        # 경로에 포함된 도로 좌표 추출
        points = []
        for section in route.get('sections', []):
            for road in section.get('roads', []):
                vertexes = road.get('vertexes', [])
                if len(vertexes) % 2:
                    raise ValueError('경로 좌표 쌍 오류')
                for i in range(0, len(vertexes), 2):
                    # 좌표는 [경도, 위도] 순서
                    point = [float(vertexes[i]), float(vertexes[i + 1])]
                    if not points or point != points[-1]:
                        points.append(point)
        if len(points) < 2:
            continue
        path_key = tuple(map(tuple, points))
        if path_key in seen_paths:
            continue  # 정확히 같은 경로를 별도 후보로 중복 표시하지 않습니다.
        seen_paths.add(path_key)
        summary = route['summary']
        if int(summary['distance']) < 0 or int(summary['duration']) < 0:
            raise ValueError('음수 거리/시간')
        result.append({
            'route_name': f'후보 {len(result)+1}',                              # 경로 이름
            'distance_m': int(summary['distance']),                             # 예상 이동거리(m)    
            'duration_sec': int(summary['duration']),                           # 예상 이동시간(초)
            'route_path_json': {'type': 'LineString', 'coordinates': points},   # 지도에 그릴 경로 좌표
        })
    # API에서 0~2개만 반환한 경우 없는 경로를 임의로 만들지 않습니다.
    return result[:3]

# 카카오 API에 경로를 요청하고, 통신 오류가 발생하면 재시도하는 함수
def _request_routes(
    client,     # HTTP 요청을 보내는 객체 (httpx.Client)
    api_key,    # 카카오모빌리티 API 인증키
    params      # 출발지·목적지·경로 탐색 조건
):
    for attempt in range(2):
        try:
            response = client.get(
                'https://apis-navi.kakaomobility.com/v1/directions',
                headers={'Authorization': 'KakaoAK ' + api_key},
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
            # 실패한 경로 결과 코드를 수집하여 어떤 문제가 발생했는지 이후 처리에서 참고할수 있음.
            codes = [
                route.get('result_code')
                for route in payload.get('routes', [])
                if route.get('result_code') != 0
            ]
            return parse_routes(payload), codes
        except (httpx.TimeoutException, httpx.TransportError):
            if attempt == 1:
                raise
        except httpx.HTTPStatusError as exc:
            if attempt == 1 or exc.response.status_code < 500:
                raise

# 경유지 좌표를 카카오 API가 요구하는 형식으로 반화하는 함수
def _waypoint_string(point):
    return f"{float(point['longitude'])},{float(point['latitude'])}"


# 카카오에서 경로 조회 -> 경로가 없으면 다른 방법으로 재탐색 -> 확보한 경로와 조회결과를 반환하는 함수
def fetch_data(query: dict) -> dict:
    params = {
        'origin': f"{query['origin_lon']},{query['origin_lat']}",
        'destination': (
            f"{query['destination_lon']},{query['destination_lat']}"
        ),
        'priority': 'RECOMMEND',
        'alternatives': 'true',
        'summary': 'false',
        'roadevent': 0,  # 전체 차로 통제 반영을 해제하지 않습니다.
    }
    attempts = []           # 어떤 방식으로 경로를 조회했는지 기록
    supplemental_failures = []  # 보충 조회 실패 기준만 기록 (인증키/URL 제외)
    error_codes = []        # 카카오 응답의 실패 결과 코드
    kind = 'INCIDENT'       # 경로 목적지가 실제 사건 위치인지 구분
    with httpx.Client(timeout=7) as client:
        routes, codes = _request_routes(client, query['api_key'], params)
        error_codes.extend(codes)
        attempts.append('RECOMMEND')
        # 기본 경로가 1~2개여도 다른 탐색 기준으로 후보를 보충합니다.
        # 처음 확보한 순서를 유지하며, 좌표가 동일한 경로는 합칩니다.
        seen_paths = {
            tuple(map(tuple, route['route_path_json']['coordinates']))
            for route in routes
        }
        for priority in ('TIME', 'DISTANCE'):
            if len(routes) >= 3:
                break
            params['priority'] = priority
            attempts.append(priority)
            try:
                extra_routes, codes = _request_routes(client, query['api_key'], params)
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                if not routes:
                    raise
                # 보충 조회 실패 때문에 이미 확보한 경로를 버리지 않습니다.
                supplemental_failures.append(priority)
                continue
            error_codes.extend(codes)
            for route in extra_routes:
                path_key = tuple(map(tuple, route['route_path_json']['coordinates']))
                if path_key in seen_paths:
                    continue
                seen_paths.add(path_key)
                routes.append(route)
                if len(routes) >= 3:
                    break
        if not routes and query.get('verified_waypoints'):
            # 추가 경유지는 외부에서 확인한 실제 도로 지점만 사용합니다.
            params['priority'] = 'RECOMMEND'
            params['waypoints'] = '|'.join(
                _waypoint_string(point) for point in query['verified_waypoints'][:5]
            )
            routes, codes = _request_routes(client, query['api_key'], params)
            error_codes.extend(codes)
            attempts.append('VERIFIED_WAYPOINTS')
        if (
            not routes
            and query.get('access_point_confirmed') is True
            and query.get('verified_access_point')
        ):
            # 확인된 접근 지점으로만 목적지를 대체하고 현장 도착과 구분합니다.
            point = query['verified_access_point']
            params.pop('waypoints', None)
            params['priority'] = 'RECOMMEND'
            params['destination'] = _waypoint_string(point)
            routes, codes = _request_routes(client, query['api_key'], params)
            error_codes.extend(codes)
            attempts.append('VERIFIED_ACCESS_POINT')
            kind = 'NEAR_INCIDENT'

    for index, route in enumerate(routes, start=1):
        route['route_name'] = f'후보 {index}'
        route['destination_kind'] = kind
    return {
        'candidates': routes[:3],
        'source': 'KAKAO_MOBILITY',
        'status': 'OK' if routes else 'NO_ROUTE',
        'attempts': attempts,
        'supplemental_failures': supplemental_failures,
        'failure_result_codes': error_codes if not routes else [],
        'destination_kind': kind,
        'reason': None if routes else '재탐색 후에도 경로를 확보하지 못했습니다.',
    }
