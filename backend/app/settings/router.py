"""감시 기준·개인 알림 설정 HTTP 진입점. 현재 업무 API는 501(미구현)을 반환합니다."""

from fastapi import APIRouter
from . import schemas, service

router = APIRouter(prefix="/settings", tags=["감시 기준·개인 알림 설정"])
# TODO: 구현하는 API부터 dependencies의 인증·권한 검사를 연결하세요.


@router.get("/monitoring", summary="get_monitoring_settings · 구현 예정")
def get_monitoring_settings():
    return service.get_monitoring_settings()


@router.put("/monitoring", summary="update_monitoring_settings · 구현 예정")
def update_monitoring_settings(body: schemas.MonitoringSettingsRequest):
    return service.update_monitoring_settings(body)


@router.patch("/me/notifications", summary="update_notification_settings · 구현 예정")
def update_notification_settings(body: schemas.NotificationSettingsRequest):
    return service.update_notification_settings(body)
