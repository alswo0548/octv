"""감시 기준·개인 알림 설정 입출력 초안. SQL 구조와 UI 단위를 확인하며 완성하세요."""

from pydantic import BaseModel
from decimal import Decimal


class MonitoringSettingsRequest(BaseModel):
    base_analysis_interval_sec: int
    alert_analysis_interval_sec: int
    verify_analysis_interval_sec: int
    candidate_confidence_threshold: Decimal
    candidate_min_detection_count: int
    temporal_validation_sec: int
    incident_confidence_threshold: Decimal
    reconnect_interval_sec: int
    max_reconnect_attempts: int
    quality_threshold: Decimal
    # TODO: 허용 범위를 검증하고 updated_by는 인증 사용자로 채우세요.


class NotificationSettingsRequest(BaseModel):
    enabled: bool
