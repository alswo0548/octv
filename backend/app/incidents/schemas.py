"""사건 목록·상세 응답의 필드와 검증 조건을 정의합니다."""

from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


class IncidentResponse(BaseModel):
    id: int
    incident_no: str
    cctv_id: int
    cctv_name: str
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


# 현재 페이지 목록과 검색 조건에 맞는 전체 건수를 묶습니다.
class IncidentPage(BaseModel):
    items: list[IncidentResponse]
    total: int
    page: int
    page_size: int
