"""
본인 사건 전달 알림은 PostgreSQL, 기기별 FCM 토큰은 기존 Redis에 저장 및 관리 하는 파일

파일 흐름
1. 로그인 사용자 ID로 본인 알림 목록을 조회하거나 한 건을 읽음 처리.
2. 기기 UUID4의 해시를 Redis 키로 사용해 FCM 토큰을 보관.
3. 기기 재등록은 이전 토큰·이전 계정 연결을 원자적으로 교체.
4. 해당 계정 소유 기기만 해제.

주요 기능
- 기존 Redis AOF/볼륨을 이용하지만 만료·데이터 소실 시 앱이 재등록해야 한다.
- Redis 토큰 원문은 API 응답과 로그로 반환하지 않습니다.
"""

import hashlib
import os
from datetime import datetime, timezone
from uuid import UUID

from redis import Redis

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.

# 서로 다른 Redis 사용처(Celery 등)와 충돌하지 않도록 키 공간을 구분합니다.
_DEVICE_PREFIX = "octv:push:device:v1:"     # 기기별 정보를 저장할 Redis 키의 시작 부분
_USER_PREFIX = "octv:push:user:v1:"         # 사용자별 기기 목록을 저장할 키의 시작 부분
_TOKEN_TTL_SECONDS = 90 * 24 * 60 * 60      # 마지막 등록 갱신 후 90일 만료
_MAX_USER_DEVICES = 10                      # 사용자당 최대 10대 등록

# 하나의 Redis 스크립트로 중복·계정 교체·기기 토큰 갱신을 모두 처리합니다.
_REGISTER_DEVICE_LUA = """
local device_key = KEYS[1]
local user_index = KEYS[2]
local user_id = ARGV[1]
local device_hash = ARGV[4]
local device_prefix = ARGV[7]
local user_prefix = ARGV[8]

-- 만료되었거나 다른 사용자에게 옮겨진 기기의 오래된 인덱스를 정리합니다.
for _, member in ipairs(redis.call('SMEMBERS', user_index)) do
    local owner = redis.call('HGET', device_prefix .. member, 'user_id')
    if not owner or owner ~= user_id then
        redis.call('SREM', user_index, member)
    end
end

-- 새 기기는 사용자당 최대 10대까지만 허용합니다.
if redis.call('SISMEMBER', user_index, device_hash) == 0
   and redis.call('SCARD', user_index) >= tonumber(ARGV[9]) then
    return 0
end

-- 같은 앱 설치에서 다른 계정으로 로그인하면 이전 계정 인덱스를 제거합니다.
local old_user_id = redis.call('HGET', device_key, 'user_id')
if old_user_id and old_user_id ~= user_id then
    redis.call('SREM', user_prefix .. old_user_id, device_hash)
end

-- 같은 기기를 다시 등록하면 이전 FCM 토큰을 덮어써 토큰 갱신을 처리합니다.
redis.call('HSET', device_key,
    'user_id', user_id,
    'fcm_token', ARGV[2],
    'platform', ARGV[3],
    'updated_at', ARGV[6])
redis.call('EXPIRE', device_key, tonumber(ARGV[5]))
redis.call('SADD', user_index, device_hash)
redis.call('EXPIRE', user_index, tonumber(ARGV[5]))
return 1
"""

# 로그아웃 또는 기기 해제 시 현재 사용자 소유 토큰만 삭제합니다.
_REMOVE_DEVICE_LUA = """
if redis.call('HGET', KEYS[1], 'user_id') ~= ARGV[1] then
    return 0
end
redis.call('DEL', KEYS[1])
redis.call('SREM', KEYS[2], ARGV[2])
return 1
"""


# 알림 목록은 현재도 같은 기관에 소속된 활성 사용자 자신의 행만 조회합니다.
def list_for_user(
    connection, 
    user_id: int,               # 로그인한 사용자 ID
    limit: int = 30,            # 한 번에 최대 30건 조회하는 기본값
    offset: int = 0,            # 몇 건을 건너뛰고 조회할지
    unread_only: bool = False   # 기본적으로 읽은 알림도 포함
) -> list[dict]:
    return connection.execute(
        """
        SELECT n.id, n.incidents_id AS incident_id, n.created_at, n.read_at
        FROM notifications AS n
        JOIN users AS u ON u.id = n.user_id
        WHERE n.user_id = %s
          AND u.is_active = TRUE
          AND u.role IN ('AGENCY_STAFF', 'RESPONDER')
          AND u.agency_id = n.agency_id
          AND (%s = FALSE OR n.read_at IS NULL)
        ORDER BY n.created_at DESC, n.id DESC
        LIMIT %s OFFSET %s
        """,
        (user_id, unread_only, limit, offset),
    ).fetchall()


