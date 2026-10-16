"""
본인 사건 전달 알림은 PostgreSQL, 기기별 FCM 토큰은 기존 Redis에 저장 및 관리 하는 파일

파일 흐름
1. 로그인 사용자 ID로 본인 알림 목록을 조회하거나 한 건을 읽음 처리.
2. 기기 UUID4의 해시를 Redis 키로 사용해 FCM 토큰을 보관.
3. 기기 재등록은 이전 토큰·이전 계정 연결을 원자적으로 교체.
4. 해당 계정 소유 기기만 해제.
5. 토큰 역인덱스로 중복 UUID·계정 변경을 정리하고 발송 직전 소유 관계를 확인.
6. DB 발송 대상 조회, Redis 중복 방지·재시도 기록, 제한된 누락 복구를 지원.

주요 기능
- 기존 Redis AOF/볼륨을 이용하지만 만료·데이터 소실 시 앱이 재등록해야 한다.
- Redis 토큰 원문은 API 응답과 로그로 반환하지 않습니다.
"""

import hashlib
import os
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

from redis import Redis

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.

# 서로 다른 Redis 사용처(Celery 등)와 충돌하지 않도록 키 공간을 구분합니다.
_DEVICE_PREFIX = "octv:push:device:v1:"     # 기기별 정보를 저장할 Redis 키의 시작 부분
_USER_PREFIX = "octv:push:user:v1:"         # 사용자별 기기 목록을 저장할 키의 시작 부분
_TOKEN_TTL_SECONDS = 90 * 24 * 60 * 60      # 마지막 등록 갱신 후 90일 만료
_MAX_USER_DEVICES = 10                      # 사용자당 최대 10대 등록
_TOKEN_PREFIX = "octv:push:token:v1:"       # FCM 토큰 해시 → 현재 기기 소유 관계
_STATE_PREFIX = "octv:push:state:v1:"       # 알림별 시도 횟수·기기별 결과 (토큰 원문 없음)
_LOCK_PREFIX = "octv:push:lock:v1:"
_STATE_TTL_SECONDS = 7 * 24 * 60 * 60       # 복구 기간(30분)보다 긴 7일 보존
_LOCK_TTL_SECONDS = 300                     # 실행 중에는 30초마다 소유 잠금만 연장

