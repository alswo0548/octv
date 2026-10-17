"""
기관 목록 조회 및 관제 관리자의 기관 추천 조회·전달 작업을 처리.
Service는 기관 전달이 가능한지 판단하고, Reposittory에 실제 DB 작업을 요청

파일 흐름
1. 기관 추천 조회·전달 요청은 활성 관제 관리자 권한을 다시 확인합니다.
2. 기존 DB 연결 한 개에서 추천·경로 조회 또는 기관 전달·DB 알림 저장을 수행합니다.
3. 전달 결과를 검증한 뒤 트랜잭션 commit이 끝나야 성공 응답을 반환합니다.
4. commit 후 알림 ID만 기존 Celery에 등록합니다. 큐 오류로 DB 저장을 되돌리지 않습니다.

주요 기능
- 기존 get_connection() 사용, 관리자 권한 확인, 전체 성공 또는 전체 rollback
"""

import logging
from typing import Any

from fastapi import HTTPException

from ..db.session import get_connection
from . import repository, schemas

log = logging.getLogger(__name__) # 오류 기록용 Python 모듈


# DB 연결을 열고 Repository의 기관 목록을 반환합니다.
def list_agencies():
    with get_connection() as connection:
        return repository.list_agencies(connection)


# Router를 통하지 않고 호출해도 비활성 계정·기관 사용자는 전달하지 못하게 확인.
# 기관 전달은 관제 관리자만 실행할 수 있도록 제한
def _require_admin(user: dict[str, Any]) -> None:
    if user.get("role") != "CONTROL_ADMIN" or user.get("is_active") is not True:
        raise HTTPException(status_code=403, detail="활성 관제 관리자 권한이 필요합니다.")


# 관리자 권한 확인 후, LangGraph가 기존 DB에 저장해 둔 기관 추천과 경로 후보만 조회합니다.
def list_recommendations(incident_id: int, user: dict[str, Any]) -> schemas.DeliveryCandidatesResponse:
    _require_admin(user)
    with get_connection() as connection:
        result = repository.list_recommendations(connection, incident_id)
        return schemas.DeliveryCandidatesResponse.model_validate(result)


# 관리자 권한 확인 후 선택 기관 상태 변경과 사용자 DB 알림을 한 트랜잭션으로 처리합니다.
def deliver(
    incident_id: int, body: schemas.DeliveryRequest, user: dict[str, Any],
) -> schemas.DeliveryResponse:
    _require_admin(user)
    with get_connection() as connection:
        result, notification_ids = repository.save_delivery(connection, incident_id, body.selections)
        # commit 전에 응답 형식을 검사해 저장은 됐는데 응답 데이터만 잘못된 상황을 막습니다.
        response = schemas.DeliveryResponse.model_validate(result)
        if response.created_notification_count != len(notification_ids):
            raise RuntimeError("생성된 DB 알림 개수가 처리 결과와 다릅니다.")

    # get_connection() 정상 종료 시 commit되며 오류 시 rollback합니다.
    # 기관 전달은 저장됐는데 응답 검사만 실패하는 상황을 줄이기 위해, commit 전에 검증하는 구조
    try:
        # 순환 import와 Worker 설정 의존성을 피하려고 COMMIT 이후 호출할 때만 가져옵니다.
        from ..notifications.service import enqueue_notification_pushes

        response.push_status = enqueue_notification_pushes(notification_ids)
    except Exception:
        # DB 저장 성공과 큐 등록 확인은 별개입니다. 원문 예외·토큰·URL은 기록하지 않습니다.
        log.warning("push_enqueue_unconfirmed incident_id=%s", incident_id)
        response.push_status = "QUEUE_UNCONFIRMED"
    return response
