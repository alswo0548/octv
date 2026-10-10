"""사건 목록·상세 API 응답 형식."""

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
    region_code: str | None
    risk_score: float | None = None
    risk_level: str | None = None
    priority_score: float | None = None
    priority: str | None = None
    analysis_status: Literal["PENDING", "READY"]
    detection_image_path: str
    detection_bbox_json: dict | list

class IncidentPage(BaseModel):
    items: list[IncidentResponse]
    total: int
    page: int
    page_size: int
