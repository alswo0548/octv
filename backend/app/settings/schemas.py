"""관리자 감시 설정의 값·단위를 검증하고 저장 정보와 Runtime 반영 범위를 반환합니다."""

from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal

PositiveInt = Annotated[int, Field(strict=True, gt=0, le=2147483647)]
Threshold = Annotated[Decimal, Field(ge=0, le=1, max_digits=5, decimal_places=4)]


class MonitoringSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_analysis_interval_sec: PositiveInt
    alert_analysis_interval_sec: PositiveInt
    verify_analysis_interval_sec: PositiveInt
    candidate_confidence_threshold: Threshold
    candidate_min_detection_count: PositiveInt
    temporal_validation_sec: PositiveInt
    incident_confidence_threshold: Threshold
    reconnect_interval_sec: PositiveInt
    max_reconnect_attempts: PositiveInt
    quality_threshold: Threshold
    # 허용 범위를 검증하고 updated_by는 인증 사용자로 채웁니다.


class SettingApplication(BaseModel):
    mode: Literal["NEXT_POLL", "RESTART_REQUIRED", "NOT_CONNECTED"]
    description: str


class MonitoringSettingsResponse(MonitoringSettingsRequest):
    id: int
    updated_by: int | None
    updated_at: datetime
    application: dict[str, SettingApplication]


class NotificationSettingsRequest(BaseModel):
    enabled: bool
