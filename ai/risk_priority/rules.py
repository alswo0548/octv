"""
OCTV 위험도 및 사건 간 우선순위 판단

주요 기능
1. 재난 유형별 기본 점수에 검증된 외부 상황 가산점을 반영 (재난 60점·주변 30점·악화 10점)
2. 동일한 위험도 점수로 HIGH/MEDIUM/LOW 및 P1/P2/P3를 동시에 결정
3. 사건 간 점수 정렬: 높은 점수 → 먼저 탐지된 사건 → 사건 ID
4. 악화점수: 침수·싱크홀은 강수, 나무·전봇대는 강수/풍속 중 최댓값, 도로 장애물은 각각 5점씩 합산

OCTV 위험도 및 사건 간 우선순위 Rule

[1. 위험도 점수 구성 - 최대 100점]
- 재난 심각성 : 최대 60점 (기본 점수 + 재난별 가산점)
- 주변 영향도 : 최대 30점 (교통량 10 + 시설 10 + 인구 5 + 도로 5)
- 악화 가능성 : 최대 10점 (재난별 강수량·풍속)

[2. 재난 유형별 기본 점수 및 심각성 가산]
- 침수        : 기본 40점 + 차로 차단 5~10 + 수위 5~10 + 지하차도 5
- 쓰러진 나무  : 기본 40점 + 차로 차단 5~10
- 싱크홀      : 기본 45점 + 도로 통제 확인 5
- 도로 장애물  : 기본 30점 + 차로 차단 10~20
※ 심각성 가산점은 조건 충족 시에만 적용하며 최대 60점으로 제한

[3. 재난별 악화 가능성 - 최대 10점]
- 침수        : 강수량 0 / 5 / 10점
- 쓰러진 나무  : 강수·풍속 점수 중 높은 값 (최대 10점)
- 싱크홀      : 강수량 0 / 5 / 10점
- 도로 장애물  : 강수량 최대 5점 + 풍속 최대 5점

※ 현재 Rule상 최고점 : 침수 100점 / 나머지 재난 90점

[4. 위험 등급 및 대응 우선순위]
- 70점 이상 : HIGH   / P1
- 40~70점 미만 : MEDIUM / P2
- 40점 미만 : LOW    / P3
※ 위험도 점수 = 우선순위 점수 (대기시간 가산 없음)
※ 동점 정렬 : 먼저 탐지된 사건 → 사건 ID

[5. 운영 원칙]
- 확인된 외부 데이터만 가산하고 미확인 데이터는 별도 표시
- 데이터 수집·외부 API 호출·DB 저장은 이 파일에서 수행하지 않음
- 최종 판단 및 기관 전달은 상황실 관리자가 결정

※ 데이터 수집·외부 API 연동·DB 저장은 수행하지 않습니다.
"""

from math import isfinite
from ..contracts import ContextSnapshot


# 위험도와 우선순위가 40,70(경계값) 기준으로 등급이 달라진다.
DEFAULT_RISK_THRESHOLDS = (40, 70)


# 재난 유형마다 위험도 계산의 기본 규칙을 미리 정해놓은 설정표
# 추후 랭그래프 설계할때 사용할 예정
RISK_POLICIES = {
    hazard: {
        "version": "OCTV_RULE_V1_1_DRAFT_20261014",
        "hazard_type": hazard,
        "base_score": base_score,
        # API 장애로 모든 재난의 판단이 중단되지 않도록 기본 필수항목 없음
        "required": [],
        "risk_thresholds": list(DEFAULT_RISK_THRESHOLDS),
    }
    for hazard, base_score in {
        "flood": 40,
        "fallen_tree": 40,
        "sinkhole": 45,
        "road_obstacle": 30,
    }.items()
}


# 필수 외부 정보가 부족하거나 관측값이 잘못된 경우
class InsufficientContext(ValueError):
    pass

"""
위험 등급을 나누는 기준이 정상적인지 확인하는 안전장치
아래의 우선순의를 정해 경계값을 찾는다.
1순위: risk_thresholds -> 새로운 정책 설정값이 있는지 확인 
2순위: thresholds -> 기존 코드에서 사용하던 설정값 확인
3순위: DEFAULT_RISK_THRESHOLEDS -> 둘 다 없으면 기본값 (40, 70) 사용
"""
def _risk_thresholds(policy=None):
    settings = policy or {}
    values = settings.get(
        "risk_thresholds", settings.get("thresholds", DEFAULT_RISK_THRESHOLDS)
    )
    try:
        medium, high = (float(value) for value in values)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("위험도 경계값은 [보통, 높음] 두 숫자여야 합니다.") from exc
    if not (isfinite(medium) and isfinite(high) and 0 <= medium < high <= 100):
        raise ValueError("위험도 경계값은 0 <= 보통 < 높음 <= 100이어야 합니다.")
    return medium, high


