"""
관리자 감시 기준 조회·저장과 로그인한 사용자 본인의 Push 수신 ON/OFF API.

파일 흐름
1. /me/notifications GET은 JWT 사용자 정보에서 현재 수신 설정을 읽습니다.
2. /me/notifications PATCH는 사용자 본인 설정만 PostgreSQL에 저장합니다.

주요 기능
- 기존 인증 함수 재사용, 다른 사람의 user_id 입력 없음
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from ..dependencies import get_current_user, require_control_admin
from . import schemas, service

router = APIRouter(prefix="/settings", tags=["감시 기준·개인 알림 설정"])
# 관리자 감시 기준은 기존 JWT·역할 검사 함수를 재사용합니다.
CurrentUser = Annotated[dict, Depends(get_current_user)]
Admin = Annotated[dict, Depends(require_control_admin)]


@router.get("/monitoring", response_model=schemas.MonitoringSettingsResponse, summary="관리자 감시 설정 조회")
def get_monitoring_settings(_admin: Admin):
    return service.get_monitoring_settings()


@router.put("/monitoring", response_model=schemas.MonitoringSettingsResponse, summary="관리자 감시 설정 저장")
def update_monitoring_settings(body: schemas.MonitoringSettingsRequest, admin: Admin):
    return service.update_monitoring_settings(body, admin)


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
