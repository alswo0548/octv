"""
OCTV 재난별 후보 기관 추천 Rule

주요 기능
1. 재난 유형별 주요 기관과 조건부 협조기관 구분
2. 기관 역할 40점·지역 연관성 40점·현장 접근성 20점 평가

[1. 기관 추천 점수 구성 - 최대 100점]
- 기본 역할 적합성 : 최대 30점 (주요 기관 30 / 조건부 협조 15)
- 상황 적합성     : 최대 10점 (확인된 지원 필요성 0 / 5 / 10)
- 지역 연관성     : 최대 40점 (담당 지역 40 / 동일 시군구 20 / 기타 0)
- 예상 이동시간   : 최대 15점 (짧을수록 높은 점수)
- 실제 이동거리   : 최대 5점 (짧을수록 높은 점수)

[2. 재난 유형별 추천 기관]
- 침수        : 주요 소방·도로관리 / 협조 지자체·경찰
- 쓰러진 나무  : 주요 도로관리·지자체 / 협조 경찰·소방
- 심각 도로 파손 : 주요 도로관리·지자체 / 협조 경찰·소방
- 도로 장애물  : 주요 도로관리 / 협조 경찰·지자체

[3. 기관 추천 처리 순서]
1. recommend() : 역할·지역·직선거리로 사전 후보 선정
2. 경로 조회·평가 : 기관별 실제 이동시간·거리 확인
3. finalize_recommendations() : 접근성 20점 반영 및 최종 순위
※ 최종 추천 기관은 최대 4개

[4. 운영 원칙]
- 담당 지역 정보가 없어도 기관을 자동 제외하지 않음
- 확인되지 않은 구조·행정 지원 필요성을 임의로 추정하지 않음
- 외부 Context 및 실행 순서는 별도 파일의 LangGraph에서 연결
- 최종 기관 선택과 정보 전달은 상황실 관리자가 결정

※ 외부 API 호출·DB 저장은 이 파일에서 수행하지 않습니다.
"""


from math import radians, sin, cos, atan2, sqrt


# 재난별 주요/조건부 협조 기관: 재난이 발생했을 때 어떤 종류의 기관을 우선 추천할지 정의
"""
흐름
① YOLO가 침수 탐지 -> hazard_type = "flood"
② AGENCY_ROLES에서 침수 정책 확인 (아래 코드) -> 해당 사건의 카테고리가 주요 기관이 어디인지, 협조 기관이 어디인지..
③ recommend()에서 실제 기관 후보 선정 -> 기관 역할 점수 + 상황 적합성 + 지역 연관성 확인
④ 경로 확인 후 최종 추천 -> 이동시간, 거리 반영해서 최대 4개 기관 추천
"""
AGENCY_ROLES = {
    'flood': {
        'primary': ('FIRE', 'ROAD_MANAGEMENT'),
        'conditional': ('LOCAL_GOVERNMENT', 'POLICE'),
    },
    'fallen_tree': {
        'primary': ('ROAD_MANAGEMENT', 'LOCAL_GOVERNMENT'),
        'conditional': ('POLICE', 'FIRE'),
    },
    'severe_road_damage': {
        'primary': ('ROAD_MANAGEMENT', 'LOCAL_GOVERNMENT'),
        'conditional': ('POLICE', 'FIRE'),
    },
    'road_obstacle': {
        'primary': ('ROAD_MANAGEMENT',),
        'conditional': ('POLICE', 'LOCAL_GOVERNMENT'),
    },
}

# 하버사인 공식(지구가 둥글다는 점을 고려한 계산법)을 활용하여 사건위치와 기관위치 사이의 진선거리를 계산
def haversine_m(a, b):
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    h = min(
        1.0,
        max(
            0.0,
            sin((lat2 - lat1) / 2) ** 2
            + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2,
        ),
    )
    return 6371000 * 2 * atan2(sqrt(h), sqrt(1 - h))

# 재난 현장의 상황을 확인 후, 각 기관에 상황 적합성 점수를 부여하는 함수
def _situation_score(agency_type, situation):
    """확인된 사건 상황으로 0/5/10점 중 하나를 자동 결정합니다.

    traffic_control: {'status':'OK','level':'PARTIAL'|'FULL','source':'UTIC'}
    rescue_support: {'status':'OK','needed':True,'source':'확인 기관'}
    admin_support: {'status':'OK','needed':True,'source':'확인 기관'}
    ※ 필요한 데이터가 없으면 0점입니다. '없음'으로 추정하지 않습니다.
    """
    # situation: 외부 데이터 등으로 확인된 사건 상황 
    # agency_type: 점수를 계산할 기관 유형
    facts = situation or {}
    if agency_type in ('POLICE', 'ROAD_MANAGEMENT'):
        fact = facts.get('traffic_control', {})
        if fact.get('status') == 'OK' and fact.get('source'):
            points = {'PARTIAL': 5, 'FULL': 10}.get(fact.get('level'), 0)
            if points:
                return points, {
                    'factor': 'traffic_control', 'level': fact['level'],
                    'source': fact['source'],
                }
    elif agency_type == 'FIRE':
        fact = facts.get('rescue_support', {})
        if (fact.get('status') == 'OK' and fact.get('needed') is True
                and fact.get('source')):
            return 10, {'factor': 'rescue_support', 'source': fact['source']}
    elif agency_type == 'LOCAL_GOVERNMENT':
        fact = facts.get('admin_support', {})
        if (fact.get('status') == 'OK' and fact.get('needed') is True
                and fact.get('source')):
            return 5, {'factor': 'admin_support', 'source': fact['source']}
    return 0, None

