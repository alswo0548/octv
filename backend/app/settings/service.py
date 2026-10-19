"""
감시 기준·개인 알림 설정: 관리자 저장→재조회, 개인 Push ON/OFF를 처리합니다.

파일 흐름
1. 본인 Push 수신 상태는 JWT로 조회한 users.notification_enabled에서 가져옵니다.
2. 설정 변경 시 PostgreSQL의 기존 사용자 행만 수정합니다.

주요 기능
- DB 알림 생성 여부와 Push 발송 허용 설정을 분리.
"""

from typing import Any
from datetime import timezone

from fastapi import HTTPException

from ..db.session import get_connection
from . import repository, schemas

DISCONNECTED_FIELDS = (
    "candidate_confidence_threshold", "candidate_min_detection_count",
    "temporal_validation_sec", "incident_confidence_threshold",
)
APPLICATION = {
    **{name: {"mode": "NEXT_POLL", "description": "실행 중인 Runtime의 다음 설정 조회 후 반영. 실행 여부는 별도 확인."}
       for name in ("base_analysis_interval_sec", "alert_analysis_interval_sec", "verify_analysis_interval_sec", "quality_threshold")},
    **{name: {"mode": "RESTART_REQUIRED", "description": "새 CaptureWorker 생성 시 적용. 기존 Worker는 Runtime 재시작 필요."}
       for name in ("reconnect_interval_sec", "max_reconnect_attempts")},
    **{name: {"mode": "NOT_CONNECTED", "description": "DB 설정과 사건화 설정 연결 대기 · 읽기 전용."}
       for name in DISCONNECTED_FIELDS},
}


def _response(row):
    if row is None:
        raise HTTPException(status_code=409, detail="감시 설정 행이 없습니다. 기존 초기 설정을 확인해주세요.")
    value = dict(row)
    value["updated_at"] = value["updated_at"].replace(tzinfo=timezone.utc) if value["updated_at"].tzinfo is None else value["updated_at"].astimezone(timezone.utc)
    return schemas.MonitoringSettingsResponse(**value, application=APPLICATION)


def get_monitoring_settings():
    # 관리자 감시 기준과 개인 알림을 분리하고 기존 SQL의 필드·단위를 사용합니다.
    with get_connection() as connection:
        return _response(repository.get_monitoring_settings(connection))


def update_monitoring_settings(body: schemas.MonitoringSettingsRequest, user: dict):
    # 저장과 재조회는 같은 트랜잭션이며 Runtime 적용 완료를 의미하지 않습니다.
    with get_connection() as connection:
        current = repository.get_monitoring_settings(connection, for_update=True)
        _response(current)
        values = body.model_dump()
        if any(values[name] != current[name] for name in DISCONNECTED_FIELDS):
            raise HTTPException(status_code=409, detail="사건화 연결 대기 항목은 변경할 수 없습니다. 다시 조회해주세요.")
        repository.save_monitoring_settings(connection, current["id"], values, user["id"])
        return _response(repository.get_monitoring_settings(connection))


# 매 HTTP 요청마다 JWT에서 조회한 로그인 사용자 정보로 현재 Push 수신 설정을 반환.
def get_notification_settings(user: dict[str, Any]) -> schemas.NotificationSettingsRequest:
    return schemas.NotificationSettingsRequest(enabled=user["notification_enabled"])


# 본인 사용자 행의 Push 수신 ON/OFF만 갱신하며 DB 알림 행은 삭제하지 않습니다.
def update_notification_settings(body: schemas.NotificationSettingsRequest,
                                 user: dict[str, Any]) -> schemas.NotificationSettingsRequest:
    with get_connection() as connection:
        row = repository.set_notification_enabled(connection, int(user["id"]), body.enabled)
        if row is None:
            raise HTTPException(status_code=403, detail="활성 사용자만 알림 설정을 변경할 수 있습니다.")
        result = schemas.NotificationSettingsRequest(enabled=row["notification_enabled"])
    return result
