"""
기존 감시 기준 API를 유지하고 로그인한 사용자의 Push 수신 ON/OFF API를 연결.

파일 흐름
1. /me/notifications GET은 JWT 사용자 정보에서 현재 수신 설정을 읽습니다.
2. /me/notifications PATCH는 사용자 본인 설정만 PostgreSQL에 저장합니다.

주요 기능
- 기존 인증 함수 재사용, 다른 사람의 user_id 입력 없음
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from ..dependencies import get_current_user
from . import schemas, service

router = APIRouter(prefix="/settings", tags=["감시 기준·개인 알림 설정"])
# TODO: 관리자 감시 기준 API는 해당 기능 구현 시 인증·권한 검사까지 연결하세요.
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.get("/monitoring", summary="get_monitoring_settings · 구현 예정")
def get_monitoring_settings():
    return service.get_monitoring_settings()


@router.put("/monitoring", summary="update_monitoring_settings · 구현 예정")
def update_monitoring_settings(body: schemas.MonitoringSettingsRequest):
    return service.update_monitoring_settings(body)


# JWT 사용자 본인의 Push 수신 설정을 조회.
@router.get("/me/notifications", response_model=schemas.NotificationSettingsRequest,
            summary="본인 Push 수신 설정 조회")
def get_notification_settings(user: CurrentUser):
    return service.get_notification_settings(user)


# 로그인 사용자 본인의 Push 수신 설정을 변경.
@router.patch("/me/notifications", response_model=schemas.NotificationSettingsRequest,
              summary="본인 Push 수신 설정 변경")
def update_notification_settings(body: schemas.NotificationSettingsRequest,
                                 user: CurrentUser):
    return service.update_notification_settings(body, user)