# 하나의 Redis 스크립트로 중복·계정 교체·기기 토큰 갱신을 모두 처리합니다.
_REGISTER_DEVICE_LUA = """
local device_key = KEYS[1]
local user_index = KEYS[2]
local token_key = KEYS[3]
local user_id = ARGV[1]
local device_hash = ARGV[4]
local device_prefix = ARGV[7]
local user_prefix = ARGV[8]
local token_hash = ARGV[10]
local token_prefix = ARGV[11]
local registration_id = ARGV[12]

-- 만료되었거나 다른 사용자에게 옮겨진 기기의 오래된 인덱스를 정리합니다.
for _, member in ipairs(redis.call('SMEMBERS', user_index)) do
    local owner = redis.call('HGET', device_prefix .. member, 'user_id')
    if not owner or owner ~= user_id then
        redis.call('SREM', user_index, member)
    end
end

-- 다른 UUID의 동일 토큰이 현재 사용자 소유라면 교체로 줄어드는 한 대를 계산합니다.
local displaced_hash = redis.call('HGET', token_key, 'device_hash')
local displaced_key = displaced_hash and (device_prefix .. displaced_hash) or nil
local displaced_owner = displaced_key and redis.call('HGET', displaced_key, 'user_id') or nil
local can_displace = displaced_key and displaced_hash ~= device_hash
    and redis.call('HGET', displaced_key, 'fcm_token') == ARGV[2]
local effective_count = redis.call('SCARD', user_index)
if can_displace and displaced_owner == user_id
   and redis.call('SISMEMBER', user_index, displaced_hash) == 1 then
    effective_count = effective_count - 1
end

-- 새 기기는 사용자당 최대 10대까지만 허용합니다. 실패하면 기존 등록은 유지합니다.
if redis.call('SISMEMBER', user_index, device_hash) == 0
   and effective_count >= tonumber(ARGV[9]) then
    return 0
end

-- 같은 앱 설치에서 다른 계정으로 로그인하면 이전 계정 인덱스를 제거합니다.
local old_user_id = redis.call('HGET', device_key, 'user_id')
if old_user_id and old_user_id ~= user_id then
    redis.call('SREM', user_prefix .. old_user_id, device_hash)
end

-- 토큰 갱신 시 이 기기가 소유한 이전 토큰 역인덱스만 제거합니다.
local old_token_hash = redis.call('HGET', device_key, 'token_hash')
if old_token_hash and old_token_hash ~= token_hash then
    local old_token_key = token_prefix .. old_token_hash
    if redis.call('HGET', old_token_key, 'device_hash') == device_hash then
        redis.call('DEL', old_token_key)
    end
end

-- 다른 UUID에 같은 FCM 토큰이 있으면 이전 기기·사용자 연결을 함께 정리합니다.
if can_displace then
    if displaced_owner then
        redis.call('SREM', user_prefix .. displaced_owner, displaced_hash)
    end
    redis.call('DEL', displaced_key)
end

-- 같은 기기를 다시 등록하면 이전 FCM 토큰을 덮어써 토큰 갱신을 처리합니다.
redis.call('HSET', device_key,
    'user_id', user_id,
    'fcm_token', ARGV[2],
    'platform', ARGV[3],
    'updated_at', ARGV[6],
    'token_hash', token_hash,
    'registration_id', registration_id)
redis.call('EXPIRE', device_key, tonumber(ARGV[5]))
redis.call('SADD', user_index, device_hash)
redis.call('EXPIRE', user_index, tonumber(ARGV[5]))
redis.call('HSET', token_key,
    'device_hash', device_hash,
    'user_id', user_id,
    'registration_id', registration_id)
redis.call('EXPIRE', token_key, tonumber(ARGV[5]))
return 1
"""

# 로그아웃 또는 기기 해제 시 현재 사용자 소유 토큰만 삭제합니다.
_REMOVE_DEVICE_LUA = """
if redis.call('HGET', KEYS[1], 'user_id') ~= ARGV[1] then
    return 0
end
local token_hash = redis.call('HGET', KEYS[1], 'token_hash')
if token_hash then
    local token_key = ARGV[3] .. token_hash
    if redis.call('HGET', token_key, 'device_hash') == ARGV[2]
       and redis.call('HGET', token_key, 'user_id') == ARGV[1]
       and redis.call('HGET', token_key, 'registration_id')
           == redis.call('HGET', KEYS[1], 'registration_id') then
        redis.call('DEL', token_key)
    end
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
    # sha256(): 토큰을 일정한 길이의 해시값으로 변환해 관리하는 함수
    token_hash = hashlib.sha256(fcm_token.encode("utf-8")).hexdigest()
    # 시간 문자열 대신 등록마다 다른 버전으로 늦게 도착한 무효 토큰 응답을 구분.
    registration_id = uuid4().hex

    # EVAL 작업은 Redis에서 원자적으로 실행되므로 동시 계정 변경의 중간 상태를 막습니다.
    with _redis_client() as client:
        result = client.eval(
            _REGISTER_DEVICE_LUA, 3, device_key, user_index, _TOKEN_PREFIX + token_hash,
            str(user_id), fcm_token, platform, device_hash,
            _TOKEN_TTL_SECONDS, now, _DEVICE_PREFIX, _USER_PREFIX,
            _MAX_USER_DEVICES, token_hash, _TOKEN_PREFIX, registration_id,
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
            str(user_id), device_hash, _TOKEN_PREFIX,
        )
    return int(result) == 1


# 현재 기기·역인덱스가 함께 일치하는 항목만 가져옵니다.
_LIST_SNAPSHOTS_LUA = """
local result = {}
for _, member in ipairs(redis.call('SMEMBERS', KEYS[1])) do
    local device_key = ARGV[2] .. member
    local owner = redis.call('HGET', device_key, 'user_id')
    if not owner or owner ~= ARGV[1] then
        redis.call('SREM', KEYS[1], member)
    else
        local token_hash = redis.call('HGET', device_key, 'token_hash')
        local version = redis.call('HGET', device_key, 'registration_id')
        if token_hash and version then
            local token_key = ARGV[3] .. token_hash
            if redis.call('HGET', token_key, 'device_hash') == member
               and redis.call('HGET', token_key, 'user_id') == owner
               and redis.call('HGET', token_key, 'registration_id') == version then
                table.insert(result, {member, token_hash, version})
            end
        end
    end
