"""시연 전용 교통 상황 투영. 실제 경로/점수/내비 권한/DB를 변경하지 않는다."""
from __future__ import annotations

from math import isfinite
from typing import Any

DEMO_CCTV_IDS = frozenset({"DEMO-N001", "DEMO-N002", "DEMO-N003"})
DELAY_SECONDS = 30 * 60  # 가정한 공사·정체 추가 시간. 실제 API 값 아님.


def _point_on_route(geometry: Any) -> list[float] | None:
    """실제 경로의 중간 좌표를 '가상 통제 표시점'으로만 사용한다."""
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        return None
    points = geometry.get("coordinates")
    if not isinstance(points, list) or len(points) < 2:
        return None
    point = points[len(points) // 2]
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        return None
    lon, lat = point[:2]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v) for v in (lon, lat)):
        return None
    if abs(lon) > 180 or abs(lat) > 85.05112878:
        return None
    return [round(lon, 6), round(lat, 6)]


def overlay_candidates(
    candidates: list[Any], *, duration_scale_sec: float, distance_scale_m: float,
) -> list[dict[str, Any]]:
    """원본 경로에 가상 통제와 가상 지연을 적용한 별도 응답 복사본을 반환한다.

    실제 API 필드(실제 점수·시간·판정·내비 가능 여부)는 그대로 유지한다.
    시연 점수는 시간 70 / 거리 30 계산식에 +30분을 적용한 별도 값이다.
    """
    rows = [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in candidates]
    if (not isfinite(duration_scale_sec) or duration_scale_sec <= 0
            or not isfinite(distance_scale_m) or distance_scale_m <= 0):
        raise ValueError("시연 점수 기준값은 양수여야 합니다.")
    usable = [r for r in rows if not r.get("disqualify_reason")
              and r.get("verification_status") != "DISQUALIFIED"
              and r.get("navigation_available")]
    if len(usable) < 2:
        return rows

    # 원래 점수순으로 타깃 선정. 실제 통제된 후보는 가상의 시나리오에 편입하지 않음.
    usable.sort(key=lambda r: (-(r.get("total_score") or 0), r["id"]))
    closure = usable[0] if len(usable) >= 3 else None
    delayed = usable[1] if closure else usable[0]
    for r in usable:
        r["demo_total_score"] = r.get("total_score")
        r["demo_duration_sec"] = r["duration_sec"]
        r["demo_rank_status"] = "ALTERNATIVE"

    if closure:
        point = _point_on_route(closure.get("route_path_json"))
        note = "기존 경로 중간 지점에 가상의 전면 통제를 설정해 시연에서만 제외"
        if point:
            note += f" (표시 좌표 {point[1]:.5f}, {point[0]:.5f}; 실제 통제 아님)"
        closure["demo_traffic"] = {
            "type": "SIMULATED_FULL_CLOSURE", "label": "시연용 가상 전면 통제",
            "reason": note, "simulated": True, "point": point,
            "delay_sec": 0,
        }
        closure["demo_rank_status"] = "SIMULATED_EXCLUDED"
        closure["demo_total_score"] = None

    adjusted_duration = delayed["duration_sec"] + DELAY_SECONDS
    adjusted_score = round(
        70 / (1 + adjusted_duration / duration_scale_sec)
        + 30 / (1 + delayed["distance_m"] / distance_scale_m), 2,
    )
    delayed["demo_traffic"] = {
        "type": "SIMULATED_DELAY", "label": "시연용 가상 공사·정체",
        "reason": "가상 정체로 예상 이동시간 30분을 추가해 시간70·거리30 기준으로 시연 점수 재계산 (실제 API 점수 유지)",
        "simulated": True, "point": _point_on_route(delayed.get("route_path_json")),
        "delay_sec": DELAY_SECONDS,
    }
    delayed["demo_duration_sec"] = adjusted_duration
    delayed["demo_total_score"] = adjusted_score
    delayed["demo_rank_status"] = "SIMULATED_DELAY"

    # 실제 통제는 맨 끝. 시연 제외는 실제 내비 가능 여부를 바꾸지 않음.
    return sorted(rows, key=lambda r: (
        2 if r.get("disqualify_reason") or r.get("verification_status") == "DISQUALIFIED"
        else 1 if r.get("demo_rank_status") == "SIMULATED_EXCLUDED" else 0,
        -(r.get("demo_total_score") if r.get("demo_total_score") is not None else -1),
        r["id"],
    ))
