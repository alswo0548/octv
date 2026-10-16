"""
감시 기준·개인 알림 설정: 기존 감시 기준은 아직 미구현, Push 수신 설정만 구현.

파일 흐름
1. 본인 Push 수신 상태는 JWT로 조회한 users.notification_enabled에서 가져옵니다.
2. 설정 변경 시 PostgreSQL의 기존 사용자 행만 수정합니다.

주요 기능
- DB 알림 생성 여부와 Push 발송 허용 설정을 분리.
"""

from typing import Any

from fastapi import HTTPException

from ..db.session import get_connection
from ..errors import FeatureNotImplemented
from . import repository, schemas


def get_monitoring_settings():
    # TODO: 관리자 감시 기준과 개인 알림 수신 설정을 분리하세요. 감시 기준은
    # backend/app/settings/sql/monitoring_settings.sql의 필드와 단위를 맞추세요.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented(
        "감시 기준·개인 알림 설정 / get_monitoring_settings 구현 예정"
    )


def update_monitoring_settings(body: schemas.MonitoringSettingsRequest):
    # TODO: 관리자 감시 기준과 개인 알림 수신 설정을 분리하세요. 감시 기준은
    # backend/app/settings/sql/monitoring_settings.sql의 필드와 단위를 맞추세요.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented(
        "감시 기준·개인 알림 설정 / update_monitoring_settings 구현 예정"
    )


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