# 알림 ID뿐 아니라 JWT의 user_id와 현재 기관 소속을 SQL에서 다시 검사.
# 로그인 사용자가 본인 알림을 읽었을 때 읽음 시간을 기록
def mark_read(
    connection, 
    notification_id: int, 
    user_id: int
) -> dict | None:
    # COALESCE: 여러 값 중 NULL이 아닌 첫 번째 값을 사용하는 SQL 함수.
    # 그렇기에 같은 알림을 여러번 눌러도 최초 읽음 시간을 유지할 수 있다
    return connection.execute(
        """
        UPDATE notifications AS n
        SET read_at = COALESCE(n.read_at, CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
        FROM users AS u
        WHERE n.id = %s
          AND n.user_id = %s
          AND u.id = n.user_id
          AND u.is_active = TRUE
          AND u.role IN ('AGENCY_STAFF', 'RESPONDER')
          AND u.agency_id = n.agency_id
        RETURNING n.id, n.incidents_id AS incident_id, n.created_at, n.read_at
        """,
        (notification_id, user_id),
    ).fetchone()


# 기기 UUID를 해시로 바꿔 Redis 키에 토큰 원문이나 기기 식별자를 노출하지 않습니다.
def _device_hash(device_id: UUID) -> str:
    return hashlib.sha256(str(device_id).encode("ascii")).hexdigest()


# 기존 OCTV Redis에 연결할 준비
# 기존 Celery와 동일한 OCTV_REDIS_URL을 사용하되 미설정 시 조용히 기본값을 사용하지 않습니다.
def _redis_client() -> Redis:
    url = os.environ.get("OCTV_REDIS_URL", "").strip()
    if not url:
        raise RuntimeError("OCTV_REDIS_URL_NOT_CONFIGURED")
    return Redis.from_url(
        url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3,
    )


# Redis Lua를 통해 기기별 토큰을 등록·갱신하며 계정 변경 시 이전 연결을 해제.
"""
왜 Lua를 사용하는지?
기존 계정 연결 제거 -> 새 사용자 연결 -> 토큰 갱신을 하나의 작업처럼 처리하기 위해. 
이를 원자적(Atomic) 처리라고 하는데, 
Redis가 해당 스크립트를 실행하는 동안 다른 명령이 중간에 끼어들지 못하도록 함 
참고로, 이 원자성은 Redis 내부 작업에 관한 것이며 PostgreSQL 작업까지 묶는다는 뜻은 아니다.
"""
def register_device_token(
    user_id: int, 
    device_id: UUID, 
    platform: str,
    fcm_token: str
) -> bool:
    device_hash = _device_hash(device_id)
    device_key = _DEVICE_PREFIX + device_hash
    user_index = _USER_PREFIX + str(user_id)
    now = datetime.now(timezone.utc).isoformat()

    # EVAL 작업은 Redis에서 원자적으로 실행되므로 동시 계정 변경의 중간 상태를 막습니다.
    with _redis_client() as client:
        result = client.eval(
            _REGISTER_DEVICE_LUA, 2, device_key, user_index,
            str(user_id), fcm_token, platform, device_hash,
            _TOKEN_TTL_SECONDS, now, _DEVICE_PREFIX, _USER_PREFIX,
            _MAX_USER_DEVICES,
        )
    return int(result) == 1


# 다른 사용자의 UUID를 전달하더라도 본인 소유가 아니면 아무것도 삭제하지 않습니다.
def remove_device_token(user_id: int, device_id: UUID) -> bool:
    device_hash = _device_hash(device_id)
    with _redis_client() as client:
        result = client.eval(
            _REMOVE_DEVICE_LUA, 2,
            _DEVICE_PREFIX + device_hash,
            _USER_PREFIX + str(user_id),
            str(user_id), device_hash,
        )
    return int(result) == 1
