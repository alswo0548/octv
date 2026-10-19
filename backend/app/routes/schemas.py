"""기관별 경로 조회 응답 형식. 저장된 경로와 확인 상태를 화면에 전달.

흐름: Router → Service의 권한 확인 → Repository의 저장 경로 조회 → 이 스키마로 응답 검증.
경로는 재계산하지 않으며, 후보가 0개여도 빈 목록으로 반환합니다.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class RouteCandidateResponse(BaseModel):
    id: int
    route_name: str
    distance_m: int
    duration_sec: int
    total_score: float | None = None
    score_breakdown_json: dict[str, Any] | None = None
    disqualify_reason: str | None = None
    route_path_json: dict[str, Any]
    rule_version: str
    verification_status: Literal["VERIFIED", "NEEDS_REVIEW", "DISQUALIFIED"] | None = None
    # 통제 정보 미확인은 안전 확인을 뜻하지 않습니다. NEEDS_REVIEW는 별도 안내가 필요합니다.
    requires_review: bool
    navigation_available: bool


class RouteCandidatesResponse(BaseModel):
    incident_id: int
    agency_id: int
    analysis_status: Literal["PENDING", "READY"]
    recommendation_status: Literal["RECOMMENDED", "DELIVERED", "COMPLETED"] | None = None
    # 아직 분석되지 않음 / 추천 기관 없음 / 경로 없음 / 제외만 있음 / 추가 확인 / 조회 가능
    result_status: Literal[
        "NOT_ANALYZED", "NO_RECOMMENDATION", "NO_ROUTES",
        "ALL_DISQUALIFIED", "NEEDS_REVIEW", "AVAILABLE",
    ]
    items: list[RouteCandidateResponse] = Field(default_factory=list)
