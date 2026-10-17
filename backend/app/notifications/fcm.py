"""
DB 알림 정보 → 개인정보 없는 FCM 메시지 작성 → Firebase 요청 → 기기별 결과 반환.

주요 기능
1. 실제 발송 시점에만 Firebase Admin SDK와 서버 자격증명을 초기화.
2. 사용자 한 명의 현재 유효한 기기(최대 10대)에 직접 FCM 요청.
3. 요청 접수·무효 토큰·일시 장애·설정 오류를 구분.
4. JWT, FCM 토큰, 자격증명, 원문 예외를 응답이나 로그에 포함하지 않습니다.

주의: ACCEPTED는 FCM 요청 접수이며 휴대폰 수신·표시 성공이 아닙니다.
DB/Redis 처리, 재시도 예약, 사용자 권한 검사는 notifications/service.py가 담당.
"""

import math
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Literal

_APP_NAME = "octv-push"
_APP_LOCK = threading.Lock()
_HTTP_TIMEOUT_SECONDS = 10
_ANDROID_CHANNEL_ID = "octv_incident_delivery"


# 비밀값 없이 기기별 FCM 결과만 Service에 전달.
# @dataclass: 여러 데이터를 하나로 묶어 관리하기 편하게 해주는 기능
@dataclass(frozen=True)
class FcmOutcome:
    status: Literal[
        "ACCEPTED",                 # Firebase 서버 요청 접수
        "UNREGISTERED",             # 등록되지 않은 무효 토튼
        "RETRY",                    # 일시적 오류, 재시도 가능
        "PERMANENT_ERROR",          # 반복해도 해결되지 않을 가능성이 높은 오류
        "CONFIG_ERROR"              # Firebase 인증,설정 문제
    ]
    code: str
    retry_after_seconds: int = 0


# 자격증명 원문 대신 고정된 설정 오류 코드만 전달.
class FcmConfigurationError(RuntimeError):
    pass


# Worker 프로세스 안에서 필요할 때만 Firebase 앱을 만들고 재사용.
def _get_firebase_app():
    import firebase_admin
    
    # 환경변수에서 Firebase 프로젝트 ID를 가져온 뒤 os.environ.get()으로 Windows에서 설정한 환경변수 값을 Python에서 읽는 기능
    project_id = os.environ.get("OCTV_FIREBASE_PROJECT_ID", "").strip()
    if not project_id:
        raise FcmConfigurationError("FIREBASE_PROJECT_NOT_CONFIGURED")
    with _APP_LOCK:
        try:
            app = firebase_admin.get_app(_APP_NAME)
        except ValueError:
            # ADC가 GOOGLE_APPLICATION_CREDENTIALS 또는 실행 환경의 서비스 계정을 사용.
            # 자격증명 JSON을 코드에 읽어 넣거나 Git에 저장하지 않습니다.
            try:
                app = firebase_admin.initialize_app(
                    options={"projectId": project_id, "httpTimeout": _HTTP_TIMEOUT_SECONDS},
                    name=_APP_NAME,
                )
            except Exception:
                raise FcmConfigurationError("FIREBASE_INITIALIZATION_FAILED") from None
        if app.project_id != project_id:
            raise FcmConfigurationError("FIREBASE_PROJECT_CHANGED_RESTART_WORKER")
        return app


