"""
본인 알림 조회·읽음 및 기기별 FCM 토큰 관리 HTTP API를 연결하여 실제 모바일 앱에서 호출할수 있다.

파일 흐름
1. JWT 인증으로 현재 사용자를 가져옵니다.
2. GET 목록은 최신순·미읽음 필터와 페이지 크기를 검사.
3. PATCH 읽음은 URL 알림 ID를 검증한 뒤 Service에 전달.
4. POST/DELETE 기기 API는 FCM 등록 토큰 등록·갱신·해제를 처리.

주요 기능
- 모든 API에서 기존 get_current_user 인증을 재사용.
- JWT와 FCM 토큰은 목적이 다르며 여기서는 FCM을 발송하지 않습니다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import UUID4

from ..dependencies import get_current_user
from . import schemas, service

router = APIRouter(prefix="/notifications", tags=["사건 전달 알림"])

# JWT에서 사용자 ID를 확인하며 클라이언트가 보낸 user_id는 사용하지 않습니다.
CurrentUser = Annotated[dict, Depends(get_current_user)]
NotificationId = Annotated[int, Path(gt=0, le=9223372036854775807)]


# 로그인 사용자 본인의 최근 알림을 최신순으로 조회.
@router.get("", response_model=list[schemas.NotificationResponse], summary="본인 알림 목록 조회")
def list_notifications(
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,            # 기본 30개 조회, 최대 100개
    offset: Annotated[int, Query(ge=0, le=1000000)] = 0,        # 처음부터 조회
    unread_only: bool = False,                                  # 읽은 알림도 함께 조회
):
    return service.list_notifications(user, limit, offset, unread_only)


# JWT 소유자의 알림만 읽음 처리하고 처리된 한 건을 반환.
@router.patch("/{notification_id}/read", response_model=schemas.NotificationResponse,
              summary="본인 알림 한 건 읽음 처리")
def mark_read(notification_id: NotificationId, user: CurrentUser):
    return service.mark_read(notification_id, user)


# 앱 설치 UUID4와 실제 FCM 등록 토큰을 받아 등록·재등록.
@router.post("/devices", response_model=schemas.DeviceTokenRegisterResponse,
             summary="FCM 기기 토큰 등록·갱신")
def register_device(body: schemas.DeviceTokenRegisterRequest, user: CurrentUser):
    return service.register_device(body, user)


# 현재 계정에 속한 앱 설치의 FCM 토큰만 해제 (로그아웃 등).
@router.delete("/devices/{device_id}", response_model=schemas.DeviceTokenRemoveResponse,
               summary="FCM 기기 토큰 해제")
def remove_device(device_id: UUID4, user: CurrentUser):
    return service.remove_device(device_id, user)