# 재난이 발생한 지역과 기관의 담당 지역을 비교하여, 기관 추천 점수 중 지역 연관성 최대 40점을 계산하는 함수
def _region_points(incident_region, agency):
    # 담당지역 목록은 참고 점수입니다. 불일치해도 자동 제외하지 않습니다.
    service = agency.get('service_region_codes')
    if service:
        if incident_region in service:
            return 40, 'service_region_codes_match'
        return 0, 'service_region_codes_mismatch'
    if (
        incident_region is not None
        and incident_region == agency.get('region_code')
    ):
        return 20, 'region_code_match_unverified'
    return 0, 'region_unverified_or_unmatched'


def _diverse_candidates(rows, limit, role_order):
    # 같은 종류의 기관만 4곳 뽑지 않도록, 역할 유형별 첫 후보를 우선합니다.
    selected, ids = [], set()
    for agency_type in role_order:
        for row in rows:
            if row['agency_type'] == agency_type and row['agency_id'] not in ids:
                selected.append(row)
                ids.add(row['agency_id'])
                break
        if len(selected) >= limit:
            return selected
    for row in rows:
        if row['agency_id'] not in ids:
            selected.append(row)
            ids.add(row['agency_id'])
        if len(selected) >= limit:
            break
    return selected

# 앞에서 분석한 함수들을 하나로 묶어
# 재난 유형, 기관 정보, 확인된 현장 상황을 이용해 최대 4개의 기관을 사전 선정하는 함수
def recommend(incident, agencies, policy, situation=None):
    """기관을 사전 선별합니다. 이 시점의 점수는 경로 미반영 임시 점수입니다.

    situation은 확인된 교통 통제·구조·행정 지원 근거를 전달받습니다.
    조건부 협조 기관은 확인된 상황 가산점이 있을 때만 후보에 넣습니다.
    """
    roles = AGENCY_ROLES[incident['hazard_type']]                               # 재난에 맞는 기관 유형 가져오기
    primary = tuple(policy.get('primary_types', roles['primary']))              # 주요 추천 기관 유형
    conditional = tuple(policy.get('conditional_types', roles['conditional']))  # 조건부 협조 기관 유형
    allowed = set(policy.get('allowed_types', (*primary, *conditional)))        # 이번 추천에서 허용하는 기관 유형 전체
    limit = min(int(policy.get('limit', 4)), 4)
    if limit <= 0:
        return []

    # 기관을 탐색할 거리 반경 설정
    normal_radius = float(policy['max_distance_m'])
    # 확대 반경은 확정된 정책에서만 지정합니다. 임의로 두 배 확대하지 않습니다.
    fallback_radius = float(
        policy.get('fallback_max_distance_m', normal_radius)
    )
    if normal_radius <= 0 or fallback_radius < normal_radius:
        raise ValueError('기관 후보 탐색 거리 설정을 확인하세요.')

    # agency(기관 DB 등)에서 조회해 기관 하나식 확인 후 점수 확정
    rows = []
    for agency in agencies:
        agency_type = agency['agency_type']
        if agency_type not in allowed:
            continue
        if agency_type in primary:
            role_points = 30
            role_name = 'PRIMARY'
        elif agency_type in conditional:
            role_points = 15
            role_name = 'CONDITIONAL'
        else:
            continue

        situation_points, evidence = _situation_score(agency_type, situation)
        if role_name == 'CONDITIONAL' and situation_points == 0:
            continue

        distance = haversine_m(
            (float(agency['latitude']), float(agency['longitude'])),
            (float(incident['latitude']), float(incident['longitude'])),
        )
        if distance > fallback_radius:
            continue

        region_points, region_source = _region_points(
            incident['region_code'], agency
        )
        rows.append({
            'agency_id': agency['id'],
            'agency_type': agency_type,
            'recommendation_score': float(
                role_points + situation_points + region_points
            ),
            'score_breakdown_json': {
                'role': role_name,
                'role_points': role_points,
                'situation_points': situation_points,
                'situation_evidence': evidence,
                'region_points': region_points,
                'jurisdiction_source': region_source,
                'straight_distance_m': round(distance),
                'candidate_stage': 'PRELIMINARY_NO_ROUTE',
                'fallback_region_search': distance > normal_radius,
            },
            'rule_version': policy['version'],
        })

    # 지역 점수와 역할 점수를 우선하고 직선거리는 사전 선별에만 사용합니다.
    rows.sort(key=lambda r: (
        -r['recommendation_score'],
        r['score_breakdown_json']['straight_distance_m'],
        r['agency_id'],
    ))
    # 기본 반경 내 기관부터 선정하여 일반 반경 안에 있는 기관만 먼저 모은다음 
    # 부족한경우 fallback 으로 주변 지역 후보를 보충.
    normal = [
        r for r in rows
        if not r['score_breakdown_json']['fallback_region_search']
    ]
    selected = _diverse_candidates(normal, limit, (*primary, *conditional))
    if len(selected) < limit:
        # 같은 지역/기본 반경에서 부족한 경우에만 주변 지역 후보를 보충합니다.
        fallback = [
            r for r in rows
            if r['score_breakdown_json']['fallback_region_search']
        ]
        selected = _diverse_candidates(
            [*selected, *fallback], limit, (*primary, *conditional)
        )

    return [
        {**row, 'recommendation_rank': index + 1}
        for index, row in enumerate(selected)
    ]

