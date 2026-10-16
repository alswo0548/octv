"""
사용자별 사건 전달 알림과 FCM 기기 토큰 요청·응답 형식을 정의합니다.
핵심은 앱 알림 데이터의 형식을 정하고, 휴대폰의 FCM 토큰을 안전하게 전달 받는 것.

파일 흐름
1. 로그인 사용자의 알림 행을 NotificationResponse (알림ID, 사건ID, 생성 읽음 시간 반환)로 반환.
2. 기기 등록 요청은 UUID4 기기 ID, FCM 토큰, OS를 검사.
3. 등록·해제 응답에는 FCM 토큰 원문을 포함하지 않습니다.

주요 기능
- 알림 읽음 시각(미읽음이면 None)과 사건 ID 응답
- Expo Push Token 혼입 방지 및 요청에 사용자 ID 추가 금지
- 이 파일은 DB나 Redis에 직접 접속하지 않습니다.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, UUID4, field_validator


# 기존 사건 전달 알림 응답 형식을 그대로 사용합니다.
class NotificationResponse(BaseModel):
    id: int
    incident_id: int # incidents_id는 Repository SELECT에서 incident_id로 변환.
    created_at: datetime
    read_at: datetime | None = None


# 앱 설치 단위의 FCM 등록 토큰을 전달받습니다. 사용자 ID는 JWT에서만 결정.
# JWT: 현재 로그인한 사용자가 누구인지 확인
# FCM 토큰: 어느 앱 설치 대상으로 Push를 보낼지 식별
class DeviceTokenRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: UUID4                                        # 앱 설치를 구분하는 임의 고유 ID 형식
    platform: Literal["android", "ios"]                     # Android 또는  iOS만 허용 
    # SecretStr는 응답/디버그 표현에 토큰 원문이 노출될 위험을 낮춥니다.
    fcm_token: SecretStr = Field(min_length=16, max_length=4096, repr=False)

    # Expo Push Token이나 공백이 포함된 값은 FCM 등록 토큰으로 취급하지 않습니다.
    @field_validator("fcm_token")                           # 특정 필드에 추가 검사 적용
    @classmethod                                            # 클래스에 소속된 메서드로 정의
    def validate_fcm_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if token.lower().startswith(("expopushtoken[", "exponentpushtoken[")):
            raise ValueError("Expo Push Token이 아닌 FCM 등록 토큰을 보내야 합니다.")
        if any(character.isspace() for character in token):
            raise ValueError("FCM 등록 토큰에는 공백을 사용할 수 없습니다.")
        return value


# FCM 토큰 원문은 돌려주지 않고 기기 등록 상태만 반환.
class DeviceTokenRegisterResponse(BaseModel):
    device_id: UUID4
    platform: Literal["android", "ios"]
    token_type: Literal["FCM"] = "FCM"
    registered: bool = True


# 사용자의 기기 토큰 연결을 해제한 결과를 반환.
class DeviceTokenRemoveResponse(BaseModel):
    removed: bool
