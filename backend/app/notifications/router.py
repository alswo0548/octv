"""사건 전달 알림 HTTP 진입점. 현재 업무 API는 501(미구현)을 반환합니다."""

from fastapi import APIRouter
from . import schemas, service

router = APIRouter(prefix="/notifications", tags=["사건 전달 알림"])
# TODO: 구현하는 API부터 dependencies의 인증·권한 검사를 연결하세요.


@router.get("", summary="list_notifications · 구현 예정")
def list_notifications():
    return service.list_notifications()


@router.patch("/{notification_id}/read", summary="mark_read · 구현 예정")
def mark_read(notification_id: int):
    return service.mark_read(notification_id)
