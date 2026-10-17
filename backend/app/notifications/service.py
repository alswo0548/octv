"""
사건 전달 알림을 로그인 사용자 범위로 조회·읽음 처리하고 기기 토큰을 관리.
즉, 로그인한 사용자의 알림을 처리하고, PostgreSQL과 Redis 작업을 각각 Repository에 요청

또한, FCM 발송의 전체 과정을 관리
repository.py 에서 DB,Redis 데이터 조회와 저장을하고
fcm.py 에서 Firebase에 실제 발송 요청을 진행하면
service.py(현재파일)에서 발송 대상 확인, 실행 순서, 실패,재시도 결정을 진행한다.

파일 흐름
1. Router가 JWT로 확인한 사용자 ID를 전달.
2. PostgreSQL에서는 본인 알림 목록 조회·읽음 처리를 실행.
3. Redis에서는 앱 설치 단위 FCM 토큰 등록·갱신·해제를 실행.
4. 결과는 Schema로 검증해서 반환하고, Redis 오류는 HTTP 503으로 구분.
5. 기관 전달 COMMIT 이후 알림 ID를 큐에 등록하고 Worker에서 권한·기기·설정을 재검사.
6. FCM 기기별 결과를 기록하고 실패한 기기만 제한적으로 재시도·복구.

주요 기능
- 요청 본문에서 user_id 또는 role을 받지 않습니다.
- 알림 조회·읽음 작업과 기기 토큰의 저장소를 분리.
"""

import logging
import math
import os
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from redis.exceptions import RedisError
from psycopg import OperationalError, InterfaceError
from psycopg.errors import QueryCanceled

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


log = logging.getLogger(__name__)
PUSH_MAX_AGE_SECONDS = 30 * 60
PUSH_MAX_ATTEMPTS = 4                      # 첫 처리 1회 + 재시도 최대 3회
_TERMINAL_STATES = {"FINISHED", "SKIPPED", "EXHAUSTED", "EXPIRED", "CONFIG_ERROR"}
_DEVICE_TERMINAL = {"ACCEPTED", "UNREGISTERED", "PERMANENT_ERROR", "CONFIG_ERROR", "CHANGED"}


# 활성화 기준 시각이 없으면 과거 알림을 임의로 발송하지 않습니다.
# Push 기능 활성화 기준 시각 확인
def _push_start_at() -> datetime:
    raw = os.environ.get("OCTV_PUSH_START_AT", "").strip()
    if not raw:
        raise ValueError("PUSH_START_AT_REQUIRED")
    start = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("PUSH_START_AT_TIMEZONE_REQUIRED")
    return start.astimezone(timezone.utc)


# 기존 Celery 앱에 알림 ID만 전달합니다. API 응답 지연을 줄이려고 발행 재시도는 짧게 제한.
# 알림 1건을 Celery 큐에 등록
def _enqueue_one_notification(notification_id: int) -> None:
    from ..workers import celery_app, send_notification_push

    # 기존 분석 Worker의 전역 설정은 유지하고, 이 발행 연결의 Redis 소켓만 짧게 제한합니다.
    transport_options = {
        **celery_app.conf.broker_transport_options,
        "socket_connect_timeout": 3, "socket_timeout": 3, "retry_on_timeout": False,
    }
    with celery_app.connection_for_write(
        connect_timeout=3, transport_options=transport_options,
    ) as connection:
        send_notification_push.apply_async(
            args=[notification_id],
            queue="notifications",
            expires=PUSH_MAX_AGE_SECONDS,
            connection=connection,
            retry=True,
            retry_policy={"max_retries": 1, "interval_start": 0.2,
                          "interval_step": 0.3, "interval_max": 0.5},
        )


# agencies/service.py가 DB COMMIT 이후 호출. 큐 실패를 DB 저장 실패로 바꾸지 않습니다.
# 기관 전달 후 생성된 DB 알림 ID를 Redis/Celery에 등록
def enqueue_notification_pushes(notification_ids: list[int]) -> str:
    # 중복 알림 ID 제거
    ids = list(dict.fromkeys(notification_ids)) 
    if not ids:
        return "NO_NEW_NOTIFICATIONS"
    # Push 기능 ON/OFF 확인
    if os.environ.get("OCTV_PUSH_ENABLED", "0") != "1": 
        return "DISABLED"
    queued = 0
    for notification_id in ids:
        # 큐 등록 중 오류가 발생해도 처리
        try:
            _enqueue_one_notification(notification_id)
            queued += 1
        except Exception:
            # 발행 응답을 못 받았어도 큐에 들어갔을 수 있습니다. 재전달은 Worker가 중복 검사.
            log.warning("push_enqueue_unconfirmed notification_id=%s", notification_id)
            break
    if queued == len(ids):
        return "QUEUED"
    return "PARTIALLY_QUEUED" if queued else "QUEUE_UNCONFIRMED"