# backend/app/integrations/context.py 의 measurements (외부데이터 통합) 그대로 사용
def assess(context: ContextSnapshot, policy: dict) -> dict:
    measurements = context.measurements
    missing = [
        key
        for key in policy.get("required", [])
        if (
            measurements.get(key, {}).get("status") != "OK"
            or measurements.get(key, {}).get("value") is None
        )
    ]
    if missing:
        raise InsufficientContext("필수 정보 미확인: " + ",".join(missing))

    hazard = policy["hazard_type"]
    base = float(policy["base_score"])
    if hazard not in RISK_POLICIES or not 0 <= base <= 60:
        raise ValueError("지원하지 않는 재난 유형 또는 기본 점수")

    components = {}  # 정상 관측값별 점수·출처·시각
    unknown = []     # 수집 실패·매핑 실패·미확정 자료는 0점과 구별
    severity_extra = 0
    exposure_extra = 0
    worsening_extra = 0

    # 숫자·범주형 관측값 공통 조회. 비가 오지 않아 0mm인 경우는 정상값입니다.
    def observation(field, numeric=False):
        item = measurements.get(field, {})
        if item.get("status") != "OK" or item.get("value") is None:
            unknown.append(field)
            return None
        value = item["value"]
        if numeric:
            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError):
                unknown.append(field)
                return None
            if not isfinite(value) or value < 0:
                unknown.append(field)
                return None
        return value

    def add(field, value, points, group):
        item = measurements[field]
        components[field] = {
            "value": value,
            "points": points,
            "group": group,
            "source": item.get("source"),
            "observed_at": item.get("observed_at"),
        }
        return points

    # 1. 재난 자체의 심각성 (기본점수 + 유형별 근거, 최대 60점)
    if hazard in {"flood", "fallen_tree", "road_obstacle"}:
        lanes = observation("blocked_lane_count", numeric=True)
        if lanes is not None:
            if hazard == "road_obstacle":
                points = (
                    20 if lanes >= 2
                    else 10 if lanes >= 1
                    else 0
                )
            else:
                points = (
                    10 if lanes >= 2
                    else 5 if lanes >= 1
                    else 0
                )
            severity_extra += add("blocked_lane_count", lanes, points, "severity")

    if hazard == "flood":
        # water_risk_level은 해당 관측소의 주의·경계 수위와 비교한 결과여야 합니다.
        water = observation("water_risk_level")
        if water is not None:
            level = str(water).upper()
            if level in {"NORMAL", "CAUTION", "WARNING", "DANGER"}:
                points = (
                    10 if level in {"WARNING", "DANGER"}
                    else 5 if level == "CAUTION"
                    else 0
                )
                severity_extra += add("water_risk_level", water, points, "severity")
            else:
                unknown.append("water_risk_level")

        # 표준노드링크와 감시 도로 매핑이 확인된 경우에만 지하차도로 인정
        structure = observation("road_type")
        if structure is not None:
            structure_name = str(structure).upper()
            if structure_name in {
                "UNDERPASS", "NORMAL", "OVERPASS", "BRIDGE", "TUNNEL"
            }:
                points = 5 if structure_name == "UNDERPASS" else 0
                severity_extra += add("road_type", structure, points, "severity")
            else:
                unknown.append("road_type")

    if hazard == "sinkhole":
        # 실제 도로 통제가 확인된 경우만 가산하며, 싱크홀 확대 추정은 하지 않습니다.
        closure = observation("closure_confirmed")
        if closure is not None:
            if closure in (
                True, 1, "1", "TRUE", "true", False, 0, "0", "FALSE", "false"
            ):
                points = (
                    5 if closure in (True, 1, "1", "TRUE", "true") else 0
                )
                severity_extra += add("closure_confirmed", closure, points, "severity")
            else:
                unknown.append("closure_confirmed")

    # 주변 영향도 (교통량 10 + 중요시설 10 + 인구 5 + 도로등급 5)
    for field, scale in (
        ("traffic_volume_level", {"LOW": 0, "MEDIUM": 5, "HIGH": 10}),
        ("population_density_level", {"LOW": 0, "MEDIUM": 3, "HIGH": 5}),
    ):
        category = observation(field)
        if category is None:
            continue
        level = str(category).upper()
        if level in scale:
            exposure_extra += add(field, category, scale[level], "exposure")
        else:
            # 수집 데이터의 LOW/MEDIUM/HIGH 경계는 02번에서 실제 분포를 확인해 확정
            unknown.append(field)

    road_rank = observation("road_rank")
    if road_rank is not None:
        rank = str(road_rank)
        if rank in {
            "101", "102", "103", "104", "105", "106", "107", "108"
        }:
            points = (
                5 if rank in {"101", "102", "103"}
                else 3 if rank in {"104", "105", "106"}
                else 0
            )
            exposure_extra += add("road_rank", road_rank, points, "exposure")
        else:
            unknown.append("road_rank")

    # 카카오맵 카테고리 검색으로 받은 가까운 병원·학교의 직선거리(m).
    # 두 시설을 더하지 않고 높은 가산점 1개만 적용합니다.
    facility_scores = []
    for field, near_points, middle_points in (
        ("nearby_hospital_distance_m", 10, 5),
        ("nearby_school_distance_m", 5, 3),
    ):
        distance = observation(field, numeric=True)
        if distance is not None:
            points = (
                near_points if distance <= 300
                else middle_points if distance <= 500
                else 0
            )
            facility_scores.append((field, distance, points))

    if facility_scores:
        chosen_field, chosen_distance, chosen_points = max(
            facility_scores,
            key=lambda x: x[2],
        )
        exposure_extra += add(chosen_field, chosen_distance, chosen_points, "exposure")
        # 미선택 시설은 점수에 중복 반영하지 않고 참고 기록으로만 남깁니다.
        for field, distance, points in facility_scores:
            if field != chosen_field:
                add(field, distance, 0, "exposure")

    # 3. 악화 가능성 (최대 10점): 검증·정규화한 강수량/풍속만 사용합니다.
    # 기상청 RN1은 rainfall_mm(mm/최근 1시간), WSD는 wind_speed_mps(m/s)로 전달합니다.
    # 관측값은 악화 환경의 근거이며, 실제 지반 확대·물체 이동을 확인한 값은 아닙니다.
    weather_scores = []
    rainfall = observation("rainfall_mm", numeric=True)
    if rainfall is not None:
        points = (
            10 if rainfall >= 30
            else 5 if rainfall >= 10
            else 0
        )
        weather_scores.append(("rainfall_mm", rainfall, points))

    # 풍속은 나무·전봇대와 도로 장애물에만 적용합니다.
    if hazard in {"fallen_tree", "road_obstacle"}:
        wind = observation("wind_speed_mps", numeric=True)
        if wind is not None:
            points = (
                10 if wind >= 21
                else 5 if wind >= 14
                else 0
            )
            weather_scores.append(("wind_speed_mps", wind, points))

    # 나무·전봇대는 높은 점수 하나만 사용하고, 동점이면 풍속을 대표 근거로 선택합니다.
    selected_weather = None
    if hazard == "fallen_tree" and weather_scores:
        selected_weather = max(
            weather_scores, key=lambda item: (item[2], item[0] == "wind_speed_mps")
        )[0]

    for field, value, points in weather_scores:
        # 도로 장애물: 비 최대 5점 + 강풍 최대 5점 (각 항목 0/2.5/5점).
        candidate_points = points / 2 if hazard == "road_obstacle" else points
        applied_points = candidate_points
        if hazard == "fallen_tree" and field != selected_weather:
            applied_points = 0
        worsening_extra += add(field, value, applied_points, "worsening")
        # 미선택 자료도 출처·시각·원래 가산점과 함께 남겨 중복 가산과 구분합니다.
        components[field]["candidate_points"] = candidate_points
        if hazard == "fallen_tree":
            components[field]["selected"] = field == selected_weather

    severity = min(60.0, base + severity_extra)
    exposure = min(30.0, exposure_extra)
    worsening = min(10.0, worsening_extra)
    score = round(min(100.0, severity + exposure + worsening), 2)
    medium, high = _risk_thresholds(policy)
    level = (
        "HIGH" if score >= high
        else "MEDIUM" if score >= medium
        else "LOW"
    )
    priority = (
        "P1" if score >= high
        else "P2" if score >= medium
        else "P3"
    )

    return {
        "risk_score": score,
        "risk_level": level,
        "risk_breakdown": {
            "base_score": base,
            "severity_score": severity,
            "exposure_score": exposure,
            "worsening_score": worsening,
            "components": components,
            "missing": sorted(set(unknown)),
            "provisional": bool(unknown),
            # 네 재난의 악화 Rule을 적용했습니다. 관측 누락은 missing/provisional로 표시합니다.
            "not_evaluated": [],
        },
        "priority_score": score,
        "priority": priority,
        "priority_breakdown": {
            "risk_score": score,
            "waiting_time_bonus": 0,
        },
        "rule_version": policy["version"],
    }


# 코드 · 사건 간 우선순위 (대기시간 가산 없음)
def assign_priorities(incidents, now=None, policy=None):
    results = []
    medium, high = _risk_thresholds(policy)
    for row in incidents:
        if row.get("risk_score") is None:
            continue
        score = round(float(row["risk_score"]), 2)
        results.append({
            **row,
            "priority_score": score,
            "priority": (
                "P1" if score >= high
                else "P2" if score >= medium
                else "P3"
            ),
            "priority_breakdown": {
                "risk_score": score,
                "waiting_time_bonus": 0,
            },
        })
    # 점수 동점: 먼저 탐지된 사건, 그다음 ID
    return sorted(
        results,
        key=lambda x: (-x["priority_score"], x["detected_at"], x["id"]),
    )