end
return result
"""

# 발송 직전 등록 버전까지 다시 확인합니다. 계정/토큰이 바뀌었다면 원문 토큰을 반환하지 않습니다.
_CURRENT_TOKEN_LUA = """
if redis.call('HGET', KEYS[1], 'user_id') ~= ARGV[1]
   or redis.call('HGET', KEYS[1], 'token_hash') ~= ARGV[3]
   or redis.call('HGET', KEYS[1], 'registration_id') ~= ARGV[4]
   or redis.call('HGET', KEYS[2], 'device_hash') ~= ARGV[2]
   or redis.call('HGET', KEYS[2], 'user_id') ~= ARGV[1]
   or redis.call('HGET', KEYS[2], 'registration_id') ~= ARGV[4] then
    return false
end
return redis.call('HGET', KEYS[1], 'fcm_token')
"""

# 오래된 FCM 실패 응답으로 새 등록 토큰을 삭제하지 않도록 조건부로 삭제.
_DROP_SNAPSHOT_LUA = """
if redis.call('HGET', KEYS[1], 'user_id') ~= ARGV[1]
   or redis.call('HGET', KEYS[1], 'token_hash') ~= ARGV[3]
   or redis.call('HGET', KEYS[1], 'registration_id') ~= ARGV[4] then
    return 0
end
if redis.call('HGET', KEYS[3], 'device_hash') == ARGV[2]
   and redis.call('HGET', KEYS[3], 'user_id') == ARGV[1]
   and redis.call('HGET', KEYS[3], 'registration_id') == ARGV[4] then
    redis.call('DEL', KEYS[3])
end
redis.call('DEL', KEYS[1])
redis.call('SREM', KEYS[2], ARGV[2])
return 1
"""

# 잠금 소유권을 확인한 작업만 TTL 연장·해제를 수행.
_RENEW_LOCK_LUA = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
return redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
"""
_RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""