# DB 저장 시각은 기존 UTC 정책을 적용하고, 타임존이 있다면 UTC로 맞춥니다.
def _created_at_utc(row: dict) -> datetime:
    value = row["created_at"]
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


# Push OFF는 DB 알림을 삭제하지 않으며, 완료·기관 변경·비활성 사용자는 늦게 발송하지 않습니다.
"""
발송하지 않아야 할 이유 검사
- 해당 알림이나 현재 기관 관계가 유효하지 않음
- 사용자가 비활성 상태이거나 발송 대상 조건에 맞지 않음
- 사용자 Push OFF 로 설정함
- Push 활성화 이전에 생성된 알림임
- 알림 생성 후 30분이 지남
"""
def _skip_reason(row: dict | None, start_at: datetime, now: datetime) -> str | None:
    if row is None:
        return "NOT_FOUND_OR_RELATION_CHANGED"
    if row.get("eligible") is not True:
        return "NOT_ELIGIBLE"
    if row.get("notification_enabled") is not True:
        return "USER_PUSH_OFF"
    created = _created_at_utc(row)
    if created < start_at:
        return "BEFORE_PUSH_START"
    if created > now + timedelta(seconds=30):
        return "INVALID_FUTURE_TIMESTAMP"
    if (now - created).total_seconds() >= PUSH_MAX_AGE_SECONDS:
        return "MESSAGE_EXPIRED"
    return None


# Task 로그/반환값에는 알림 ID, 상태, 개수, 고정 사유 코드만 포함.
def _push_summary(notification_id: int, state: dict) -> dict:
    results = list(state.get("results", {}).values())
    summary = {
        "notification_id": notification_id,
        "status": state["status"],
        "attempts": int(state.get("attempts", 0)),
        "accepted_count": sum(item["status"] == "ACCEPTED" for item in results),
        "failed_count": sum(item["status"] in {"UNREGISTERED", "PERMANENT_ERROR", "CONFIG_ERROR"}
                            for item in results),
        "changed_count": sum(item["status"] == "CHANGED" for item in results),
        "reason": state.get("reason", ""),
    }
    if state["status"] == "WAITING":
        summary["retry_in"] = max(1, math.ceil(float(state["next_attempt_at"]) - time.time()))
    return summary


# 명시적 생략·종료 결과를 기록해서 Beat가 같은 알림을 반복 발송하지 않게 합니다.
def _finish_push(client, lease, notification_id: int, state: dict, status: str, reason: str) -> dict:
    state.update(status=status, reason=reason, next_attempt_at=0)
    repository.save_push_state(client, notification_id, state, lease)
    log.info("push_processed notification_id=%s status=%s reason=%s", notification_id, status, reason)
    return _push_summary(notification_id, state)


# 기본 60/120/240초에 분산 지연을 더하되 FCM의 더 긴 Retry-After를 먼저 존중.
# 실패 시 재시도 시간 계산
def _plan_retry(state: dict, deadline: float, retry_after: int = 0) -> None:
    if state["attempts"] >= PUSH_MAX_ATTEMPTS:
        state.update(status="EXHAUSTED", reason="ATTEMPT_LIMIT", next_attempt_at=0)
        return
    delay = max(60 * 2 ** (state["attempts"] - 1) + random.randint(0, 15), retry_after)
    next_at = time.time() + delay
    if next_at >= deadline:
        # 허용 시간보다 긴 Retry-After를 짧게 잘라서 일찍 재시도하지 않습니다.
        state.update(status="EXPIRED", reason="RETRY_OUTSIDE_DELIVERY_WINDOW", next_attempt_at=0)
    else:
        state.update(status="WAITING", next_attempt_at=next_at)