# Retry-After의 초 단위 값과 HTTP 날짜를 처리하며 원문 헤더는 외부에 반환하지 않습니다.
def _retry_after_seconds(exc: Exception) -> int:
    response = getattr(exc, "http_response", None)
    if response is None:
        response = getattr(exc, "response", None)
    value = getattr(response, "headers", {}).get("Retry-After") if response is not None else None
    if not value:
        return 0
    try:
        seconds = float(value)
        if math.isfinite(seconds):
            return max(0, math.ceil(seconds))
        return 0
    except (ValueError, TypeError):
        try:
            retry_at = parsedate_to_datetime(str(value))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0, math.ceil((retry_at - datetime.now(timezone.utc)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return 0


# 영구 오류를 반복하지 않고, 토큰 삭제는 UNREGISTERED일 때만 허용.
def _classify_error(exc: Exception) -> FcmOutcome:
    from firebase_admin import exceptions, messaging
    from google.auth import exceptions as auth_errors
    from requests import exceptions as request_errors

    if isinstance(exc, messaging.UnregisteredError):
        return FcmOutcome("UNREGISTERED", "UNREGISTERED")
    if isinstance(exc, (messaging.SenderIdMismatchError, messaging.ThirdPartyAuthError)):
        return FcmOutcome("CONFIG_ERROR", "FIREBASE_PROJECT_OR_APNS_AUTH")
    if isinstance(exc, (exceptions.UnauthenticatedError, exceptions.PermissionDeniedError,
                        auth_errors.DefaultCredentialsError, auth_errors.RefreshError)):
        return FcmOutcome("CONFIG_ERROR", "FIREBASE_AUTH_OR_PERMISSION")
    if isinstance(exc, (messaging.QuotaExceededError, exceptions.ResourceExhaustedError,
                        exceptions.UnavailableError, exceptions.InternalError,
                        exceptions.DeadlineExceededError, exceptions.AbortedError,
                        auth_errors.TransportError, request_errors.Timeout,
                        request_errors.ConnectionError)):
        return FcmOutcome("RETRY", "FCM_TEMPORARY_ERROR", _retry_after_seconds(exc))
    if isinstance(exc, (exceptions.InvalidArgumentError, ValueError, TypeError)):
        # INVALID_ARGUMENT는 메시지 형식 오류일 수도 있으므로 토큰을 지우지 않습니다.
        return FcmOutcome("PERMANENT_ERROR", "INVALID_ARGUMENT_OR_PAYLOAD")
    if isinstance(exc, (FcmConfigurationError, OSError)):
        return FcmOutcome("CONFIG_ERROR", "FIREBASE_CONFIGURATION")
    # 알 수 없는 오류를 무한 재시도하지 않습니다. 원문 예외와 요청 객체는 반환하지 않습니다.
    return FcmOutcome("PERMANENT_ERROR", "FCM_UNCLASSIFIED_ERROR")


# 같은 알림의 기기들을 한 번 요청하고 입력 순서와 같은 순서로 결과를 반환.
def send_to_devices(
    notification_id: int,
    incident_id: int,
    tokens: list[str],
    ttl_seconds: int,
) -> list[FcmOutcome]:
    if not tokens:
        return []
    if len(tokens) > 10 or len(set(tokens)) != len(tokens):
        return [FcmOutcome("PERMANENT_ERROR", "INVALID_DEVICE_BATCH") for _ in tokens]
    if ttl_seconds <= 0:
        return [FcmOutcome("PERMANENT_ERROR", "MESSAGE_EXPIRED") for _ in tokens]
    try:
        # 이 import 이전에는 Firebase 연결이나 자격증명 초기화가 발생하지 않습니다.
        from firebase_admin import messaging
    except ImportError:
        return [FcmOutcome("CONFIG_ERROR", "FIREBASE_SDK_NOT_INSTALLED") for _ in tokens]
    try:
        app = _get_firebase_app()
        ttl = min(int(ttl_seconds), 1800)
        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(
                title="OCTV 사건 전달",
                body="새로운 사건이 전달되었습니다. 앱에서 확인해 주세요.",
            ),
            # ID는 화면 이동용 힌트. 
            # 알림을 눌렀을 때 해당 사건 상세 화면으로 이동하기 위한 정보
            data={
                "schema_version": "1",
                "type": "INCIDENT_DELIVERED",
                "incident_id": str(incident_id),
                "notification_id": str(notification_id),
            },
            android=messaging.AndroidConfig(
                priority="high",
                ttl=timedelta(seconds=ttl),
                notification=messaging.AndroidNotification(
                    channel_id=_ANDROID_CHANNEL_ID,
                    sound="default",
                    tag=f"octv_notification_{notification_id}",
                ),
            ),
            apns=messaging.APNSConfig(
                headers={
                    "apns-priority": "10",
                    "apns-push-type": "alert",
                    "apns-expiration": str(int(time.time()) + ttl),
                    "apns-collapse-id": f"octv_notification_{notification_id}",
                },
                payload=messaging.APNSPayload(aps=messaging.Aps(sound="default")),
            ),
        )
        # 지원되는 등록 토큰 계약을 사용. UUID4를 FID로 바꾸어 보내지 않습니다.
        # SDK 내부 HTTP 재시도는 별도입니다. 이 호출만으로 exactly-once를 보장하지 않습니다.
        # 실제 전송은 여기서 일어난다.
        response = messaging.send_each_for_multicast(message, app=app)
        if len(response.responses) != len(tokens):
            return [FcmOutcome("RETRY", "UNCONFIRMED_BATCH_RESULT") for _ in tokens]
        return [
            FcmOutcome("ACCEPTED", "FCM_ACCEPTED") if item.success
            else _classify_error(item.exception)
            for item in response.responses
        ]
    except Exception as exc:
        outcome = _classify_error(exc)
        return [outcome for _ in tokens]
