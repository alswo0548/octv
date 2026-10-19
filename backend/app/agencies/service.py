"""
기관 목록 조회와 추천·경로 조회,
관제 관리자의 기관 전달 작업을 처리합니다.
"""

import logging
from typing import Any

from fastapi import HTTPException

from ..db.session import (
    get_connection,
)
from ..incidents import (
    repository as incident_repository,
)
from . import (
    repository,
    schemas,
)


log = logging.getLogger(
    __name__
)


# ------------------------------------------------------------
# 회원가입용 기관 목록
# ------------------------------------------------------------

def list_agencies():
    with get_connection() as connection:
        return repository.list_agencies(
            connection
        )


# ------------------------------------------------------------
# 공통 권한 확인
# ------------------------------------------------------------

def _recommendation_scope(
    user: dict[str, Any],
) -> int | None:
    """
    추천기관/경로 조회 범위를 결정한다.

    CONTROL_ADMIN
        → None
        → 모든 추천기관 조회

    AGENCY_STAFF / RESPONDER
        → 자신의 agency_id
        → 전달된 자기 기관 추천만 조회
    """

    if (
        user.get(
            "is_active"
        )
        is not True
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "활성 사용자만 "
                "접근할 수 있습니다."
            ),
        )

    role = user.get(
        "role"
    )

    if (
        role
        == "CONTROL_ADMIN"
    ):
        return None

    if role in (
        "AGENCY_STAFF",
        "RESPONDER",
    ):
        agency_id = user.get(
            "agency_id"
        )

        if agency_id is None:
            raise HTTPException(
                status_code=403,
                detail=(
                    "소속 기관 정보가 "
                    "필요합니다."
                ),
            )

        return int(
            agency_id
        )

    raise HTTPException(
        status_code=403,
        detail=(
            "접근 권한이 없습니다."
        ),
    )


def _require_admin(
    user: dict[str, Any],
) -> None:
    """
    기관 전달은 관제 관리자만 가능하다.
    """

    if (
        user.get(
            "role"
        )
        != "CONTROL_ADMIN"
        or user.get(
            "is_active"
        )
        is not True
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "활성 관제 관리자 "
                "권한이 필요합니다."
            ),
        )


# ------------------------------------------------------------
# 추천기관 / 경로 조회
# ------------------------------------------------------------

def list_recommendations(
    incident_id: int,
    user: dict[str, Any],
) -> schemas.DeliveryCandidatesResponse:
    """
    로그인 사용자의 역할에 따라
    추천기관 및 경로 조회 범위를 제한한다.
    """

    agency_id = (
        _recommendation_scope(
            user
        )
    )

    with get_connection() as connection:
        result = (
            repository.list_recommendations(
                connection,
                incident_id,
                agency_id=agency_id,
            )
        )

    return (
        schemas.DeliveryCandidatesResponse
        .model_validate(
            result
        )
    )


# ------------------------------------------------------------
# 기관 전달
# ------------------------------------------------------------

def deliver(
    incident_id: int,
    body: schemas.DeliveryRequest,
    user: dict[str, Any],
) -> schemas.DeliveryResponse:
    """
    관제 관리자가 선택한 기관에 사건을 전달한다.
    """

    _require_admin(
        user
    )

    with get_connection() as connection:
        (
            result,
            notification_ids,
        ) = (
            repository.save_delivery(
                connection,
                incident_id,
                body.selections,
            )
        )

        # commit 전에 응답 구조 검증
        response = (
            schemas.DeliveryResponse
            .model_validate(
                result
            )
        )

        if (
            response.created_notification_count
            != len(
                notification_ids
            )
        ):
            raise RuntimeError(
                "생성된 DB 알림 개수가 "
                "처리 결과와 다릅니다."
            )

    # 기존 기관 전달 이후 Push 로직은 보존한다.
    try:
        from ..notifications.service import (
            enqueue_notification_pushes,
        )

        response.push_status = (
            enqueue_notification_pushes(
                notification_ids
            )
        )

    except Exception:
        log.warning(
            "push_enqueue_unconfirmed "
            "incident_id=%s",
            incident_id,
        )

        response.push_status = (
            "QUEUE_UNCONFIRMED"
        )

    return response


# ------------------------------------------------------------
# 현장 대응 완료
# ------------------------------------------------------------

def complete_delivery(
    incident_id: int,
    user: dict[str, Any],
):
    """
    현장대응자가 자기 기관의 대응을 완료한다.

    기관 상태 변경과 Incident 전체 완료 판단은
    하나의 DB 트랜잭션에서 처리한다.
    """

    if (
        user.get("is_active")
        is not True
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "활성 사용자만 "
                "대응 완료 처리할 수 있습니다."
            ),
        )

    if (
        user.get("role")
        != "RESPONDER"
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "현장대응자만 "
                "대응 완료 처리할 수 있습니다."
            ),
        )

    agency_id = user.get(
        "agency_id"
    )

    if agency_id is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "소속 기관 정보가 "
                "필요합니다."
            ),
        )

    with get_connection() as connection:

        completed = (
            repository.complete_delivery(
                connection,
                incident_id,
                int(agency_id),
            )
        )

        incident = (
            incident_repository
            .resolve_if_all_deliveries_completed(
                connection,
                incident_id,
            )
        )

        if incident is None:
            raise HTTPException(
                status_code=404,
                detail="사건이 없습니다.",
            )

        return {
            "incident_id":
                incident_id,

            "agency_id":
                int(agency_id),

            "agency_recommendation_id":
                completed[
                    "agency_recommendation_id"
                ],

            "recommendation_status":
                completed[
                    "recommendation_status"
                ],

            "incident_status":
                incident["status"],
        }