# 알림 한 건에 대해 DB를 새로 조회. 네트워크 발송 전 연결은 닫힙니다.
def _read_push_notification(notification_id: int) -> dict | None:
    with get_connection() as connection:
        return repository.find_push_notification(connection, notification_id)


# 잠금 안에서 상태·대상·현재 기기를 검사하고, 실패한 기기만 FCM으로 다시 보냅니다.
"""
실제 발송 전 과정을 관리
1. Redis 발송 기록 확인 (이미 처리한 알림인지 확인)
2. DB 사용자,기관,Push 설정 확인 (현재 발송 가능한 대상인지 검사)
3. Redis 기기 토큰 확인 (현재 등록된 기기와 토큰인지 재검증)
4. fcm.send_to_devices() 호출 (Firebase 서버에 발송 요청)
5. 결과 기록 및 후속 처리 (성공 기록, 무효 토큰 정리, 일시 오류 재시도)
"""
def _dispatch_locked(client, lease, notification_id: int, start_at: datetime) -> dict:
    state = repository.load_push_state(client, notification_id) or {
        "version": 1, "status": "READY", "attempts": 0,
        "targets": None, "results": {}, "next_attempt_at": 0,
    }
    if state["status"] in _TERMINAL_STATES:
        return _push_summary(notification_id, state)
    if float(state.get("next_attempt_at", 0)) > time.time():
        return _push_summary(notification_id, state)

    row = _read_push_notification(notification_id)
    reason = _skip_reason(row, start_at, datetime.now(timezone.utc))
    if reason:
        return _finish_push(client, lease, notification_id, state, "SKIPPED", reason)
    user_id = int(row["user_id"])
    if "user_id" in state and state["user_id"] != user_id:
        return _finish_push(client, lease, notification_id, state, "SKIPPED", "TARGET_USER_CHANGED")
    state["user_id"] = user_id
    deadline = _created_at_utc(row).timestamp() + PUSH_MAX_AGE_SECONDS
    if int(state["attempts"]) >= PUSH_MAX_ATTEMPTS:
        return _finish_push(client, lease, notification_id, state, "EXHAUSTED", "ATTEMPT_LIMIT")

    if state["targets"] is None:
        snapshots = repository.list_device_snapshots(client, user_id)
        if not snapshots:
            # 등록 지연은 제한적으로 기다립니다. 역인덱스 없는 과거 토큰은 추정해서 쓰지 않습니다.
            state["attempts"] += 1
            state["reason"] = "NO_CURRENT_DEVICE"
            _plan_retry(state, deadline)
            repository.save_push_state(client, notification_id, state, lease)
            return _push_summary(notification_id, state)
        state["targets"] = snapshots
        # 첫 발송 후보를 고정해 재시도 도중 로그인한 다른 기기로 과거 알림을 퍼뜨리지 않습니다.
        repository.save_push_state(client, notification_id, state, lease)

    # 스냅샷 저장 중 기관/설정이 바뀔 수 있어 DB를 재확인한 다음 현재 토큰을 읽습니다.
    row = _read_push_notification(notification_id)
    reason = _skip_reason(row, start_at, datetime.now(timezone.utc))
    if reason or int(row["user_id"]) != user_id:
        return _finish_push(client, lease, notification_id, state, "SKIPPED", reason or "TARGET_USER_CHANGED")

    current: list[tuple[dict, str]] = []
    for snapshot in state["targets"]:
        previous = state["results"].get(snapshot["token_hash"], {})
        if previous.get("status") in _DEVICE_TERMINAL:
            continue
        token = repository.current_snapshot_token(client, user_id, snapshot)
        if token:
            current.append((snapshot, token))
        else:
            state["results"][snapshot["token_hash"]] = {
                "status": "CHANGED", "code": "REGISTRATION_CHANGED_OR_EXPIRED",
            }
    if not current:
        return _finish_push(client, lease, notification_id, state, "FINISHED", "NO_PENDING_TARGETS")

    lease.ensure_owned()
    if os.environ.get("OCTV_PUSH_ENABLED", "0") != "1":
        return {"notification_id": notification_id, "status": "DISABLED"}
    ttl = int(deadline - time.time())
    if ttl <= 0:
        return _finish_push(client, lease, notification_id, state, "EXPIRED", "MESSAGE_EXPIRED")

    # FCM 호출 전에 시도 횟수를 저장합니다. 작업 재전달/복구로 횟수가 0으로 돌아가지 않습니다.
    state.update(status="SENDING", attempts=int(state["attempts"]) + 1, next_attempt_at=0)
    repository.save_push_state(client, notification_id, state, lease)
    from .fcm import send_to_devices

    outcomes = send_to_devices(                             # 중요 핵심 코드
        notification_id,                                    # DB 알림 번호
        int(row["incident_id"]),                            # 사건 번호
        [token for _, token in current],                    # 현재 발송 가능한 기기, 토큰 (리스트 컴프리헨션 문법으로 기기 정보와 토큰이 묶인 데이터에서 토큰만 추출해 리스트로 만듦. 이미 처리한 토큰은 재시도 대상에서 재외해 중복 발송도 줄여준다.)
        ttl,                                                # 알림 유효 시간
    )
    retry_after = 0
    invalid_snapshots: list[dict] = []
    for (snapshot, _), outcome in zip(current, outcomes, strict=True):
        state["results"][snapshot["token_hash"]] = {"status": outcome.status, "code": outcome.code}
        if outcome.status == "RETRY":
            retry_after = max(retry_after, outcome.retry_after_seconds)
        elif outcome.status == "UNREGISTERED":
            invalid_snapshots.append(snapshot)
        elif outcome.status in {"CONFIG_ERROR", "PERMANENT_ERROR"}:
            log.warning("push_fcm_rejected notification_id=%s code=%s", notification_id, outcome.code)
    pending_retry = any(item["status"] == "RETRY" for item in state["results"].values())
    if pending_retry:
        state["reason"] = "FCM_TEMPORARY_ERROR"
        _plan_retry(state, deadline, retry_after)
    else:
        state.update(status="FINISHED", reason="ALL_TARGETS_PROCESSED", next_attempt_at=0)

    # 접수된 기기를 먼저 기록한 뒤 토큰을 정리합니다. 정리 실패 때문에 성공 기기를 재발송하지 않습니다.
    repository.save_push_state(client, notification_id, state, lease)
    for snapshot in invalid_snapshots:
        repository.drop_invalid_snapshot(client, user_id, snapshot)
    summary = _push_summary(notification_id, state)
    log.info("push_processed notification_id=%s status=%s accepted=%s",
             notification_id, summary["status"], summary["accepted_count"])
    return summary


