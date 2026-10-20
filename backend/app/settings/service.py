"""
감시 기준·개인 알림 설정: 관리자 저장→재조회, 개인 Push ON/OFF를 처리합니다.

파일 흐름
1. 본인 Push 수신 상태는 JWT로 조회한 users.notification_enabled에서 가져옵니다.
2. 설정 변경 시 PostgreSQL의 기존 사용자 행만 수정합니다.

주요 기능
- DB 알림 생성 여부와 Push 발송 허용 설정을 분리.
"""

from datetime import timezone
from typing import Any

from fastapi import HTTPException

from ..db.session import get_connection
from . import (
    repository,
    schemas,
)


# ============================================================
# Runtime 적용 범위
# ============================================================


SAMPLING_LIVE_FIELDS = (
    "base_analysis_interval_sec",
    "alert_analysis_interval_sec",
    "verify_analysis_interval_sec",
    "quality_threshold",
)


CAPTURE_RESTART_FIELDS = (
    "reconnect_interval_sec",
    "max_reconnect_attempts",
)


INCIDENT_RESTART_FIELDS = (
    "candidate_confidence_threshold",
    "candidate_min_detection_count",
    "temporal_validation_sec",
    "incident_confidence_threshold",
)


APPLICATION = {
    **{
        name: {
            "mode": "NEXT_POLL",
            "description": (
                "실행 중인 CCTV Runtime이 "
                "다음 monitoring_settings 조회에서 "
                "반영합니다."
            ),
        }
        for name in SAMPLING_LIVE_FIELDS
    },

    **{
        name: {
            "mode": "RESTART_REQUIRED",
            "description": (
                "CaptureWorker 생성 시 적용되는 설정입니다. "
                "이미 실행 중인 Worker에는 "
                "Runtime 재시작 후 적용됩니다."
            ),
        }
        for name in CAPTURE_RESTART_FIELDS
    },

    **{
        name: {
            "mode": "RESTART_REQUIRED",
            "description": (
                "Incident Pipeline에 연결된 설정입니다. "
                "DB 저장 후 CCTV Incident Runtime을 "
                "재시작하면 적용됩니다."
            ),
        }
        for name in INCIDENT_RESTART_FIELDS
    },
}


# ============================================================
# Monitoring Settings
# ============================================================


def _response(
    row,
) -> schemas.MonitoringSettingsResponse:

    if row is None:

        raise HTTPException(
            status_code=409,
            detail=(
                "감시 설정 행이 없습니다. "
                "기존 초기 설정을 확인해주세요."
            ),
        )

    value = dict(
        row
    )

    updated_at = value[
        "updated_at"
    ]

    value[
        "updated_at"
    ] = (
        updated_at.replace(
            tzinfo=timezone.utc
        )
        if updated_at.tzinfo is None
        else updated_at.astimezone(
            timezone.utc
        )
    )

    return (
        schemas
        .MonitoringSettingsResponse(
            **value,
            application=APPLICATION,
        )
    )


def get_monitoring_settings():
    """
    관리자용 현재 monitoring_settings 조회.
    """

    with get_connection() as connection:

        return _response(
            repository
            .get_monitoring_settings(
                connection
            )
        )


def update_monitoring_settings(
    body: schemas.MonitoringSettingsRequest,
    user: dict,
):
    """
    관리자가 monitoring_settings 값을 저장한다.

    모든 필드는 기존 monitoring_settings 테이블의
    기존 컬럼만 사용한다.

    DB 구조 변경은 수행하지 않는다.

    Runtime 반영 시점은 각 필드의
    application 정보로 응답한다.
    """

    with get_connection() as connection:

        current = (
            repository
            .get_monitoring_settings(
                connection,
                for_update=True,
            )
        )

        _response(
            current
        )

        values = (
            body.model_dump()
        )

        repository.save_monitoring_settings(
            connection,
            int(
                current[
                    "id"
                ]
            ),
            values,
            int(
                user[
                    "id"
                ]
            ),
        )

        return _response(
            repository
            .get_monitoring_settings(
                connection
            )
        )


# ============================================================
# Personal Push Settings
# ============================================================


def get_notification_settings(
    user: dict[str, Any],
) -> schemas.NotificationSettingsRequest:
    """
    JWT 사용자 본인의 Push 수신 설정.
    """

    return (
        schemas
        .NotificationSettingsRequest(
            enabled=(
                user[
                    "notification_enabled"
                ]
            )
        )
    )


def update_notification_settings(
    body: schemas.NotificationSettingsRequest,
    user: dict[str, Any],
) -> schemas.NotificationSettingsRequest:
    """
    사용자 본인의 Push ON/OFF만 변경한다.

    기존 notifications 데이터는 삭제하지 않는다.
    """

    with get_connection() as connection:

        row = (
            repository
            .set_notification_enabled(
                connection,
                int(
                    user[
                        "id"
                    ]
                ),
                body.enabled,
            )
        )

        if row is None:

            raise HTTPException(
                status_code=403,
                detail=(
                    "활성 사용자만 "
                    "알림 설정을 변경할 수 있습니다."
                ),
            )

        return (
            schemas
            .NotificationSettingsRequest(
                enabled=(
                    row[
                        "notification_enabled"
                    ]
                )
            )
        )