# recommend()에서 선정된 최대 4개의 기관 후보에서 
# 그 기관들의 실제 이동시간과 거리를 반영해서 최종 점수와 추천 순위를 결정하는 함수
# recommend() 에서 주요역학 30 + 상황 10 + 지역 40 으로 최대 80점으로 기관 사전 선정했다면 
# 카카오 경로 조회 후 기관별 경로 최대 3개 평가 후 접근성 최대 20점을 반영하여 최종 추천 결과를 반환
def finalize_recommendations(
    preliminary,        # recommend() 에서 선정한 기관 후보 목록
    routes_by_agency,   # 기관 ID별 경로 평가 결과
    policy,             # 기관 추천 정책 설정
    route_policy        # 경로 점수 계싹 기준시간, 기준거리 설정
):
    """경로 평가 후 실제 이동시간 15점·거리 5점을 더해 최종 추천합니다.

    routes_by_agency: {agency_id: evaluate()에서 반환한 경로 목록}
    검증된 경로 우선, 미확인 경로 후순위, 경로 없으면 접근성 0점입니다.
    05번에서는 이 함수를 호출한 결과만 DB에 저장해야 합니다.
    """
    duration_scale = float(route_policy['duration_scale_sec'])
    distance_scale = float(route_policy['distance_scale_m'])
    if duration_scale <= 0 or distance_scale <= 0:
        raise ValueError('시간·거리 기준값은 0보다 커야 합니다.')

    # 사전 선정한 기관을 하나씩 확인하여 기관별 추천 가능한 경로를 가져온다
    result = []
    for row in preliminary:
        valid_routes = [
            route for route in routes_by_agency.get(row['agency_id'], [])
            if not route.get('disqualify_reason')       # 제외 사유가 없는 경로만 남긴다.
        ]
        # 가장 적합한 대표 경로 선정
        valid_routes.sort(key=lambda route: (
            route.get('score_breakdown_json', {}).get('verification_status')
            != 'VERIFIED',
            -(route.get('total_score') or 0),
            route['duration_sec'],
        ))
        best = valid_routes[0] if valid_routes else None
        # 아직 경로확인 전이니 점수 초기화 후, 실제경로가 있을시에 아래 if문에서 최종 접근성 계산을 실행
        time_points = distance_points = 0.0
        access_status = 'NO_AVAILABLE_ROUTE'
        if best:
            access_status = best['score_breakdown_json']['verification_status']
            time_points = 15 / (1 + best['duration_sec'] / duration_scale)
            distance_points = 5 / (1 + best['distance_m'] / distance_scale)

        # 점수 근거
        breakdown = {
            **row['score_breakdown_json'],
            'candidate_stage': 'FINAL',
            'access_status': access_status,
            'access_time_points': round(time_points, 2),
            'access_distance_points': round(distance_points, 2),
            'travel_duration_sec': best['duration_sec'] if best else None,
            'travel_distance_m': best['distance_m'] if best else None,
            'route_name': best['route_name'] if best else None,
        }
        # 기관 최종 점수 계산
        score = round(
            breakdown['role_points'] + breakdown['situation_points']
            + breakdown['region_points'] + time_points + distance_points,
            2,
        )
        if score < policy.get('min_score', 0):
            continue
        result.append({
            **row,
            'recommendation_score': score,
            'score_breakdown_json': breakdown,
        })

    # 검증 경로를 우선하고, 같은 상태에서 기관 점수로 순위를 결정합니다.
    status_order = {'VERIFIED': 0, 'NEEDS_REVIEW': 1, 'NO_AVAILABLE_ROUTE': 2}
    result.sort(key=lambda row: (
        status_order.get(row['score_breakdown_json']['access_status'], 2),
        -row['recommendation_score'],
        row['agency_id'],
    ))
    return [
        {**row, 'recommendation_rank': index + 1}
        for index, row in enumerate(result[:min(int(policy.get('limit', 4)), 4)])
    ]