# Worker가 호출하는 진입 함수. 원문 DB/Redis/FCM 예외를 Celery 로그에 넘기지 않습니다.
"""
주요 역할
1. Push 기능과 필수 환경설정 확인
2. Redis 잠금 획득 후 _dispatch_locked() 실행
3. 저장소 오류나 잠금 오류 발생 시 안전한 결과 반환
여기서 Redis 잠금은 같은 알림을 Worker 여러 개가 동시에 발송하지 않도록 제한하는 기능
"""
def dispatch_notification_push(notification_id: int) -> dict:
    if type(notification_id) is not int or not 0 < notification_id <= 9223372036854775807:
        return {"status": "INVALID_NOTIFICATION_ID"}
    if os.environ.get("OCTV_PUSH_ENABLED", "0") != "1":
        return {"notification_id": notification_id, "status": "DISABLED"}
    try:
        start_at = _push_start_at()
    except (TypeError, ValueError, OverflowError):
        log.error("push_configuration_error code=PUSH_START_AT")
        return {"notification_id": notification_id, "status": "CONFIG_ERROR", "reason": "PUSH_START_AT"}
    try:
        with repository._redis_client() as client:
            with repository.push_lease(client, str(notification_id)) as lease:
                if lease is None:
                    return {"notification_id": notification_id, "status": "ALREADY_RUNNING"}
                return _dispatch_locked(client, lease, notification_id, start_at)
    except (RedisError, OperationalError, InterfaceError, QueryCanceled, OSError, repository.PushLeaseLost):
        # Redis에서 안전한 상태 확인이 불가능하면 FCM을 먼저 보내지 않습니다.
        log.warning("push_storage_or_lease_retry notification_id=%s", notification_id)
        return {"notification_id": notification_id, "status": "RETRY", "retry_in": 60}
    except Exception:
        # 코드/상태 파손을 자동으로 초기화해 재발송하지 않습니다. 원문 예외를 숨긴 고정 코드만 남깁니다.
        log.error("push_internal_error notification_id=%s code=PUSH_STATE_OR_CONFIGURATION", notification_id)
        return {"notification_id": notification_id, "status": "ERROR", "reason": "PUSH_STATE_OR_CONFIGURATION"}