# 잠금이 만료된 옛 Worker가 새 Worker의 결과를 덮어쓰지 못하게 합니다.
_SAVE_OWNED_LUA = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], ARGV[2], 'EX', tonumber(ARGV[3]))
return 1
"""


# 발송 직전 DB 알림·현재 사용자·기관 전달 관계를 한 번에 확인.
def find_push_notification(connection, notification_id: int) -> dict | None:
    # FCM 호출 전에 연결을 닫습니다. 외부 네트워크 동안 DB 트랜잭션을 잡고 있지 않습니다.
    connection.execute("SET LOCAL statement_timeout = '5000ms'")
    return connection.execute(
        """
        SELECT n.id AS notification_id, n.incidents_id AS incident_id,
               n.user_id, n.agency_id, n.created_at, u.notification_enabled,
               (u.is_active = TRUE
                AND u.role IN ('AGENCY_STAFF', 'RESPONDER')
                AND u.agency_id = n.agency_id
                AND ar.recommendation_status = 'DELIVERED'
                AND i.status IN ('CONFIRMED', 'SENT')) AS eligible
        FROM notifications AS n
        JOIN users AS u ON u.id = n.user_id
        JOIN incident_agency_recommendations AS ar
          ON ar.id = n.agency_recommendation_id
         AND ar.agency_id = n.agency_id
         AND ar.incident_id = n.incidents_id
        JOIN incidents AS i ON i.id = n.incidents_id
        WHERE n.id = %s
        """,
        (notification_id,),
    ).fetchone()


# 최근 DB 알림을 ID 기준으로 나누어 조회. 이미 발송됐는지는 Redis에서 따로 확인.
def list_push_recovery_ids(
    connection, since: datetime, until: datetime, after_id: int = 0, limit: int = 100,
) -> list[int]:
    connection.execute("SET LOCAL statement_timeout = '5000ms'")
    rows = connection.execute(
        """
        SELECT id FROM notifications
        WHERE created_at >= %s AND created_at <= %s AND id > %s
        ORDER BY id
        LIMIT %s
        """,
        (since, until, after_id, limit),
    ).fetchall()
    return [int(row["id"]) for row in rows]


# 토큰 원문 없이 현재 등록의 스냅샷을 만듭니다. 재시도 중 새 로그인 기기는 추가하지 않습니다.
def list_device_snapshots(client: Redis, user_id: int) -> list[dict]:
    rows = client.eval(
        _LIST_SNAPSHOTS_LUA, 1, _USER_PREFIX + str(user_id),
        str(user_id), _DEVICE_PREFIX, _TOKEN_PREFIX,
    )
    unique: dict[str, dict] = {}
    for device_hash, token_hash, registration_id in rows:
        unique.setdefault(token_hash, {
            "device_hash": device_hash,
            "token_hash": token_hash,
            "registration_id": registration_id,
        })
    return list(unique.values())[:_MAX_USER_DEVICES]


# 사용자·기기·토큰·등록 버전이 현재도 같을 때만 발송에 쓸 원문을 얻습니다.
def current_snapshot_token(client: Redis, user_id: int, snapshot: dict) -> str | None:
    result = client.eval(
        _CURRENT_TOKEN_LUA, 2,
        _DEVICE_PREFIX + snapshot["device_hash"], _TOKEN_PREFIX + snapshot["token_hash"],
        str(user_id), snapshot["device_hash"], snapshot["token_hash"], snapshot["registration_id"],
    )
    return str(result) if result else None


# UNREGISTERED가 확인된 과거 등록과 현재 등록이 같을 때만 삭제합니다.
def drop_invalid_snapshot(client: Redis, user_id: int, snapshot: dict) -> bool:
    result = client.eval(
        _DROP_SNAPSHOT_LUA, 3,
        _DEVICE_PREFIX + snapshot["device_hash"], _USER_PREFIX + str(user_id),
        _TOKEN_PREFIX + snapshot["token_hash"],
        str(user_id), snapshot["device_hash"], snapshot["token_hash"], snapshot["registration_id"],
    )
    return int(result) == 1


# 잠금을 잃은 작업은 추가 발송·결과 저장을 중단하도록 구분합니다.
class PushLeaseLost(RuntimeError):
    pass


# 네트워크 호출이 길어져도 자신이 소유한 Redis 잠금만 주기적으로 연장합니다.
class PushLease:
    # 토큰이 아닌 잠금 소유 난수를 만들고, 종료/소유권 상실 신호를 준비합니다.
    def __init__(self, client: Redis, scope: str):
        self.client = client
        self.key = _LOCK_PREFIX + scope
        self.owner = uuid4().hex
        self.stopped = threading.Event()
        self.lost = threading.Event()
        self.thread: threading.Thread | None = None

    # SET NX EX로 같은 알림의 동시 처리를 제한합니다.
    def acquire(self) -> bool:
        acquired = self.client.set(self.key, self.owner, nx=True, ex=_LOCK_TTL_SECONDS)
        if not acquired:
            return False
        self.thread = threading.Thread(target=self._renew, daemon=True, name="octv-push-lease")
        self.thread.start()
        return True

    # 잠금 연장에 실패하면 소유권이 불확실하므로 추가 작업을 막습니다.
    def _renew(self) -> None:
        while not self.stopped.wait(30):
            try:
                renewed = self.client.eval(
                    _RENEW_LOCK_LUA, 1, self.key, self.owner, _LOCK_TTL_SECONDS,
                )
                if int(renewed) == 1:
                    continue
            except Exception:
                pass
            self.lost.set()
            return

    # 발송 직전 현재 잠금 소유권도 확인합니다.
    def ensure_owned(self) -> None:
        if self.lost.is_set() or self.client.get(self.key) != self.owner:
            self.lost.set()
            raise PushLeaseLost("PUSH_LEASE_LOST")

    # 연장 스레드를 먼저 종료하고, 자신의 잠금인 경우에만 삭제합니다.
    def close(self) -> None:
        self.stopped.set()
        if self.thread is not None:
            self.thread.join(timeout=4)
        try:
            self.client.eval(_RELEASE_LOCK_LUA, 1, self.key, self.owner)
        except Exception:
            # Redis 장애 시 다른 잠금을 지우지 않고 기존 TTL 만료에 맡깁니다.
            pass


# 성공·실패 어느 경로에서도 잠금 정리를 수행합니다.
@contextmanager
def push_lease(client: Redis, scope: str):
    lease = PushLease(client, scope)
    acquired = lease.acquire()
    try:
        yield lease if acquired else None
    finally:
        if acquired:
            lease.close()


# JSON 상태에는 토큰 원문을 저장하지 않습니다. 파손된 상태를 빈 상태로 간주해 재발송하지 않습니다.
def load_push_state(client: Redis, notification_id: int) -> dict:
    raw = client.get(_STATE_PREFIX + str(notification_id))
    if raw is None:
        return {}
    state = json.loads(raw)
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ValueError("PUSH_STATE_INVALID")
    return state


# 잠금을 가진 현재 Worker만 7일 TTL의 발송 기록을 저장합니다.
def save_push_state(client: Redis, notification_id: int, state: dict, lease: PushLease) -> None:
    lease.ensure_owned()
    payload = json.dumps(state, ensure_ascii=True, separators=(",", ":"))
    result = client.eval(
        _SAVE_OWNED_LUA, 2, lease.key, _STATE_PREFIX + str(notification_id),
        lease.owner, payload, _STATE_TTL_SECONDS,
    )
    if int(result) != 1:
        raise PushLeaseLost("PUSH_LEASE_LOST")


# 복구 순회 위치를 기억해 조회량 상한에 걸려도 같은 앞부분만 반복하지 않습니다.
def load_recovery_cursor(client: Redis) -> int:
    return int(client.get("octv:push:recovery:cursor:v1") or 0)


# 다음 복구가 이어서 볼 ID를 저장하되 한 바퀴 끝나면 0부터 다시 확인합니다.
def save_recovery_cursor(client: Redis, cursor: int, lease: PushLease) -> None:
    result = client.eval(
        _SAVE_OWNED_LUA, 2, lease.key, "octv:push:recovery:cursor:v1",
        lease.owner, str(cursor), _STATE_TTL_SECONDS,
    )
    if int(result) != 1:
        raise PushLeaseLost("PUSH_LEASE_LOST")


# 실행 중인 알림은 복구 스캐너에서 다시 큐에 넣지 않습니다.
def push_is_running(client: Redis, notification_id: int) -> bool:
    return bool(client.exists(_LOCK_PREFIX + str(notification_id)))


# 아직 Worker가 가져가지 않은 복구 작업의 반복 큐 등록을 2분 동안 줄입니다.
def reserve_recovery_enqueue(client: Redis, notification_id: int) -> bool:
    return bool(client.set(
        "octv:push:recovery:queued:v1:" + str(notification_id), "1", nx=True, ex=120,
    ))
