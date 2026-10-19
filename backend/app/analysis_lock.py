"""Incident AI 분석 Celery Task의 중복 등록을 Redis Lock으로 제한합니다."""

import os
from pathlib import Path
from uuid import uuid4

import redis
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(
    PROJECT_ROOT / ".env"
)


ANALYSIS_LOCK_PREFIX = "octv:analysis:incident"

# Worker가 장시간 중단된 경우에도 Lock이 영구적으로 남지 않도록 TTL을 둡니다.
# 필요하면 .env에서 OCTV_ANALYSIS_LOCK_TTL_SEC로 조정할 수 있습니다.
ANALYSIS_LOCK_TTL_SEC = int(
    os.environ.get(
        "OCTV_ANALYSIS_LOCK_TTL_SEC",
        "21600",  # 기본 6시간
    )
)


# 내가 만든 Lock만 삭제하도록 token을 비교한 뒤 DEL 합니다.
_RELEASE_LOCK_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""


def _get_redis_client():
    return redis.Redis.from_url(
        os.environ["OCTV_REDIS_URL"],
        decode_responses=True,
    )


def _analysis_lock_key(
    incident_id: int,
) -> str:
    return (
        f"{ANALYSIS_LOCK_PREFIX}:"
        f"{int(incident_id)}"
    )


def acquire_analysis_lock(
    incident_id: int,
) -> str | None:
    """
    Incident 분석 Lock을 획득합니다.

    성공:
        생성한 token 반환

    이미 다른 Task가 대기/처리 중:
        None 반환
    """

    client = _get_redis_client()

    token = uuid4().hex

    acquired = client.set(
        _analysis_lock_key(incident_id),
        token,
        nx=True,
        ex=ANALYSIS_LOCK_TTL_SEC,
    )

    if not acquired:
        return None

    return token


def release_analysis_lock(
    incident_id: int,
    lock_token: str | None,
) -> bool:
    """
    해당 Task가 소유한 Lock만 해제합니다.

    이전 Task가 늦게 끝나더라도
    새 Task의 Lock을 잘못 삭제하지 않도록
    token을 확인합니다.
    """

    if not lock_token:
        return False

    client = _get_redis_client()

    released = client.eval(
        _RELEASE_LOCK_SCRIPT,
        1,
        _analysis_lock_key(incident_id),
        lock_token,
    )

    return bool(released)