# 최근 DB 알림과 Redis 상태를 대조합니다. 읽음 시각을 발송 완료 표시로 사용하지 않습니다.
"""
DB에 알림은 있지만 발송 처리가 누락됐거나 재시도가 필요한 알림을 다시 확인하는 함수
OCTV 에서의 예시 
1. 105번 DB 알림 저장 성공
2. Redis 큐 등록 중 장애
3. DB 알림은 그대로 존재
4. Celery Beat가 복구 작업 실행
5. 최근 DB 알림과 Redis 처리 기록 비교
6. 복구 가능한 알림만 다시 큐 등록

Celery Beat 이란?
Celery Worker가 작업을 실행하는 역할이라면, 
Celery Beat는 정해진 시간마다 작업을 등록하는 역할
Beat와 Worker가 함께 실행돼야 자동 복구가 동작한다.
"""
def recover_notification_pushes() -> dict:
    if (os.environ.get("OCTV_PUSH_ENABLED", "0") != "1"
            or os.environ.get("OCTV_PUSH_RECOVERY_ENABLED", "0") != "1"):
        return {"status": "DISABLED"}
    try:
        start_at = _push_start_at()
        now = datetime.now(timezone.utc)
        since = max(start_at, now - timedelta(seconds=PUSH_MAX_AGE_SECONDS))
        if since > now:
            return {"status": "NOT_STARTED"}
        scanned = queued = 0
        started = time.monotonic()
        with repository._redis_client() as client:
            with repository.push_lease(client, "recovery") as lease:
                if lease is None:
                    return {"status": "ALREADY_RUNNING"}
                cursor = repository.load_recovery_cursor(client)
                # 최대 1,000개 또는 약 90초 단위로 끊고 다음 Beat가 이어서 순회합니다.
                for _ in range(10):
                    lease.ensure_owned()
                    with get_connection() as connection:
                        ids = repository.list_push_recovery_ids(
                            connection, since.replace(tzinfo=None), now.replace(tzinfo=None), cursor, 100,
                        )
                    if not ids:
                        repository.save_recovery_cursor(client, 0, lease)
                        return {"status": "FINISHED", "scanned": scanned, "queued": queued}
                    for notification_id in ids:
                        if time.monotonic() - started >= 90:
                            repository.save_recovery_cursor(client, cursor, lease)
                            return {"status": "CONTINUE_NEXT_TICK", "scanned": scanned, "queued": queued}
                        try:
                            state = repository.load_push_state(client, notification_id)
                        except (ValueError, TypeError):
                            # 손상된 기록을 없는 기록으로 취급하면 중복 발송되므로 건너뜁니다.
                            log.error("push_recovery_invalid_state notification_id=%s", notification_id)
                            cursor = notification_id
                            scanned += 1
                            continue
                        if (state.get("status") not in _TERMINAL_STATES
                                and float(state.get("next_attempt_at", 0)) <= time.time()
                                and not repository.push_is_running(client, notification_id)
                                and repository.reserve_recovery_enqueue(client, notification_id)):
                            # DB 알림 생성은 하지 않습니다. 기존 ID의 누락/미완료 작업만 다시 등록합니다.
                            _enqueue_one_notification(notification_id)
                            queued += 1
                        cursor = notification_id
                        scanned += 1
                    repository.save_recovery_cursor(client, cursor, lease)
                    if len(ids) < 100:
                        # COMMIT 순서가 ID 순서와 다를 수 있어 매 순회 종료 후 처음부터 다시 확인합니다.
                        repository.save_recovery_cursor(client, 0, lease)
                        return {"status": "FINISHED", "scanned": scanned, "queued": queued}
                return {"status": "CONTINUE_NEXT_TICK", "scanned": scanned, "queued": queued}
    except Exception:
        log.warning("push_recovery_unconfirmed code=STORAGE_QUEUE_OR_CONFIGURATION")
        return {"status": "UNCONFIRMED", "reason": "STORAGE_QUEUE_OR_CONFIGURATION"}
