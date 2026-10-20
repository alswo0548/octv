"""사건 목록·상세 응답의 필드와 검증 조건을 정의합니다."""

from pydantic import BaseModel, Field
from typing import Any, Literal
from datetime import datetime


class IncidentResponse(BaseModel):
    id: int
    incident_no: str
    cctv_id: int
    cctv_name: str
    provider: str | None = None
    address: str | None = None
    hazard_type: str
    status: Literal["DETECTED", "CONFIRMED", "SENT", "RESOLVED", "FALSE_POSITIVE"]
    confidence: float = Field(ge=0, le=1)
    detected_at: datetime
    last_detected_at: datetime
    latitude: float
    longitude: float
    # 필수 필드이지만 값 자체는 null일 수 있습니다.
    region_code: str | None
    # 평가 전에는 점수·등급이 없을 수 있습니다.
    risk_score: float | None = None
    risk_level: str | None = None
    priority_score: float | None = None
    priority: str | None = None
    # Service가 risk_level의 존재 여부로 계산하는 화면용 상태입니다.
    analysis_status: Literal["PENDING", "READY"]
    representative_image_updated_at: datetime | None = None
    detection_bbox_json: dict | list


class IncidentDetailResponse(IncidentResponse):
    risk_breakdown_json: dict[str, Any] | None = None
    priority_breakdown_json: dict[str, Any] | None = None
    rule_version: str | None = None

    # AI 분석 완료 후 추천 기관과 기관별 경로 후보를 함께 반환합니다.
    # 분석 전이거나 추천 가능한 기관이 없으면 빈 리스트입니다.
    recommendations: list[dict[str, Any]] = Field(
        default_factory=list
    )


# 현재 페이지 목록과 검색 조건에 맞는 전체 건수를 묶습니다.
class IncidentPage(BaseModel):
    items: list[IncidentResponse]
    total: int
    page: int
    page_size: int
