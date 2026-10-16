"""
사건 전달 알림을 로그인 사용자 범위로 조회·읽음 처리하고 기기 토큰을 관리.
즉, 로그인한 사용자의 알림을 처리하고, PostgreSQL과 Redis 작업을 각각 Repository에 요청

파일 흐름
1. Router가 JWT로 확인한 사용자 ID를 전달.
2. PostgreSQL에서는 본인 알림 목록 조회·읽음 처리를 실행.
3. Redis에서는 앱 설치 단위 FCM 토큰 등록·갱신·해제를 실행.
4. 결과는 Schema로 검증해서 반환하고, Redis 오류는 HTTP 503으로 구분.

주요 기능
- 요청 본문에서 user_id 또는 role을 받지 않습니다.
- 알림 조회·읽음 작업과 기기 토큰의 저장소를 분리.
"""

from typing import Any

from fastapi import HTTPException
from redis.exceptions import RedisError

from ..db.session import get_connection
from . import repository, schemas


# 로그인 사용자 본인의 사건 전달 알림 목록만 반환.
def list_notifications(
    user: dict[str, Any], 
    limit: int = 30,
    offset: int = 0, 
    unread_only: bool = False
) -> list[schemas.NotificationResponse]:
    with get_connection() as connection:
        rows = repository.list_for_user(
            connection,
            int(user["id"]), 
            limit=limit, 
            offset=offset, 
            unread_only=unread_only,
        )
    return [schemas.NotificationResponse.model_validate(row) for row in rows]


# 본인의 알림만 읽음 처리하며, 다른 사용자 알림은 존재 여부를 노출하지 않고 404를 반환.
def mark_read(notification_id: int, user: dict[str, Any]) -> schemas.NotificationResponse:
    with get_connection() as connection:
        row = repository.mark_read(connection, notification_id, int(user["id"]))
        if row is None:
            raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다.")
        # 응답 형식 검증이 끝나야 정상적으로 트랜잭션이 확정.
        response = schemas.NotificationResponse.model_validate(row)
    return response


# 사용자 JWT로 기기 소유자를 지정하고 FCM 토큰을 Redis에 등록하거나 갱신.
def register_device(body: schemas.DeviceTokenRegisterRequest,
                    user: dict[str, Any]) -> schemas.DeviceTokenRegisterResponse:
    try:
        registered = repository.register_device_token(
            int(user["id"]),                                # JWT로 확인된 사용자 ID
            body.device_id,                                 # 앱 설치 UUID
            body.platform,                                  # Android / iOS
            body.fcm_token.get_secret_value(),              # 휴대폰 FCM 토큰
        )
    except (RedisError, OSError, RuntimeError, ValueError):
        # Redis URL이나 토큰 원문을 오류 메시지/로그에 노출하지 않습니다.
        raise HTTPException(status_code=503, detail="기기 토큰 저장소를 사용할 수 없습니다.") from None
    if not registered:
        raise HTTPException(status_code=409, detail="등록 가능한 기기는 최대 10대입니다.")
    return schemas.DeviceTokenRegisterResponse(
        device_id=body.device_id, platform=body.platform,
    )


# 로그아웃 시 등록된 기기 UUID를 받아 해당 계정과 연결된 FCM 토큰을 해제.
def remove_device(device_id: Any, user: dict[str, Any]) -> schemas.DeviceTokenRemoveResponse:
    try:
        removed = repository.remove_device_token(int(user["id"]), device_id)
    except (RedisError, OSError, RuntimeError, ValueError):
        raise HTTPException(status_code=503, detail="기기 토큰 저장소를 사용할 수 없습니다.") from None
    return schemas.DeviceTokenRemoveResponse(removed=removed)
