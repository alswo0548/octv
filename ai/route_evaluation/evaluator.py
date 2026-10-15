
"""
OCTV 기관별 추천 경로 평가 Rule

주요 기능
1. 카카오모빌리티에서 확보한 경로 후보의 시간·거리 점수 계산
2. 예상 이동시간 70점·실제 이동거리 30점으로 경로 평가
3. 확인된 전면 통제 구간을 통과하는 경로는 추천 제외
4. VERIFIED / NEEDS_REVIEW / DISQUALIFIED 상태 구분

[1. 경로 평가 점수 구성 - 최대 100점]
- 예상 이동시간 : 최대 70점 (시간이 짧을수록 높은 점수)
- 실제 이동거리 : 최대 30점 (거리가 짧을수록 높은 점수)

[2. 경로 점수 계산 방식]
- 시간 점수 = 70 / (1 + 예상시간 / 기준시간)
- 거리 점수 = 30 / (1 + 이동거리 / 기준거리)
- 최종 점수 = 시간 점수 + 거리 점수

※ 기준시간 10분·기준거리 5km 가정 시
- 5분 / 2.5km  : 66.67점
- 10분 / 5km   : 50.00점
- 20분 / 10km  : 33.33점
※ 기준값과 같은 경로는 50점이며 최고점이 아님

[3. 경로 통제 확인 기준]
- VERIFIED     : 최신 통제 정보 확인, 통행 불가 구간과 교차 없음
- NEEDS_REVIEW : 통제 정보 누락·오류·오래됨 또는 위치 대조 불확실
- DISQUALIFIED : 전면 통제·통행 불가 구간 통과 확인

※ 전면 통제 경로는 점수와 관계없이 추천 제외
※ 일부 차로 차단은 전면 통제로 간주하지 않음

[4. 경로 추천 및 정렬]
- 기관별 최대 3개 경로 후보를 평가
- 일반 후보 → 확인 필요 후보 → 제외 경로 순으로 구분
- 추천 가능한 경로는 각 구분 안에서 점수순 정렬
- 제외 경로는 추천하지 않고 제외 사유 표시

[5. 운영 원칙]
- 대표 경로의 시간·거리를 기관 접근성 평가에 재사용
- 점수·출처·통제 확인 상태·제외 사유를 보존
- 일반 차량 기준으로 특수차량 접근성은 보장하지 않음
- 최종 경로 선택은 상황실 관리자가 결정

※ 외부 API 호출·DB 저장은 이 파일에서 수행하지 않습니다.
"""


from shapely.geometry import shape


def evaluate(
    context,        # 경로 평가 정책과 도로 통제 정보
    candidates,     # maps.py 에서 확보한 경로 후보
    intersects      # 경로와 통제 구역의 겹침을 검사할 함수
):
    evaluated = []
    policy = context['policy']
    if policy.get('time_points', 70) != 70 or policy.get('distance_points', 30) != 30:
        raise ValueError('확정된 경로 가중치는 시간 70점·거리 30점입니다.')
    duration_scale = float(policy['duration_scale_sec'])
    distance_scale = float(policy['distance_scale_m'])
    if duration_scale <= 0 or distance_scale <= 0:
        raise ValueError('경로 시간·거리 기준값은 0보다 커야 합니다.')

    # 통제 데이터가 실제로 전면 통제 구역만 포함하도록 검증된 경우에만 제외합니다.
    # 추후 연결 단계에서 blocked_zones_verified=True를 명시해야 합니다.
    zones = context.get('blocked_zones')
    closure_checked = (
        context.get('closure_status') == 'OK'                   # 통제 정보 정상 확인
        and isinstance(zones, list)                             # 통제 구역은 리스트 형태
        and context.get('blocked_zones_verified') is True       # 해당 구역 정보가 검정되었다고 전달 받음
    )                                                           # 세 가지 조건을 모두 만족해야 closure_checked=True가 됨.
    # VERIFIED: 통제 정보 대조 완료
    # NEEDS_REVIEW: 추가 확인 필요
    # DISQUALIFIED: 추천 제외
    # NEAR_INCIDENT: 재난 현장 주변까지의 경로
    for route in candidates[:3]:
        reason = None
        status = 'VERIFIED' if closure_checked else 'NEEDS_REVIEW'
        if closure_checked and any(
            intersects(route['route_path_json'], zone) for zone in zones
        ):
            reason = '확인된 전면 통제·통행 불가 구간 통과'
            status = 'DISQUALIFIED'
        elif route.get('destination_kind') == 'NEAR_INCIDENT':
            # 현장 주변 접근 지점까지의 경로는 현장 도착을 보장하지 않습니다.
            status = 'NEEDS_REVIEW'

        score = None if reason else round(
            70 / (1 + route['duration_sec'] / duration_scale)
            + 30 / (1 + route['distance_m'] / distance_scale),
            2,
        )
        evaluated.append({
            **route,
            'total_score': score,
            'disqualify_reason': reason,
            'score_breakdown_json': {
                'duration_sec': route['duration_sec'],
                'distance_m': route['distance_m'],
                'verification_status': status,
                'closure_status': context.get('closure_status'),
                'destination_kind': route.get('destination_kind', 'INCIDENT'),
                'excluded': bool(reason),
            },
            'rule_version': context['rule_version'],
        })
    # 경로 정렬
    return sorted(
        evaluated,
        key=lambda r: (
            {'VERIFIED': 0, 'NEEDS_REVIEW': 1, 'DISQUALIFIED': 2}[
                r['score_breakdown_json']['verification_status']
            ],
            -(r['total_score'] or 0),
            r['duration_sec'],
        ),
    )

"""
Shapely(셰이플리)를 실제로 사용하는 부분인데, 
Shapely란? Python에서 지도상의 위치, 선, 영역 같은 공간 데이터를 계산하는 라이브러리
아래 함수에서는 
shape(route_geometry): GeoJSON 경로를 Shapely의 도형 객체로 변환
shape(blocked_geometry): 통제 구역을 도형 객체로 변환
.intersects(...): 두 도형이 겹치거나 닿는지 검사
이후 반환값은 
True   # 경로와 통제 구역이 교차함
False  # 경로와 통제 구역이 교차하지 않음
"""
def intersects_geojson(route_geometry, blocked_geometry):
    return shape(route_geometry).intersects(shape(blocked_geometry))
